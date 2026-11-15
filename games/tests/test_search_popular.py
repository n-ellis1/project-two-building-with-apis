"""The "Popular on IGDB" row on the blank Search IGDB page.

The IGDB client is mocked at its module boundary (`games.igdb.popular_games`), and
the cache is cleared around every test. No test here contacts Twitch or IGDB.
"""

import re
from unittest import mock

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from games import igdb
from games.tests.factories import make_entry, make_game, make_user

SEARCH_URL = reverse("games:search")


def popular(*ids):
    return [igdb.IgdbGame(igdb_id=n, name=f"Popular {n}", cover_image_id=f"co{n}") for n in ids]


def row_ids(response):
    """IGDB IDs of the row's cards, in page order."""
    return [int(n) for n in re.findall(r'data-popular-id="(\d+)"', response.content.decode())]


def card(response, igdb_id):
    """The HTML of one card in the row, found by its IGDB ID."""
    match = re.search(
        rf'<li [^>]*data-popular-id="{igdb_id}".*?</li>', response.content.decode(), re.DOTALL
    )
    assert match, f"no popular card for IGDB ID {igdb_id}"
    return match.group(0)


def entry_url(entry):
    return reverse("games:entry_detail", args=[entry.pk])


class FakeClock:
    """Stands in for the `time` module inside Django's cache backends."""

    def __init__(self, now):
        self.now = now

    def time(self):
        return self.now


class PopularRowCacheAndFailureTests(TestCase):
    """TDD cycle 2 (follow-up after Phase 8): one shared cached row, Saved links
    resolved per signed-in user, and a failed feed that never blocks searching."""

    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)

    def test_second_blank_load_reuses_the_cached_row_with_saved_links_per_user(self):
        me, other = make_user("me"), make_user("other")
        my_entry = make_entry(me, make_game("Popular 7001", igdb_id=7001))
        other_entry = make_entry(other, make_game("Popular 7002", igdb_id=7002))

        with mock.patch("games.igdb.popular_games", return_value=popular(7001, 7002, 7003)) as feed:
            self.client.force_login(me)
            mine = self.client.get(SEARCH_URL)
            self.client.force_login(other)
            theirs = self.client.get(SEARCH_URL)

        # One feed request: the second load (another user) reuses the cached row.
        feed.assert_called_once_with()
        for response in (mine, theirs):
            self.assertEqual(response.status_code, 200)
            self.assertEqual(row_ids(response), [7001, 7002, 7003])

        # Saved links come from each user's own entries, never from the shared cache.
        self.assertIn('data-testid="popular-saved-link"', card(mine, 7001))
        self.assertIn(f'href="{entry_url(my_entry)}"', card(mine, 7001))
        self.assertNotIn("popular-saved-link", card(mine, 7002))
        self.assertNotIn(entry_url(other_entry), mine.content.decode())

        self.assertIn('data-testid="popular-saved-link"', card(theirs, 7002))
        self.assertIn(f'href="{entry_url(other_entry)}"', card(theirs, 7002))
        self.assertNotIn("popular-saved-link", card(theirs, 7001))
        self.assertNotIn(entry_url(my_entry), theirs.content.decode())

    def test_a_failed_feed_hides_the_row_keeps_search_usable_and_is_retried_next_load(self):
        self.client.force_login(make_user("searcher"))

        with mock.patch(
            "games.igdb.popular_games",
            side_effect=[igdb.IgdbError("igdb_timeout"), popular(7001)],
        ) as feed:
            failed = self.client.get(SEARCH_URL)
            retried = self.client.get(SEARCH_URL)

        self.assertEqual(failed.status_code, 200)
        self.assertContains(failed, 'name="q"')  # the search box is still there
        self.assertNotContains(failed, 'data-testid="popular-row"')
        self.assertNotContains(failed, 'data-testid="search-error"')  # no blocking banner
        self.assertNotContains(failed, igdb.MESSAGES["igdb_timeout"])

        # The failure wasn't cached, so the next blank load asks again and shows the row.
        self.assertEqual(feed.call_count, 2)
        self.assertContains(retried, 'data-testid="popular-row"')
        self.assertEqual(row_ids(retried), [7001])

    def test_the_cached_row_lasts_one_hour_then_is_fetched_again(self):
        self.client.force_login(make_user("searcher"))
        clock = FakeClock(1_000_000.0)

        with (
            mock.patch("django.core.cache.backends.base.time", clock),
            mock.patch("django.core.cache.backends.locmem.time", clock),
            mock.patch("games.igdb.popular_games", return_value=popular(7001)) as feed,
        ):
            self.client.get(SEARCH_URL)
            clock.now += igdb.POPULAR_CACHE_SECONDS - 1
            self.client.get(SEARCH_URL)
            self.assertEqual(feed.call_count, 1)  # still cached just before the hour
            clock.now += 2
            response = self.client.get(SEARCH_URL)

        self.assertEqual(igdb.POPULAR_CACHE_SECONDS, 3600)
        self.assertEqual(feed.call_count, 2)  # expired after the hour, fetched again
        self.assertEqual(row_ids(response), [7001])

    def test_each_card_is_one_link_holding_the_cover_and_title(self):
        self.client.force_login(make_user("searcher"))
        games = [
            igdb.IgdbGame(igdb_id=7001, name="With Cover", cover_image_id="co7001"),
            igdb.IgdbGame(igdb_id=7002, name="No Cover"),
        ]
        with mock.patch("games.igdb.popular_games", return_value=games):
            response = self.client.get(SEARCH_URL)

        for game in games:
            html = card(response, game.igdb_id)
            links = re.findall(r"<a [^>]*>.*?</a>", html, re.DOTALL)
            self.assertEqual(len(links), 1)  # no Saved link here, so the card is one link
            [link] = links
            self.assertIn(f'href="{reverse("games:igdb_game", args=[game.igdb_id])}"', link)
            self.assertIn("<img ", link)
            self.assertIn('loading="lazy"', link)
            self.assertIn(game.name, link)
        self.assertIn("/t_cover_small/co7001.jpg", card(response, 7001))
        self.assertIn('data-cover-placeholder="', card(response, 7001))
        self.assertIn("games/img/cover-placeholder.svg", card(response, 7002))
        self.assertNotIn("images.igdb.com", card(response, 7002))
        self.assertContains(response, "overflow-x-auto")  # CSS-only horizontal scroll

    def test_a_title_search_never_requests_the_popular_feed(self):
        self.client.force_login(make_user("searcher"))

        with (
            mock.patch("games.igdb.popular_games", return_value=popular(7001)) as feed,
            mock.patch("games.igdb.search_games", return_value=[]),
        ):
            response = self.client.get(SEARCH_URL, {"q": "zelda"})

        feed.assert_not_called()
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'data-testid="popular-row"')
