"""Updating entries through the API (`/api/entries/<id>/`). No test here contacts IGDB."""

from datetime import date
from decimal import Decimal

from django.urls import reverse
from rest_framework.test import APITestCase

from games.api import IGDB_ID_UNCHANGEABLE
from games.models import Entry
from games.tests.factories import make_entry, make_game, make_user
from games.validation import FINISH_BEFORE_START, PLATFORM_NOT_LISTED

TRACKING = [
    "status",
    "favorite",
    "rating",
    "notes",
    "platform_played",
    "start_date",
    "finish_date",
    "hours_played",
]


def tracking(entry: Entry) -> dict:
    """The entry's stored tracking values, read fresh from the database."""
    entry = Entry.objects.get(pk=entry.pk)
    return {name: getattr(entry, name) for name in TRACKING}


def detail_url(entry: Entry) -> str:
    return reverse("api-entry-detail", args=[entry.pk])


class PatchMergesStoredValuesTests(APITestCase):
    def setUp(self):
        self.user = make_user("patcher")
        self.client.force_authenticate(self.user)
        game = make_game("Hollow Knight", platforms=["PC", "Nintendo Switch"])
        self.entry = make_entry(
            self.user,
            game,
            status=Entry.Status.PLAYING,
            favorite=True,
            rating=8,
            notes="Up to the City of Tears.",
            platform_played="PC",
            start_date=date(2026, 3, 10),
            hours_played=Decimal("12.5"),
        )

    def test_finish_date_before_stored_start_date_is_a_field_error(self):
        before = tracking(self.entry)

        response = self.client.patch(
            detail_url(self.entry), {"finish_date": "2026-03-01"}, format="json"
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {"finish_date": [FINISH_BEFORE_START]})
        self.assertEqual(tracking(self.entry), before)

    def test_valid_single_field_patch_changes_only_that_field(self):
        before = tracking(self.entry)

        response = self.client.patch(detail_url(self.entry), {"status": "completed"}, format="json")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "completed")
        self.assertEqual(tracking(self.entry), {**before, "status": "completed"})


class PutAndUpdateRulesTests(APITestCase):
    def setUp(self):
        self.user = make_user("putter")
        self.client.force_authenticate(self.user)
        self.game = make_game("Hollow Knight", platforms=["PC", "Nintendo Switch"])
        self.entry = make_entry(
            self.user,
            self.game,
            status=Entry.Status.PLAYING,
            favorite=True,
            rating=8,
            notes="Up to the City of Tears.",
            platform_played="PC",
            start_date=date(2026, 3, 10),
            finish_date=date(2026, 4, 1),
            hours_played=Decimal("12.5"),
        )

    def test_put_resets_omitted_optional_fields(self):
        created_at = self.entry.created_at

        response = self.client.put(detail_url(self.entry), {"status": "dropped"}, format="json")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            tracking(self.entry),
            {
                "status": "dropped",
                "favorite": False,
                "rating": None,
                "notes": "",
                "platform_played": "",
                "start_date": None,
                "finish_date": None,
                "hours_played": None,
            },
        )
        entry = Entry.objects.get(pk=self.entry.pk)
        self.assertEqual(
            (entry.game, entry.owner, entry.created_at), (self.game, self.user, created_at)
        )
        self.assertEqual(response.json()["notes"], "")

    def test_put_with_no_fields_resets_status_to_want_to_play(self):
        response = self.client.put(detail_url(self.entry), {}, format="json")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(tracking(self.entry)["status"], "want_to_play")

    def test_put_finish_before_start_is_a_field_error(self):
        before = tracking(self.entry)

        response = self.client.put(
            detail_url(self.entry),
            {"start_date": "2026-05-10", "finish_date": "2026-05-01"},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {"finish_date": [FINISH_BEFORE_START]})
        self.assertEqual(tracking(self.entry), before)

    def test_igdb_id_on_update_is_rejected(self):
        other_game = make_game("Celeste")
        before = tracking(self.entry)
        for method in ("patch", "put"):
            for igdb_id in (other_game.igdb_id, self.game.igdb_id):
                with self.subTest(method=method, igdb_id=igdb_id):
                    response = getattr(self.client, method)(
                        detail_url(self.entry),
                        {"igdb_id": igdb_id, "notes": "changed"},
                        format="json",
                    )

                    self.assertEqual(response.status_code, 400)
                    self.assertEqual(response.json(), {"igdb_id": [IGDB_ID_UNCHANGEABLE]})
                    self.assertEqual(tracking(self.entry), before)
                    self.assertEqual(Entry.objects.get(pk=self.entry.pk).game, self.game)

    def test_nested_game_input_and_read_only_fields_are_ignored(self):
        other = make_user("not_me")
        response = self.client.patch(
            detail_url(self.entry),
            {
                "game": {"name": "Renamed", "igdb_id": 1, "platforms": ["Dreamcast"]},
                "owner": other.pk,
                "id": 999_999,
                "created_at": "2000-01-01T00:00:00Z",
                "notes": "Only this changes.",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        entry = Entry.objects.get(pk=self.entry.pk)
        self.game.refresh_from_db()
        self.assertEqual(entry.notes, "Only this changes.")
        self.assertEqual(
            (entry.owner, entry.game, entry.created_at),
            (self.user, self.game, self.entry.created_at),
        )
        self.assertEqual(self.game.name, "Hollow Knight")
        self.assertEqual(
            sorted(self.game.platforms.values_list("name", flat=True)), ["Nintendo Switch", "PC"]
        )
        self.assertEqual(response.json()["game"]["name"], "Hollow Knight")


class StalePlatformUpdateTests(APITestCase):
    """A platform played that a refresh removed may stay unchanged; a new value must be
    one the game currently lists (or blank). Same rule as the website form."""

    def setUp(self):
        self.user = make_user("stale")
        self.client.force_authenticate(self.user)
        game = make_game("Old Game", platforms=["PC"])
        self.entry = make_entry(self.user, game, platform_played="Sega Saturn", notes="old")

    def patch(self, data):
        return self.client.patch(detail_url(self.entry), data, format="json")

    def put(self, data):
        return self.client.put(detail_url(self.entry), data, format="json")

    def test_patch_other_fields_keeps_the_stale_platform(self):
        response = self.patch({"notes": "new notes"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(tracking(self.entry)["platform_played"], "Sega Saturn")

    def test_patch_resending_the_same_stale_platform_is_allowed(self):
        response = self.patch({"platform_played": "Sega Saturn", "rating": 6})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(tracking(self.entry)["platform_played"], "Sega Saturn")

    def test_put_resending_the_same_stale_platform_is_allowed(self):
        response = self.put({"platform_played": "Sega Saturn", "status": "completed"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(tracking(self.entry)["platform_played"], "Sega Saturn")

    def test_changing_to_an_unlisted_platform_is_a_field_error(self):
        before = tracking(self.entry)
        for send in (self.patch, self.put):
            with self.subTest(method=send.__name__):
                response = send({"platform_played": "Dreamcast"})

                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.json(), {"platform_played": [PLATFORM_NOT_LISTED]})
                self.assertEqual(tracking(self.entry), before)

    def test_changing_to_a_listed_platform_or_blank_is_allowed(self):
        self.assertEqual(self.patch({"platform_played": "PC"}).status_code, 200)
        self.assertEqual(tracking(self.entry)["platform_played"], "PC")
        self.assertEqual(self.patch({"platform_played": ""}).status_code, 200)
        self.assertEqual(tracking(self.entry)["platform_played"], "")
