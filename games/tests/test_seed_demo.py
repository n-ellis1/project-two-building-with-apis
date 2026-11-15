"""The demo seed command: safe to rerun, never overwrites, works offline (stories 116-118)."""

import os
from io import StringIO
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.management import CommandError, call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from games.models import ELIGIBLE_GAME_CATEGORIES, Entry, Game, Genre, Platform, Theme

User = get_user_model()
DEMO_USERS = ("demo_a", "demo_b")
TEST_PASSWORD = "seed-test-password-not-real"


def no_network(*args, **kwargs):
    raise AssertionError("The seed command must not make network requests.")


@mock.patch("socket.create_connection", no_network)
@mock.patch("requests.sessions.Session.request", no_network)
class SeedDemoTests(TestCase):
    def seed(self, password=TEST_PASSWORD):
        env = {"DEMO_PASSWORD": password} if password is not None else {}
        out = StringIO()
        with mock.patch.dict(os.environ, env):
            if password is None:
                os.environ.pop("DEMO_PASSWORD", None)
            call_command("seed_demo", stdout=out)
        return out.getvalue()

    def demo_user(self, username):
        user = User.objects.filter(username=username).first()
        self.assertIsNotNone(user, f"{username} was not created")
        return user

    def snapshot(self):
        """Every seeded row, so two runs can be compared exactly."""
        return {
            "users": list(User.objects.order_by("username").values_list("username", "password")),
            "games": list(Game.objects.order_by("igdb_id").values()),
            "platforms": list(Platform.objects.order_by("igdb_id").values()),
            "genres": list(Genre.objects.order_by("igdb_id").values()),
            "themes": list(Theme.objects.order_by("igdb_id").values()),
            "entries": list(Entry.objects.order_by("id").values()),
            "game_links": [
                (g.igdb_id, sorted(g.platforms.values_list("igdb_id", flat=True)))
                for g in Game.objects.order_by("igdb_id")
            ],
        }

    def test_running_twice_gives_the_same_rows(self):
        self.seed()
        first = self.snapshot()
        self.assertEqual([u for u, _ in first["users"]], list(DEMO_USERS))
        self.assertGreater(len(first["entries"]), 20)

        output = self.seed()

        self.assertEqual(self.snapshot(), first)
        self.assertIn("0 created", output)

    def test_seeded_users_can_sign_in_with_the_env_password(self):
        self.seed()
        for username in DEMO_USERS:
            with self.subTest(user=username):
                self.assertTrue(self.demo_user(username).check_password(TEST_PASSWORD))

    def test_a_rerun_keeps_changed_passwords_and_edited_entries(self):
        self.seed()
        demo_a = self.demo_user("demo_a")
        demo_a.set_password("changed-by-the-user")
        demo_a.save()
        entry = demo_a.entries.order_by("id").first()
        entry.notes = "My own notes"
        entry.rating = 3
        entry.save()

        self.seed(password="a-different-env-password")

        demo_a.refresh_from_db()
        entry.refresh_from_db()
        self.assertTrue(demo_a.check_password("changed-by-the-user"))
        self.assertEqual((entry.notes, entry.rating), ("My own notes", 3))

    def test_missing_password_stops_with_a_clear_message_and_creates_nothing(self):
        for missing in (None, "", "   "):
            with self.subTest(password=missing):
                with self.assertRaisesMessage(CommandError, "DEMO_PASSWORD"):
                    self.seed(password=missing)
                self.assertFalse(User.objects.exists())
                self.assertFalse(Game.objects.exists())
                self.assertFalse(Entry.objects.exists())

    def test_an_unrelated_account_with_a_demo_username_stops_the_seed_untouched(self):
        # An account the seeder didn't create, which already has its own entry.
        stranger = User.objects.create_user("demo_b", password="stranger-password")
        own_game = Game.objects.create(igdb_id=1, name="Their Game", last_fetched_at=timezone.now())
        own_entry = Entry.objects.create(owner=stranger, game=own_game, notes="theirs")
        before = self.snapshot()

        with self.assertRaisesMessage(CommandError, "demo_b"):
            self.seed()

        self.assertEqual(self.snapshot(), before)
        stranger.refresh_from_db()
        self.assertTrue(stranger.check_password("stranger-password"))
        self.assertEqual(list(stranger.entries.all()), [own_entry])
        self.assertFalse(User.objects.filter(username="demo_a").exists())


