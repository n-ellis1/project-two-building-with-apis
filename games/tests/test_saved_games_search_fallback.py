"""My Saved Games: the Roman-numeral search fallback (B3). SQLite only, never IGDB."""

import re
from html import unescape
from unittest import mock

from django.test import TestCase
from django.urls import reverse

from games.models import Entry
from games.queries import EntryQuery, resolve_saved_search
from games.tests.factories import make_entry, make_game, make_user

LIST_URL = reverse("games:saved_games")


def row_titles(response):
    return re.findall(
        r'<a class="fw-semibold" href="[^"]*">([^<]*)</a>', unescape(response.content.decode())
    )


def notice(response):
    match = re.search(
        r'data-testid="search-fallback">(.*?)</p>', response.content.decode(), re.DOTALL
    )
    return unescape(match.group(1)) if match else None


class SavedGamesSearchFallbackTests(TestCase):
    def setUp(self):
        self.me = make_user("me")
        self.other = make_user("other")
        self.client.force_login(self.me)
        patcher = mock.patch("games.igdb.search_games", side_effect=AssertionError("no IGDB"))
        patcher.start()
        self.addCleanup(patcher.stop)

    def get(self, **params):
        response = self.client.get(LIST_URL, params)
        self.assertEqual(response.status_code, 200)
        return response

    def test_a_match_for_the_typed_term_takes_priority_over_the_roman_numeral(self):
        make_entry(self.me, make_game("Dark Souls III"))
        make_entry(self.me, make_game("Bloodborne"), notes="Easier than Dark Souls 3 for me")

        response = self.get(q="Dark Souls 3")

        self.assertEqual(row_titles(response), ["Bloodborne"])
        self.assertIsNone(notice(response))

    def test_no_match_for_the_typed_term_falls_back_to_the_roman_numeral(self):
        make_entry(self.me, make_game("Dark Souls III"))
        make_entry(self.me, make_game("Dark Souls II"))

        response = self.get(q="dark souls 3")

        self.assertEqual(row_titles(response), ["Dark Souls III"])
        self.assertEqual(
            " ".join(notice(response).split()),
            "No matches for “dark souls 3”. Showing results for “dark souls III”.",
        )
        # The URL, the search box and links keep what was typed.
        self.assertContains(response, 'name="q" value="dark souls 3"')
        detail = reverse(
            "games:entry_detail",
            args=[Entry.objects.get(owner=self.me, game__name="Dark Souls III").pk],
        )
        self.assertContains(response, f'href="{detail}?q=dark+souls+3"')

    def test_another_users_entries_never_decide_or_appear_in_the_fallback(self):
        # Only the other user has a typed-term match (their notes) and a Roman-numeral
        # match; neither may affect my list.
        their_game = make_game("Dark Souls III")
        their_entry = make_entry(self.other, their_game, notes="dark souls 3 speedrun")
        mine = make_entry(self.me, make_game("Dark Souls III: The Ringed City"))

        response = self.get(q="dark souls 3")

        self.assertEqual(row_titles(response), ["Dark Souls III: The Ringed City"])
        self.assertIsNotNone(notice(response))
        self.assertNotContains(response, reverse("games:entry_detail", args=[their_entry.pk]))
        self.assertContains(response, reverse("games:entry_detail", args=[mine.pk]))

        # And with nothing of mine matching either term, nothing of theirs shows.
        make_entry(self.me, make_game("Celeste"))
        mine.delete()
        response = self.get(q="dark souls 3")
        self.assertContains(response, "No saved games match your search and filters.")
        self.assertNotContains(response, "speedrun")
        self.assertNotContains(response, reverse("games:entry_detail", args=[their_entry.pk]))

    def test_the_fallback_is_decided_under_the_active_filters(self):
        make_entry(self.me, make_game("Bloodborne"), notes="dark souls 3 vibes", status="completed")
        make_entry(self.me, make_game("Dark Souls III"), status="playing")

        playing = self.get(q="dark souls 3", status="playing")
        self.assertEqual(row_titles(playing), ["Dark Souls III"])
        self.assertIsNotNone(notice(playing))
        self.assertContains(playing, 'value="playing" selected')

        completed = self.get(q="dark souls 3", status="completed")
        self.assertEqual(row_titles(completed), ["Bloodborne"])
        self.assertIsNone(notice(completed))

    def test_paging_and_sorting_keep_the_typed_term_and_the_same_search_on_every_page(self):
        for n in range(1, 13):
            make_entry(self.me, make_game(f"Saga III Part {n:02d}"))
        make_entry(self.me, make_game("Other Game"))

        page1 = self.get(q="saga 3", sort="title_desc")
        self.assertEqual(len(row_titles(page1)), 10)
        self.assertEqual(row_titles(page1)[0], "Saga III Part 12")
        self.assertIsNotNone(notice(page1))
        next_link = re.search(r'href="([^"]*)"[^>]*rel="next"', page1.content.decode()).group(1)
        self.assertEqual(unescape(next_link), f"{LIST_URL}?q=saga+3&sort=title_desc&page=2")

        page2 = self.get(q="saga 3", sort="title_desc", page="2")
        self.assertEqual(row_titles(page2), ["Saga III Part 02", "Saga III Part 01"])
        self.assertIsNotNone(notice(page2))

        # Out of range: the last page of the same (fallback) search, not a different one.
        past_end = self.get(q="saga 3", sort="title_desc", page="99")
        self.assertEqual(row_titles(past_end), ["Saga III Part 02", "Saga III Part 01"])

    def test_an_htmx_swap_pushes_the_typed_term(self):
        make_entry(self.me, make_game("Dark Souls III"))
        response = self.client.get(LIST_URL, {"q": "dark souls 3"}, headers={"HX-Request": "true"})
        self.assertEqual(response["HX-Push-Url"], f"{LIST_URL}?q=dark+souls+3")
        self.assertIsNotNone(notice(response))

    def test_neither_term_matching_shows_the_normal_empty_state(self):
        make_entry(self.me, make_game("Celeste"))
        response = self.get(q="Qwxz Saga 4")
        self.assertContains(response, "No saved games match your search and filters.")
        self.assertIsNone(notice(response))

    def test_resolve_saved_search_only_switches_terms_with_a_final_2_to_9(self):
        make_entry(self.me, make_game("Final Fantasy X"))
        make_entry(self.me, make_game("Halo I"))
        for q in ("Final Fantasy 10", "Halo 1", "zelda", ""):
            with self.subTest(q=q):
                query = EntryQuery(q=q)
                self.assertEqual(resolve_saved_search(self.me, query), query)
