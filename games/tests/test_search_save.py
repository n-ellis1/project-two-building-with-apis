"""Saving from IGDB search (`/search/save/`), with the IGDB client mocked at its
module boundary. No test here contacts Twitch or IGDB."""

import re
from html import escape, unescape
from unittest import mock

from django.test import TestCase
from django.urls import reverse

from games import igdb
from games.models import Entry, Game
from games.saving import GENERIC_SAVE_MESSAGE, SaveFailed
from games.tests.factories import csrf_client, make_entry, make_game, make_user
from games.tests.test_save_service import fetched, row_counts

SAVE_URL = reverse("games:search_save")
SEARCH_URL = reverse("games:search")
SAVED_GAMES_URL = reverse("games:saved_games")
UPSTREAM_CODES = [
    "igdb_timeout",
    "igdb_unreachable",
    "igdb_rate_limited",
    "igdb_unavailable",
    "igdb_misconfigured",
]


def messages_html(response) -> list[str]:
    return re.findall(
        r'<div class="alert[^"]*"[^>]*data-testid="message">(.*?)</div>',
        response.content.decode(),
        re.S,
    )


def save_forms(response) -> dict[int, dict[str, str]]:
    """Each Save form's hidden fields, keyed by IGDB ID, as the browser would send them."""
    forms = {}
    for form in re.findall(
        r'<form[^>]*data-testid="save-form".*?</form>', response.content.decode(), re.S
    ):
        fields = {
            name: unescape(value)
            for name, value in re.findall(r'name="(\w+)" value="([^"]*)"', form)
        }
        fields.pop("csrfmiddlewaretoken", None)
        forms[int(fields["igdb_id"])] = fields
    return forms


class SaveSetupMixin:
    def setUp(self):
        self.user = make_user("saver")
        self.client.force_login(self.user)

    def post(self, igdb_id="26758", q="silksong", page="1", **extra):
        return self.client.post(SAVE_URL, {"igdb_id": igdb_id, "q": q, "page": page, **extra})


class NewSaveTests(SaveSetupMixin, TestCase):
    def test_a_new_save_stores_the_game_and_lands_on_edit_with_defaults(self):
        record = fetched(26758, 0, name="Hollow Knight: Silksong")
        with mock.patch("games.igdb.fetch_game", return_value=record) as fetch:
            response = self.post()

        fetch.assert_called_once_with(26758)
        entry = Entry.objects.get(owner=self.user)
        self.assertRedirects(
            response, reverse("games:entry_edit", args=[entry.pk]), fetch_redirect_response=False
        )
        self.assertEqual(entry.status, Entry.Status.WANT_TO_PLAY)
        self.assertFalse(entry.favorite)
        game = entry.game
        self.assertEqual((game.igdb_id, game.name), (26758, "Hollow Knight: Silksong"))
        self.assertEqual(game.platforms.count(), 1)
        self.assertEqual(game.genres.count(), 1)
        self.assertEqual(game.themes.count(), 1)

        page = self.client.get(response["Location"])
        self.assertContains(page, "Added Hollow Knight: Silksong to your games.")

    def test_the_owner_always_comes_from_the_session(self):
        other = make_user("other")
        game = make_game("Stored", igdb_id=4242)
        response = self.post(igdb_id="4242", owner=str(other.pk), owner_id=str(other.pk))

        entry = Entry.objects.get(game=game)
        self.assertEqual(entry.owner, self.user)
        self.assertFalse(Entry.objects.filter(owner=other).exists())
        self.assertRedirects(response, reverse("games:entry_edit", args=[entry.pk]))


class DuplicateSaveTests(SaveSetupMixin, TestCase):
    def test_saving_again_goes_to_my_existing_entry_with_already_in_your_games(self):
        game = make_game("Hollow Knight", igdb_id=14593)
        existing = make_entry(self.user, game, notes="keep me", rating=9)

        with mock.patch("games.igdb.fetch_game") as fetch:
            response = self.post(igdb_id="14593", q="hollow")

        fetch.assert_not_called()
        self.assertRedirects(
            response,
            reverse("games:entry_detail", args=[existing.pk]),
            fetch_redirect_response=False,
        )
        self.assertEqual(Entry.objects.filter(owner=self.user, game=game).count(), 1)
        existing.refresh_from_db()
        self.assertEqual((existing.notes, existing.rating), ("keep me", 9))
        self.assertContains(self.client.get(response["Location"]), "Already in your games")


