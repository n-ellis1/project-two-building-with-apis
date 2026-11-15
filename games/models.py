from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q
from django.utils import timezone


class GameCategory(models.IntegerChoices):
    """IGDB `game_type` IDs with IGDB's own labels (verified 2026-11-14)."""

    MAIN_GAME = 0, "Main Game"
    DLC = 1, "DLC"
    EXPANSION = 2, "Expansion"
    BUNDLE = 3, "Bundle"
    STANDALONE_EXPANSION = 4, "Standalone Expansion"
    MOD = 5, "Mod"
    EPISODE = 6, "Episode"
    SEASON = 7, "Season"
    REMAKE = 8, "Remake"
    REMASTER = 9, "Remaster"
    EXPANDED_GAME = 10, "Expanded Game"
    PORT = 11, "Port"
    FORK = 12, "Fork"
    PACK = 13, "Pack / Addon"
    UPDATE = 14, "Update"


# The approved allowlist (Phase 1). Bundle, Mod, Pack / Addon, Update and any
# future type are excluded, as is any record with a version parent.
ELIGIBLE_GAME_CATEGORIES = frozenset({0, 1, 2, 4, 6, 7, 8, 9, 10, 11, 12})


def is_eligible(game_category, version_parent) -> bool:
    """The one eligibility rule for new saves, in Python (search applies the same rule
    as `igdb.ELIGIBILITY_WHERE`).

    Eligible only if there is no version parent (records with one are editions) and the
    Game Category is on the allowlist. 0 (Main Game) is valid; a missing type (None) or a
    non-integer is not, and neither is any type not yet reviewed.
    """
    return (
        version_parent is None
        and isinstance(game_category, int)
        and not isinstance(game_category, bool)
        and game_category in ELIGIBLE_GAME_CATEGORIES
    )


class IgdbNamedItem(models.Model):
    """A platform, genre or theme imported from IGDB."""

    igdb_id = models.PositiveIntegerField("IGDB ID", unique=True)
    name = models.CharField(max_length=200)

    class Meta:
        abstract = True
        ordering = ["name"]

    def __str__(self):
        return self.name


class Platform(IgdbNamedItem):
    pass


class Genre(IgdbNamedItem):
    pass


class Theme(IgdbNamedItem):
    pass


class Game(models.Model):
    """One IGDB game, shared by every user who saves it. Read-only to users."""

    igdb_id = models.PositiveIntegerField("IGDB ID", unique=True)
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, blank=True)
    summary = models.TextField(blank=True)
    first_release_date = models.DateField(null=True, blank=True)
    game_category = models.PositiveSmallIntegerField(
        "Game Category", choices=GameCategory.choices, default=GameCategory.MAIN_GAME
    )
    version_parent = models.PositiveIntegerField("version parent (IGDB ID)", null=True, blank=True)
    cover_image_id = models.CharField(max_length=100, blank=True)
    igdb_url = models.URLField("IGDB URL", max_length=500, blank=True)
    last_fetched_at = models.DateTimeField()
    platforms = models.ManyToManyField(Platform, blank=True, related_name="games")
    genres = models.ManyToManyField(Genre, blank=True, related_name="games")
    themes = models.ManyToManyField(Theme, blank=True, related_name="games")

    class Meta:
        ordering = ["name", "igdb_id"]

    def __str__(self):
        return self.name

    @property
    def category_badge(self) -> str:
        """IGDB's label for non-main games; empty for Main Game (no badge)."""
        if self.game_category == GameCategory.MAIN_GAME:
            return ""
        try:
            return GameCategory(self.game_category).label
        except ValueError:
            return ""


class Entry(models.Model):
    """A user's tracking data for one saved game. Private to its owner."""

    class Status(models.TextChoices):
        WANT_TO_PLAY = "want_to_play", "Want to Play"
        PLAYING = "playing", "Playing"
        COMPLETED = "completed", "Completed"
        ON_HOLD = "on_hold", "On Hold"
        DROPPED = "dropped", "Dropped"

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="entries"
    )
    # PROTECT: a Game that still has entries can't be deleted. Deleting an entry
    # never touches the Game.
    game = models.ForeignKey(Game, on_delete=models.PROTECT, related_name="entries")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.WANT_TO_PLAY)
    favorite = models.BooleanField(default=False)
    rating = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(10)],
    )
    notes = models.TextField(blank=True)
    # Plain text chosen from the game's platform names, not a foreign key, so a
    # refresh that removes the platform keeps the user's value.
    platform_played = models.CharField(max_length=200, blank=True)
    start_date = models.DateField(null=True, blank=True)
    finish_date = models.DateField(null=True, blank=True)
    hours_played = models.DecimalField(
        max_digits=7,
        decimal_places=1,
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
    )
    # A default rather than auto_now_add, so the demo seed can set a fixed "date added".
    created_at = models.DateTimeField("date added", default=timezone.now, editable=False)
    updated_at = models.DateTimeField("last updated", auto_now=True)

    class Meta:
        verbose_name_plural = "entries"
        constraints = [
            models.UniqueConstraint(fields=["owner", "game"], name="unique_entry_per_owner_game"),
            models.CheckConstraint(
                condition=Q(rating__isnull=True) | Q(rating__gte=1, rating__lte=10),
                name="entry_rating_1_to_10",
            ),
            models.CheckConstraint(
                condition=Q(hours_played__isnull=True) | Q(hours_played__gte=0),
                name="entry_hours_not_negative",
            ),
        ]

    def __str__(self):
        return f"{self.game} ({self.owner})"


class DemoAccount(models.Model):
    """Marks a user account the demo seed command created.

    The seeder only adds data to accounts carrying this marker. If a demo username
    belongs to any other account, it stops without changing anything.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="demo_account"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return str(self.user)
