"""My Saved Games: isolation, order, 10 per page, forgiving pages (stories 7, 46, 60, 63-64, 68)."""

import re
from datetime import timedelta
from unittest import mock

from django.templatetags.static import static
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from games.covers import cover_url
from games.models import GameCategory
from games.queries import EntryQuery

from .factories import make_entry, make_game, make_user
from .test_covers import ImgCollector

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
        self.assertContains(page1, f'href="{URL}?page=2"')
        self.assertNotContains(page1, ">Previous<")
        self.assertContains(page1, "Page 1 of 2")

        page2 = self.client.get(URL, {"page": "2"})
        self.assertEqual(self.titles(page2), [f"Game {n:02d}" for n in range(5, 0, -1)])
        # Page 1 links carry no `page` parameter.
        self.assertContains(page2, f'href="{URL}" hx-get="{URL}" rel="prev"')
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

    def test_rows_link_to_detail_and_show_small_covers_or_the_placeholder(self):
        with_cover = make_entry(self.user, make_game("Celeste", cover_image_id="co3byy"))
        no_cover = make_entry(self.user, make_game("Scuffed Rocket League", cover_image_id=""))

        response = self.client.get(URL)

        for entry in (with_cover, no_cover):
            with self.subTest(game=entry.game.name):
                self.assertContains(
                    response, f'href="{reverse("games:entry_detail", args=[entry.pk])}"'
                )
        parser = ImgCollector()
        parser.feed(response.content.decode())
        covers = {img["alt"]: img for img in parser.imgs if "game-cover" in img.get("class", "")}
        self.assertEqual(covers["Celeste"]["src"], cover_url("co3byy", "small"))
        self.assertEqual(covers["Celeste"]["srcset"], f"{cover_url('co3byy', 'small_2x')} 2x")
        self.assertEqual((covers["Celeste"]["width"], covers["Celeste"]["height"]), ("90", "128"))
        self.assertEqual(
            covers["Scuffed Rocket League"]["src"], static("games/img/cover-placeholder.svg")
        )
        self.assertNotIn("srcset", covers["Scuffed Rocket League"])

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


def hrefs(response, rel=None, testid=None):
    """All href values in the page, or those on links with a given rel/data-testid."""
    html = response.content.decode()
    if rel:
        return re.findall(rf'href="([^"]*)"[^>]*rel="{rel}"', html)
    if testid:
        return re.findall(rf'href="([^"]*)"[^>]*data-testid="{testid}"', html)
    return re.findall(r'href="([^"]*)"', html)


