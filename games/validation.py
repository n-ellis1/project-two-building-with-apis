"""Shared tracking-field validation for the website form, the API serializer and the
save service (API create).

DRF serializers don't run model `clean()` methods, so every caller uses this one function.
It raises Django's `ValidationError` with a dict keyed by field name; DRF converts that
into its standard field-error format.
"""

from django.core.exceptions import ValidationError

PLATFORM_NOT_LISTED = "Choose one of this game's platforms, or leave it blank."
FINISH_BEFORE_START = "Finish date can't be before the start date."


def validate_tracking(game, values, *, stored_platform_played=""):
    """Check the cross-field tracking rules for an entry of `game`.

    `values` holds the submitted tracking values, already merged with the stored
    ones for a partial update. `stored_platform_played` is the entry's current
    saved platform ("" for a new entry), which may stay even if it is stale.
    """
    errors = {}

    platform = values.get("platform_played") or ""
    if (
        platform
        and platform != stored_platform_played
        and not game.platforms.filter(name=platform).exists()
    ):
        errors["platform_played"] = [PLATFORM_NOT_LISTED]

    start, finish = values.get("start_date"), values.get("finish_date")
    if start and finish and finish < start:
        errors["finish_date"] = [FINISH_BEFORE_START]

    if errors:
        raise ValidationError(errors)