class FailedSaveTests(SaveSetupMixin, TestCase):
    def follow_failed_save(self, error, search_error=None, **post):
        """POST a save that fails with `error`, then follow the redirect to the search,
        whose reload either works (no results) or fails with `search_error`."""
        search = {"side_effect": search_error} if search_error else {"return_value": []}
        with (
            mock.patch("games.igdb.fetch_game", side_effect=error),
            mock.patch("games.igdb.search_games", **search),
        ):
            response = self.post(**post)
            followed = self.client.get(response["Location"])
        return response, followed

    def test_each_failure_returns_to_the_same_search_and_page_with_its_message(self):
        for code in [*UPSTREAM_CODES, "igdb_game_not_found", "game_category_excluded"]:
            with self.subTest(code):
                response, followed = self.follow_failed_save(
                    igdb.IgdbError(code), q="hollow knight", page="3"
                )
                self.assertRedirects(
                    response, f"{SEARCH_URL}?q=hollow+knight&page=3", fetch_redirect_response=False
                )
                [message] = messages_html(followed)
                self.assertIn(escape(igdb.MESSAGES[code]), message)
                has_link = f'href="{SAVED_GAMES_URL}"' in message
                self.assertEqual(has_link, code in UPSTREAM_CODES)
                self.assertEqual(Entry.objects.count(), 0)

    def test_the_message_still_shows_when_reloading_the_results_fails_too(self):
        response, followed = self.follow_failed_save(
            igdb.IgdbError("igdb_unreachable"),
            search_error=igdb.IgdbError("igdb_unreachable"),
            q="hollow knight",
            page="2",
        )
        self.assertRedirects(
            response, f"{SEARCH_URL}?q=hollow+knight&page=2", fetch_redirect_response=False
        )
        [message] = messages_html(followed)
        self.assertIn(escape(igdb.MESSAGES["igdb_unreachable"]), message)
        self.assertIn(f'href="{SAVED_GAMES_URL}"', message)
        # The failed reload shows its own error too, never "No matches.".
        self.assertContains(followed, 'data-testid="search-error"')
        self.assertNotContains(followed, "No matches.")
        self.assertContains(followed, 'value="hollow knight"')  # search text kept

    def test_an_unexpected_failure_shows_only_the_generic_message(self):
        with mock.patch("games.views.save_game", side_effect=SaveFailed()):
            response = self.post(q="hollow", page="2")
        self.assertRedirects(
            response, f"{SEARCH_URL}?q=hollow&page=2", fetch_redirect_response=False
        )
        with mock.patch("games.igdb.search_games", return_value=[]):
            [message] = messages_html(self.client.get(response["Location"]))
        self.assertIn(escape(GENERIC_SAVE_MESSAGE), message)
        self.assertIn(f'href="{SAVED_GAMES_URL}"', message)

    def test_q_and_page_are_cleaned_like_the_search_page(self):
        cases = [
            ({"q": "  hollow   knight ", "page": "abc"}, f"{SEARCH_URL}?q=hollow+knight"),
            ({"q": "a&b=c", "page": "0"}, f"{SEARCH_URL}?q=a%26b%3Dc"),
            ({"q": "", "page": "4"}, SEARCH_URL),
            ({"q": "x" * 500, "page": "2"}, f"{SEARCH_URL}?q={'x' * 200}&page=2"),
        ]
        for post, expected in cases:
            with (
                self.subTest(post=post),
                mock.patch("games.igdb.fetch_game", side_effect=igdb.IgdbError("igdb_timeout")),
            ):
                response = self.post(**post)
                self.assertRedirects(response, expected, fetch_redirect_response=False)

    def test_an_id_that_cant_be_a_game_is_refused_without_calling_igdb(self):
        for bad in ["", "abc", "0", "-5", "1.5", " 12", "12 ", "99999999999", "２"]:
            with self.subTest(igdb_id=bad), mock.patch("games.igdb.fetch_game") as fetch:
                response = self.post(igdb_id=bad, q="zelda")
                fetch.assert_not_called()
                self.assertRedirects(
                    response, f"{SEARCH_URL}?q=zelda", fetch_redirect_response=False
                )
                with mock.patch("games.igdb.search_games", return_value=[]):
                    [message] = messages_html(self.client.get(response["Location"]))
                self.assertIn(escape(igdb.MESSAGES["igdb_game_not_found"]), message)
        self.assertEqual(Game.objects.count(), 0)

    def test_an_excluded_id_posted_directly_is_refused(self):
        # The Witcher 3 GOTY (a version-parent edition) and a Bundle.
        for record in (fetched(22439, 0, version_parent=1942), fetched(89841, 3)):
            with self.subTest(igdb_id=record.igdb_id):
                with mock.patch("games.igdb.fetch_game", return_value=record):
                    response = self.post(igdb_id=str(record.igdb_id), q="witcher")
                with mock.patch("games.igdb.search_games", return_value=[]):
                    [message] = messages_html(self.client.get(response["Location"]))
                self.assertIn(
                    escape(
                        "This release can't be saved. Search for the base game or a "
                        "supported release."
                    ),
                    message,
                )
        self.assertEqual(Game.objects.count(), 0)


