"""Owner-scoped entry lookups and the saved-entries query builder, shared by the
website and API.

Every entry lookup starts from `owned_entries(user)`, so another user's entry ID behaves
exactly like an ID that doesn't exist (404).

Query state flows one way: request values -> `parse_entry_query()` (forgiving, for the
website; the API adds a strict parser in Phase 10) -> `EntryQuery` -> `saved_entries()`.
Controls, pager links, Clear filters and detail return links are all rendered from the
same `EntryQuery`, so they can never disagree with the results.
"""

import re
from dataclasses import dataclass, replace
from urllib.parse import urlencode

from django.db.models import F, Q
from django.db.models.functions import Lower
from django.shortcuts import get_object_or_404
from django.urls import reverse

from .models import Entry, Theme

PAGE_SIZE = 10

# Longest search term kept from the URL; anything longer is cut, not rejected.
MAX_SEARCH_LENGTH = 200

# The seven whitelisted sorts: URL value -> label, in dropdown order.
SORT_LABELS = {
    "added": "Date Added (Newest First)",
    "title": "Title A to Z",
    "title_desc": "Title Z to A",
    "rating": "Rating (Highest First)",
    "release": "Release Date (Newest First)",
    "hours": "Hours Played (Most First)",
    "updated": "Last Updated (Newest First)",
}
DEFAULT_SORT = "added"

# Non-title sorts break ties by title A to Z (case-insensitive), then entry ID, so
# paging never repeats or skips an entry. Title sorts break ties by entry ID only.
# Missing values sort last. No sort orders by a many-to-many field, which keeps
# `distinct()` returning one row per entry.
TITLE_THEN_ID = (Lower("game__name"), "id")
ORDERINGS = {
    "added": (F("created_at").desc(), *TITLE_THEN_ID),
    "title": (Lower("game__name"), "id"),
    "title_desc": (Lower("game__name").desc(), "id"),
    "rating": (F("rating").desc(nulls_last=True), *TITLE_THEN_ID),
    "release": (F("game__first_release_date").desc(nulls_last=True), *TITLE_THEN_ID),
    "hours": (F("hours_played").desc(nulls_last=True), *TITLE_THEN_ID),
    "updated": (F("updated_at").desc(), *TITLE_THEN_ID),
}
DEFAULT_ORDERING = ORDERINGS[DEFAULT_SORT]


def parse_page(value) -> int:
    """Website (forgiving) page parsing: anything that isn't a positive integer is 1.

    Call this before `Paginator.get_page()`, which handles pages past the end but
    would send 0 and negative numbers to the last page.
    """
    try:
        page = int(str(value).strip())
    except TypeError, ValueError:
        return 1
    return page if page >= 1 else 1


def owned_entries(user):
    """The only starting point for listing or looking up entries."""
    return Entry.objects.filter(owner=user)


def get_owned_entry_or_404(user, entry_id):
    """One of `user`'s entries by entry ID; 404 for anyone else's or a missing ID."""
    return get_object_or_404(owned_entries(user), pk=entry_id)


def user_themes(user):
    """Themes on the user's own saved games, alphabetical, regardless of any filter.

    Another user's saved games never add a theme here.
    """
    return Theme.objects.filter(games__entries__owner=user).distinct().order_by(Lower("name"), "id")


def user_platforms_played(user) -> list[str]:
    """The distinct, non-blank Platform Played values on the user's entries, A to Z."""
    values = (
        owned_entries(user)
        .exclude(platform_played="")
        .values_list("platform_played", flat=True)
        .distinct()
    )
    return sorted(values, key=str.casefold)


@dataclass(frozen=True)
class EntryQuery:
    """Already-validated saved-entries query state (search, filters, sort).

    The website parses request values into this forgivingly; the API (Phase 10)
    parses strictly. Both then call `saved_entries(user, query)`.
    """

    q: str = ""
    status: str = ""
    platform: str = ""
    favorite: bool = False
    theme: int | None = None  # IGDB theme ID
    sort: str = DEFAULT_SORT

    @property
    def has_filters(self) -> bool:
        return bool(self.status or self.platform or self.favorite or self.theme is not None)

    def without_filters(self) -> EntryQuery:
        """Clear filters: keeps the search and sort, drops Status, Platform, Favorite, Theme."""
        return EntryQuery(q=self.q, sort=self.sort)

    def params(self, page: int = 1) -> list[tuple[str, str]]:
        """URL parameters for this state, leaving out defaults (and page 1)."""
        pairs = [
            ("q", self.q),
            ("status", self.status),
            ("platform", self.platform),
            ("favorite", "1" if self.favorite else ""),
            ("theme", "" if self.theme is None else str(self.theme)),
            ("sort", "" if self.sort == DEFAULT_SORT else self.sort),
            ("page", str(page) if page > 1 else ""),
        ]
        return [(key, value) for key, value in pairs if value]

    def querystring(self, page: int = 1) -> str:
        """`?q=...&page=2`, or an empty string when everything is a default."""
        params = self.params(page)
        return f"?{urlencode(params)}" if params else ""


