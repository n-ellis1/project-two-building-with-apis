"""Refresh from IGDB (`/games/<entry id>/refresh/`), with the IGDB client mocked at its
module boundary. No test here contacts Twitch or IGDB."""

import re
from datetime import date, datetime
from decimal import Decimal
from html import unescape
from types import SimpleNamespace
from unittest import mock

from django.core.cache import cache
from django.db import DatabaseError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from games import igdb, saving
from games.models import Entry, Game, Platform
from games.saving import GENERIC_REFRESH_MESSAGE, save_game
from games.tests.factories import csrf_client, make_entry, make_game, make_user
from games.tests.test_save_service import fetched, row_counts
from games.views import refresh_attempt_key

SAVED_GAMES_URL = reverse("games:saved_games")
FAILURE_CODES = [
    "igdb_timeout",
    "igdb_unreachable",
    "igdb_rate_limited",
    "igdb_unavailable",
    "igdb_misconfigured",
    "igdb_game_not_found",
]
# Every failure but "not found" gets the My Saved Games link (as on search and save).
NO_LINK_CODES = {"igdb_game_not_found"}
THROTTLE_MESSAGE = "A refresh was attempted for this game in the last 10 minutes. Try again later."


class CacheClock:
    """A controlled clock for Django's local-memory cache only.

    The cache sets and checks expiry with `time.time()`, looked up through the name
    `time` in its `base` and `locmem` modules. Swapping that name in just those two
    modules moves cache expiry forward without waiting, and nothing else sees it.
    """

    def __init__(self, test, start=1_800_000_000.0):
        self.now = start
        fake_time = SimpleNamespace(time=lambda: self.now)
        for target in (
            "django.core.cache.backends.base.time",
            "django.core.cache.backends.locmem.time",
        ):
            patcher = mock.patch(target, fake_time)
            patcher.start()
            test.addCleanup(patcher.stop)

    def advance(self, seconds):
        self.now += seconds


GAME_FIELDS = [
    "igdb_id",
    "name",
    "slug",
    "summary",
    "first_release_date",
    "game_category",
    "version_parent",
    "cover_image_id",
    "igdb_url",
    "last_fetched_at",
]
TRACKING_FIELDS = [
    "owner_id",
    "game_id",
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
]


def messages_in(response) -> list[tuple[str, bool]]:
    """Each rendered message's text, and whether it has the My Saved Games link."""
    found = []
    for body in re.findall(
        r'<div class="alert[^"]*"[^>]*data-testid="message">(.*?)</div>',
        response.content.decode(),
        re.S,
    ):
        text = unescape(re.sub(r"<a .*?</a>", "", body, flags=re.S)).strip()
        found.append((" ".join(text.split()), f'href="{SAVED_GAMES_URL}"' in body))
    return found


def snapshot(game: Game) -> dict:
    """Everything a refresh could change, read fresh from the database."""
    game = Game.objects.get(pk=game.pk)
    return {
        "game": {name: getattr(game, name) for name in GAME_FIELDS},
        "platforms": sorted(game.platforms.values_list("igdb_id", "name")),
        "genres": sorted(game.genres.values_list("igdb_id", "name")),
        "themes": sorted(game.themes.values_list("igdb_id", "name")),
        "entries": sorted(Entry.objects.values_list(*TRACKING_FIELDS)),
        "rows": row_counts(),
    }


