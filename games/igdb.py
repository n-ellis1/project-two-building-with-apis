"""The one IGDB client. Called only from the server, never from templates or the browser.

Built on `scripts/igdb_search.py`'s request, timeout and error-mapping approach, but it
raises `IgdbError` (a PRD error code plus its fixed, safe message) instead of exiting.

Secrets policy: the client secret and access token are never logged, never put in an
error message, and never used in a cache key. Exception text from `requests` is dropped
(`from None`), because it can include request details.
"""

from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta

import requests
from django.conf import settings
from django.core.cache import cache

TOKEN_URL = "https://id.twitch.tv/oauth2/token"
IGDB_GAMES_URL = "https://api.igdb.com/v4/games"
IGDB_POPULARITY_URL = "https://api.igdb.com/v4/popularity_primitives"
TIMEOUT_SECONDS = 10

# The Twitch app token lives in Django's local-memory cache under a fixed key that
# contains nothing secret, and expires a little before Twitch says it will.
TOKEN_CACHE_KEY = "igdb:access_token"
TOKEN_EXPIRY_MARGIN_SECONDS = 300

# Results shown per IGDB search page; one extra is requested to know whether Next exists.
SEARCH_PAGE_SIZE = 10

# "Popular on IGDB": PopScore's Visits ranking (popularity type 1). More candidates are
# asked for than shown, so ineligible or missing games can be skipped.
VISITS_POPULARITY_TYPE = 1
POPULAR_CANDIDATES = 50
POPULAR_LIMIT = 10

# The finished row is shared game data only (IDs, titles, cover IDs, categories), the
# same for every user, so it is cached under a fixed key with no secrets or user IDs.
# PopScore itself is recalculated every 24 hours.
POPULAR_CACHE_KEY = "igdb:popular_games"
POPULAR_CACHE_SECONDS = 60 * 60

# The approved Phase 1 eligibility rule, applied by IGDB before limit and offset.
ELIGIBILITY_WHERE = "where version_parent = null & game_type = (0,1,2,4,6,7,8,9,10,11,12);"

SEARCH_FIELDS = (
    "fields name, first_release_date, platforms.name, game_type, version_parent, cover.image_id;"
)

# Everything the save service stores for one game (and Phase 9 refresh updates).
FETCH_FIELDS = (
    "fields name, slug, summary, first_release_date, game_type, version_parent, "
    "cover.image_id, url, platforms.name, genres.name, themes.name;"
)

UNIX_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)

# The PRD's fixed, safe messages. Nothing else from IGDB or Twitch ever reaches a user.
MESSAGES = {
    "igdb_timeout": "IGDB took too long to respond. Try again in a moment.",
    "igdb_unreachable": "Couldn't reach IGDB. Try again in a moment.",
    "igdb_rate_limited": "IGDB is receiving too many requests. Wait a few seconds and try again.",
    "igdb_unavailable": "IGDB is having problems right now. Try again later.",
    "igdb_misconfigured": (
        "Game search and imports aren't set up on this server. "
        "Your saved games are still available."
    ),
    "igdb_game_not_found": "IGDB has no game with that ID.",
    "game_category_excluded": (
        "This release can't be saved. Search for the base game or a supported release."
    ),
}


class IgdbError(Exception):
    """An expected IGDB or Twitch failure. `message` is always one of `MESSAGES`."""

    def __init__(self, code: str, retry_after: int | None = None):
        self.code = code
        self.message = MESSAGES[code]
        self.retry_after = retry_after
        super().__init__(self.message)


@dataclass(frozen=True)
class IgdbGame:
    """One search result, already reduced to the fields the site shows."""

    igdb_id: int
    name: str
    first_release_date: date | None = None
    platforms: tuple[str, ...] = field(default_factory=tuple)
    game_category: int | None = None
    cover_image_id: str = ""

    @property
    def category_badge(self) -> str:
        return category_badge(self.game_category)


def category_badge(game_category) -> str:
    """IGDB's label for a non-main Game Category; empty for Main Game, missing or unknown."""
    from .models import GameCategory

    if game_category in (None, GameCategory.MAIN_GAME):
        return ""
    try:
        return GameCategory(game_category).label
    except ValueError:
        return ""


