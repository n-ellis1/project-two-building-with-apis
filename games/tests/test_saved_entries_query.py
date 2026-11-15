"""The shared saved-entries query builder (stories 47, 48, 49-59).

These tests call `saved_entries(user, EntryQuery(...))` directly, because the
API reuses the same builder in Phase 10. The website's forgiving parsing is
tested in `test_saved_games.py`.
"""

from datetime import date, timedelta
from decimal import Decimal
from urllib.parse import urlencode

from django.core.paginator import Paginator
from django.http import QueryDict
from django.test import TestCase
from django.utils import timezone

from games.models import Entry
from games.queries import (
    PAGE_SIZE,
    EntryQuery,
    parse_entry_query,
    saved_entries,
    user_platforms_played,
    user_themes,
)

from .factories import make_entry, make_game, make_user


def names(entries):
    return [entry.game.name for entry in entries]


class SearchTests(TestCase):
    """Story 47: case-insensitive search over title, summary, platform, genre,
    theme and the user's notes. Story 48: each entry appears once."""

    def setUp(self):
        self.user = make_user("demo_a")
        # Each game matches exactly one search term, through exactly one field.
        make_entry(self.user, make_game("Zephyr Quest"))
        make_entry(self.user, make_game("Summary Match", summary="A haunted Lighthouse keeper."))
        make_entry(self.user, make_game("Platform Match", platforms=["Sega Dreamcast"]))
        make_entry(self.user, make_game("Genre Match", genres=["Rhythm"]))
        make_entry(self.user, make_game("Theme Match", themes=[(19, "Horror")]))
        make_entry(self.user, make_game("Notes Match"), notes="The LICKER still gets me.")

    def test_each_field_matches_case_insensitively(self):
        for term, expected in [
            ("zEPHYR", "Zephyr Quest"),
            ("lighthouse", "Summary Match"),
            ("DREAMCAST", "Platform Match"),
            ("rhythm", "Genre Match"),
            ("hOrRoR", "Theme Match"),
            ("licker", "Notes Match"),
        ]:
            with self.subTest(term=term):
                self.assertEqual(names(saved_entries(self.user, EntryQuery(q=term))), [expected])

    def test_an_entry_matching_through_several_related_rows_appears_once(self):
        make_entry(
            self.user,
            make_game(
                "Neo Collection",
                platforms=["Neo Geo AES", "Neo Geo CD"],
                genres=["Neo Arcade"],
                themes=["Neo Noir"],
            ),
        )

        results = saved_entries(self.user, EntryQuery(q="neo"))

        self.assertEqual(names(results), ["Neo Collection"])
        self.assertEqual(results.count(), 1)

    def test_notes_only_in_another_users_entry_find_nothing(self):
        other = make_user("demo_b")
        # The same shared Game, so a join through the game's other entries would leak.
        shared = make_game("Resident Evil 2")
        make_entry(self.user, shared, notes="Leon A done.")
        make_entry(other, shared, notes="Mr. X stalking sections were the highlight.")

        results = saved_entries(self.user, EntryQuery(q="stalking"))

        self.assertEqual(names(results), [])
        self.assertEqual(results.count(), 0)