class MethodAndAuthTests(TestCase):
    def test_get_is_rejected_and_saves_nothing(self):
        self.client.force_login(make_user("saver"))
        make_game("Stored", igdb_id=4242)
        with mock.patch("games.igdb.fetch_game") as fetch:
            response = self.client.get(SAVE_URL, {"igdb_id": "4242"})
        self.assertEqual(response.status_code, 405)
        fetch.assert_not_called()
        self.assertEqual(Entry.objects.count(), 0)

    def test_signed_out_post_redirects_to_login_and_saves_nothing(self):
        make_game("Stored", igdb_id=4242)
        with mock.patch("games.igdb.fetch_game") as fetch:
            response = self.client.post(SAVE_URL, {"igdb_id": "4242"})
        self.assertRedirects(
            response, f"{reverse('login')}?next={SAVE_URL}", fetch_redirect_response=False
        )
        fetch.assert_not_called()
        self.assertEqual(Entry.objects.count(), 0)

    def test_post_without_a_csrf_token_is_rejected(self):
        user = make_user("saver")
        make_game("Stored", igdb_id=4242)
        with mock.patch("games.igdb.search_games", return_value=[]):
            client, token = csrf_client(user, SEARCH_URL + "?q=stored")
        self.assertEqual(client.post(SAVE_URL, {"igdb_id": "4242"}).status_code, 403)
        self.assertEqual(Entry.objects.count(), 0)
        response = client.post(SAVE_URL, {"igdb_id": "4242", "csrfmiddlewaretoken": token})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Entry.objects.filter(owner=user).count(), 1)


class OutageSaveCheckTests(TestCase):
    """Mirrors the repeatable browser check: B loads results with one stored game and
    one new game, IGDB then fails, and B submits both already-loaded forms."""

    def test_stored_game_saves_without_igdb_and_new_game_saves_nothing(self):
        user_a, user_b = make_user("demo_a"), make_user("demo_b")
        stored = make_game("Hollow Knight", igdb_id=14593, platforms=["PC (Microsoft Windows)"])
        make_entry(user_a, stored)
        new_id = 26758
        self.client.force_login(user_b)

        # 1. While IGDB works, B's results show both games with Save forms.
        results = [
            igdb.IgdbGame(igdb_id=14593, name="Hollow Knight"),
            igdb.IgdbGame(igdb_id=new_id, name="Hollow Knight: Silksong"),
        ]
        with mock.patch("games.igdb.search_games", return_value=results):
            page = self.client.get(SEARCH_URL, {"q": "hollow knight"})
        forms = save_forms(page)
        self.assertEqual(set(forms), {14593, new_id})  # the stored game isn't "Saved" for B

        # 2. IGDB goes down (every client call fails), and B submits both loaded forms.
        outage = igdb.IgdbError("igdb_unreachable")
        with (
            mock.patch("games.igdb.fetch_game", side_effect=outage) as fetch,
            mock.patch("games.igdb.search_games", side_effect=outage),
        ):
            stored_response = self.client.post(SAVE_URL, forms[14593])
            fetch.assert_not_called()
            entry = Entry.objects.get(owner=user_b, game=stored)
            self.assertRedirects(
                stored_response,
                reverse("games:entry_edit", args=[entry.pk]),
                fetch_redirect_response=False,
            )
            self.assertEqual(entry.status, Entry.Status.WANT_TO_PLAY)
            self.assertFalse(entry.favorite)
            edit_page = self.client.get(stored_response["Location"])  # as the browser would
            self.assertContains(edit_page, "Added Hollow Knight to your games.")

            before = row_counts()
            new_response = self.client.post(SAVE_URL, forms[new_id])
            followed = self.client.get(new_response["Location"])

        fetch.assert_called_once_with(new_id)
        self.assertEqual(new_response["Location"], f"{SEARCH_URL}?q=hollow+knight")
        [message] = messages_html(followed)
        self.assertIn(escape(igdb.MESSAGES["igdb_unreachable"]), message)
        self.assertIn(f'href="{SAVED_GAMES_URL}"', message)
        self.assertEqual(row_counts(), before)
        self.assertFalse(Game.objects.filter(igdb_id=new_id).exists())
        self.assertEqual(list(Entry.objects.filter(owner=user_b)), [entry])