@dataclass(frozen=True)
class IgdbNamed:
    """A platform, genre or theme as IGDB returns it."""

    igdb_id: int
    name: str


@dataclass(frozen=True)
class IgdbGameDetails:
    """One game fetched by ID, with everything the save service stores.

    `game_category` and `version_parent` are passed through as IGDB sent them
    (None when missing), so the save service can apply the eligibility rule.
    """

    igdb_id: int
    name: str
    slug: str = ""
    summary: str = ""
    first_release_date: date | None = None
    game_category: int | None = None
    version_parent: int | None = None
    cover_image_id: str = ""
    igdb_url: str = ""
    platforms: tuple[IgdbNamed, ...] = ()
    genres: tuple[IgdbNamed, ...] = ()
    themes: tuple[IgdbNamed, ...] = ()

    @property
    def category_badge(self) -> str:
        return category_badge(self.game_category)


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------


def _credentials() -> tuple[str, str]:
    client_id = (settings.IGDB_CLIENT_ID or "").strip()
    client_secret = (settings.IGDB_CLIENT_SECRET or "").strip()
    if not client_id or not client_secret:
        raise IgdbError("igdb_misconfigured")
    return client_id, client_secret


def _post(url: str, **kwargs) -> requests.Response:
    try:
        return requests.post(url, timeout=TIMEOUT_SECONDS, **kwargs)
    except requests.Timeout:
        raise IgdbError("igdb_timeout") from None
    except requests.ConnectionError:
        raise IgdbError("igdb_unreachable") from None
    except requests.RequestException:
        raise IgdbError("igdb_unreachable") from None


def _retry_after(response) -> int | None:
    """A valid Retry-After in whole seconds (kept for the API in Phase 10), else None.

    Only a plain non-negative number of seconds counts; HTTP dates and anything
    else are dropped rather than passed on.
    """
    value = str(response.headers.get("Retry-After", "")).strip()
    if value.isascii() and value.isdigit() and len(value) <= 6:
        return int(value)
    return None


def _fetch_token(client_id: str, client_secret: str) -> tuple[str, int]:
    """A new app access token and its `expires_in` (seconds) from Twitch."""
    response = _post(
        TOKEN_URL,
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "grant_type": "client_credentials",
        },
    )
    if response.status_code in (400, 401, 403):
        raise IgdbError("igdb_misconfigured")
    if response.status_code == 429:
        raise IgdbError("igdb_rate_limited", retry_after=_retry_after(response))
    if not response.ok:
        raise IgdbError("igdb_unavailable")
    try:
        data = response.json()
    except ValueError:
        raise IgdbError("igdb_unavailable") from None
    if not isinstance(data, dict):
        raise IgdbError("igdb_unavailable")
    token = data.get("access_token")
    expires_in = data.get("expires_in")
    if not isinstance(token, str) or not token:
        raise IgdbError("igdb_unavailable")
    if isinstance(expires_in, bool) or not isinstance(expires_in, int):
        expires_in = 0  # use it for this request, but don't cache it
    return token, expires_in


def _cached_token(client_id: str, client_secret: str) -> str:
    token = cache.get(TOKEN_CACHE_KEY)
    if not token:
        token, expires_in = _fetch_token(client_id, client_secret)
        timeout = expires_in - TOKEN_EXPIRY_MARGIN_SECONDS
        if timeout > 0:
            cache.set(TOKEN_CACHE_KEY, token, timeout)
    return token


def _send(url: str, body: str, client_id: str, token: str) -> requests.Response:
    return _post(
        url,
        headers={
            "Client-ID": client_id,
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "Content-Type": "text/plain; charset=utf-8",
        },
        data=body.encode("utf-8"),
    )


