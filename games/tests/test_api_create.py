"""Creating entries through the API (`POST /api/entries/`), through the one save service.

IGDB is mocked at the client boundary (`games.igdb.fetch_game`). No test here contacts
Twitch or IGDB.
"""

from datetime import date
from decimal import Decimal
from unittest import mock

from django.db import connection
from django.test import TransactionTestCase
from django.urls import reverse
from rest_framework.test import APIClient, APITestCase

from games import igdb
from games.models import Entry
from games.saving import GENERIC_SAVE_MESSAGE, SaveFailed
from games.tests.factories import make_entry, make_game, make_user
from games.tests.test_save_service import fetched, row_counts
from games.validation import FINISH_BEFORE_START, PLATFORM_NOT_LISTED
from games.views import ALREADY_SAVED_MESSAGE

LIST_URL = reverse("api-entry-list")
UPSTREAM_CODES = [
    "igdb_timeout",
    "igdb_unreachable",
    "igdb_rate_limited",
    "igdb_unavailable",
    "igdb_misconfigured",
]
NEW_IGDB_ID = 26758


class CreateErrorResponseTests(APITestCase):
    def setUp(self):
        self.user = make_user("creator")
        self.client.force_authenticate(self.user)
        # Unhandled exceptions become plain 500 responses (as for a real client)
        # instead of being re-raised into the test.
        self.client.raise_request_exception = False

    def create(self, igdb_id=NEW_IGDB_ID):
        return self.client.post(LIST_URL, {"igdb_id": igdb_id}, format="json")

    def test_upstream_failures_are_503_with_detail_and_code(self):
        for code in UPSTREAM_CODES:
            with self.subTest(code=code):
                before = row_counts()
                with mock.patch("games.igdb.fetch_game", side_effect=igdb.IgdbError(code)):
                    response = self.create()

                self.assertEqual(response.status_code, 503)
                self.assertEqual(response.json(), {"detail": igdb.MESSAGES[code], "code": code})
                self.assertNotIn("Retry-After", response.headers)
                self.assertEqual(row_counts(), before)

    def test_rate_limit_passes_on_retry_after_only_when_the_client_supplies_it(self):
        with mock.patch(
            "games.igdb.fetch_game",
            side_effect=igdb.IgdbError("igdb_rate_limited", retry_after=7),
        ):
            response = self.create()

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.headers["Retry-After"], "7")
        self.assertEqual(response.json()["code"], "igdb_rate_limited")

        with mock.patch(
            "games.igdb.fetch_game",
            side_effect=igdb.IgdbError("igdb_rate_limited", retry_after=None),
        ):
            response = self.create()

        self.assertEqual(response.status_code, 503)
        self.assertNotIn("Retry-After", response.headers)

    def test_unknown_igdb_game_is_400(self):
        before = row_counts()
        with mock.patch("games.igdb.fetch_game", side_effect=igdb.IgdbError("igdb_game_not_found")):
            response = self.create()

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json(),
            {"detail": igdb.MESSAGES["igdb_game_not_found"], "code": "igdb_game_not_found"},
        )
        self.assertEqual(row_counts(), before)

    def test_excluded_release_is_400_whether_fetched_or_stored(self):
        excluded = {
            "detail": igdb.MESSAGES["game_category_excluded"],
            "code": "game_category_excluded",
        }

        # Fetched from IGDB: a Bundle (3). The real save service applies the rule.
        before = row_counts()
        with mock.patch("games.igdb.fetch_game", return_value=fetched(NEW_IGDB_ID, 3)):
            response = self.create()
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), excluded)
        self.assertEqual(row_counts(), before)

        # Already stored as an edition: refused from the stored values, no IGDB call.
        edition = make_game("Some Game: Deluxe Edition", version_parent=1942)
        before = row_counts()
        with mock.patch("games.igdb.fetch_game") as fetch:
            response = self.create(edition.igdb_id)
        fetch.assert_not_called()
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), excluded)
        self.assertEqual(row_counts(), before)

    def test_already_saved_is_400_and_leaves_the_existing_entry_unchanged(self):
        game = make_game("Hades", platforms=["PC"])
        existing = make_entry(
            self.user,
            game,
            status=Entry.Status.COMPLETED,
            rating=9,
            notes="Escaped on heat 8.",
            platform_played="PC",
            start_date=date(2026, 1, 2),
        )
        stored = Entry.objects.filter(pk=existing.pk).values().get()
        before = row_counts()

        with mock.patch("games.igdb.fetch_game") as fetch:
            response = self.create(game.igdb_id)

        fetch.assert_not_called()
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json(), {"detail": ALREADY_SAVED_MESSAGE, "code": "duplicate_entry"}
        )
        self.assertEqual(ALREADY_SAVED_MESSAGE, "Already in your games")
        self.assertEqual(row_counts(), before)
        self.assertEqual(Entry.objects.filter(pk=existing.pk).values().get(), stored)

    def test_unexpected_save_failure_is_a_safe_generic_500(self):
        before = row_counts()
        with mock.patch("games.api.save_game", side_effect=SaveFailed()):
            response = self.create()

        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.headers["Content-Type"], "application/json")
        self.assertEqual(response.json(), {"detail": GENERIC_SAVE_MESSAGE, "code": "save_failed"})
        self.assertEqual(row_counts(), before)


