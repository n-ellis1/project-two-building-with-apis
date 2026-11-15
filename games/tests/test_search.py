"""The IGDB search page, with the IGDB client mocked at its module boundary.

No test here contacts Twitch or IGDB.
"""

import re
from datetime import date
from html import escape, unescape
from unittest import mock

from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from games import igdb
from games.tests.factories import make_entry, make_game, make_user
from games.tests.test_igdb_client import (
    FAKE_CLIENT_ID,
    FAKE_SECRET,
    FAKE_TOKEN_1,
    FakeHttp,
    FakeResponse,
    token_response,
)

SEARCH_URL = reverse("games:search")


def fake_games(count, start=1):
    return [igdb.IgdbGame(igdb_id=n, name=f"Result {n}") for n in range(start, start + count)]


def shown_ids(response):
    return [int(n) for n in re.findall(r'data-igdb-id="(\d+)"', response.content.decode())]


def pager_href(response, rel):
    """The href of the pager link with `rel` ("prev" or "next"), or None."""
    match = re.search(
        rf'<a [^>]*href="([^"]*)"[^>]*rel="{rel}"|<a [^>]*rel="{rel}"[^>]*href="([^"]*)"',
        response.content.decode(),
    )
    if not match:
        return None
    return unescape(match.group(1) or match.group(2))


@override_settings(IGDB_CLIENT_ID=FAKE_CLIENT_ID, IGDB_CLIENT_SECRET=FAKE_SECRET)
class SearchQueryBodyTests(SimpleTestCase):
    """TDD cycle 2, client half: what page 2 asks IGDB for."""

    def test_page_2_sends_the_eligibility_clause_limit_11_and_offset_10(self):
        from django.core.cache import cache

        cache.clear()
        self.addCleanup(cache.clear)
        fake = FakeHttp(
            twitch=[token_response(FAKE_TOKEN_1)], igdb_responses=[FakeResponse(200, [])]
        )
        with mock.patch("games.igdb.requests.post", side_effect=fake):
            igdb.search_games("The Witcher 3", 2)

        [body] = fake.igdb_bodies()
        lines = body.decode("utf-8").splitlines()
        self.assertIn('search "The Witcher 3";', lines)
        self.assertIn(
            "where version_parent = null & game_type = (0,1,2,4,6,7,8,9,10,11,12);", lines
        )
        self.assertIn("limit 11;", lines)
        self.assertIn("offset 10;", lines)


class SearchPagerTests(TestCase):
    """TDD cycle 2, page half: 10 shown, Previous on page 2, Next only for an 11th result."""

    def setUp(self):
        self.client.force_login(make_user("searcher"))

    def get_page_2(self, returned):
        with mock.patch("games.igdb.search_games", return_value=returned) as search:
            response = self.client.get(SEARCH_URL, {"q": "the witcher", "page": "2"})
        search.assert_called_once_with("the witcher", 2)
        self.assertEqual(response.status_code, 200)
        return response

    def test_eleven_results_show_ten_with_previous_and_next(self):
        response = self.get_page_2(fake_games(11))

        self.assertEqual(shown_ids(response), list(range(1, 11)))
        self.assertEqual(pager_href(response, "prev"), f"{SEARCH_URL}?q=the+witcher")
        self.assertEqual(pager_href(response, "next"), f"{SEARCH_URL}?q=the+witcher&page=3")

    def test_exactly_ten_results_show_ten_with_previous_and_no_next(self):
        response = self.get_page_2(fake_games(10))

        self.assertEqual(shown_ids(response), list(range(1, 11)))
        self.assertEqual(pager_href(response, "prev"), f"{SEARCH_URL}?q=the+witcher")
        self.assertIsNone(pager_href(response, "next"))


def result_row(response, igdb_id):
    """The HTML of one search result row, found by its IGDB ID."""
    match = re.search(
        rf'<li [^>]*data-igdb-id="{igdb_id}".*?</li>', response.content.decode(), re.DOTALL
    )
    assert match, f"no result row for IGDB ID {igdb_id}"
    return match.group(0)


