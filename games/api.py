"""The saved-entry REST API (`/api/entries/`).

Every request starts from `owned_entries(request.user)`, so another user's entry ID
returns 404 for every method. The owner always comes from the authenticated user.
"""

from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers, status, viewsets
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response

from . import igdb
from .covers import cover_url
from .models import Entry, Game
from .queries import (
    PAGE_SIZE,
    owned_entries,
    parse_entry_query_strict,
    resolve_saved_search,
    saved_entries,
)
from .saving import SaveFailed, save_game
from .validation import validate_tracking
from .views import ALREADY_SAVED_MESSAGE, MAX_IGDB_ID


class EntryPagination(PageNumberPagination):
    """10 per page. A bad or out-of-range `page` is DRF's standard 404, and only
    positive integers are pages (DRF's `?page=last` is turned off)."""

    page_size = PAGE_SIZE
    last_page_strings = ()


class GameSerializer(serializers.ModelSerializer):
    """The nested, read-only game, served from SQLite."""

    platforms = serializers.SlugRelatedField(many=True, read_only=True, slug_field="name")
    genres = serializers.SlugRelatedField(many=True, read_only=True, slug_field="name")
    themes = serializers.SlugRelatedField(many=True, read_only=True, slug_field="name")
    game_category_label = serializers.SerializerMethodField()
    cover_url = serializers.SerializerMethodField()

    class Meta:
        model = Game
        fields = [
            "igdb_id",
            "name",
            "first_release_date",
            "game_category",
            "game_category_label",
            "platforms",
            "genres",
            "themes",
            "cover_url",
            "igdb_url",
        ]
        read_only_fields = fields

    def get_game_category_label(self, game) -> str:
        return game.get_game_category_display() if game.game_category is not None else ""

    def get_cover_url(self, game) -> str | None:
        return cover_url(game.cover_image_id, "large")


TRACKING_FIELDS = [
    "status",
    "favorite",
    "rating",
    "notes",
    "platform_played",
    "start_date",
    "finish_date",
    "hours_played",
]


IGDB_ID_UNCHANGEABLE = "An entry's IGDB ID can't be changed. Create a new entry instead."


def put_defaults() -> dict:
    """What PUT resets an omitted tracking field to: the model's blank or default value."""
    return {name: Entry._meta.get_field(name).get_default() for name in TRACKING_FIELDS}


class EntrySerializer(serializers.ModelSerializer):
    """An entry's tracking fields plus its nested, read-only game.

    `igdb_id` is required on create and rejected on update. The owner is never a
    field: it always comes from the authenticated user. Anything sent inside `game`
    is ignored (read-only).
    """

    game = GameSerializer(read_only=True)
    igdb_id = serializers.IntegerField(write_only=True, min_value=1, max_value=MAX_IGDB_ID)

    class Meta:
        model = Entry
        fields = ["id", "igdb_id", "game", *TRACKING_FIELDS, "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance is not None and "igdb_id" in self.fields:
            self.fields["igdb_id"].required = False

    def validate(self, attrs):
        """The shared cross-field rules (`validate_tracking`), as on the website form.

        On an update the submitted values are merged over the stored ones for
        validation only, so a PATCH of just `finish_date` is still checked against
        the stored `start_date`, and an unchanged stale platform stays allowed. A PUT
        first resets every omitted tracking field to its default. On create the
        save service runs the same check once it has the game (`save_game`).
        """
        if self.instance is not None:
            if "igdb_id" in attrs:
                raise serializers.ValidationError({"igdb_id": [IGDB_ID_UNCHANGEABLE]})
            if not self.partial:
                attrs = put_defaults() | attrs
            entry = self.instance
            merged = {name: getattr(entry, name) for name in TRACKING_FIELDS} | attrs
            try:
                validate_tracking(entry.game, merged, stored_platform_played=entry.platform_played)
            except DjangoValidationError as error:
                raise serializers.ValidationError(error.message_dict) from None
        return attrs

    def update(self, entry, validated_data):
        """Write only the submitted tracking fields (plus the automatic `updated_at`)."""
        for name, value in validated_data.items():
            setattr(entry, name, value)
        entry.save(update_fields=[*validated_data, "updated_at"])
        return entry


# Save-service failures the client can fix by changing the request (400); every other
# IgdbError is an upstream or configuration failure (503).
CLIENT_ERROR_CODES = {"igdb_game_not_found", "game_category_excluded"}
DUPLICATE_CODE = "duplicate_entry"
SAVE_FAILED_CODE = "save_failed"


def error_response(detail: str, code: str, status_code: int, retry_after=None) -> Response:
    """`{"detail", "code"}` with one of the fixed, safe messages only."""
    headers = {}
    if retry_after is not None:
        headers["Retry-After"] = str(retry_after)
    return Response({"detail": detail, "code": code}, status=status_code, headers=headers)


def save_error_response(error: igdb.IgdbError) -> Response:
    if error.code in CLIENT_ERROR_CODES:
        return error_response(error.message, error.code, status.HTTP_400_BAD_REQUEST)
    retry_after = None
    if (
        error.code == "igdb_rate_limited"
        and isinstance(error.retry_after, int)
        and not isinstance(error.retry_after, bool)
        and error.retry_after >= 0
    ):
        retry_after = error.retry_after
    return error_response(
        error.message, error.code, status.HTTP_503_SERVICE_UNAVAILABLE, retry_after
    )


class EntryViewSet(viewsets.ModelViewSet):
    serializer_class = EntrySerializer
    pagination_class = EntryPagination

    def get_queryset(self):
        return (
            owned_entries(self.request.user)
            .select_related("game")
            .prefetch_related("game__platforms", "game__genres", "game__themes")
            .order_by("-created_at", "id")
        )

    def create(self, request, *args, **kwargs):
        """Save `igdb_id` through the one save service, with any tracking values sent.
        The owner is always the authenticated user; any posted owner is ignored.

        Upstream failures are 503 (with Retry-After for a rate limit, when IGDB gave a
        valid one). Unknown, excluded and already-saved games are 400. An unexpected
        failure is a generic 500. Every error body is `{"detail", "code"}`.
        """
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        tracking = {name: values[name] for name in TRACKING_FIELDS if name in values}
        try:
            result = save_game(request.user, values["igdb_id"], tracking)
        except DjangoValidationError as error:
            # Invalid tracking for this game; the save service rolled everything back.
            raise serializers.ValidationError(error.message_dict) from None
        except igdb.IgdbError as error:
            return save_error_response(error)
        except SaveFailed as error:
            return error_response(
                error.message, SAVE_FAILED_CODE, status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        if not result.created:
            return error_response(
                ALREADY_SAVED_MESSAGE, DUPLICATE_CODE, status.HTTP_400_BAD_REQUEST
            )
        data = self.get_serializer(result.entry).data
        return Response(data, status=status.HTTP_201_CREATED)

    def list(self, request, *args, **kwargs):
        """The user's entries through the website's query builder, parsed strictly.

        Invalid filters or sort give 400 keyed by parameter. The `q` search uses the
        same Roman-numeral fallback as My Saved Games (`resolve_saved_search`),
        decided on the user's whole filtered list before paging.
        """
        try:
            query = parse_entry_query_strict(request.user, request.query_params)
        except DjangoValidationError as error:
            raise serializers.ValidationError(error.message_dict) from None
        query = resolve_saved_search(request.user, query)
        entries = saved_entries(request.user, query).prefetch_related(
            "game__genres", "game__themes"
        )
        page = self.paginate_queryset(entries)
        return self.get_paginated_response(self.get_serializer(page, many=True).data)