class SortTests(TestCase):
    """Stories 55, 57, 58, 59: sorts, missing values last, stable tie-breakers."""

    def setUp(self):
        self.user = make_user("demo_a")
        self.added = timezone.now() - timedelta(days=30)

    def add(self, name, game_date=None, **fields):
        # Each entry is added an hour after the previous one, so the default
        # sort (newest first) never matches the order the tests expect.
        self.added += timedelta(hours=1)
        game = make_game(name, first_release_date=game_date)
        return make_entry(self.user, game, created_at=self.added, **fields)

    def pages(self, query):
        paginator = Paginator(saved_entries(self.user, query), PAGE_SIZE)
        return [names(paginator.page(n)) for n in paginator.page_range]

    def test_rating_highest_first_unrated_last_ties_by_title_then_id_across_pages(self):
        self.add("Aardvark Unrated")  # unrated: last, even though it sorts first by title
        self.add("Top Pick", rating=10)
        # Ten entries tied on rating 7 straddle the page 1 / page 2 boundary.
        # "alpha" and "Alpha" tie on case-insensitive title too, so entry ID decides:
        # lowercase "alpha" was created first.
        for name in ("delta", "India", "alpha", "Bravo", "Alpha"):
            self.add(name, rating=7)
        for name in ("Golf", "charlie", "hotel", "Echo", "foxtrot"):
            self.add(name, rating=7)
        self.add("Low Rated", rating=3)
        self.add("zulu unrated")

        page1, page2 = self.pages(EntryQuery(sort="rating"))

        self.assertEqual(
            page1,
            [
                "Top Pick",
                "alpha",
                "Alpha",
                "Bravo",
                "charlie",
                "delta",
                "Echo",
                "foxtrot",
                "Golf",
                "hotel",
            ],
        )
        self.assertEqual(page2, ["India", "Low Rated", "Aardvark Unrated", "zulu unrated"])
        # Nothing repeated or skipped across the boundary.
        all_names = page1 + page2
        self.assertEqual(len(all_names), len(set(all_names)))
        self.assertEqual(sorted(all_names), sorted(names(self.user.entries.all())))

    def sorted_names(self, sort):
        return names(saved_entries(self.user, EntryQuery(sort=sort)))

    def test_title_sorts_ignore_case_and_break_ties_by_entry_id_only(self):
        first_doom = self.add("DOOM")
        self.add("banjo")
        second_doom = self.add("Doom")
        self.add("Celeste")

        self.assertEqual(self.sorted_names("title"), ["banjo", "Celeste", "DOOM", "Doom"])
        # Z to A reverses the title, but equal titles still go by entry ID ascending.
        self.assertEqual(self.sorted_names("title_desc"), ["DOOM", "Doom", "Celeste", "banjo"])
        self.assertLess(first_doom.pk, second_doom.pk)

    def test_reversing_the_title_sort_with_the_same_search_and_filters_keeps_the_count(self):
        for n in range(1, 8):
            self.add(f"Horror {n}", status="playing")
        self.add("Horror Dropped", status="dropped")
        a_to_z = saved_entries(self.user, EntryQuery(q="horror", status="playing", sort="title"))
        z_to_a = saved_entries(
            self.user, EntryQuery(q="horror", status="playing", sort="title_desc")
        )

        self.assertEqual(a_to_z.count(), z_to_a.count())
        self.assertEqual(a_to_z.count(), 7)
        self.assertEqual(names(a_to_z), list(reversed(names(z_to_a))))

    def test_release_date_newest_first_unknown_dates_last(self):
        self.add("No Date")
        self.add("Old", game_date=date(1998, 1, 1))
        self.add("New", game_date=date(2024, 5, 1))
        self.add("Also New", game_date=date(2024, 5, 1))

        self.assertEqual(self.sorted_names("release"), ["Also New", "New", "Old", "No Date"])

    def test_hours_most_first_blank_hours_last(self):
        self.add("Blank")
        self.add("Short", hours_played=Decimal("2.5"))
        self.add("Long", hours_played=Decimal("80"))
        self.add("Zero", hours_played=Decimal("0"))

        self.assertEqual(self.sorted_names("hours"), ["Long", "Short", "Zero", "Blank"])

    def test_last_updated_newest_first(self):
        older = self.add("Updated Long Ago")
        newer = self.add("Updated Recently")
        now = timezone.now()
        Entry.objects.filter(pk=older.pk).update(updated_at=now - timedelta(days=5))
        Entry.objects.filter(pk=newer.pk).update(updated_at=now)

        self.assertEqual(self.sorted_names("updated"), ["Updated Recently", "Updated Long Ago"])

    def test_date_added_newest_first_is_the_default_and_unknown_sorts_use_it(self):
        self.add("First Added")
        self.add("Last Added")
        expected = ["Last Added", "First Added"]
        self.assertEqual(names(saved_entries(self.user)), expected)
        self.assertEqual(self.sorted_names("bogus"), expected)


class FilterTests(TestCase):
    """Stories 49-52: Status, Platform Played, Favorite and Theme, alone and combined."""

    def setUp(self):
        self.user = make_user("demo_a")
        horror, survival = (19, "Horror"), (21, "Survival")
        make_entry(
            self.user,
            make_game("Resident Evil 2", themes=[horror, survival]),
            status="playing",
            platform_played="PlayStation",
        )
        make_entry(
            self.user,
            make_game("Dead Space", themes=[horror]),
            status="completed",
            favorite=True,
            platform_played="PC (Microsoft Windows)",
        )
        make_entry(
            self.user,
            make_game("Subnautica", themes=[survival]),
            status="playing",
            favorite=True,
            platform_played="PC (Microsoft Windows)",
        )
        make_entry(self.user, make_game("Portal 2", themes=["Comedy"]))

    def matching(self, **fields):
        return sorted(names(saved_entries(self.user, EntryQuery(**fields))))

    def test_each_filter_alone(self):
        self.assertEqual(self.matching(status="playing"), ["Resident Evil 2", "Subnautica"])
        self.assertEqual(
            self.matching(platform="PC (Microsoft Windows)"), ["Dead Space", "Subnautica"]
        )
        self.assertEqual(self.matching(favorite=True), ["Dead Space", "Subnautica"])
        self.assertEqual(self.matching(theme=19), ["Dead Space", "Resident Evil 2"])
        self.assertEqual(self.matching(theme=21), ["Resident Evil 2", "Subnautica"])

    def test_filters_combine_with_each_other_and_with_search(self):
        self.assertEqual(self.matching(theme=19, status="playing"), ["Resident Evil 2"])
        self.assertEqual(self.matching(theme=21, favorite=True), ["Subnautica"])
        self.assertEqual(
            self.matching(platform="PC (Microsoft Windows)", favorite=True, status="completed"),
            ["Dead Space"],
        )
        # "i" matches RE2's title and its Survival theme, and Subnautica's title and
        # theme; with the Theme join on top, each still appears once.
        results = saved_entries(self.user, EntryQuery(q="i", theme=21))
        self.assertEqual(sorted(names(results)), ["Resident Evil 2", "Subnautica"])
        self.assertEqual(results.count(), 2)

    def test_a_valid_combination_that_matches_nothing_is_empty(self):
        self.assertEqual(self.matching(theme=19, favorite=True, status="playing"), [])