def _query(url: str, body: str):
    """One IGDB request. A 401 (token rejected) gets exactly one fresh token and one
    resend of the same body; a second 401, or any 403, is a configuration error."""
    client_id, client_secret = _credentials()
    response = _send(url, body, client_id, _cached_token(client_id, client_secret))
    if response.status_code == 401:
        cache.delete(TOKEN_CACHE_KEY)
        response = _send(url, body, client_id, _cached_token(client_id, client_secret))
        if response.status_code == 401:
            cache.delete(TOKEN_CACHE_KEY)
            raise IgdbError("igdb_misconfigured")
    if response.status_code == 403:
        raise IgdbError("igdb_misconfigured")
    if response.status_code == 429:
        raise IgdbError("igdb_rate_limited", retry_after=_retry_after(response))
    if not response.ok:
        raise IgdbError("igdb_unavailable")
    try:
        return response.json()
    except ValueError:
        raise IgdbError("igdb_unavailable") from None


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------


def escape_query_string(text: str) -> str:
    """Escape backslashes and double quotes for an Apicalypse string literal."""
    return text.replace("\\", "\\\\").replace('"', '\\"')


def build_search_query(q: str, page: int) -> str:
    """Ask for one more than a page, at the page's offset, with the eligibility rule."""
    offset = (page - 1) * SEARCH_PAGE_SIZE
    return (
        f'search "{escape_query_string(q)}";\n'
        f"{SEARCH_FIELDS}\n"
        f"{ELIGIBILITY_WHERE}\n"
        f"limit {SEARCH_PAGE_SIZE + 1};\n"
        f"offset {offset};\n"
    )


def _release_date(timestamp) -> date | None:
    if isinstance(timestamp, bool) or not isinstance(timestamp, (int, float)):
        return None
    try:
        return (UNIX_EPOCH + timedelta(seconds=timestamp)).date()
    except OverflowError, ValueError:
        return None


def _to_game(record) -> IgdbGame | None:
    if not isinstance(record, dict):
        return None
    igdb_id = record.get("id")
    if isinstance(igdb_id, bool) or not isinstance(igdb_id, int):
        return None
    platforms = record.get("platforms")
    names = tuple(
        p["name"]
        for p in (platforms if isinstance(platforms, list) else [])
        if isinstance(p, dict) and isinstance(p.get("name"), str)
    )
    cover = record.get("cover")
    cover_id = cover.get("image_id") if isinstance(cover, dict) else ""
    game_type = record.get("game_type")
    return IgdbGame(
        igdb_id=igdb_id,
        name=str(record.get("name") or "Unknown"),
        first_release_date=_release_date(record.get("first_release_date")),
        platforms=names,
        game_category=game_type if isinstance(game_type, int) else None,
        cover_image_id=cover_id if isinstance(cover_id, str) else "",
    )


def build_fetch_query(igdb_id: int) -> str:
    """One game by ID. Deliberately no eligibility clause: the save service checks the
    record in Python, so an excluded ID is reported as excluded, not as not found."""
    return f"{FETCH_FIELDS}\nwhere id = {int(igdb_id)};\nlimit 1;\n"


def _named(items, max_length=200) -> tuple[IgdbNamed, ...]:
    return tuple(
        IgdbNamed(item["id"], item["name"][:max_length])
        for item in (items if isinstance(items, list) else [])
        if isinstance(item, dict)
        and _is_id(item.get("id"))
        and isinstance(item.get("name"), str)
        and item["name"]
    )


