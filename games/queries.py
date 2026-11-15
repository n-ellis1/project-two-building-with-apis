"""Owner-scoped entry lookups and saved-games paging, shared by the website and API.

Every entry lookup starts from `owned_entries(user)`, so another user's entry ID behaves
exactly like an ID that doesn't exist (404).
"""

from django.db.models.functions import Lower
from django.shortcuts import get_object_or_404

from .models import Entry

PAGE_SIZE = 10

# Date Added (Newest First), the default sort. Ties break by title A to Z
# (case-insensitive), then entry ID, so paging never repeats or skips an entry.
DEFAULT_ORDERING = ("-created_at", Lower("game__name"), "id")


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


def saved_entries(user):
    """The user's entries for My Saved Games, newest first, with game data loaded."""
    return (
        owned_entries(user)
        .select_related("game")
        .prefetch_related("game__platforms")
        .order_by(*DEFAULT_ORDERING)
    )
