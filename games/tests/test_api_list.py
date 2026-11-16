"""Listing entries through the API (`GET /api/entries/`) with strict query parameters.

The website parses the same parameters forgivingly (`parse_entry_query`); the API
rejects bad values instead. No test here contacts IGDB.
"""

from django.urls import reverse
from rest_framework.test import APITestCase

from games.models import Entry
from games.tests.factories import make_entry, make_game, make_user

LIST_URL = reverse("api-entry-list")


class StrictListParameterTests(APITestCase):
    def setUp(self):
        self.user = make_user("lister")
        self.client.force_authenticate(self.user)
        horror = make_game(
            "Alan Wake 2", platforms=["PC", "PlayStation 5"], themes=[(19, "Horror")]
        )
        self.alan = make_entry(
            self.user,
            horror,
            status=Entry.Status.PLAYING,
            favorite=True,
            platform_played="PC",
        )
        make_entry(
            self.user,
            make_game("Balatro", platforms=["PC"]),
            status=Entry.Status.COMPLETED,
            platform_played="PC",
        )

        # Another user's entry: its theme and platform played are on none of my games.
        other = make_user("someone_else")
        make_entry(
            other,
            make_game("Starfield", platforms=["Xbox Series X|S"], themes=[(18, "Science fiction")]),
            platform_played="Xbox Series X|S",
        )

    def test_invalid_values_are_400_under_their_parameter(self):
        cases = [
            ("status", "finished"),
            ("platform", "Sega Saturn"),  # not a Platform Played on my entries
            ("platform", "Xbox Series X|S"),  # only another user's Platform Played
            ("favorite", "maybe"),
            ("sort", "bogus"),
            ("theme", "horror"),  # malformed: not an IGDB theme ID
            ("theme", "-19"),
            ("theme", "18"),  # only on another user's saved games
        ]
        for name, value in cases:
            with self.subTest(name=name, value=value):
                response = self.client.get(LIST_URL, {name: value})

                self.assertEqual(response.status_code, 400)
                body = response.json()
                self.assertEqual(list(body), [name])
                self.assertIsInstance(body[name], list)
                self.assertTrue(body[name] and all(isinstance(m, str) for m in body[name]))

    def test_bad_or_out_of_range_page_is_404(self):
        for page in ["abc", "1.5", "last", "0", "-1", "2", "99"]:
            with self.subTest(page=page):
                response = self.client.get(LIST_URL, {"page": page})

                self.assertEqual(response.status_code, 404)

    def test_valid_filtered_query_returns_only_matching_entries(self):
        response = self.client.get(
            LIST_URL,
            {
                "status": "playing",
                "platform": "PC",
                "favorite": "true",
                "theme": "19",
                "sort": "title",
                "page": "1",
            },
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["count"], 1)
        self.assertIsNone(body["next"])
        self.assertIsNone(body["previous"])
        self.assertEqual([entry["id"] for entry in body["results"]], [self.alan.pk])


def result_ids(response) -> list[int]:
    return [entry["id"] for entry in response.json()["results"]]


class ApiSearchFallbackTests(APITestCase):
    """`q` reuses the website's Roman-numeral fallback (`resolve_saved_search`)."""

    def setUp(self):
        self.user = make_user("searcher")
        self.client.force_authenticate(self.user)
        self.other = make_user("other_searcher")

    def test_roman_numeral_form_is_tried_when_typed_term_matches_nothing(self):
        dark_souls = make_entry(self.user, make_game("Dark Souls III"))
        make_entry(self.user, make_game("Elden Ring"))

        response = self.client.get(LIST_URL, {"q": "Dark Souls 3"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["count"], 1)
        self.assertEqual(result_ids(response), [dark_souls.pk])

    def test_typed_term_takes_priority_when_it_matches(self):
        make_entry(self.user, make_game("Dark Souls III"))
        typed_match = make_entry(
            self.user, make_game("Elden Ring"), notes="Easier than Dark Souls 3 for me."
        )

        response = self.client.get(LIST_URL, {"q": "Dark Souls 3"})

        self.assertEqual(response.json()["count"], 1)
        self.assertEqual(result_ids(response), [typed_match.pk])

    def test_fallback_and_search_never_reach_another_users_entries(self):
        mine = make_entry(self.user, make_game("Hades"))
        make_entry(self.other, make_game("Dark Souls III"), notes="secret-phrase-only-b")

        for q in ["Dark Souls 3", "Dark Souls III", "secret-phrase-only-b"]:
            with self.subTest(q=q):
                response = self.client.get(LIST_URL, {"q": q})

                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["count"], 0)
                self.assertNotIn(mine.pk, result_ids(response))
