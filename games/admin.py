from django.contrib import admin

from .models import DemoAccount, Entry, Game, Genre, Platform, Theme


class ReadOnlyAdmin(admin.ModelAdmin):
    """Imported IGDB data: viewable, but not added, changed or deleted in the admin."""

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Game)
class GameAdmin(ReadOnlyAdmin):
    list_display = ("name", "igdb_id", "game_category", "first_release_date", "last_fetched_at")
    list_filter = ("game_category",)
    search_fields = ("name", "igdb_id")


@admin.register(Platform, Genre, Theme)
class NamedItemAdmin(ReadOnlyAdmin):
    list_display = ("name", "igdb_id")
    search_fields = ("name",)


@admin.register(Entry)
class EntryAdmin(admin.ModelAdmin):
    """Tracking fields are editable for debugging; owner, game and timestamps aren't."""

    list_display = ("game", "owner", "status", "favorite", "rating", "updated_at")
    list_filter = ("status", "favorite")
    search_fields = ("game__name", "owner__username")
    readonly_fields = ("owner", "game", "created_at", "updated_at")
    fields = (
        "owner",
        "game",
        "status",
        "favorite",
        "rating",
        "notes",
        "platform_played",
        "start_date",
        "finish_date",
        "hours_played",
        "created_at",
        "updated_at",
    )

    def has_add_permission(self, request):
        # Entries are created by saving a game (or the demo seed), never by hand.
        return False


@admin.register(DemoAccount)
class DemoAccountAdmin(ReadOnlyAdmin):
    list_display = ("user", "created_at")
