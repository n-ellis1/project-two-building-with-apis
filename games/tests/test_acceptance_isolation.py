"""Phase 12 acceptance sweep: the PRD's owner-isolation matrix in one place.

Two users. Signed in as B, every way of reaching A's entry, on the website and
through the API, behaves as if it doesn't exist, and changes nothing. The
detailed per-feature tests live in each feature's own module; this module walks
the PRD's "Owner isolation" acceptance criteria end to end.

IGDB is patched to fail if called. Tokens exist only in the test database.
"""

import re
from datetime import date
from decimal import Decimal
from unittest import mock

from django.core.cache import cache
from django.test import Client, TestCase
from django.urls import reverse
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from games.models import Entry, Game
from games.tests.factories import csrf_client, make_entry, make_game, make_user
from games.tests.test_save_service import row_counts
from games.views import refresh_attempt_key

PASSWORD = "test-pass-not-real"
A_ONLY_NOTE = "zz-a-only-secret-note"
A_ONLY_TITLE = "Signalis A Only"
SAVED_GAMES_URL = reverse("games:saved_games")
API_LIST_URL = reverse("api-entry-list")
HORROR = 19


def api_detail_url(entry_id) -> str:
    return reverse("api-entry-detail", args=[entry_id])


def no_igdb():
    """Patch every IGDB entry point the website and API use, to fail if called."""
    patches = [
        mock.patch(f"games.igdb.{name}", side_effect=AssertionError(f"IGDB {name} called"))
        for name in ("search_games", "fetch_game", "popular_games")
    ]
    return patches