def parse_entry_query(user, params) -> EntryQuery:
    """Website (forgiving) parsing of `q`, `status`, `platform`, `favorite`, `theme`, `sort`.

    Never raises: an unknown status, platform or sort, a malformed theme, or a theme
    or platform that isn't on the user's own saved games is dropped, so a bad or
    stale link still shows the list. Only values that pass are ever echoed back.
    """
    q = " ".join(str(params.get("q", "")).split())[:MAX_SEARCH_LENGTH]

    status = params.get("status", "")
    if status not in Entry.Status.values:
        status = ""

    platform = params.get("platform", "")
    if platform and platform not in user_platforms_played(user):
        platform = ""

    favorite = params.get("favorite", "") == "1"

    theme = None
    raw_theme = str(params.get("theme", "")).strip()
    if raw_theme.isascii() and raw_theme.isdigit():
        candidate = int(raw_theme)
        if user_themes(user).filter(igdb_id=candidate).exists():
            theme = candidate

    sort = params.get("sort", "")
    if sort not in SORT_LABELS:
        sort = DEFAULT_SORT

    return EntryQuery(
        q=q, status=status, platform=platform, favorite=favorite, theme=theme, sort=sort
    )


def search_condition(term: str) -> Q:
    """Case-insensitive match on the game's title, summary, platform, genre and
    theme names, or the entry's own notes (never another user's notes)."""
    return (
        Q(game__name__icontains=term)
        | Q(game__summary__icontains=term)
        | Q(game__platforms__name__icontains=term)
        | Q(game__genres__name__icontains=term)
        | Q(game__themes__name__icontains=term)
        | Q(notes__icontains=term)
    )


def saved_entries(user, query: EntryQuery = EntryQuery()):
    """The user's entries for My Saved Games, matching `query`, with game data loaded.

    The search and Theme joins can return one entry several times, so `distinct()`
    is applied here, before the caller counts or paginates.
    """
    entries = owned_entries(user)
    if query.q:
        entries = entries.filter(search_condition(query.q))
    if query.status:
        entries = entries.filter(status=query.status)
    if query.platform:
        entries = entries.filter(platform_played=query.platform)
    if query.favorite:
        entries = entries.filter(favorite=True)
    if query.theme is not None:
        entries = entries.filter(game__themes__igdb_id=query.theme)
    if query.q or query.theme is not None:
        entries = entries.distinct()
    return (
        entries.select_related("game")
        .prefetch_related("game__platforms")
        .order_by(*ORDERINGS.get(query.sort, DEFAULT_ORDERING))
    )


ROMAN_NUMERALS = {
    "2": "II",
    "3": "III",
    "4": "IV",
    "5": "V",
    "6": "VI",
    "7": "VII",
    "8": "VIII",
    "9": "IX",
}
TRAILING_NUMBER = re.compile(r"^(.*\S)\s+([2-9])$")


def roman_numeral_variant(q: str) -> str:
    """`q` with a final standalone 2–9 as a Roman numeral ("Dark Souls 3" -> "Dark Souls III"),
    or "" when the text doesn't end that way.

    The one trailing-number rule, used by Search IGDB (an empty page 1 retries once)
    and by My Saved Games through `resolve_saved_search()`.
    """
    match = TRAILING_NUMBER.match(q)
    if not match:
        return ""
    return f"{match.group(1)} {ROMAN_NUMERALS[match.group(2)]}"


def resolve_saved_search(user, query: EntryQuery) -> EntryQuery:
    """The query whose search actually runs on My Saved Games.

    The typed term wins whenever it matches anything under the active filters. Only
    when it matches nothing, and it ends in a standalone 2–9, is the Roman-numeral
    form tried once; it is used if it matches. Both checks run on the user's whole
    filtered list in SQLite, never on a page, so an empty or out-of-range page can't
    switch the search. Every check starts from the user's own entries.
    """
    variant = roman_numeral_variant(query.q)
    if not variant or saved_entries(user, query).exists():
        return query
    fallback = replace(query, q=variant)
    return fallback if saved_entries(user, fallback).exists() else query


def saved_games_url(query: EntryQuery = EntryQuery(), page: int = 1) -> str:
    """My Saved Games for `query` at `page`, always on our own route."""
    return reverse("games:saved_games") + query.querystring(page)