class RefreshTestCase(TestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        self.owner = make_user("owner")
        self.other = make_user("other")
        self.game = make_game(
            "Hollow Knight",
            igdb_id=14593,
            platforms=["PC (Microsoft Windows)", "Nintendo Switch"],
            genres=["Platform"],
            themes=[(1, "Action")],
            slug="hollow-knight",
            summary="A stored summary.",
            first_release_date=date(2017, 2, 24),
            game_category=0,
            cover_image_id="co1rgi",
            igdb_url="https://www.igdb.com/games/hollow-knight",
        )
        # A fixed, older "last refreshed" time, so any change to it shows.
        Game.objects.filter(pk=self.game.pk).update(
            last_fetched_at=timezone.make_aware(datetime(2026, 11, 1, 9, 30))
        )
        self.entry = make_entry(
            self.owner,
            self.game,
            status=Entry.Status.PLAYING,
            favorite=True,
            rating=9,
            notes="Mantis Lords next.",
            platform_played="Nintendo Switch",
            start_date=date(2026, 10, 1),
            hours_played=Decimal("12.5"),
        )
        self.other_entry = make_entry(
            self.other,
            self.game,
            status=Entry.Status.COMPLETED,
            rating=10,
            notes="Done.",
            platform_played="PC (Microsoft Windows)",
            start_date=date(2026, 9, 1),
            finish_date=date(2026, 9, 30),
            hours_played=Decimal("40.0"),
        )
        self.client.force_login(self.owner)

    def refresh_url(self, entry=None) -> str:
        return reverse("games:entry_refresh", args=[(entry or self.entry).pk])


class FailedRefreshTests(RefreshTestCase):
    """TDD cycle 1: a failed refresh changes nothing and shows the fixed message."""

    def test_each_igdb_failure_keeps_all_stored_data_and_shows_the_fixed_message(self):
        before = snapshot(self.game)
        detail_url = reverse("games:entry_detail", args=[self.entry.pk])

        for code in FAILURE_CODES:
            with self.subTest(code=code):
                cache.clear()  # each failure is its own first attempt, not throttled
                with mock.patch("games.igdb.fetch_game", side_effect=igdb.IgdbError(code)) as fetch:
                    response = self.client.post(self.refresh_url())

                fetch.assert_called_once_with(14593)
                self.assertRedirects(response, detail_url, fetch_redirect_response=False)
                self.assertEqual(snapshot(self.game), before)

                page = self.client.get(response["Location"])
                self.assertEqual(
                    messages_in(page), [(igdb.MESSAGES[code], code not in NO_LINK_CODES)]
                )
                # The detail page still shows the old details and refresh time.
                self.assertContains(page, "A stored summary.")
                self.assertContains(page, "last refreshed November 1, 2026, 9:30 a.m.")
                self.assertNotContains(page, "Traceback")


class RefreshThrottleTests(RefreshTestCase):
    """TDD cycle 2: one refresh attempt per game per 10 minutes, across all users,
    counted by attempt (a failure counts too)."""

    def test_a_failed_attempt_throttles_every_user_for_that_game_for_ten_minutes(self):
        clock = CacheClock(self)
        other_client = self.client_class()
        other_client.force_login(self.other)
        second_game = make_game("Celeste", igdb_id=26226)
        second_entry = make_entry(self.owner, second_game)
        outage = igdb.IgdbError("igdb_unavailable")

        # A's attempt fails, but it still counts as the attempt.
        with mock.patch("games.igdb.fetch_game", side_effect=outage) as fetch:
            response = self.client.post(self.refresh_url())
        fetch.assert_called_once_with(14593)
        self.client.get(response["Location"])  # shows (and so uses up) A's message
        before = snapshot(self.game)

        # 9 min 59 s later, B refreshes the same game through B's own entry: throttled.
        clock.advance(599)
        other_detail = reverse("games:entry_detail", args=[self.other_entry.pk])
        with mock.patch("games.igdb.fetch_game", side_effect=outage) as fetch:
            response = other_client.post(self.refresh_url(self.other_entry))
        fetch.assert_not_called()
        self.assertRedirects(response, other_detail, fetch_redirect_response=False)
        self.assertEqual(messages_in(other_client.get(other_detail)), [(THROTTLE_MESSAGE, False)])
        self.assertEqual(snapshot(self.game), before)

        # A different game isn't throttled by it.
        with mock.patch("games.igdb.fetch_game", side_effect=outage) as fetch:
            response = self.client.post(self.refresh_url(second_entry))
        fetch.assert_called_once_with(26226)
        page = self.client.get(response["Location"])
        self.assertEqual(messages_in(page), [(outage.message, True)])

        # Just past 10 minutes after A's attempt, the original game can be tried again.
        clock.advance(2)
        with mock.patch("games.igdb.fetch_game", side_effect=outage) as fetch:
            response = other_client.post(self.refresh_url(self.other_entry))
        fetch.assert_called_once_with(14593)
        page = other_client.get(response["Location"])
        self.assertEqual(messages_in(page), [(outage.message, True)])


class ReclassifyingRefreshTests(RefreshTestCase):
    """TDD cycle 3: a successful refresh that makes the game ineligible stores the new
    classification, keeps every entry, and later saves are refused from the stored
    values without calling IGDB."""

    CASES = [
        # (label, game_type IGDB now sends, version_parent IGDB now sends)
        ("a version parent appears", 0, 11133),
        ("the game type leaves the allowlist", 3, None),  # Bundle
        ("IGDB sends no game type", None, None),
    ]

    def test_a_refresh_that_makes_the_game_ineligible_keeps_entries_and_blocks_new_saves(self):
        newcomer = make_user("newcomer")
        detail_url = reverse("games:entry_detail", args=[self.entry.pk])

        for label, game_type, version_parent in self.CASES:
            with self.subTest(case=label):
                cache.clear()  # each case is a first attempt
                # Start every case from the stored, eligible classification.
                Game.objects.filter(pk=self.game.pk).update(game_category=0, version_parent=None)
                entries_before = snapshot(self.game)["entries"]

                record = fetched(14593, game_type, version_parent, name="Hollow Knight")
                with mock.patch("games.igdb.fetch_game", return_value=record) as fetch:
                    response = self.client.post(self.refresh_url())
                fetch.assert_called_once_with(14593)
                self.assertRedirects(response, detail_url, fetch_redirect_response=False)
                self.client.get(detail_url)  # use up this case's message

                # The new classification is stored, exactly as IGDB sent it.
                self.game.refresh_from_db()
                self.assertEqual(
                    (self.game.game_category, self.game.version_parent),
                    (game_type, version_parent),
                )
                # Both users' entries and tracking data are untouched.
                self.assertEqual(snapshot(self.game)["entries"], entries_before)

                # A third user's save is refused from the stored values, with no IGDB call.
                with mock.patch("games.igdb.fetch_game") as fetch:
                    with self.assertRaises(igdb.IgdbError) as raised:
                        save_game(newcomer, 14593)
                fetch.assert_not_called()
                self.assertEqual(raised.exception.code, "game_category_excluded")
                self.assertFalse(Entry.objects.filter(owner=newcomer).exists())


def updated_record(pc_id: int) -> igdb.IgdbGameDetails:
    """What IGDB now says about Hollow Knight: new details, Nintendo Switch gone, the
    PC platform sent under a different name, PlayStation 4 added, a new genre."""
    return igdb.IgdbGameDetails(
        igdb_id=14593,
        name="Hollow Knight: Voidheart Edition",
        slug="hollow-knight-voidheart",
        summary="A newer summary.",
        first_release_date=date(2017, 2, 25),
        game_category=0,
        version_parent=None,
        cover_image_id="co93cr",
        igdb_url="https://www.igdb.com/games/hollow-knight-voidheart",
        platforms=(
            igdb.IgdbNamed(pc_id, "PC (Windows, renamed upstream)"),
            igdb.IgdbNamed(48, "PlayStation 4"),
        ),
        genres=(igdb.IgdbNamed(31, "Adventure"),),
        themes=(igdb.IgdbNamed(1, "Action"), igdb.IgdbNamed(17, "Fantasy")),
    )


class SuccessfulRefreshTests(RefreshTestCase):
    def setUp(self):
        super().setUp()
        self.pc_id = Platform.objects.get(name="PC (Microsoft Windows)").igdb_id
        self.detail_url = reverse("games:entry_detail", args=[self.entry.pk])

    def refresh(self, record=None):
        with mock.patch(
            "games.igdb.fetch_game", return_value=record or updated_record(self.pc_id)
        ) as fetch:
            response = self.client.post(self.refresh_url())
        fetch.assert_called_once_with(14593)
        return response

    def test_a_refresh_updates_details_links_and_time_together_and_keeps_entries(self):
        entries_before = snapshot(self.game)["entries"]
        started = timezone.now()

        response = self.refresh()

        self.assertRedirects(response, self.detail_url, fetch_redirect_response=False)
        after = snapshot(self.game)
        self.assertEqual(
            {name: value for name, value in after["game"].items() if name != "last_fetched_at"},
            {
                "igdb_id": 14593,
                "name": "Hollow Knight: Voidheart Edition",
                "slug": "hollow-knight-voidheart",
                "summary": "A newer summary.",
                "first_release_date": date(2017, 2, 25),
                "game_category": 0,
                "version_parent": None,
                "cover_image_id": "co93cr",
                "igdb_url": "https://www.igdb.com/games/hollow-knight-voidheart",
            },
        )
        self.assertGreaterEqual(after["game"]["last_fetched_at"], started)
        # Links follow IGDB; an existing platform keeps its stored name, so nobody's
        # platform played value goes stale just because IGDB renamed it.
        self.assertEqual(
            after["platforms"], [(48, "PlayStation 4"), (self.pc_id, "PC (Microsoft Windows)")]
        )
        self.assertEqual(after["genres"], [(31, "Adventure")])
        self.assertEqual(after["themes"], [(1, "Action"), (17, "Fantasy")])
        self.assertEqual(after["entries"], entries_before)

        page = self.client.get(response["Location"])
        self.assertEqual(
            messages_in(page), [("Refreshed Hollow Knight: Voidheart Edition from IGDB.", False)]
        )
        self.assertContains(page, "A newer summary.")
        self.assertNotContains(page, "last refreshed November 1, 2026")

    def test_a_removed_platform_is_kept_with_a_warning_and_other_fields_still_save(self):
        self.refresh()  # Nintendo Switch is no longer listed

        page = self.client.get(self.detail_url)
        self.assertContains(page, 'data-testid="stale-platform-warning"')
        self.assertContains(page, "IGDB no longer lists Nintendo Switch for this game.")
        self.entry.refresh_from_db()
        self.assertEqual(self.entry.platform_played, "Nintendo Switch")

        # B's PC is still listed, so B sees no warning.
        other_client = self.client_class()
        other_client.force_login(self.other)
        other_page = other_client.get(reverse("games:entry_detail", args=[self.other_entry.pk]))
        self.assertNotContains(other_page, 'data-testid="stale-platform-warning"')

        # Editing the notes while keeping the stale platform still works.
        edit_url = reverse("games:entry_edit", args=[self.entry.pk])
        self.assertContains(
            self.client.get(edit_url),
            '<option value="Nintendo Switch" selected>'
            "Nintendo Switch (no longer listed for this game)</option>",
            html=True,
        )
        response = self.client.post(
            edit_url,
            {
                "status": "playing",
                "favorite": "on",
                "rating": "9",
                "platform_played": "Nintendo Switch",
                "start_date": "2026-10-01",
                "finish_date": "",
                "hours_played": "12.5",
                "notes": "Beat the Mantis Lords.",
            },
        )
        self.assertRedirects(response, self.detail_url)
        self.entry.refresh_from_db()
        self.assertEqual(
            (self.entry.notes, self.entry.platform_played),
            ("Beat the Mantis Lords.", "Nintendo Switch"),
        )

    def test_a_database_failure_after_writes_begin_rolls_everything_back(self):
        before = snapshot(self.game)
        real_link_game = saving._link_game

        def link_then_fail(game, details):
            real_link_game(game, details)  # the Game row and its links are written...
            raise DatabaseError("disk I/O error near secret detail")  # ...then this

        with mock.patch("games.saving._link_game", side_effect=link_then_fail):
            response = self.refresh()

        self.assertRedirects(response, self.detail_url, fetch_redirect_response=False)
        self.assertEqual(snapshot(self.game), before)
        page = self.client.get(response["Location"])
        self.assertEqual(messages_in(page), [(GENERIC_REFRESH_MESSAGE, True)])
        self.assertNotContains(page, "secret detail")
        self.assertContains(page, "last refreshed November 1, 2026, 9:30 a.m.")
        # It was still an attempt, so the game stays throttled.
        self.assertIsNotNone(cache.get(refresh_attempt_key(14593)))


class RefreshAccessTests(RefreshTestCase):
    def test_get_by_the_owner_is_405_with_no_igdb_call_and_no_attempt(self):
        before = snapshot(self.game)
        with mock.patch("games.igdb.fetch_game") as fetch:
            response = self.client.get(self.refresh_url())
        self.assertEqual(response.status_code, 405)
        fetch.assert_not_called()
        self.assertIsNone(cache.get(refresh_attempt_key(14593)))
        self.assertEqual(snapshot(self.game), before)

    def test_a_signed_out_post_goes_to_login_with_no_igdb_call_and_no_attempt(self):
        self.client.logout()
        with mock.patch("games.igdb.fetch_game") as fetch:
            response = self.client.post(self.refresh_url())
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response["Location"])
        fetch.assert_not_called()
        self.assertIsNone(cache.get(refresh_attempt_key(14593)))

    def test_another_users_csrf_valid_post_is_404_with_no_igdb_call_and_no_attempt(self):
        before = snapshot(self.game)
        other_detail = reverse("games:entry_detail", args=[self.other_entry.pk])
        client, token = csrf_client(self.other, other_detail)

        with mock.patch("games.igdb.fetch_game") as fetch:
            response = client.post(self.refresh_url(), {"csrfmiddlewaretoken": token})
        self.assertEqual(response.status_code, 404)
        fetch.assert_not_called()
        self.assertIsNone(cache.get(refresh_attempt_key(14593)))
        self.assertEqual(snapshot(self.game), before)

        # The same client and token do work on B's own entry, so the 404 above was
        # the ownership check, not a CSRF rejection.
        with mock.patch(
            "games.igdb.fetch_game", side_effect=igdb.IgdbError("igdb_unavailable")
        ) as fetch:
            response = client.post(
                self.refresh_url(self.other_entry), {"csrfmiddlewaretoken": token}
            )
        self.assertRedirects(response, other_detail, fetch_redirect_response=False)
        fetch.assert_called_once_with(14593)

    def test_the_detail_page_has_a_csrf_protected_refresh_form_with_the_list_state(self):
        page = self.client.get(
            reverse("games:entry_detail", args=[self.entry.pk]) + "?q=hollow&sort=title&page=2"
        )
        form = re.search(
            r'<form method="post" action="([^"]*)"[^>]*data-testid="refresh-form">(.*?)</form>',
            page.content.decode(),
            re.S,
        )
        self.assertIsNotNone(form)
        self.assertEqual(unescape(form[1]), self.refresh_url() + "?q=hollow&sort=title&page=2")
        self.assertIn('name="csrfmiddlewaretoken"', form[2])
        self.assertIn("Refresh from IGDB", form[2])


