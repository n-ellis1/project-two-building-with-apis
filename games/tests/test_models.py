"""Game and Entry models: defaults, constraints and badges (stories 36, 39, 44, 68, 84)."""

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from games.models import ELIGIBLE_GAME_CATEGORIES, Entry, Game, GameCategory

from .factories import make_entry, make_game, make_user


class EntryDefaultsTests(TestCase):
    def test_new_entries_are_want_to_play_and_not_favorite(self):
        entry = make_entry(make_user("player"))
        self.assertEqual(entry.status, Entry.Status.WANT_TO_PLAY)
        self.assertFalse(entry.favorite)
        self.assertIsNone(entry.rating)
        self.assertIsNone(entry.hours_played)
        self.assertEqual(entry.platform_played, "")

    def test_the_five_statuses(self):
        self.assertEqual(
            Entry.Status.labels,
            ["Want to Play", "Playing", "Completed", "On Hold", "Dropped"],
        )


class EntryConstraintTests(TestCase):
    def setUp(self):
        self.user = make_user("player")
        self.game = make_game("Hollow Knight")

    def test_one_entry_per_user_and_game(self):
        make_entry(self.user, self.game)
        with self.assertRaises(IntegrityError), transaction.atomic():
            make_entry(self.user, self.game)
        self.assertEqual(Entry.objects.count(), 1)

    def test_different_users_can_save_the_same_game(self):
        make_entry(self.user, self.game)
        make_entry(make_user("other"), self.game)
        self.assertEqual(self.game.entries.count(), 2)

    def test_rating_outside_1_to_10_is_rejected(self):
        for bad in (0, 11):
            with self.subTest(rating=bad):
                entry = Entry(owner=self.user, game=self.game, rating=bad)
                with self.assertRaises(ValidationError) as caught:
                    entry.full_clean()
                self.assertIn("rating", caught.exception.message_dict)
                with self.assertRaises(IntegrityError), transaction.atomic():
                    entry.save()

    def test_ratings_1_and_10_and_unrated_are_allowed(self):
        for good in (1, 10, None):
            with self.subTest(rating=good):
                Entry(owner=self.user, game=self.game, rating=good).full_clean()

    def test_negative_hours_are_rejected(self):
        entry = Entry(owner=self.user, game=self.game, hours_played=Decimal("-1"))
        with self.assertRaises(ValidationError) as caught:
            entry.full_clean()
        self.assertIn("hours_played", caught.exception.message_dict)
        with self.assertRaises(IntegrityError), transaction.atomic():
            entry.save()

    def test_zero_and_fractional_hours_are_allowed(self):
        for good in (Decimal("0"), Decimal("12.5")):
            with self.subTest(hours=good):
                Entry(owner=self.user, game=self.game, hours_played=good).full_clean()


class DeletionTests(TestCase):
    def test_deleting_an_entry_keeps_the_game_and_other_entries(self):
        game = make_game("Celeste")
        mine = make_entry(make_user("player"), game)
        theirs = make_entry(make_user("other"), game)

        mine.delete()

        self.assertTrue(Game.objects.filter(pk=game.pk).exists())
        self.assertTrue(Entry.objects.filter(pk=theirs.pk).exists())

    def test_deleting_the_last_entry_keeps_the_game(self):
        game = make_game("Celeste")
        make_entry(make_user("player"), game).delete()
        self.assertTrue(Game.objects.filter(pk=game.pk).exists())


class CategoryBadgeTests(TestCase):
    def test_main_game_has_no_badge(self):
        self.assertEqual(make_game(game_category=GameCategory.MAIN_GAME).category_badge, "")

    def test_non_main_games_use_igdb_labels(self):
        cases = {
            GameCategory.EXPANSION: "Expansion",
            GameCategory.REMAKE: "Remake",
            GameCategory.REMASTER: "Remaster",
            GameCategory.PORT: "Port",
            GameCategory.STANDALONE_EXPANSION: "Standalone Expansion",
        }
        for category, label in cases.items():
            with self.subTest(category=category):
                self.assertEqual(make_game(game_category=category).category_badge, label)

    def test_allowlist_matches_the_approved_rule(self):
        self.assertEqual(ELIGIBLE_GAME_CATEGORIES, {0, 1, 2, 4, 6, 7, 8, 9, 10, 11, 12})
