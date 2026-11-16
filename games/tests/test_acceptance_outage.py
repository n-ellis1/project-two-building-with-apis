"""Phase 12 acceptance sweep: browsing saved games during an IGDB outage.

The real IGDB client runs, with HTTP failing in each mode the PRD names:
unreachable, timeout, rate limit, and credentials missing. In every mode, all
saved-games features keep working from SQLite, and the IGDB features show the
fixed message with the My Saved Games link. The same test methods run once per
mode (one subclass each).

No test here contacts IGDB or Twitch: `requests.post` is replaced for every test.
"""

import re
from datetime import date, timedelta
from decimal import Decimal
from html import unescape
from unittest import mock

import requests
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from games import igdb
from games.models import Entry, Game
from games.queries import SORT_LABELS
from games.tests.factories import csrf_client, make_entry, make_game, make_user
from games.tests.test_igdb_client import FakeResponse, token_response
from games.tests.test_save_service import row_counts

SAVED_GAMES_URL = reverse("games:saved_games")
API_LIST_URL = reverse("api-entry-list")
NEW_GAME_IGDB_ID = 26_758  # not stored anywhere in the test database
FAKE_CREDENTIALS = {"IGDB_CLIENT_ID": "fake-client-id", "IGDB_CLIENT_SECRET": "fake-client-secret"}


def ids(page) -> list[int]:
    return [entry.pk for entry in page]


def message_texts(response) -> list[tuple[str, bool]]:
    """Each flash message's text, and whether it carries the My Saved Games link."""
    found = []
    for body in re.findall(
        r'<div class="alert[^"]*"[^>]*data-testid="message">(.*?)</div>',
        response.content.decode(),
        re.S,
    ):
        text = unescape(re.sub(r"<a .*?</a>", "", body, flags=re.S))
        found.append((" ".join(text.split()), f'href="{SAVED_GAMES_URL}"' in body))
    return found