class RefreshReturnStateTests(RefreshTestCase):
    """The redirect keeps the validated My Saved Games state, so the detail page's
    "My Saved Games" link still returns to the same list view."""

    VALID = (
        "?q=+hollow+++knight+&status=playing&platform=Nintendo+Switch&favorite=1"
        "&theme=1&sort=title&page=2&next=https%3A%2F%2Fevil.example%2F"
    )
    CLEAN = (
        "?q=hollow+knight&status=playing&platform=Nintendo+Switch&favorite=1"
        "&theme=1&sort=title&page=2"
    )

    def test_success_and_throttled_redirects_keep_only_the_validated_list_state(self):
        pc_id = Platform.objects.get(name="PC (Microsoft Windows)").igdb_id
        detail_url = reverse("games:entry_detail", args=[self.entry.pk])
        with mock.patch("games.igdb.fetch_game", return_value=updated_record(pc_id)):
            response = self.client.post(self.refresh_url() + self.VALID)
        self.assertRedirects(response, detail_url + self.CLEAN, fetch_redirect_response=False)

        page = self.client.get(response["Location"])
        return_link = re.search(
            r'href="([^"]*)" data-testid="saved-games-return"', page.content.decode()
        )
        self.assertEqual(unescape(return_link[1]), SAVED_GAMES_URL + self.CLEAN)

        # The throttled path keeps it too.
        with mock.patch("games.igdb.fetch_game") as fetch:
            response = self.client.post(self.refresh_url() + self.VALID)
        fetch.assert_not_called()
        self.assertRedirects(response, detail_url + self.CLEAN, fetch_redirect_response=False)

    def test_unknown_or_foreign_values_are_dropped_from_the_redirect(self):
        detail_url = reverse("games:entry_detail", args=[self.entry.pk])
        with mock.patch("games.igdb.fetch_game", side_effect=igdb.IgdbError("igdb_timeout")):
            response = self.client.post(
                self.refresh_url()
                + "?status=bogus&platform=Xbox&theme=999&sort=bogus&page=-3&favorite=yes"
                + "&next=%2F%2Fevil.example%2F"
            )
        self.assertRedirects(response, detail_url, fetch_redirect_response=False)
