"""API authentication, owner isolation and IGDB-outage behavior.

Tokens here are created in the test database only. No test contacts IGDB or Twitch.
"""

from datetime import date
from unittest import mock

import requests
from django.conf import settings
from django.test import override_settings
from django.urls import reverse
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient, APITestCase

from games import igdb
from games.models import Entry, Game
from games.tests.factories import make_entry, make_game, make_user
from games.tests.test_save_service import row_counts

LIST_URL = reverse("api-entry-list")


def detail_url(entry_id) -> str:
    return reverse("api-entry-detail", args=[entry_id])


def token_client(user) -> APIClient:
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Token {Token.objects.create(user=user).key}")
    return client


def session_client(user) -> APIClient:
    client = APIClient()
    client.force_login(user)  # a real Django session, as after signing in on the website
    return client


class AuthenticationTests(APITestCase):
    def setUp(self):
        self.user = make_user("api_user")
        self.entry = make_entry(self.user, make_game("Tunic"))

    def test_no_credentials_is_401_for_every_method(self):
        client = APIClient()
        requests_to_send = [
            ("get", LIST_URL),
            ("post", LIST_URL),
            ("get", detail_url(self.entry.pk)),
            ("put", detail_url(self.entry.pk)),
            ("patch", detail_url(self.entry.pk)),
            ("delete", detail_url(self.entry.pk)),
        ]
        for method, url in requests_to_send:
            with self.subTest(method=method, url=url):
                response = getattr(client, method)(url, {}, format="json")

                self.assertEqual(response.status_code, 401)
                self.assertEqual(response.headers["WWW-Authenticate"], "Token")
        self.assertTrue(Entry.objects.filter(pk=self.entry.pk).exists())

    def test_invalid_token_is_401(self):
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION="Token not-a-real-token")

        self.assertEqual(client.get(LIST_URL).status_code, 401)

    def test_valid_token_works(self):
        client = token_client(self.user)

        response = client.get(LIST_URL)

        self.assertEqual(response.status_code, 200)
        self.assertEqual([e["id"] for e in response.json()["results"]], [self.entry.pk])
        self.assertEqual(
            client.patch(
                detail_url(self.entry.pk), {"status": "playing"}, format="json"
            ).status_code,
            200,
        )

    def test_website_session_works_including_the_browsable_api(self):
        client = session_client(self.user)

        self.assertEqual(client.get(LIST_URL).status_code, 200)
        page = client.get(LIST_URL, HTTP_ACCEPT="text/html")
        self.assertEqual(page.status_code, 200)
        self.assertIn("text/html", page.headers["Content-Type"])
        self.assertContains(page, "Tunic")

    def test_session_writes_need_the_csrf_token(self):
        client = APIClient(enforce_csrf_checks=True)
        client.force_login(self.user)

        response = client.patch(detail_url(self.entry.pk), {"status": "playing"}, format="json")

        self.assertEqual(response.status_code, 403)
        self.assertEqual(Entry.objects.get(pk=self.entry.pk).status, "want_to_play")

        # With the token from a page that sets the cookie, the same write works.
        client.get(reverse("games:saved_games"))
        csrf = client.cookies[settings.CSRF_COOKIE_NAME].value
        response = client.patch(
            detail_url(self.entry.pk), {"status": "playing"}, format="json", HTTP_X_CSRFTOKEN=csrf
        )
        self.assertEqual(response.status_code, 200)