class OutageSweep:
    """The checks. Each subclass sets `code` and installs its failure in `fail_igdb()`."""

    code = ""

    def fail_igdb(self):
        raise NotImplementedError

    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        self.http = self.fail_igdb()

        self.user = make_user("outage_sweep")
        self.other = make_user("outage_other")
        today = timezone.localdate()
        # Twelve entries (two pages), each found by one distinctive value.
        self.entries = {}
        for n in range(12):
            game = make_game(
                f"Game {n:02d}",
                igdb_id=200_000 + n,
                platforms=[f"Console {n % 3}"],
                genres=[f"Genre {n % 4}"],
                themes=[(19, "Horror")] if n % 2 == 0 else [(21, "Survival")],
                summary=f"summary-word-{n}",
                first_release_date=date(2000 + n, 1, 1),
                game_category=2 if n == 0 else 0,
                cover_image_id=f"co{n}",
            )
            self.entries[n] = make_entry(
                self.user,
                game,
                status=Entry.Status.PLAYING if n < 3 else Entry.Status.WANT_TO_PLAY,
                favorite=n in (4, 5),
                rating=n % 10 + 1 if n != 11 else None,
                notes=f"notes-word-{n}",
                platform_played=f"Console {n % 3}",
                start_date=today - timedelta(days=30),
                hours_played=Decimal(n) if n != 10 else None,
            )
        # A game another user saved, stored locally: saving it needs no IGDB call.
        self.stored = make_game("Stored By Other", igdb_id=300_001, platforms=["PC"])
        make_entry(self.other, self.stored)
        self.client.force_login(self.user)

    # --- My Saved Games, detail, edit (SQLite only) ---------------------------------

    def test_my_saved_games_shows_titles_platforms_badges_and_tracking_data(self):
        response = self.client.get(SAVED_GAMES_URL, {"sort": "title"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["page_obj"].paginator.count, 12)
        for text in ("Game 00", "Console 0", "Expansion", "Playing", "★ Favorite"):
            self.assertContains(response, text)

    def test_search_across_every_field(self):
        for term, n in (
            ("game 07", 7),
            ("summary-word-8", 8),
            ("notes-word-9", 9),
        ):
            with self.subTest(term=term):
                page = self.client.get(SAVED_GAMES_URL, {"q": term}).context["page_obj"]
                self.assertEqual(ids(page), [self.entries[n].pk])
        for term, expected in (
            ("console 1", {1, 4, 7, 10}),
            ("genre 3", {3, 7, 11}),
            ("survival", {1, 3, 5, 7, 9, 11}),
        ):
            with self.subTest(term=term):
                page = self.client.get(SAVED_GAMES_URL, {"q": term}).context["page_obj"]
                self.assertEqual(set(ids(page)), {self.entries[n].pk for n in expected})

    def test_each_of_the_four_filters(self):
        for params, expected in (
            ({"status": "playing"}, {0, 1, 2}),
            ({"platform": "Console 2"}, {2, 5, 8, 11}),
            ({"favorite": "1"}, {4, 5}),
            ({"theme": "21"}, {1, 3, 5, 7, 9, 11}),
        ):
            with self.subTest(params=params):
                page = self.client.get(SAVED_GAMES_URL, params).context["page_obj"]
                self.assertEqual(set(ids(page)), {self.entries[n].pk for n in expected})

    def test_all_seven_sorts_and_pagination(self):
        for sort in SORT_LABELS:
            with self.subTest(sort=sort):
                first = self.client.get(SAVED_GAMES_URL, {"sort": sort})
                second = self.client.get(SAVED_GAMES_URL, {"sort": sort, "page": 2})

                self.assertEqual(first.status_code, 200)
                self.assertEqual(len(first.context["page_obj"]), 10)
                self.assertEqual(len(second.context["page_obj"]), 2)
                both = ids(first.context["page_obj"]) + ids(second.context["page_obj"])
                self.assertEqual(sorted(both), sorted(e.pk for e in self.entries.values()))
        titles = [
            entry.game.name
            for entry in self.client.get(SAVED_GAMES_URL, {"sort": "title_desc"}).context[
                "page_obj"
            ]
        ]
        self.assertEqual(titles[0], "Game 11")

    def test_detail_and_edit_pages_load_and_save(self):
        entry = self.entries[0]
        detail = self.client.get(reverse("games:entry_detail", args=[entry.pk]))
        self.assertEqual(detail.status_code, 200)
        for text in ("Game 00", "Console 0", "notes-word-0", "data-cover-placeholder"):
            self.assertContains(detail, text)

        edit_url = reverse("games:entry_edit", args=[entry.pk])
        self.assertEqual(self.client.get(edit_url).status_code, 200)
        response = self.client.post(
            edit_url,
            {
                "status": "completed",
                "rating": "8",
                "platform_played": "Console 0",
                "start_date": "2026-01-01",
                "finish_date": "2026-02-01",
                "hours_played": "20",
                "notes": "finished offline",
            },
        )
        self.assertRedirects(response, reverse("games:entry_detail", args=[entry.pk]))
        entry.refresh_from_db()
        self.assertEqual((entry.status, entry.notes), ("completed", "finished offline"))

    # --- API -------------------------------------------------------------------------

    def test_api_list_and_retrieve(self):
        api = APIClient()
        api.force_authenticate(self.user)

        listing = api.get(API_LIST_URL, {"q": "notes-word-3", "sort": "title"})
        detail = api.get(reverse("api-entry-detail", args=[self.entries[3].pk]))

        self.assertEqual(listing.status_code, 200)
        self.assertEqual([e["id"] for e in listing.json()["results"]], [self.entries[3].pk])
        self.assertEqual(api.get(API_LIST_URL).json()["count"], 12)
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.json()["game"]["name"], "Game 03")

    def test_api_saves_a_stored_game_and_refuses_a_new_one_with_503(self):
        api = APIClient()
        api.force_authenticate(self.user)

        stored = api.post(API_LIST_URL, {"igdb_id": self.stored.igdb_id}, format="json")
        before = row_counts()
        new = api.post(API_LIST_URL, {"igdb_id": NEW_GAME_IGDB_ID}, format="json")

        self.assertEqual(stored.status_code, 201)
        self.assertEqual(new.status_code, 503)
        self.assertEqual(new.json(), {"detail": igdb.MESSAGES[self.code], "code": self.code})
        self.assertEqual(row_counts(), before)

    # --- IGDB features: fixed message with the My Saved Games link -------------------

    def test_igdb_search_shows_the_message_with_the_link_and_keeps_the_text(self):
        response = self.client.get(reverse("games:search"), {"q": "hollow knight"})

        self.assertEqual(response.status_code, 200)
        error = re.search(
            r'data-testid="search-error">(.*?)</div>', response.content.decode(), re.S
        ).group(1)
        self.assertIn(igdb.MESSAGES[self.code], unescape(error))
        self.assertIn(f'href="{SAVED_GAMES_URL}"', error)
        self.assertContains(response, 'value="hollow knight"')
        self.assertNotContains(response, "No matches.")

    def test_refresh_shows_the_message_with_the_link_and_changes_nothing(self):
        entry = self.entries[0]
        game_before = Game.objects.filter(pk=entry.game.pk).values().get()
        client, token = csrf_client(self.user, SAVED_GAMES_URL)

        response = client.post(
            reverse("games:entry_refresh", args=[entry.pk]),
            {"csrfmiddlewaretoken": token},
            follow=True,
        )

        self.assertIn((igdb.MESSAGES[self.code], True), message_texts(response))
        self.assertEqual(Game.objects.filter(pk=entry.game.pk).values().get(), game_before)

    def test_website_saves_a_stored_game_and_a_new_game_saves_nothing(self):
        client, token = csrf_client(self.user, SAVED_GAMES_URL)
        save_url = reverse("games:search_save")

        stored = client.post(
            save_url, {"csrfmiddlewaretoken": token, "igdb_id": self.stored.igdb_id}
        )
        entry = Entry.objects.get(owner=self.user, game=self.stored)
        self.assertRedirects(stored, reverse("games:entry_edit", args=[entry.pk]))

        before = row_counts()
        new = client.post(
            save_url,
            {"csrfmiddlewaretoken": token, "igdb_id": NEW_GAME_IGDB_ID, "q": "dark souls"},
            follow=True,
        )
        self.assertEqual(new.redirect_chain[0][0], "/search/?q=dark+souls")
        self.assertIn((igdb.MESSAGES[self.code], True), message_texts(new))
        self.assertEqual(row_counts(), before)


