"""The one save service: add an IGDB game to a user's list.

Used by the website's Save button and by the API's create (with optional tracking values).
"""

from dataclasses import dataclass

from django.db import DatabaseError, IntegrityError, transaction
from django.utils import timezone

from . import igdb
from .models import Entry, Game, Genre, Platform, Theme, is_eligible
from .queries import owned_entries
from .validation import validate_tracking

GENERIC_SAVE_MESSAGE = "Something went wrong while saving this game. Try again."


class SaveFailed(Exception):
    """An unexpected failure while saving (a database error, or an integrity error
    that isn't a confirmed duplicate). Users only ever see `GENERIC_SAVE_MESSAGE`."""

    message = GENERIC_SAVE_MESSAGE

    def __init__(self):
        super().__init__(self.message)


@dataclass(frozen=True)
class SaveResult:
    """The user's entry for the game, and whether this call created it
    (`created=False` means it was already in their games)."""

    entry: Entry
    created: bool


def save_game(user, igdb_id: int, tracking: dict | None = None) -> SaveResult:
    """Save IGDB game `igdb_id` to `user`'s list. The owner is always `user`.

    `tracking` holds optional, already type-checked tracking values for the new entry
    (the API's create). They are checked with the shared `validate_tracking()` against
    the game's platforms inside the write transaction, after any IGDB fetch, so an
    invalid value raises Django's `ValidationError` and rolls back the Game, its
    links and the Entry together. They are never applied to an existing entry.

    - **Already mine:** returns my existing entry unchanged (`created=False`), before
      any eligibility check or IGDB call.
    - **Already stored:** reused with no IGDB call, so it still saves during an outage.
      If its stored version parent is set or its stored Game Category is off the
      allowlist, it is refused (`game_category_excluded`), still with no IGDB call.
    - **New:** fetched from IGDB first. A failed fetch raises `IgdbError`, and an
      ineligible record raises `game_category_excluded`, both before any database
      write. The Game, its platform, genre and theme links, and the Entry are then
      written in one transaction, so a later failure rolls all of them back.

    A failed write always rolls back. Only an `IntegrityError` can be a duplicate, and
    only if my entry for this game is confirmed after the rollback. Any other
    database error, or an `IntegrityError` with no such entry, raises `SaveFailed`
    (a generic, safe message). The one exception: a new Game whose insert collided
    with another request's is retried once as a stored Game.
    """
    tracking = dict(tracking or {})
    existing = _my_entry(user, igdb_id)
    if existing is not None:
        return SaveResult(existing, created=False)

    game = Game.objects.filter(igdb_id=igdb_id).first()
    if game is not None:
        return _save_stored(user, game, tracking)

    details = igdb.fetch_game(igdb_id)  # raises IgdbError; nothing written yet
    if not is_eligible(details.game_category, details.version_parent):
        raise igdb.IgdbError("game_category_excluded")
    return _save_new(user, details, tracking)


def _my_entry(user, igdb_id: int) -> Entry | None:
    """The user's own entry for this game, through the owner-scoped helper."""
    return owned_entries(user).filter(game__igdb_id=igdb_id).first()


def _create_entry(user, game: Game, tracking: dict) -> Entry:
    """The new Entry, with any tracking values checked first. Call only inside a
    transaction: a `ValidationError` here rolls back everything written before it."""
    if tracking:
        validate_tracking(game, tracking)
    return Entry.objects.create(owner=user, game=game, **tracking)


def _save_stored(user, game: Game, tracking: dict) -> SaveResult:
    # Stored-classification rule: the stored values decide, with no IGDB call.
    if not is_eligible(game.game_category, game.version_parent):
        raise igdb.IgdbError("game_category_excluded")
    try:
        with transaction.atomic():
            entry = _create_entry(user, game, tracking)
    except IntegrityError:
        pass  # rolled back; maybe a simultaneous save of mine, judged below
    except DatabaseError:
        raise SaveFailed() from None
    else:
        return SaveResult(entry, created=True)
    return _duplicate_or_fail(user, game.igdb_id)