class OwnerIsolationTests(APITestCase):
    """With user B's token or session, user A's entry behaves as if it doesn't exist."""

    def setUp(self):
        self.user_a, self.user_b = make_user("demo_a_test"), make_user("demo_b_test")
        game = make_game("Signalis", platforms=["PC"], themes=[(19, "Horror")])
        self.entry_a = make_entry(
            self.user_a,
            game,
            status="playing",
            rating=9,
            notes="a-only-secret-note",
            platform_played="PC",
            start_date=date(2026, 2, 1),
        )
        self.entry_b = make_entry(self.user_b, make_game("Tetris Effect"))

    def stored_a(self) -> dict:
        return Entry.objects.filter(pk=self.entry_a.pk).values().get()

    def clients_for_b(self):
        return [("token", token_client(self.user_b)), ("session", session_client(self.user_b))]

    def test_every_method_on_another_users_entry_is_404_and_changes_nothing(self):
        before = self.stored_a()
        for kind, client in self.clients_for_b():
            for method, data in [
                ("get", None),
                ("put", {"status": "dropped", "notes": "b was here"}),
                ("patch", {"notes": "b was here"}),
                ("delete", None),
            ]:
                with self.subTest(auth=kind, method=method):
                    response = getattr(client, method)(
                        detail_url(self.entry_a.pk), data, format="json"
                    )

                    self.assertEqual(response.status_code, 404)
                    self.assertNotIn("a-only-secret-note", response.content.decode())
                    self.assertEqual(self.stored_a(), before)

    def test_another_users_entry_looks_the_same_as_a_missing_one(self):
        client = token_client(self.user_b)
        missing = client.get(detail_url(9_999_999))
        someone_elses = client.get(detail_url(self.entry_a.pk))

        self.assertEqual(
            (someone_elses.status_code, someone_elses.json()),
            (missing.status_code, missing.json()),
        )

    def test_list_and_search_never_include_another_users_entries(self):
        for kind, client in self.clients_for_b():
            with self.subTest(auth=kind):
                everything = client.get(LIST_URL).json()
                self.assertEqual([e["id"] for e in everything["results"]], [self.entry_b.pk])

                search = client.get(LIST_URL, {"q": "a-only-secret-note"}).json()
                self.assertEqual((search["count"], search["results"]), (0, []))

    def test_theme_and_platform_only_on_another_users_games_are_400(self):
        client = token_client(self.user_b)

        self.assertEqual(client.get(LIST_URL, {"theme": 19}).status_code, 400)
        self.assertEqual(client.get(LIST_URL, {"platform": "PC"}).status_code, 400)

    def test_create_sets_the_owner_from_the_request_even_if_another_owner_is_posted(self):
        game = make_game("Outer Wilds")
        for kind, client in self.clients_for_b():
            with self.subTest(auth=kind):
                Entry.objects.filter(owner=self.user_b, game=game).delete()

                response = client.post(
                    LIST_URL,
                    {"igdb_id": game.igdb_id, "owner": self.user_a.pk, "owner_id": self.user_a.pk},
                    format="json",
                )

                self.assertEqual(response.status_code, 201)
                entry = Entry.objects.get(pk=response.json()["id"])
                self.assertEqual(entry.owner, self.user_b)
                self.assertFalse(Entry.objects.filter(owner=self.user_a, game=game).exists())

    def test_b_can_save_a_game_a_already_saved_without_touching_as_entry(self):
        before = self.stored_a()
        client = token_client(self.user_b)

        response = client.post(LIST_URL, {"igdb_id": self.entry_a.game.igdb_id}, format="json")

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["notes"], "")
        self.assertEqual(self.stored_a(), before)


@override_settings(IGDB_CLIENT_ID="fake-client-id", IGDB_CLIENT_SECRET="fake-client-secret")
class OutageTests(APITestCase):
    """IGDB unreachable at the HTTP layer (the real client, with requests failing)."""

    def setUp(self):
        self.user = make_user("outage_user")
        self.client.force_authenticate(self.user)
        self.stored = make_game("Stored Game", platforms=["PC"])
        self.entry = make_entry(self.user, make_game("Already Mine"), notes="still here")
        unreachable = mock.patch(
            "games.igdb.requests.post", side_effect=requests.ConnectionError("network down")
        )
        self.http = unreachable.start()
        self.addCleanup(unreachable.stop)

    def test_list_and_retrieve_still_work(self):
        listing = self.client.get(LIST_URL, {"q": "still here", "sort": "title"})
        detail = self.client.get(detail_url(self.entry.pk))

        self.assertEqual(listing.status_code, 200)
        self.assertEqual([e["id"] for e in listing.json()["results"]], [self.entry.pk])
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.json()["notes"], "still here")
        self.http.assert_not_called()

    def test_creating_a_new_game_is_503_and_writes_nothing(self):
        before = row_counts()

        response = self.client.post(LIST_URL, {"igdb_id": 26758}, format="json")

        self.assertEqual(response.status_code, 503)
        self.assertEqual(
            response.json(),
            {"detail": igdb.MESSAGES["igdb_unreachable"], "code": "igdb_unreachable"},
        )
        self.assertEqual(row_counts(), before)

    def test_saving_a_stored_game_still_works(self):
        response = self.client.post(LIST_URL, {"igdb_id": self.stored.igdb_id}, format="json")

        self.assertEqual(response.status_code, 201)
        self.http.assert_not_called()


class MissingCredentialsTests(APITestCase):
    """The offline test runner blanks the IGDB credentials, as on a server without them."""

    def test_list_works_and_a_new_game_is_503_misconfigured(self):
        user = make_user("no_creds")
        self.client.force_authenticate(user)
        entry = make_entry(user, make_game("Local Only"))

        listing = self.client.get(LIST_URL)
        create = self.client.post(LIST_URL, {"igdb_id": 26758}, format="json")

        self.assertEqual([e["id"] for e in listing.json()["results"]], [entry.pk])
        self.assertEqual(create.status_code, 503)
        self.assertEqual(create.json()["code"], "igdb_misconfigured")
        self.assertFalse(Game.objects.filter(igdb_id=26758).exists())
