"""My Saved Games: isolation, order, 10 per page, forgiving pages (stories 7, 46, 60, 63-64, 68)."""

from datetime import timedelta
from unittest import mock

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from games.models import GameCategory

from .factories import make_entry, make_game, make_user

URL = reverse("games:saved_games")


def make_entries(owner, prefix, count, start=None):
    """`count` entries named "<prefix> 01".., the highest number added most recently."""
    start = start or timezone.now() - timedelta(days=count)
    return [
        make_entry(
            owner,
            make_game(f"{prefix} {n:02d}", platforms=["PC (Microsoft Windows)"]),
            created_at=start + timedelta(hours=n),
        )
        for n in range(1, count + 1)
    ]


class OwnerIsolationTests(TestCase):
    def setUp(self):
        self.user_a = make_user("demo_a")
        self.user_b = make_user("demo_b")
        make_entries(self.user_a, "Alpha Only", 15)
        make_entries(self.user_b, "Bravo Only", 13)

    def test_user_b_never_sees_user_a_entries_on_any_page(self):
        self.client.force_login(self.user_b)
        for page in ("1", "2", "99"):
            with self.subTest(page=page):
                response = self.client.get(URL, {"page": page})
                self.assertContains(response, "Bravo Only")
                self.assertNotContains(response, "Alpha Only")
                self.assertTrue(all(e.owner == self.user_b for e in response.context["page_obj"]))


class ListingTests(TestCase):
    def setUp(self):
        self.user = make_user("player")
        self.client.force_login(self.user)

    def titles(self, response):
        return [entry.game.name for entry in response.context["page_obj"]]

    def test_ten_per_page_newest_first_with_previous_and_next(self):
        make_entries(self.user, "Game", 15)

        page1 = self.client.get(URL)
        self.assertEqual(self.titles(page1), [f"Game {n:02d}" for n in range(15, 5, -1)])
        self.assertContains(page1, 'href="?page=2"')
        self.assertNotContains(page1, ">Previous<")
        self.assertContains(page1, "Page 1 of 2")

        page2 = self.client.get(URL, {"page": "2"})
        self.assertEqual(self.titles(page2), [f"Game {n:02d}" for n in range(5, 0, -1)])
        self.assertContains(page2, 'href="?page=1"')
        self.assertNotContains(page2, ">Next<")

    def test_bad_pages_show_page_1_and_past_the_end_shows_the_last_page(self):
        make_entries(self.user, "Game", 25)
        for raw, expected in [("0", 1), ("abc", 1), ("-1", 1), ("2.5", 1), ("", 1), ("99", 3)]:
            with self.subTest(page=raw):
                response = self.client.get(URL, {"page": raw})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.context["page_obj"].number, expected)

    def test_ties_on_date_added_break_by_title_ignoring_case_then_entry_id(self):
        added = timezone.now()
        for name in ("beta", "Alpha", "Gamma", "alpha"):
            make_entry(self.user, make_game(name), created_at=added)
        first_alpha, second_alpha = self.user.entries.filter(game__name__iexact="alpha").order_by(
            "id"
        )

        entries = list(self.client.get(URL).context["page_obj"])

        self.assertEqual([e.game.name for e in entries][2:], ["beta", "Gamma"])
        self.assertEqual(entries[:2], [first_alpha, second_alpha])

    def test_rows_show_title_platforms_status_favorite_and_badges_for_non_main_games(self):
        make_entry(
            self.user,
            make_game("Dark Souls III", platforms=["PlayStation 4", "Xbox One"]),
            status="completed",
            favorite=True,
        )
        make_entry(
            self.user,
            make_game("Dark Souls III: The Ringed City", game_category=GameCategory.EXPANSION),
        )

        response = self.client.get(URL)

        self.assertContains(response, "PlayStation 4, Xbox One")
        self.assertContains(response, "Completed")
        self.assertContains(response, "Want to Play")
        self.assertContains(response, 'data-testid="favorite-badge"', count=1)
        self.assertContains(response, 'data-testid="category-badge"', count=1)
        self.assertContains(response, ">Expansion</span>")
        self.assertNotContains(response, "Main Game")

    def test_empty_state_for_a_user_with_no_entries(self):
        make_entries(make_user("someone_else"), "Not Mine", 3)
        response = self.client.get(URL)
        self.assertContains(response, "You haven't saved any games yet.")
        self.assertNotContains(response, "Not Mine")

    def test_the_list_never_contacts_the_network(self):
        make_entries(self.user, "Game", 3)

        def fail(*args, **kwargs):
            raise AssertionError("My Saved Games must not make network requests.")

        with (
            mock.patch("socket.create_connection", fail),
            mock.patch("requests.sessions.Session.request", fail),
        ):
            self.assertEqual(self.client.get(URL).status_code, 200)

    def test_signed_out_visitors_are_redirected_to_login(self):
        self.client.logout()
        self.assertRedirects(self.client.get(URL), f"{reverse('login')}?next={URL}")