class CreateWithTrackingTests(APITestCase):
    def setUp(self):
        self.user = make_user("tracker")
        self.client.force_authenticate(self.user)

    def test_valid_create_saves_the_tracking_fields_and_returns_the_entry(self):
        record = fetched(NEW_IGDB_ID, 0, name="Hollow Knight: Silksong")
        platform = record.platforms[0].name
        payload = {
            "igdb_id": NEW_IGDB_ID,
            "status": "playing",
            "favorite": True,
            "rating": 9,
            "notes": "Day one.",
            "platform_played": platform,
            "start_date": "2026-09-04",
            "finish_date": "2026-09-20",
            "hours_played": 31.5,
        }
        with mock.patch("games.igdb.fetch_game", return_value=record) as fetch:
            response = self.client.post(LIST_URL, payload, format="json")

        fetch.assert_called_once_with(NEW_IGDB_ID)
        self.assertEqual(response.status_code, 201)
        body = response.json()
        entry = Entry.objects.get(pk=body["id"])
        self.assertEqual(entry.owner, self.user)
        self.assertEqual(entry.game.igdb_id, NEW_IGDB_ID)
        self.assertEqual(
            (
                entry.status,
                entry.favorite,
                entry.rating,
                entry.notes,
                entry.platform_played,
                entry.start_date,
                entry.finish_date,
                entry.hours_played,
            ),
            (
                "playing",
                True,
                9,
                "Day one.",
                platform,
                date(2026, 9, 4),
                date(2026, 9, 20),
                Decimal("31.5"),
            ),
        )
        for name, value in payload.items():
            if name != "igdb_id":
                self.assertEqual(body[name], value, name)
        self.assertNotIn("igdb_id", body)
        self.assertEqual(body["game"]["igdb_id"], NEW_IGDB_ID)
        self.assertEqual(body["game"]["name"], "Hollow Knight: Silksong")

    def test_create_with_only_igdb_id_uses_the_defaults(self):
        game = make_game("Celeste")

        response = self.client.post(LIST_URL, {"igdb_id": game.igdb_id}, format="json")

        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual((body["status"], body["favorite"]), ("want_to_play", False))
        self.assertIsNone(body["rating"])

    def test_invalid_tracking_writes_nothing_even_when_igdb_returned_a_new_game(self):
        cases = [
            ({"platform_played": "Sega Saturn"}, "platform_played", PLATFORM_NOT_LISTED),
            (
                {"start_date": "2026-05-10", "finish_date": "2026-05-01"},
                "finish_date",
                FINISH_BEFORE_START,
            ),
        ]
        for tracking_values, field, message in cases:
            with self.subTest(field=field):
                before = row_counts()
                with mock.patch(
                    "games.igdb.fetch_game", return_value=fetched(NEW_IGDB_ID, 0)
                ) as fetch:
                    response = self.client.post(
                        LIST_URL, {"igdb_id": NEW_IGDB_ID, **tracking_values}, format="json"
                    )

                fetch.assert_called_once_with(NEW_IGDB_ID)  # IGDB succeeded
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.json(), {field: [message]})
                self.assertEqual(row_counts(), before)

    def test_invalid_tracking_for_a_stored_game_writes_nothing(self):
        game = make_game("Hades", platforms=["PC"])
        before = row_counts()

        response = self.client.post(
            LIST_URL, {"igdb_id": game.igdb_id, "platform_played": "Xbox"}, format="json"
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {"platform_played": [PLATFORM_NOT_LISTED]})
        self.assertEqual(row_counts(), before)

    def test_field_errors_come_before_any_igdb_call(self):
        cases = [
            {},
            {"igdb_id": "abc"},
            {"igdb_id": 0},
            {"igdb_id": 2_147_483_648},
            {"igdb_id": NEW_IGDB_ID, "rating": 11},
            {"igdb_id": NEW_IGDB_ID, "hours_played": -1},
            {"igdb_id": NEW_IGDB_ID, "status": "finished"},
        ]
        for payload in cases:
            with self.subTest(payload=payload):
                with mock.patch("games.igdb.fetch_game") as fetch:
                    response = self.client.post(LIST_URL, payload, format="json")

                fetch.assert_not_called()
                self.assertEqual(response.status_code, 400)
                expected_field = next((name for name in payload if name != "igdb_id"), "igdb_id")
                self.assertIn(expected_field, response.json())


class CreateFetchOutsideTransactionTests(TransactionTestCase):
    def test_igdb_is_called_outside_any_write_transaction(self):
        user = make_user("outside_tx")
        client = APIClient()
        client.force_authenticate(user)
        seen = []

        def fetch(igdb_id):
            seen.append(connection.in_atomic_block)
            return fetched(igdb_id, 0)

        with mock.patch("games.igdb.fetch_game", side_effect=fetch):
            response = client.post(LIST_URL, {"igdb_id": NEW_IGDB_ID}, format="json")

        self.assertEqual(response.status_code, 201)
        self.assertEqual(seen, [False])