def _save_new(user, details: igdb.IgdbGameDetails, tracking: dict) -> SaveResult:
    game_insert_collided = False
    try:
        with transaction.atomic():
            try:
                game = _insert_game(details)
            except IntegrityError:
                game_insert_collided = True
                raise
            _link_game(game, details)  # before validation: platform played needs the links
            entry = _create_entry(user, game, tracking)
    except IntegrityError:
        pass  # the Game, its links and the Entry are all rolled back; judged below
    except DatabaseError:
        raise SaveFailed() from None  # also rolled back as a whole
    else:
        return SaveResult(entry, created=True)

    if game_insert_collided and _my_entry(user, details.igdb_id) is None:
        # Another request stored this Game first. Reuse it once, as a stored Game
        # (eligibility rechecked on the stored values, no second IGDB call).
        stored = Game.objects.filter(igdb_id=details.igdb_id).first()
        if stored is not None:
            return _save_stored(user, stored, tracking)
    return _duplicate_or_fail(user, details.igdb_id)


def _duplicate_or_fail(user, igdb_id: int) -> SaveResult:
    """After a rolled-back IntegrityError: a duplicate only if my entry is confirmed."""
    existing = _my_entry(user, igdb_id)
    if existing is not None:
        return SaveResult(existing, created=False)
    raise SaveFailed()


GENERIC_REFRESH_MESSAGE = "Something went wrong while refreshing this game. Try again."

# The Game fields a refresh overwrites with what IGDB sends now.
REFRESHED_FIELDS = (
    "name",
    "slug",
    "summary",
    "first_release_date",
    "game_category",
    "version_parent",
    "cover_image_id",
    "igdb_url",
)


class RefreshFailed(Exception):
    """An unexpected database failure while storing a refresh (rolled back as a whole).
    Users only ever see `GENERIC_REFRESH_MESSAGE`."""

    message = GENERIC_REFRESH_MESSAGE

    def __init__(self):
        super().__init__(self.message)


def refresh_game(game: Game) -> Game:
    """Update a stored, shared Game from IGDB. Used by the website's Refresh button.

    The fetch happens first, outside any transaction: a failed fetch raises
    `IgdbError` with nothing written. The Game's details (both classification fields
    included, even a missing Game Category or a new version parent), its platform,
    genre and theme links, and its last-fetched time are then written in one
    transaction, so a database error rolls all of them back (`RefreshFailed`).

    No eligibility check: a refresh stores whatever IGDB now says, so a game that has
    become ineligible keeps every entry and only new saves are refused (the
    stored-classification rule in `save_game`). Entries are never touched, and
    existing platform, genre and theme names are never renamed, so a stored platform
    played value only goes stale if the game loses that platform.
    """
    details = igdb.fetch_game(game.igdb_id)  # raises IgdbError; nothing written yet
    try:
        with transaction.atomic():
            for name in REFRESHED_FIELDS:
                setattr(game, name, getattr(details, name))
            game.last_fetched_at = timezone.now()
            game.save(update_fields=[*REFRESHED_FIELDS, "last_fetched_at"])
            _link_game(game, details)
    except DatabaseError:
        game.refresh_from_db()  # drop the unsaved values from this instance
        raise RefreshFailed() from None
    return game


def _insert_game(details: igdb.IgdbGameDetails) -> Game:
    """The fetched game's row. Call only inside a transaction."""
    return Game.objects.create(
        igdb_id=details.igdb_id,
        name=details.name,
        slug=details.slug,
        summary=details.summary,
        first_release_date=details.first_release_date,
        game_category=details.game_category,
        version_parent=details.version_parent,
        cover_image_id=details.cover_image_id,
        igdb_url=details.igdb_url,
        last_fetched_at=timezone.now(),
    )


def _link_game(game: Game, details: igdb.IgdbGameDetails) -> None:
    """The game's platform, genre and theme links. Call only inside a transaction."""
    game.platforms.set(_named_items(Platform, details.platforms))
    game.genres.set(_named_items(Genre, details.genres))
    game.themes.set(_named_items(Theme, details.themes))


def _named_items(model, items):
    """Rows for IGDB platforms, genres or themes, matched by IGDB ID. Existing rows
    are reused as stored (names aren't updated here)."""
    return [
        model.objects.get_or_create(igdb_id=item.igdb_id, defaults={"name": item.name})[0]
        for item in items
    ]