class SeededDataTests(TestCase):
    """The stored demo data supports this phase's checks and the later phases' walks."""

    @classmethod
    def setUpTestData(cls):
        with (
            mock.patch("socket.create_connection", no_network),
            mock.patch("requests.sessions.Session.request", no_network),
            mock.patch.dict(os.environ, {"DEMO_PASSWORD": TEST_PASSWORD}),
        ):
            call_command("seed_demo", stdout=StringIO())
        cls.demo_a = User.objects.get(username="demo_a")
        cls.demo_b = User.objects.get(username="demo_b")

    def theme_names(self, user):
        return set(Theme.objects.filter(games__entries__owner=user).values_list("name", flat=True))

    def test_every_stored_game_passes_the_eligibility_rule(self):
        for game in Game.objects.all():
            with self.subTest(game=game.name):
                self.assertIsNone(game.version_parent)
                self.assertIn(game.game_category, ELIGIBLE_GAME_CATEGORIES)

    def test_demo_a_has_horror_and_survival_and_demo_b_has_neither(self):
        self.assertTrue({"Horror", "Survival"} <= self.theme_names(self.demo_a))
        self.assertFalse({"Horror", "Survival"} & self.theme_names(self.demo_b))

    def test_demo_a_has_a_horror_game_with_status_playing(self):
        self.assertTrue(
            self.demo_a.entries.filter(
                status=Entry.Status.PLAYING, game__themes__igdb_id=19
            ).exists()
        )

    def test_a_stored_game_is_saved_by_a_but_not_by_b(self):
        a_only = Game.objects.filter(entries__owner=self.demo_a).exclude(entries__owner=self.demo_b)
        self.assertTrue(a_only.filter(name="Dark Souls III").exists())

    def test_both_lists_fill_more_than_one_page_and_some_games_are_shared(self):
        self.assertGreater(self.demo_a.entries.count(), 10)
        self.assertGreater(self.demo_b.entries.count(), 10)
        shared = Game.objects.filter(entries__owner=self.demo_a).filter(entries__owner=self.demo_b)
        self.assertTrue(shared.exists())

    def test_a_stale_platform_entry_and_a_game_without_a_cover_exist(self):
        stale = [
            e
            for e in Entry.objects.exclude(platform_played="")
            if not e.game.platforms.filter(name=e.platform_played).exists()
        ]
        self.assertEqual(len(stale), 1)
        self.assertTrue(Game.objects.filter(cover_image_id="").exists())

    def test_seeded_entry_dates_are_sensible(self):
        for entry in Entry.objects.exclude(start_date=None).exclude(finish_date=None):
            with self.subTest(entry=str(entry)):
                self.assertLessEqual(entry.start_date, entry.finish_date)

    def test_demo_a_reaches_page_2_and_demo_b_never_sees_a_only_games(self):
        url = reverse("games:saved_games")
        self.client.force_login(self.demo_a)
        page1 = self.client.get(url)
        page2 = self.client.get(url, {"page": "2"})
        self.assertEqual(len(page1.context["page_obj"]), 10)
        self.assertContains(page1, f'href="{url}?page=2"')
        self.assertEqual(page2.context["page_obj"].number, 2)
        self.assertEqual(len(page2.context["page_obj"]), self.demo_a.entries.count() - 10)

        a_only = Game.objects.filter(entries__owner=self.demo_a).exclude(entries__owner=self.demo_b)
        self.client.force_login(self.demo_b)
        for page in ("1", "2", "99"):
            with self.subTest(page=page):
                response = self.client.get(url, {"page": page})
                self.assertTrue(all(e.owner == self.demo_b for e in response.context["page_obj"]))
                for game in a_only:
                    self.assertNotContains(response, game.name)