class QueryStateViewTests(TestCase):
    """Stories 47-67 through the website: forgiving parameters, links that keep state,
    page-1 resets, Clear filters, owner isolation and the empty state."""

    def setUp(self):
        self.user = make_user("demo_a")
        self.client.force_login(self.user)
        start = timezone.now() - timedelta(days=30)
        # 12 Horror games at Playing, so the filtered list reaches page 2.
        for n in range(1, 13):
            make_entry(
                self.user,
                make_game(f"Horror {n:02d}", themes=[(19, "Horror")]),
                status="playing",
                created_at=start + timedelta(hours=n),
            )
        make_entry(self.user, make_game("Portal 2", themes=[(27, "Comedy")]), status="completed")
        self.state = {"q": "horror", "status": "playing", "theme": "19", "sort": "title"}
        self.state_qs = "q=horror&amp;status=playing&amp;theme=19&amp;sort=title"

    def test_pager_links_keep_search_filters_and_sort(self):
        page1 = self.client.get(URL, self.state)
        self.assertEqual(hrefs(page1, rel="next"), [f"{URL}?{self.state_qs}&amp;page=2"])

        page2 = self.client.get(URL, {**self.state, "page": "2"})
        self.assertEqual(hrefs(page2, rel="prev"), [f"{URL}?{self.state_qs}"])
        self.assertEqual(page2.context["page_obj"].number, 2)
        self.assertEqual(len(page2.context["page_obj"]), 2)

    def test_the_controls_form_has_no_page_field_so_any_change_returns_to_page_1(self):
        response = self.client.get(URL, {**self.state, "page": "2"})
        form = re.search(
            r'<form[^>]*data-testid="saved-games-controls".*?</form>',
            response.content.decode(),
            re.S,
        ).group(0)
        self.assertIn(f'action="{URL}"', form)
        self.assertIn('method="get"', form)
        self.assertNotIn('name="page"', form)

    def test_clear_filters_keeps_search_and_sort_and_returns_to_page_1(self):
        response = self.client.get(URL, {**self.state, "favorite": "1", "page": "2"})
        self.assertEqual(
            hrefs(response, testid="clear-filters"), [f"{URL}?q=horror&amp;sort=title"]
        )

    def test_no_clear_filters_link_without_filters(self):
        response = self.client.get(URL, {"q": "horror", "sort": "title"})
        self.assertNotContains(response, 'data-testid="clear-filters"')

    def test_detail_links_carry_the_list_state_and_page(self):
        response = self.client.get(URL, {**self.state, "page": "2"})
        detail = reverse("games:entry_detail", args=[response.context["page_obj"][0].pk])
        self.assertIn(f"{detail}?{self.state_qs}&amp;page=2", hrefs(response))

    def test_bad_values_are_ignored_and_never_echoed(self):
        response = self.client.get(
            URL, {"sort": "bogus<script>", "theme": "abc", "status": "nope", "page": "0"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["query"], EntryQuery())
        self.assertEqual(response.context["page_obj"].number, 1)
        self.assertEqual(len(response.context["page_obj"]), 10)
        self.assertNotContains(response, "bogus")
        self.assertNotContains(response, "<script>")

    def test_a_page_past_the_end_shows_the_last_filtered_page(self):
        response = self.client.get(URL, {**self.state, "page": "99"})
        self.assertEqual(response.context["page_obj"].number, 2)

    def test_empty_state_when_nothing_matches(self):
        response = self.client.get(URL, {"q": "no such game anywhere", "theme": "19"})
        self.assertContains(response, "No saved games match your search and filters.")
        self.assertNotContains(response, 'data-testid="entry-row"')
        # The controls stay, so the search can be changed, and Clear filters is offered.
        self.assertContains(response, 'value="no such game anywhere"')
        self.assertEqual(
            hrefs(response, testid="clear-filters"), [f"{URL}?q=no+such+game+anywhere"]
        )

    def test_sort_label_in_the_summary_matches_the_sort(self):
        response = self.client.get(URL, {"sort": "hours"})
        self.assertContains(response, "sorted by Hours Played (Most First)")


class QueryStateIsolationTests(TestCase):
    """Stories 54, 66 and the PRD owner-isolation criteria for the list."""

    def setUp(self):
        self.user_a = make_user("demo_a")
        self.user_b = make_user("demo_b")
        make_entry(
            self.user_a,
            make_game("Resident Evil 2", themes=[(19, "Horror"), (21, "Survival")]),
            notes="Licker in the police station hallway still gets me.",
        )
        make_entry(self.user_b, make_game("Portal 2", themes=[(27, "Comedy")]))
        self.client.force_login(self.user_b)

    def test_user_b_theme_dropdown_has_no_horror_or_survival(self):
        response = self.client.get(URL)
        self.assertContains(response, '<option value="27">Comedy</option>', html=True)
        self.assertNotContains(response, "Horror")
        self.assertNotContains(response, "Survival")

    def test_a_theme_id_from_user_a_games_is_ignored_for_user_b(self):
        response = self.client.get(URL, {"theme": "19"})
        self.assertIsNone(response.context["query"].theme)
        self.assertContains(response, "Portal 2")
        self.assertNotContains(response, 'data-testid="clear-filters"')

    def test_notes_only_in_user_a_entries_find_nothing_for_user_b(self):
        response = self.client.get(URL, {"q": "Licker"})
        self.assertContains(response, "No saved games match your search and filters.")
        self.assertNotContains(response, "Resident Evil 2")