class SavedLinkTests(TestCase):
    """TDD cycle 3: "Saved" links go to the signed-in user's own entry only."""

    def test_saved_links_point_to_my_entry_and_never_expose_another_users_entry(self):
        me = make_user("me")
        other = make_user("other")
        shared_game = make_game("Shared Game", igdb_id=5001)
        other_only_game = make_game("Other Only Game", igdb_id=5002)
        my_shared_entry = make_entry(me, shared_game)
        other_shared_entry = make_entry(other, shared_game)
        other_only_entry = make_entry(other, other_only_game)

        returned = [
            igdb.IgdbGame(igdb_id=5001, name="Shared Game"),
            igdb.IgdbGame(igdb_id=5002, name="Other Only Game"),
        ]
        self.client.force_login(me)
        with mock.patch("games.igdb.search_games", return_value=returned):
            response = self.client.get(SEARCH_URL, {"q": "game"})
        html = response.content.decode()

        shared_row = result_row(response, 5001)
        self.assertIn('data-testid="saved-link"', shared_row)
        self.assertIn(
            f'href="{reverse("games:entry_detail", args=[my_shared_entry.pk])}"', shared_row
        )
        self.assertIn(">Saved<", shared_row)

        other_only_row = result_row(response, 5002)
        self.assertNotIn('data-testid="saved-link"', other_only_row)
        self.assertNotIn("Saved", other_only_row)

        for entry in (other_shared_entry, other_only_entry):
            self.assertNotIn(reverse("games:entry_detail", args=[entry.pk]), html)

    def test_saved_lookup_is_one_query_and_unsaved_results_get_a_save_form(self):
        me = make_user("me")
        make_entry(me, make_game("Mine", igdb_id=6001))
        returned = fake_games(10, start=6001)
        self.client.force_login(me)
        with mock.patch("games.igdb.search_games", return_value=returned):
            self.client.get(SEARCH_URL, {"q": "warm up"})  # session and user queries
            with self.assertNumQueries(3):  # session, user, saved entries
                response = self.client.get(SEARCH_URL, {"q": "game", "page": "2"})

        self.assertContains(response, 'data-testid="saved-link"', count=1)
        self.assertContains(response, 'data-testid="save-form"', count=9)
        self.assertNotIn('data-testid="save-form"', result_row(response, 6001))
        row = result_row(response, 6002)
        self.assertIn(f'action="{reverse("games:search_save")}"', row)
        self.assertIn('method="post"', row)
        self.assertIn("csrfmiddlewaretoken", row)
        self.assertIn('name="igdb_id" value="6002"', row)
        self.assertIn('name="q" value="game"', row)
        self.assertIn('name="page" value="2"', row)
        self.assertNotIn("hx-post", row)  # an ordinary form, so it can redirect to edit


class SearchSetupMixin:
    def setUp(self):
        self.user = make_user("searcher")
        self.client.force_login(self.user)

    def get(self, params, returned=(), headers=None, **patch):
        options = (
            {"side_effect": patch["side_effect"]}
            if "side_effect" in patch
            else {"return_value": list(returned)}
        )
        with mock.patch("games.igdb.search_games", **options) as search:
            response = self.client.get(SEARCH_URL, params, headers=headers or {})
        self.assertEqual(response.status_code, 200)
        return response, search