class IsolationTestCase(TestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        self.igdb_mocks = []
        for patcher in no_igdb():
            self.igdb_mocks.append(patcher.start())
            self.addCleanup(patcher.stop)

        self.user_a = make_user("demo_a_sweep", PASSWORD)
        self.user_b = make_user("demo_b_sweep", PASSWORD)
        self.game_a = make_game(
            A_ONLY_TITLE,
            igdb_id=101_001,
            platforms=["PC (Microsoft Windows)"],
            genres=["Adventure"],
            themes=[(HORROR, "Horror"), (21, "Survival")],
            game_category=0,
        )
        self.entry_a = make_entry(
            self.user_a,
            self.game_a,
            status=Entry.Status.PLAYING,
            favorite=True,
            rating=9,
            notes=A_ONLY_NOTE,
            platform_played="PC (Microsoft Windows)",
            start_date=date(2026, 2, 1),
            hours_played=Decimal("7.5"),
        )
        self.game_b = make_game("Tetris Effect", igdb_id=101_002, themes=[(1, "Action")])
        self.entry_b = make_entry(self.user_b, self.game_b)
        # A stored game neither user has saved yet, so creates need no IGDB call.
        self.unsaved = make_game("Celeste", igdb_id=101_003, platforms=["PC (Microsoft Windows)"])

    def stored_a(self) -> dict:
        """A's entry and its shared Game, read fresh from the database."""
        return {
            "entry": Entry.objects.filter(pk=self.entry_a.pk).values().get(),
            "game": Game.objects.filter(pk=self.game_a.pk).values().get(),
            "rows": row_counts(),
        }

    def assert_igdb_never_called(self):
        for igdb_mock in self.igdb_mocks:
            igdb_mock.assert_not_called()

    def assert_no_refresh_attempt(self, game):
        self.assertIsNone(cache.get(refresh_attempt_key(game.igdb_id)))


class WebsiteIsolationTests(IsolationTestCase):
    def test_get_of_as_detail_edit_and_delete_pages_is_404_like_a_missing_id(self):
        self.client.force_login(self.user_b)
        missing_id = Entry.objects.order_by("-pk").first().pk + 1000
        for name in ("games:entry_detail", "games:entry_edit", "games:entry_delete"):
            for entry_id in (self.entry_a.pk, missing_id):
                with self.subTest(page=name, entry_id=entry_id):
                    response = self.client.get(reverse(name, args=[entry_id]))

                    self.assertEqual(response.status_code, 404)
                    self.assertNotContains(response, A_ONLY_TITLE, status_code=404)

    def test_csrf_valid_posts_to_as_edit_delete_and_refresh_are_404_and_change_nothing(self):
        before = self.stored_a()
        client, token = csrf_client(self.user_b, SAVED_GAMES_URL)
        edit_data = {
            "csrfmiddlewaretoken": token,
            "status": "dropped",
            "notes": "changed by b",
            "platform_played": "",
        }
        for name, data in (
            ("games:entry_edit", edit_data),
            ("games:entry_delete", {"csrfmiddlewaretoken": token}),
            ("games:entry_refresh", {"csrfmiddlewaretoken": token}),
        ):
            with self.subTest(action=name):
                response = client.post(reverse(name, args=[self.entry_a.pk]), data)

                self.assertEqual(response.status_code, 404)
        self.assertEqual(self.stored_a(), before)
        self.assert_igdb_never_called()
        self.assert_no_refresh_attempt(self.game_a)

        # The same client and token work on B's own entry, so each 404 was the owner check.
        response = client.post(
            reverse("games:entry_edit", args=[self.entry_b.pk]),
            {**edit_data, "status": "playing", "notes": "mine"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Entry.objects.get(pk=self.entry_b.pk).notes, "mine")

    def test_refresh_is_post_only_even_for_the_owner(self):
        self.client.force_login(self.user_a)
        before = self.stored_a()

        response = self.client.get(reverse("games:entry_refresh", args=[self.entry_a.pk]))

        self.assertEqual(response.status_code, 405)
        self.assertEqual(self.stored_a(), before)
        self.assert_igdb_never_called()
        self.assert_no_refresh_attempt(self.game_a)

    def test_bs_list_and_search_never_show_as_entries(self):
        self.client.force_login(self.user_b)
        for params in ({}, {"q": A_ONLY_NOTE}, {"q": "signalis"}, {"q": "horror"}):
            with self.subTest(params=params):
                response = self.client.get(SAVED_GAMES_URL, params)

                self.assertEqual(response.status_code, 200)
                self.assertNotContains(response, A_ONLY_TITLE)
                self.assertNotContains(response, f"/games/{self.entry_a.pk}/")
                shown = [entry.pk for entry in response.context["page_obj"]]
                self.assertNotIn(self.entry_a.pk, shown)
        # Searching A's notes as B finds nothing at all.
        response = self.client.get(SAVED_GAMES_URL, {"q": A_ONLY_NOTE})
        self.assertEqual(response.context["page_obj"].paginator.count, 0)

    def test_bs_theme_dropdown_lists_only_bs_themes_and_as_theme_id_is_ignored(self):
        self.client.force_login(self.user_b)

        page = self.client.get(SAVED_GAMES_URL).content.decode()
        options = re.findall(r'<option value="(\d+)"[^>]*>([^<]+)</option>', page)
        self.assertIn(("1", "Action"), options)
        self.assertNotIn("Horror", page)
        self.assertNotIn("Survival", page)

        filtered = self.client.get(SAVED_GAMES_URL, {"theme": HORROR})
        self.assertEqual(filtered.status_code, 200)
        self.assertEqual(filtered.context["query"].theme, None)
        self.assertEqual([entry.pk for entry in filtered.context["page_obj"]], [self.entry_b.pk])

    def test_saving_from_search_sets_the_owner_to_the_signed_in_user(self):
        client, token = csrf_client(self.user_b, SAVED_GAMES_URL)

        response = client.post(
            reverse("games:search_save"),
            {
                "csrfmiddlewaretoken": token,
                "igdb_id": self.unsaved.igdb_id,
                "owner": self.user_a.pk,
                "owner_id": self.user_a.pk,
            },
        )

        entry = Entry.objects.get(game=self.unsaved)
        self.assertEqual(entry.owner, self.user_b)
        self.assertRedirects(response, reverse("games:entry_edit", args=[entry.pk]))
        self.assertFalse(Entry.objects.filter(owner=self.user_a, game=self.unsaved).exists())

    def test_signed_out_visitor_is_sent_to_login_and_returned_to_the_page(self):
        client = Client()
        target = reverse("games:entry_detail", args=[self.entry_b.pk])

        response = client.get(target)

        login_url = f"{reverse('login')}?next={target}"
        self.assertRedirects(response, login_url)
        signed_in = client.post(login_url, {"username": self.user_b.username, "password": PASSWORD})
        self.assertRedirects(signed_in, target)


class ApiIsolationTests(IsolationTestCase):
    def clients_for_b(self):
        by_token = APIClient()
        by_token.credentials(
            HTTP_AUTHORIZATION=f"Token {Token.objects.create(user=self.user_b).key}"
        )
        by_session = APIClient()
        # A real website session. APIClient skips CSRF by default; the CSRF rule for
        # session writes is tested in test_api_access.py.
        by_session.force_login(self.user_b)
        return {"token": by_token, "session": by_session}

    def test_get_put_patch_delete_on_as_entry_are_404_and_change_nothing(self):
        before = self.stored_a()
        url = api_detail_url(self.entry_a.pk)
        for label, client in self.clients_for_b().items():
            for method, body in (
                ("get", None),
                ("put", {"status": "dropped"}),
                ("patch", {"notes": "changed by b"}),
                ("delete", None),
            ):
                with self.subTest(auth=label, method=method):
                    response = getattr(client, method)(url, body, format="json")

                    self.assertEqual(response.status_code, 404)
        self.assertEqual(self.stored_a(), before)
        self.assert_igdb_never_called()

    def test_bs_api_list_and_search_never_include_as_entries(self):
        client = self.clients_for_b()["token"]
        for params in ({}, {"q": A_ONLY_NOTE}, {"q": "signalis"}):
            with self.subTest(params=params):
                response = client.get(API_LIST_URL, params)

                self.assertEqual(response.status_code, 200)
                ids = [entry["id"] for entry in response.json()["results"]]
                self.assertNotIn(self.entry_a.pk, ids)
        self.assertEqual(client.get(API_LIST_URL, {"q": A_ONLY_NOTE}).json()["count"], 0)

    def test_as_theme_id_is_400_on_bs_api_list(self):
        client = self.clients_for_b()["token"]

        response = client.get(API_LIST_URL, {"theme": HORROR})

        self.assertEqual(response.status_code, 400)
        self.assertIn("theme", response.json())

    def test_create_sets_the_owner_from_the_token_even_if_another_owner_is_posted(self):
        client = self.clients_for_b()["token"]

        response = client.post(
            API_LIST_URL,
            {"igdb_id": self.unsaved.igdb_id, "owner": self.user_a.pk},
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(Entry.objects.get(pk=response.json()["id"]).owner, self.user_b)
        self.assertFalse(Entry.objects.filter(owner=self.user_a, game=self.unsaved).exists())
        self.assert_igdb_never_called()

    def test_unauthenticated_requests_are_401(self):
        client = APIClient()
        for method, url in (
            ("get", API_LIST_URL),
            ("post", API_LIST_URL),
            ("get", api_detail_url(self.entry_a.pk)),
            ("patch", api_detail_url(self.entry_a.pk)),
            ("put", api_detail_url(self.entry_a.pk)),
            ("delete", api_detail_url(self.entry_a.pk)),
        ):
            with self.subTest(method=method, url=url):
                self.assertEqual(getattr(client, method)(url, {}, format="json").status_code, 401)
        self.assertTrue(Entry.objects.filter(pk=self.entry_a.pk).exists())