def failing_http(igdb_answer):
    """`requests.post` for a working Twitch and a failing IGDB (`igdb_answer`)."""

    def post(url, **kwargs):
        if url == igdb.TOKEN_URL:
            return token_response("fake-token-not-real")
        if isinstance(igdb_answer, BaseException):
            raise igdb_answer
        return igdb_answer

    return post


@override_settings(**FAKE_CREDENTIALS)
class UnreachableOutageTests(OutageSweep, TestCase):
    """Wi-Fi off: every request, Twitch included, fails to connect."""

    code = "igdb_unreachable"

    def fail_igdb(self):
        patcher = mock.patch(
            "games.igdb.requests.post", side_effect=requests.ConnectionError("network down")
        )
        self.addCleanup(patcher.stop)
        return patcher.start()


@override_settings(**FAKE_CREDENTIALS)
class TimeoutOutageTests(OutageSweep, TestCase):
    code = "igdb_timeout"

    def fail_igdb(self):
        patcher = mock.patch(
            "games.igdb.requests.post", side_effect=failing_http(requests.Timeout("slow"))
        )
        self.addCleanup(patcher.stop)
        return patcher.start()


@override_settings(**FAKE_CREDENTIALS)
class RateLimitedOutageTests(OutageSweep, TestCase):
    code = "igdb_rate_limited"

    def fail_igdb(self):
        patcher = mock.patch(
            "games.igdb.requests.post", side_effect=failing_http(FakeResponse(429))
        )
        self.addCleanup(patcher.stop)
        return patcher.start()


@override_settings(IGDB_CLIENT_ID="", IGDB_CLIENT_SECRET="")
class MissingCredentialsOutageTests(OutageSweep, TestCase):
    """No IGDB credentials: Django starts, and no request is ever sent."""

    code = "igdb_misconfigured"

    def fail_igdb(self):
        patcher = mock.patch(
            "games.igdb.requests.post", side_effect=AssertionError("no request expected")
        )
        self.addCleanup(patcher.stop)
        return patcher.start()

    def tearDown(self):
        self.http.assert_not_called()