class SearchPageStateTests(SearchSetupMixin, TestCase):
    def test_signed_out_visitors_are_redirected_and_igdb_is_never_called(self):
        self.client.logout()
        with mock.patch("games.igdb.search_games") as search:
            response = self.client.get(SEARCH_URL, {"q": "zelda"})
        self.assertRedirects(response, f"{reverse('login')}?next=/search/%3Fq%3Dzelda")
        search.assert_not_called()

    def test_a_blank_search_shows_the_form_and_makes_no_igdb_call(self):
        for q in ("", "   "):
            with self.subTest(q=q):
                response, search = self.get({"q": q})
                search.assert_not_called()
                self.assertContains(response, 'id="igdb-q"')
                self.assertNotContains(response, "No matches.")
                self.assertNotContains(response, "No more results")

    def test_search_text_is_trimmed_collapsed_and_kept_in_the_box(self):
        response, search = self.get({"q": "  the   witcher  3 "}, fake_games(1))
        search.assert_called_once_with("the witcher 3", 1)
        self.assertContains(response, 'name="q" value="the witcher 3"')

    def test_overlong_search_text_is_cut_to_200_characters(self):
        _, search = self.get({"q": "x" * 500})
        search.assert_called_once_with("x" * 200, 1)

    def test_a_bad_page_counts_as_page_1(self):
        for page in ("", "abc", "0", "-1", "2.5", "1e3"):
            with self.subTest(page=page):
                response, search = self.get({"q": "zelda", "page": page}, fake_games(3))
                search.assert_called_once_with("zelda", 1)
                self.assertIsNone(pager_href(response, "prev"))

    def test_page_1_with_more_results_has_next_but_no_previous(self):
        response, _ = self.get({"q": "zelda"}, fake_games(11))
        self.assertIsNone(pager_href(response, "prev"))
        self.assertEqual(pager_href(response, "next"), f"{SEARCH_URL}?q=zelda&page=2")

    def test_a_single_page_of_results_has_no_pager(self):
        response, _ = self.get({"q": "zelda"}, fake_games(4))
        self.assertEqual(shown_ids(response), [1, 2, 3, 4])
        self.assertNotContains(response, 'aria-label="Search result pages"')

    def test_an_empty_page_1_says_no_matches(self):
        response, _ = self.get({"q": "qwxzv nonsense"})
        self.assertContains(response, "No matches.")
        self.assertNotContains(response, "No more results")
        self.assertNotContains(response, 'aria-label="Search result pages"')

    def test_an_empty_later_page_says_no_more_results_with_a_page_1_link(self):
        response, _ = self.get({"q": "the witcher", "page": "40"})
        self.assertContains(response, "No more results")
        self.assertContains(response, f'href="{SEARCH_URL}?q=the+witcher"')
        self.assertNotContains(response, "No matches.")
        self.assertIsNone(pager_href(response, "prev"))
        self.assertIsNone(pager_href(response, "next"))

    def test_results_show_cover_title_release_date_platforms_and_badge(self):
        returned = [
            igdb.IgdbGame(
                igdb_id=287844,
                name="Resident Evil 2",
                first_release_date=date(1999, 11, 1),
                platforms=("Nintendo 64",),
                game_category=11,
                cover_image_id="co2abc",
            ),
            igdb.IgdbGame(igdb_id=880, name="Resident Evil 2 (main)", game_category=0),
        ]
        response, _ = self.get({"q": "resident evil 2"}, returned)

        port_row, main_row = result_row(response, 287844), result_row(response, 880)
        self.assertIn("t_cover_small/co2abc.jpg", port_row)
        self.assertIn("t_cover_small_2x/co2abc.jpg 2x", port_row)
        self.assertIn('alt="Resident Evil 2"', port_row)
        self.assertIn("Nov 1, 1999", port_row)
        self.assertIn("Nintendo 64", port_row)
        self.assertIn('data-testid="category-badge">Port<', port_row)
        self.assertNotIn("category-badge", main_row)
        self.assertIn("cover-placeholder.svg", main_row)
        self.assertIn("date unknown", main_row)
        self.assertIn("Platforms unknown", main_row)


class SearchErrorTests(SearchSetupMixin, TestCase):
    def test_each_error_shows_its_message_and_saved_games_link_never_an_empty_message(self):
        for code, message in igdb.MESSAGES.items():
            if code in ("igdb_game_not_found", "game_category_excluded"):
                continue  # save errors (Phase 8), never raised by search
            with self.subTest(code):
                response, _ = self.get(
                    {"q": 'the "witcher"', "page": "2"}, side_effect=igdb.IgdbError(code)
                )
                error = re.search(
                    r'data-testid="search-error">(.*?)</div>', response.content.decode(), re.DOTALL
                ).group(1)
                self.assertIn(escape(message), error)
                self.assertIn(f'href="{reverse("games:saved_games")}"', error)
                self.assertContains(response, 'name="q" value="the &quot;witcher&quot;"')
                self.assertNotContains(response, "No matches.")
                self.assertNotContains(response, "No more results")
                self.assertNotContains(response, 'aria-label="Search result pages"')

    def test_the_saved_games_link_works_while_igdb_is_failing(self):
        response, _ = self.get({"q": "zelda"}, side_effect=igdb.IgdbError("igdb_unreachable"))
        self.assertContains(response, "Go to My Saved Games")
        with mock.patch("games.igdb.search_games", side_effect=AssertionError("no IGDB")):
            self.assertEqual(self.client.get(reverse("games:saved_games")).status_code, 200)


