"""The IGDB game detail page (`/search/games/<igdb_id>/`), opened from the popular row
or a search result title. The client is mocked at its module boundary; no test here
contacts Twitch or IGDB."""

from datetime import date
from html import escape
from unittest import mock

from django.test import TestCase
from django.urls import reverse

from games import igdb
from games.models import Game
from games.tests.factories import make_entry, make_game, make_user

UNSTORED_ID = 1942


def page_url(igdb_id):
    return reverse("games:igdb_game", args=[igdb_id])


def details(igdb_id=UNSTORED_ID, **fields):
    values = {
        "name": "The Witcher 3: Wild Hunt",
        "summary": "Geralt hunts for Ciri.",
        "first_release_date": date(2015, 5, 19),
        "game_category": 0,
        "cover_image_id": "coWitcher",
        "igdb_url": "https://www.igdb.com/games/the-witcher-3-wild-hunt",
        "platforms": (igdb.IgdbNamed(6, "PC (Microsoft Windows)"), igdb.IgdbNamed(48, "PS4")),
        **fields,
    }
    return igdb.IgdbGameDetails(igdb_id=igdb_id, **values)


class IgdbGamePageTests(TestCase):
    def setUp(self):
        self.me = make_user("me")
        self.client.force_login(self.me)

    def get(self, igdb_id, **patch):
        options = patch or {"return_value": details(igdb_id)}
        with mock.patch("games.igdb.fetch_game", **options) as fetch:
            response = self.client.get(page_url(igdb_id))
        return response, fetch

    def test_an_unsaved_unstored_game_opens_by_igdb_id_with_its_details_and_save(self):
        response, fetch = self.get(UNSTORED_ID)

        fetch.assert_called_once_with(UNSTORED_ID)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '<h1 class="h3 mb-0">The Witcher 3: Wild Hunt</h1>')
        self.assertContains(response, "Geralt hunts for Ciri.")
        self.assertContains(response, "May 19, 2015")
        self.assertContains(response, "PC (Microsoft Windows), PS4")
        self.assertContains(response, "/t_cover_big/coWitcher.jpg")  # the large cover
        self.assertContains(response, 'data-cover-placeholder="')  # failed-cover fallback
        self.assertContains(response, f'href="{reverse("games:search")}"')
        self.assertContains(response, 'data-testid="save-form"')
        self.assertContains(response, f'action="{reverse("games:search_save")}"')
        self.assertContains(response, f'name="igdb_id" value="{UNSTORED_ID}"')
        self.assertFalse(Game.objects.exists())  # opening a game never stores it

    def test_a_missing_cover_uses_the_local_placeholder(self):
        response, _ = self.get(UNSTORED_ID, return_value=details(cover_image_id=""))
        self.assertContains(response, "games/img/cover-placeholder.svg")
        self.assertNotContains(response, "images.igdb.com")

    def test_a_stored_game_loads_from_sqlite_with_no_igdb_call_during_an_outage(self):
        make_game(
            "Hollow Knight",
            igdb_id=14593,
            summary="A bug kingdom.",
            first_release_date=date(2017, 2, 24),
            cover_image_id="coHollow",
            platforms=["Nintendo Switch", "PC (Microsoft Windows)"],
        )

        response, fetch = self.get(14593, side_effect=igdb.IgdbError("igdb_unreachable"))

        fetch.assert_not_called()
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Hollow Knight")
        self.assertContains(response, "A bug kingdom.")
        self.assertContains(response, "February 24, 2017")
        self.assertContains(response, "Nintendo Switch, PC (Microsoft Windows)")
        self.assertContains(response, "/t_cover_big/coHollow.jpg")
        self.assertContains(response, 'data-testid="save-form"')
        self.assertNotContains(response, escape(igdb.MESSAGES["igdb_unreachable"]))

    def test_my_saved_game_links_to_my_entry_and_another_users_shows_save(self):
        other = make_user("other")
        mine = make_game("Mine", igdb_id=501)
        theirs = make_game("Theirs", igdb_id=502)
        my_entry = make_entry(self.me, mine)
        their_entry = make_entry(other, theirs)
        make_entry(other, mine)  # someone else saving my game changes nothing for me

        mine_page, _ = self.get(501)
        theirs_page, _ = self.get(502)

        self.assertContains(
            mine_page, f'href="{reverse("games:entry_detail", args=[my_entry.pk])}"'
        )
        self.assertContains(mine_page, 'data-testid="saved-link"')
        self.assertNotContains(mine_page, 'data-testid="save-form"')

        self.assertNotContains(theirs_page, 'data-testid="saved-link"')
        self.assertNotContains(theirs_page, reverse("games:entry_detail", args=[their_entry.pk]))
        self.assertContains(theirs_page, 'data-testid="save-form"')

    def test_an_ineligible_game_shows_the_excluded_message_and_no_save(self):
        make_game("Bundle", igdb_id=601, game_category=3)
        cases = {
            "stored bundle": (601, {}),
            "fetched edition": (602, {"return_value": details(602, version_parent=1942)}),
            "fetched mod": (603, {"return_value": details(603, game_category=5)}),
        }
        for label, (igdb_id, patch) in cases.items():
            with self.subTest(label):
                response, _ = self.get(igdb_id, **patch)
                self.assertEqual(response.status_code, 200)
                self.assertNotContains(response, 'data-testid="save-form"')
                self.assertContains(response, escape(igdb.MESSAGES["game_category_excluded"]))

    def test_an_unknown_id_is_a_404_with_the_fixed_message(self):
        response, _ = self.get(999999, side_effect=igdb.IgdbError("igdb_game_not_found"))

        self.assertEqual(response.status_code, 404)
        self.assertContains(response, escape(igdb.MESSAGES["igdb_game_not_found"]), status_code=404)
        self.assertNotContains(response, "Go to My Saved Games", status_code=404)
        self.assertContains(response, f'href="{reverse("games:search")}"', status_code=404)

    def test_an_id_too_large_to_be_a_game_is_a_404_with_no_igdb_call(self):
        response, fetch = self.get(2_147_483_648)
        self.assertEqual(response.status_code, 404)
        fetch.assert_not_called()

    def test_an_outage_for_an_unstored_game_shows_the_message_and_both_links(self):
        for code in ("igdb_timeout", "igdb_unreachable", "igdb_rate_limited", "igdb_misconfigured"):
            with self.subTest(code):
                response, _ = self.get(UNSTORED_ID, side_effect=igdb.IgdbError(code))
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, escape(igdb.MESSAGES[code]))
                self.assertContains(response, "Go to My Saved Games")
                self.assertContains(response, f'href="{reverse("games:search")}"')
                self.assertNotContains(response, 'data-testid="save-form"')

    def test_signed_out_visitors_are_redirected_and_igdb_is_never_called(self):
        self.client.logout()
        response, fetch = self.get(UNSTORED_ID)
        self.assertRedirects(response, f"{reverse('login')}?next={page_url(UNSTORED_ID)}")
        fetch.assert_not_called()