def _is_id(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _text(value, max_length=None) -> str:
    text = value if isinstance(value, str) else ""
    return text[:max_length] if max_length else text


def fetch_game(igdb_id: int) -> IgdbGameDetails:
    """One game by IGDB ID with everything the save service stores.

    Raises `IgdbError("igdb_game_not_found")` when IGDB has no game with that ID, and
    the usual codes for timeouts, rate limits, outages and configuration problems.
    `game_category` and `version_parent` are returned as IGDB sent them (None when
    missing or malformed); eligibility is the save service's decision.
    """
    data = _query(IGDB_GAMES_URL, build_fetch_query(igdb_id))
    if not isinstance(data, list):
        raise IgdbError("igdb_unavailable")
    record = next((r for r in data if isinstance(r, dict) and r.get("id") == int(igdb_id)), None)
    if record is None:
        raise IgdbError("igdb_game_not_found")
    cover = record.get("cover")
    cover_id = cover.get("image_id") if isinstance(cover, dict) else ""
    game_type = record.get("game_type")
    if isinstance(game_type, bool) or not isinstance(game_type, int) or game_type < 0:
        game_type = None  # missing or malformed: never eligible
    version_parent = record.get("version_parent")
    if version_parent is not None and not _is_id(version_parent):
        # Dropping it would make an edition look eligible, so refuse the response.
        raise IgdbError("igdb_unavailable")
    url = _text(record.get("url"), 500)
    return IgdbGameDetails(
        igdb_id=record["id"],
        name=_text(record.get("name"), 255) or "Unknown",
        slug=_text(record.get("slug"), 255),
        summary=_text(record.get("summary")),
        first_release_date=_release_date(record.get("first_release_date")),
        game_category=game_type,
        version_parent=version_parent,
        cover_image_id=_text(cover_id, 100),
        igdb_url=url if url.startswith("https://") else "",
        platforms=_named(record.get("platforms")),
        genres=_named(record.get("genres")),
        themes=_named(record.get("themes")),
    )


def build_popularity_query() -> str:
    """The top PopScore Visits primitives, highest first (see docs/research/igdb-popscore.md)."""
    return (
        "fields game_id, value;\n"
        f"where popularity_type = {VISITS_POPULARITY_TYPE};\n"
        "sort value desc;\n"
        f"limit {POPULAR_CANDIDATES};\n"
    )


def build_games_by_id_query(igdb_ids) -> str:
    """Eligible games among `igdb_ids`, in one request. The explicit limit matters:
    IGDB's default of 10 would silently drop the rest."""
    ids = ",".join(str(int(igdb_id)) for igdb_id in igdb_ids)
    eligible = ELIGIBILITY_WHERE.removesuffix(";")
    return f"{SEARCH_FIELDS}\n{eligible} & id = ({ids});\nlimit {POPULAR_CANDIDATES};\n"


def popular_games() -> list[IgdbGame]:
    """Up to 10 eligible games in IGDB PopScore Visits order. Two IGDB requests.

    The ranking holds game IDs only, so those games are fetched in one batch. IGDB
    returns them in its own order, so PopScore's order is restored here. Missing
    records and ineligible ones (checked again in Python, the same rule as saving)
    are skipped, and the following ranks fill in.
    """
    from .models import is_eligible

    primitives = _query(IGDB_POPULARITY_URL, build_popularity_query())
    if not isinstance(primitives, list):
        raise IgdbError("igdb_unavailable")
    ranked = []
    for primitive in primitives:
        game_id = primitive.get("game_id") if isinstance(primitive, dict) else None
        if _is_id(game_id) and game_id not in ranked:
            ranked.append(game_id)
    ranked = ranked[:POPULAR_CANDIDATES]  # the games request's limit must cover them all
    if not ranked:
        return []

    records = _query(IGDB_GAMES_URL, build_games_by_id_query(ranked))
    if not isinstance(records, list):
        raise IgdbError("igdb_unavailable")
    by_id = {}
    for record in records:
        game = _to_game(record)
        version_parent = record.get("version_parent") if game else None
        if game is not None and is_eligible(game.game_category, version_parent):
            by_id[game.igdb_id] = game
    return [by_id[game_id] for game_id in ranked if game_id in by_id][:POPULAR_LIMIT]


def cached_popular_games() -> list[IgdbGame]:
    """`popular_games()`, cached for an hour. A failure raises `IgdbError` and is never
    cached, so the next call tries again. Per-user data (Saved links) never goes in."""
    games = cache.get(POPULAR_CACHE_KEY)
    if games is None:
        games = popular_games()
        cache.set(POPULAR_CACHE_KEY, games, POPULAR_CACHE_SECONDS)
    return games


def search_games(q: str, page: int) -> list[IgdbGame]:
    """Up to 11 eligible games for page `page` of `q` (the 11th only signals Next)."""
    data = _query(IGDB_GAMES_URL, build_search_query(q, page))
    if not isinstance(data, list):
        raise IgdbError("igdb_unavailable")
    return [game for game in map(_to_game, data) if game is not None]