@override_settings(IGDB_CLIENT_ID=FAKE_CLIENT_ID, IGDB_CLIENT_SECRET=FAKE_SECRET)
class SearchSecretLeakTests(TestCase):
    """End to end through the real client with HTTP mocked (still no live calls)."""

    def setUp(self):
        from django.core.cache import cache

        cache.clear()
        self.addCleanup(cache.clear)
        self.client.force_login(make_user("searcher"))

    def test_no_secret_or_token_appears_in_any_error_response_or_log(self):
        from games.tests.test_igdb_client import FAKE_TOKEN_2, CaptureLogs, failure_cases

        for label, twitch, igdb_responses, code, _calls in failure_cases():
            with self.subTest(label):
                from django.core.cache import cache

                cache.clear()
                fake = FakeHttp(twitch=twitch, igdb_responses=igdb_responses)
                with (
                    CaptureLogs() as logs,
                    mock.patch("games.igdb.requests.post", side_effect=fake),
                ):
                    response = self.client.get(SEARCH_URL, {"q": "zelda"})
                body = response.content.decode()
                self.assertIn(escape(igdb.MESSAGES[code]), body)
                for secret in (FAKE_SECRET, FAKE_TOKEN_1, FAKE_TOKEN_2):
                    self.assertNotIn(secret, body)
                    self.assertNotIn(secret, str(response.headers))
                    for record in logs.records:
                        self.assertNotIn(secret, record)

    def test_a_successful_search_page_contains_no_secret_or_token(self):
        fake = FakeHttp(
            twitch=[token_response(FAKE_TOKEN_1)],
            igdb_responses=[FakeResponse(200, [{"id": 1, "name": "Zelda"}])],
        )
        with mock.patch("games.igdb.requests.post", side_effect=fake):
            response = self.client.get(SEARCH_URL, {"q": "zelda"})
        self.assertContains(response, "Zelda")
        for secret in (FAKE_CLIENT_ID, FAKE_SECRET, FAKE_TOKEN_1):
            self.assertNotContains(response, secret)


class SearchHtmxTests(SearchSetupMixin, TestCase):
    HTMX = {"HX-Request": "true"}
    RESTORE = {"HX-Request": "true", "HX-History-Restore-Request": "true"}

    def test_an_htmx_pager_request_gets_only_the_region_with_a_clean_push_url(self):
        response, search = self.get({"q": "the witcher", "page": "2"}, fake_games(11), self.HTMX)
        search.assert_called_once_with("the witcher", 2)
        body = response.content.decode()
        self.assertIn('id="search-region"', body)
        self.assertNotIn("<html", body)
        self.assertNotIn('id="igdb-q"', body)
        self.assertEqual(shown_ids(response), list(range(1, 11)))
        self.assertEqual(response["HX-Push-Url"], f"{SEARCH_URL}?q=the+witcher&page=2")

    def test_the_pushed_url_uses_only_validated_values(self):
        response, _ = self.get(
            {"q": "  zelda ", "page": "abc", "x": "<script>"}, fake_games(2), self.HTMX
        )
        self.assertEqual(response["HX-Push-Url"], f"{SEARCH_URL}?q=zelda")

    def test_a_history_restore_and_a_normal_request_get_the_full_page(self):
        for headers in (self.RESTORE, {}):
            with self.subTest(headers=headers):
                response, _ = self.get({"q": "zelda", "page": "2"}, fake_games(11), headers)
                self.assertContains(response, "<html")
                self.assertContains(response, 'id="igdb-q"')
                self.assertContains(response, 'id="search-region"')
                self.assertNotIn("HX-Push-Url", response)

    def test_every_response_varies_on_both_htmx_headers(self):
        for headers in (self.HTMX, self.RESTORE, {}):
            with self.subTest(headers=headers):
                response, _ = self.get({"q": "zelda"}, fake_games(1), headers)
                vary = {v.strip() for v in response["Vary"].split(",")}
                self.assertTrue({"HX-Request", "HX-History-Restore-Request"} <= vary)

    def test_full_page_opts_out_of_htmx_history_outside_the_swapped_region(self):
        response, _ = self.get({"q": "zelda"}, fake_games(1))
        body = response.content.decode()
        history = body.index('hx-history="false"')
        region = body.index('id="search-region"')
        self.assertLess(history, region)
        region_html = body[region:]
        self.assertNotIn('hx-history="false"', region_html)

    def test_pager_links_work_without_javascript_and_swap_with_htmx(self):
        response, _ = self.get({"q": "zelda", "page": "2"}, fake_games(11))
        body = unescape(response.content.decode())
        for target in (f"{SEARCH_URL}?q=zelda", f"{SEARCH_URL}?q=zelda&page=3"):
            self.assertIn(f'href="{target}" hx-get="{target}"', body)
        self.assertIn('hx-target="#search-region"', body)
        self.assertIn('hx-push-url="true"', body)
        # The search form itself is ordinary navigation, so a new search is a full page.
        form = re.search(r'<form method="get"[^>]*>', body).group(0)
        self.assertNotIn("hx-", form)