class SearchResultTitleLinkTests(TestCase):
    def test_result_titles_link_to_the_detail_page_and_save_controls_stay(self):
        me = make_user("me")
        entry = make_entry(me, make_game("Saved One", igdb_id=11))
        self.client.force_login(me)
        results = [igdb.IgdbGame(igdb_id=11, name="Saved One"), igdb.IgdbGame(12, "New One")]

        with mock.patch("games.igdb.search_games", return_value=results):
            response = self.client.get(reverse("games:search"), {"q": "one"})

        for igdb_id in (11, 12):
            self.assertContains(response, f'href="{page_url(igdb_id)}"')
        self.assertContains(response, f'href="{reverse("games:entry_detail", args=[entry.pk])}"')
        self.assertContains(response, 'name="igdb_id" value="12"')


class SaveFromDetailReturnTests(TestCase):
    """TDD cycle 3 (follow-up after Phase 8): a failed save from the detail page comes
    back to that page, rebuilt from the validated IGDB ID on our own route. A posted
    return value is only ever a name we recognise, never a URL we redirect to."""

    def test_a_failed_save_returns_to_the_detail_page_and_forged_return_urls_are_ignored(self):
        from games.models import Entry
        from games.tests.test_search_save import messages_html, save_forms

        user = make_user("saver")
        self.client.force_login(user)
        save_url = reverse("games:search_save")
        outage = igdb.IgdbError("igdb_unavailable")

        # The fields exactly as the detail page's Save form sends them.
        with mock.patch("games.igdb.fetch_game", return_value=details()):
            fields = save_forms(self.client.get(page_url(UNSTORED_ID)))[UNSTORED_ID]

        with mock.patch("games.igdb.fetch_game", side_effect=outage):
            response = self.client.post(save_url, fields)
            self.assertRedirects(response, page_url(UNSTORED_ID), fetch_redirect_response=False)
            # Back on the detail page (which can't load the game either), the save's
            # safe message shows with the My Saved Games link.
            page = self.client.get(response["Location"])
        [message] = messages_html(page)
        self.assertIn(escape(igdb.MESSAGES["igdb_unavailable"]), message)
        self.assertIn("Go to My Saved Games", message)
        self.assertFalse(Game.objects.exists())
        self.assertFalse(Entry.objects.exists())

        forged = {
            "absolute URL": {"igdb_id": "1942", "return_to": "https://evil.example/"},
            "scheme-relative URL": {"igdb_id": "1942", "return_to": "//evil.example/x"},
            "local path": {"igdb_id": "1942", "return_to": "/games/1/delete/"},
            "next beside a valid return_to": {
                "igdb_id": "1942",
                "return_to": "igdb_game",
                "next": "https://evil.example/",
            },
            "invalid IGDB ID": {"igdb_id": "1942/../../evil", "return_to": "igdb_game"},
        }
        expected = {
            "next beside a valid return_to": page_url(UNSTORED_ID),
        }
        for label, data in forged.items():
            with self.subTest(label), mock.patch("games.igdb.fetch_game", side_effect=outage):
                location = self.client.post(save_url, data)["Location"]
                self.assertNotIn("evil", location)
                # Unrecognised return values fall back to Search IGDB, as in Phase 8.
                self.assertEqual(location, expected.get(label, reverse("games:search")))

    def test_when_the_page_also_fails_the_save_message_shows_once_with_the_link(self):
        self.client.force_login(make_user("saver"))
        fields = {"igdb_id": str(UNSTORED_ID), "return_to": "igdb_game"}
        for code in ("igdb_timeout", "igdb_unavailable", "igdb_misconfigured"):
            with (
                self.subTest(code),
                mock.patch("games.igdb.fetch_game", side_effect=igdb.IgdbError(code)),
            ):
                response = self.client.post(reverse("games:search_save"), fields, follow=True)
                body = response.content.decode()
                self.assertEqual(body.count(escape(igdb.MESSAGES[code])), 1)
                self.assertEqual(body.count("Go to My Saved Games"), 1)
                self.assertContains(response, f'href="{reverse("games:search")}"')

    def test_with_no_pending_message_a_failed_page_still_shows_its_own_error(self):
        self.client.force_login(make_user("viewer"))
        with mock.patch("games.igdb.fetch_game", side_effect=igdb.IgdbError("igdb_timeout")):
            response = self.client.get(page_url(UNSTORED_ID))
        self.assertContains(response, 'data-testid="igdb-game-error"')
        self.assertContains(response, escape(igdb.MESSAGES["igdb_timeout"]), count=1)

    def test_new_and_duplicate_saves_from_the_page_behave_as_in_phase_8(self):
        from games.models import Entry
        from games.tests.test_save_service import fetched

        user = make_user("saver")
        self.client.force_login(user)
        fields = {
            "igdb_id": str(UNSTORED_ID),
            "return_to": "igdb_game",
            "next": "https://evil.example/",
        }
        with mock.patch("games.igdb.fetch_game", return_value=fetched(UNSTORED_ID, 0)):
            new = self.client.post(reverse("games:search_save"), fields)
        entry = Entry.objects.get(owner=user)
        self.assertRedirects(
            new, reverse("games:entry_edit", args=[entry.pk]), fetch_redirect_response=False
        )

        with mock.patch("games.igdb.fetch_game", side_effect=AssertionError("no IGDB")):
            again = self.client.post(reverse("games:search_save"), fields, follow=True)
        self.assertRedirects(again, reverse("games:entry_detail", args=[entry.pk]))
        self.assertContains(again, "Already in your games")
        self.assertEqual(Entry.objects.filter(owner=user).count(), 1)