class DropdownChoiceTests(TestCase):
    """Stories 53, 54: the Theme dropdown lists only the user's own themes, A to Z."""

    def setUp(self):
        self.user_a = make_user("demo_a")
        self.user_b = make_user("demo_b")
        make_entry(
            self.user_a,
            make_game("Resident Evil 2", themes=[(19, "Horror"), (21, "Survival"), (1, "Action")]),
            status="playing",
            platform_played="PlayStation",
        )
        shared = make_game("Portal 2", themes=[(27, "Comedy"), (18, "science fiction")])
        make_entry(self.user_a, shared, platform_played="Xbox 360")
        make_entry(self.user_b, shared, platform_played="PC (Microsoft Windows)")

    def test_themes_are_the_users_own_alphabetical_and_unique(self):
        self.assertEqual(
            [t.name for t in user_themes(self.user_a)],
            ["Action", "Comedy", "Horror", "science fiction", "Survival"],
        )
        self.assertEqual([t.name for t in user_themes(self.user_b)], ["Comedy", "science fiction"])

    def test_platforms_played_are_the_users_own_non_blank_values(self):
        make_entry(self.user_a, make_game("Unplayed"))
        self.assertEqual(user_platforms_played(self.user_a), ["PlayStation", "Xbox 360"])
        self.assertEqual(user_platforms_played(self.user_b), ["PC (Microsoft Windows)"])


class ForgivingParseTests(TestCase):
    """Stories 63-66: the website ignores bad values instead of failing."""

    def setUp(self):
        self.user_a = make_user("demo_a")
        self.user_b = make_user("demo_b")
        make_entry(
            self.user_a,
            make_game("Resident Evil 2", themes=[(19, "Horror")]),
            platform_played="PlayStation",
        )
        make_entry(self.user_b, make_game("Portal 2", themes=[(27, "Comedy")]))

    def parse(self, user, **params):
        return parse_entry_query(user, QueryDict(urlencode(params)))

    def test_valid_values_are_kept(self):
        query = self.parse(
            self.user_a,
            q="  leon   kennedy ",
            status="playing",
            platform="PlayStation",
            favorite="1",
            theme="19",
            sort="title_desc",
        )
        self.assertEqual(
            query,
            EntryQuery(
                q="leon kennedy",
                status="playing",
                platform="PlayStation",
                favorite=True,
                theme=19,
                sort="title_desc",
            ),
        )

    def test_missing_values_give_the_defaults(self):
        self.assertEqual(self.parse(self.user_a), EntryQuery())

    def test_unknown_or_malformed_values_are_dropped(self):
        for field, raw in [
            ("status", "finished"),
            ("platform", "Sega Saturn"),
            ("favorite", "yes"),
            ("theme", "abc"),
            ("theme", "19.0"),
            ("theme", "-19"),
            ("theme", "١٩"),  # Arabic-Indic digits: not an ASCII integer
            ("sort", "bogus"),
            ("sort", "-created_at"),
        ]:
            with self.subTest(field=field, raw=raw):
                self.assertEqual(self.parse(self.user_a, **{field: raw}), EntryQuery())

    def test_a_theme_only_on_another_users_games_is_ignored(self):
        self.assertEqual(self.parse(self.user_a, theme="27").theme, None)
        self.assertEqual(self.parse(self.user_b, theme="19").theme, None)

    def test_a_platform_only_on_another_users_entries_is_ignored(self):
        self.assertEqual(self.parse(self.user_b, platform="PlayStation").platform, "")


class QueryStringTests(TestCase):
    def test_defaults_and_page_1_are_left_out(self):
        self.assertEqual(EntryQuery().querystring(), "")
        self.assertEqual(EntryQuery(sort="added").querystring(page=1), "")

    def test_state_and_page_are_kept_in_a_fixed_order(self):
        query = EntryQuery(
            q="dead space", status="playing", platform="PC", favorite=True, theme=19, sort="title"
        )
        self.assertEqual(
            query.querystring(page=2),
            "?q=dead+space&status=playing&platform=PC&favorite=1&theme=19&sort=title&page=2",
        )

    def test_clear_filters_keeps_search_and_sort_only(self):
        query = EntryQuery(
            q="dead", status="playing", platform="PC", favorite=True, theme=19, sort="title"
        )
        self.assertEqual(query.without_filters(), EntryQuery(q="dead", sort="title"))
        self.assertFalse(query.without_filters().has_filters)
        self.assertTrue(query.has_filters)