def search_by_term(answers):
    """A fake `search_games` answering by (term, page); unknown pairs return no results."""

    def fake(q, page):
        answer = answers.get((q, page), [])
        if isinstance(answer, Exception):
            raise answer
        return answer

    return fake


class RomanNumeralFallbackTests(SearchSetupMixin, TestCase):
    """B2: an empty page 1 for "... 3" retries once as "... III"."""

    def test_an_empty_exact_search_retries_once_with_the_roman_numeral(self):
        answers = {("Dark Souls 3", 1): [], ("Dark Souls III", 1): fake_games(2, start=11133)}
        response, search = self.get({"q": "Dark Souls 3"}, side_effect=search_by_term(answers))

        self.assertEqual(
            search.call_args_list, [mock.call("Dark Souls 3", 1), mock.call("Dark Souls III", 1)]
        )
        self.assertEqual(shown_ids(response), [11133, 11134])
        notice = re.search(
            r'data-testid="search-fallback">(.*?)</p>', response.content.decode(), re.DOTALL
        ).group(1)
        self.assertIn("No matches for “Dark Souls 3”", notice)
        self.assertIn("Showing results for “Dark Souls III”", notice)
        self.assertContains(response, 'name="q" value="Dark Souls III"')
        self.assertNotContains(response, "No matches.")

    def test_a_successful_exact_search_makes_no_fallback_request(self):
        response, search = self.get({"q": "Resident Evil 2"}, fake_games(3))

        search.assert_called_once_with("Resident Evil 2", 1)
        self.assertNotContains(response, 'data-testid="search-fallback"')
        self.assertContains(response, 'name="q" value="Resident Evil 2"')

    def test_pagination_after_a_fallback_uses_the_matched_term(self):
        answers = {("Dark Souls 3", 1): [], ("Dark Souls III", 1): fake_games(11)}
        response, _ = self.get({"q": "Dark Souls 3"}, side_effect=search_by_term(answers))

        self.assertEqual(shown_ids(response), list(range(1, 11)))
        self.assertIsNone(pager_href(response, "prev"))
        self.assertEqual(pager_href(response, "next"), f"{SEARCH_URL}?q=Dark+Souls+III&page=2")

        # Following Next searches the matched term directly, with no fallback.
        answers[("Dark Souls III", 2)] = fake_games(3, start=11)
        response, search = self.get(
            {"q": "Dark Souls III", "page": "2"}, side_effect=search_by_term(answers)
        )
        search.assert_called_once_with("Dark Souls III", 2)
        self.assertEqual(pager_href(response, "prev"), f"{SEARCH_URL}?q=Dark+Souls+III")

    def test_an_htmx_request_pushes_the_matched_term(self):
        answers = {("Dark Souls 3", 1): [], ("Dark Souls III", 1): fake_games(1)}
        response, _ = self.get(
            {"q": "Dark Souls 3"},
            headers={"HX-Request": "true"},
            side_effect=search_by_term(answers),
        )
        self.assertEqual(response["HX-Push-Url"], f"{SEARCH_URL}?q=Dark+Souls+III")

    def test_an_error_on_the_exact_search_shows_the_error_with_no_fallback(self):
        answers = {("Dark Souls 3", 1): igdb.IgdbError("igdb_timeout")}
        response, search = self.get({"q": "Dark Souls 3"}, side_effect=search_by_term(answers))

        search.assert_called_once_with("Dark Souls 3", 1)
        self.assertContains(response, escape(igdb.MESSAGES["igdb_timeout"]))
        self.assertContains(response, 'name="q" value="Dark Souls 3"')
        self.assertNotContains(response, "No matches.")

    def test_an_error_on_the_fallback_shows_the_error_and_keeps_the_original_text(self):
        answers = {
            ("Dark Souls 3", 1): [],
            ("Dark Souls III", 1): igdb.IgdbError("igdb_unavailable"),
        }
        response, search = self.get({"q": "Dark Souls 3"}, side_effect=search_by_term(answers))

        self.assertEqual(search.call_count, 2)
        self.assertContains(response, escape(igdb.MESSAGES["igdb_unavailable"]))
        self.assertContains(response, 'name="q" value="Dark Souls 3"')
        self.assertNotContains(response, "No matches.")

    def test_when_neither_term_matches_the_page_says_no_matches(self):
        response, search = self.get({"q": "Qwxz Saga 4"}, side_effect=search_by_term({}))

        self.assertEqual(
            search.call_args_list, [mock.call("Qwxz Saga 4", 1), mock.call("Qwxz Saga IV", 1)]
        )
        self.assertContains(response, "No matches.")
        self.assertContains(response, 'name="q" value="Qwxz Saga 4"')
        self.assertNotContains(response, 'data-testid="search-fallback"')

    def test_no_fallback_for_later_pages_or_text_without_a_final_standalone_2_to_9(self):
        cases = [
            ({"q": "Dark Souls 3", "page": "2"}, ("Dark Souls 3", 2)),
            ({"q": "zelda"}, ("zelda", 1)),
            ({"q": "Halo 1"}, ("Halo 1", 1)),
            ({"q": "Final Fantasy 10"}, ("Final Fantasy 10", 1)),
            ({"q": "Doom3"}, ("Doom3", 1)),
            ({"q": "3"}, ("3", 1)),
            ({"q": "Resident Evil 2 Remake"}, ("Resident Evil 2 Remake", 1)),
        ]
        for params, expected_call in cases:
            with self.subTest(params=params):
                _, search = self.get(params, side_effect=search_by_term({}))
                search.assert_called_once_with(*expected_call)

    def test_each_number_from_2_to_9_maps_to_its_roman_numeral(self):
        from games.queries import roman_numeral_variant

        expected = ["II", "III", "IV", "V", "VI", "VII", "VIII", "IX"]
        for digit, roman in zip("23456789", expected, strict=True):
            self.assertEqual(roman_numeral_variant(f"Game {digit}"), f"Game {roman}")


