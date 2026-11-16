"""Retrieving and deleting entries through the API, and the response shape.
No test here contacts IGDB."""

from datetime import date

from django.urls import reverse
from rest_framework.test import APITestCase

from games.covers import cover_url
from games.models import Entry, Game, GameCategory
from games.tests.factories import make_entry, make_game, make_user

LIST_URL = reverse("api-entry-list")


def detail_url(entry_id) -> str:
    return reverse("api-entry-detail", args=[entry_id])


class RetrieveShapeTests(APITestCase):
    def setUp(self):
        self.user = make_user("reader")
        self.client.force_authenticate(self.user)
        self.game = make_game(
            "The Witcher 3: Wild Hunt - Blood and Wine",
            igdb_id=12503,
            platforms=["PC (Microsoft Windows)", "PlayStation 4"],
            genres=["Role-playing (RPG)"],
            themes=[(1, "Action"), (17, "Fantasy")],
            first_release_date=date(2016, 5, 31),
            game_category=GameCategory.EXPANSION,
            cover_image_id="co1r7f",
            igdb_url="https://www.igdb.com/games/the-witcher-3-wild-hunt-blood-and-wine",
        )
        self.entry = make_entry(self.user, self.game, rating=10, notes="Toussaint!")

    def test_entry_has_tracking_fields_and_a_nested_read_only_game(self):
        response = self.client.get(detail_url(self.entry.pk))

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(
            set(body),
            {
                "id",
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
            },
        )
        self.assertEqual(
            (body["id"], body["rating"], body["notes"]), (self.entry.pk, 10, "Toussaint!")
        )
        self.assertEqual(
            body["game"],
            {
                "igdb_id": 12503,
                "name": "The Witcher 3: Wild Hunt - Blood and Wine",
                "first_release_date": "2016-05-31",
                "game_category": 2,
                "game_category_label": "Expansion",
                "platforms": ["PC (Microsoft Windows)", "PlayStation 4"],
                "genres": ["Role-playing (RPG)"],
                "themes": ["Action", "Fantasy"],
                "cover_url": cover_url("co1r7f", "large"),
                "igdb_url": "https://www.igdb.com/games/the-witcher-3-wild-hunt-blood-and-wine",
            },
        )

    def test_game_without_cover_or_category_has_nulls(self):
        game = make_game("Mystery", cover_image_id="", game_category=None)
        entry = make_entry(self.user, game)

        game_body = self.client.get(detail_url(entry.pk)).json()["game"]

        self.assertIsNone(game_body["cover_url"])
        self.assertIsNone(game_body["game_category"])
        self.assertEqual(game_body["game_category_label"], "")

    def test_list_pages_hold_ten_with_next_and_previous_links(self):
        for number in range(11):
            make_entry(self.user, make_game(f"Game {number:02}"))

        first = self.client.get(LIST_URL, {"sort": "title"}).json()
        second = self.client.get(LIST_URL, {"sort": "title", "page": 2}).json()

        self.assertEqual(first["count"], 12)
        self.assertEqual(len(first["results"]), 10)
        self.assertIsNone(first["previous"])
        self.assertIn("page=2", first["next"])
        self.assertIn("sort=title", first["next"])
        self.assertEqual(len(second["results"]), 2)
        self.assertIsNone(second["next"])
        self.assertIsNotNone(second["previous"])
        ids = [e["id"] for e in first["results"] + second["results"]]
        self.assertEqual(len(set(ids)), 12)


class DeleteTests(APITestCase):
    def test_delete_returns_204_and_keeps_the_shared_game(self):
        user, other = make_user("deleter"), make_user("other_owner")
        game = make_game("Shared Game")
        mine = make_entry(user, game)
        theirs = make_entry(other, game, notes="theirs")
        self.client.force_authenticate(user)

        response = self.client.delete(detail_url(mine.pk))

        self.assertEqual(response.status_code, 204)
        self.assertFalse(Entry.objects.filter(pk=mine.pk).exists())
        self.assertTrue(Game.objects.filter(pk=game.pk).exists())
        self.assertEqual(Entry.objects.get(pk=theirs.pk).notes, "theirs")
        self.assertEqual(self.client.get(detail_url(mine.pk)).status_code, 404)

    def test_deleting_the_last_entry_keeps_the_game(self):
        user = make_user("last_one")
        game = make_game("Only Mine")
        entry = make_entry(user, game)
        self.client.force_authenticate(user)

        self.assertEqual(self.client.delete(detail_url(entry.pk)).status_code, 204)
        self.assertTrue(Game.objects.filter(pk=game.pk).exists())