@override_settings(IGDB_CLIENT_ID=FAKE_CLIENT_ID, IGDB_CLIENT_SECRET=FAKE_SECRET)
class RomanNumeralFallbackRequestTests(TestCase):
    """Through the real client with HTTP mocked: both requests carry the eligibility clause."""

    def test_both_igdb_requests_use_the_eligibility_clause_on_page_1(self):
        from django.core.cache import cache

        cache.clear()
        self.addCleanup(cache.clear)
        self.client.force_login(make_user("searcher"))
        fake = FakeHttp(
            twitch=[token_response(FAKE_TOKEN_1)],
            igdb_responses=[
                FakeResponse(200, []),
                FakeResponse(200, [{"id": 11133, "name": "Dark Souls III", "game_type": 0}]),
            ],
        )
        with mock.patch("games.igdb.requests.post", side_effect=fake):
            response = self.client.get(SEARCH_URL, {"q": "Dark Souls 3"})

        self.assertEqual(shown_ids(response), [11133])
        exact, fallback = (body.decode("utf-8").splitlines() for body in fake.igdb_bodies())
        self.assertIn('search "Dark Souls 3";', exact)
        self.assertIn('search "Dark Souls III";', fallback)
        for lines in (exact, fallback):
            self.assertIn(igdb.ELIGIBILITY_WHERE, lines)
            self.assertIn("limit 11;", lines)
            self.assertIn("offset 0;", lines)
