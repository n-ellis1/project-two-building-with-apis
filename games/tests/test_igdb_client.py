"""The IGDB client with mocked HTTP. No test here contacts Twitch or IGDB."""

import logging
from datetime import date
from unittest import mock

import requests
from django.core.cache import cache, caches
from django.test import SimpleTestCase, override_settings

from games import igdb

FAKE_CLIENT_ID = "fake-client-id-not-real"
FAKE_SECRET = "fake-secret-not-real-7f3a"
FAKE_TOKEN_1 = "fake-token-one-not-real-91b2"
FAKE_TOKEN_2 = "fake-token-two-not-real-44c8"


class FakeResponse:
    def __init__(self, status_code=200, json_data=None, headers=None):
        self.status_code = status_code
        self._json = json_data
        self.headers = headers or {}

    @property
    def ok(self):
        return 200 <= self.status_code < 400

    def json(self):
        if self._json is None:
            raise ValueError("no JSON")
        return self._json


def token_response(token, expires_in=5_000_000):
    return FakeResponse(200, {"access_token": token, "expires_in": expires_in})


class FakeHttp:
    """Stands in for `requests.post`, answering Twitch and IGDB from queued responses.

    A queued exception (for example `requests.Timeout`) is raised instead of returned.
    """

    def __init__(self, twitch=(), igdb_responses=()):
        self.twitch = list(twitch)
        self.igdb = list(igdb_responses)
        self.twitch_calls = []
        self.igdb_calls = []

    def __call__(self, url, **kwargs):
        if url == igdb.TOKEN_URL:
            self.twitch_calls.append(kwargs)
            return self._answer(self.twitch.pop(0))
        if url == igdb.IGDB_GAMES_URL:
            self.igdb_calls.append(kwargs)
            return self._answer(self.igdb.pop(0))
        raise AssertionError(f"unexpected URL {url}")

    @staticmethod
    def _answer(item):
        if isinstance(item, BaseException):
            raise item
        return item

    def igdb_tokens(self):
        return [call["headers"]["Authorization"] for call in self.igdb_calls]

    def igdb_bodies(self):
        return [call["data"] for call in self.igdb_calls]


@override_settings(IGDB_CLIENT_ID=FAKE_CLIENT_ID, IGDB_CLIENT_SECRET=FAKE_SECRET)
class TokenReuseAndRetryTests(SimpleTestCase):
    """TDD cycle 1: token reuse, one refresh and retry after a 401, no second retry."""

    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)

    def run_with(self, fake, *searches):
        with mock.patch("games.igdb.requests.post", side_effect=fake):
            return [igdb.search_games(q, page) for q, page in searches]

    def test_two_searches_reuse_one_twitch_token(self):
        fake = FakeHttp(
            twitch=[token_response(FAKE_TOKEN_1), token_response(FAKE_TOKEN_2)],
            igdb_responses=[FakeResponse(200, []), FakeResponse(200, [])],
        )
        self.run_with(fake, ("zelda", 1), ("mario", 1))

        self.assertEqual(len(fake.twitch_calls), 1)
        self.assertEqual(fake.igdb_tokens(), [f"Bearer {FAKE_TOKEN_1}"] * 2)

    def test_an_igdb_401_refreshes_the_token_once_and_retries_the_same_query(self):
        fake = FakeHttp(
            twitch=[token_response(FAKE_TOKEN_1), token_response(FAKE_TOKEN_2)],
            igdb_responses=[FakeResponse(401), FakeResponse(200, [{"id": 1, "name": "Zelda"}])],
        )
        [results] = self.run_with(fake, ("zelda", 2))

        self.assertEqual(len(fake.twitch_calls), 2)
        self.assertEqual(fake.igdb_tokens(), [f"Bearer {FAKE_TOKEN_1}", f"Bearer {FAKE_TOKEN_2}"])
        first_body, retry_body = fake.igdb_bodies()
        self.assertEqual(retry_body, first_body)
        self.assertEqual([game.name for game in results], ["Zelda"])

    def test_a_second_401_raises_igdb_misconfigured_without_another_retry(self):
        fake = FakeHttp(
            twitch=[token_response(FAKE_TOKEN_1), token_response(FAKE_TOKEN_2)],
            igdb_responses=[FakeResponse(401), FakeResponse(401)],
        )
        with self.assertRaises(igdb.IgdbError) as raised:
            self.run_with(fake, ("zelda", 1))

        self.assertEqual(raised.exception.code, "igdb_misconfigured")
        self.assertEqual(len(fake.twitch_calls), 2)
        self.assertEqual(len(fake.igdb_calls), 2)


@override_settings(IGDB_CLIENT_ID=FAKE_CLIENT_ID, IGDB_CLIENT_SECRET=FAKE_SECRET)
class TokenRegressionTests(SimpleTestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)

    def search(self, fake, q="zelda"):
        with mock.patch("games.igdb.requests.post", side_effect=fake):
            return igdb.search_games(q, 1)

    def test_an_igdb_403_raises_igdb_misconfigured_with_no_refresh_or_retry(self):
        fake = FakeHttp(
            twitch=[token_response(FAKE_TOKEN_1), token_response(FAKE_TOKEN_2)],
            igdb_responses=[FakeResponse(403), FakeResponse(200, [])],
        )
        with self.assertRaises(igdb.IgdbError) as raised:
            self.search(fake)

        self.assertEqual(raised.exception.code, "igdb_misconfigured")
        self.assertEqual(len(fake.twitch_calls), 1)
        self.assertEqual(len(fake.igdb_calls), 1)

    def test_the_token_expires_from_the_cache_shortly_before_expires_in(self):
        expires_in = 1000
        cached_for = expires_in - igdb.TOKEN_EXPIRY_MARGIN_SECONDS
        fake = FakeHttp(
            twitch=[token_response(FAKE_TOKEN_1, expires_in), token_response(FAKE_TOKEN_2)],
            igdb_responses=[FakeResponse(200, [])] * 3,
        )
        start = 1_800_000_000.0
        with mock.patch("django.core.cache.backends.locmem.time.time") as clock:
            clock.return_value = start
            self.search(fake)
            clock.return_value = start + cached_for - 1
            self.search(fake)
            clock.return_value = start + cached_for + 1
            self.search(fake)

        self.assertLess(cached_for, expires_in)
        self.assertEqual(len(fake.twitch_calls), 2)
        self.assertEqual(
            fake.igdb_tokens(),
            [f"Bearer {FAKE_TOKEN_1}", f"Bearer {FAKE_TOKEN_1}", f"Bearer {FAKE_TOKEN_2}"],
        )

    def test_the_cache_key_contains_no_credentials_or_token(self):
        fake = FakeHttp(
            twitch=[token_response(FAKE_TOKEN_1)], igdb_responses=[FakeResponse(200, [])]
        )
        self.search(fake)

        for secret in (FAKE_CLIENT_ID, FAKE_SECRET, FAKE_TOKEN_1):
            self.assertNotIn(secret, igdb.TOKEN_CACHE_KEY)
            for key in caches["default"]._cache:
                self.assertNotIn(secret, key)
        self.assertEqual(cache.get(igdb.TOKEN_CACHE_KEY), FAKE_TOKEN_1)

    def test_a_token_without_a_usable_expires_in_is_used_but_not_cached(self):
        fake = FakeHttp(
            twitch=[
                FakeResponse(200, {"access_token": FAKE_TOKEN_1}),
                token_response(FAKE_TOKEN_2, expires_in=igdb.TOKEN_EXPIRY_MARGIN_SECONDS),
                token_response(FAKE_TOKEN_1),
            ],
            igdb_responses=[FakeResponse(200, [])] * 3,
        )
        self.search(fake)
        self.search(fake)
        self.search(fake)

        self.assertEqual(len(fake.twitch_calls), 3)


# PRD "Errors and messages" table, copied verbatim.
PRD_MESSAGES = {
    "igdb_timeout": "IGDB took too long to respond. Try again in a moment.",
    "igdb_unreachable": "Couldn't reach IGDB. Try again in a moment.",
    "igdb_rate_limited": "IGDB is receiving too many requests. Wait a few seconds and try again.",
    "igdb_unavailable": "IGDB is having problems right now. Try again later.",
    "igdb_misconfigured": "Game search and imports aren't set up on this server. "
    "Your saved games are still available.",
    "igdb_game_not_found": "IGDB has no game with that ID.",
    "game_category_excluded": "This release can't be saved. "
    "Search for the base game or a supported release.",
}

# A request exception whose text includes secrets, to prove it is never passed on.
LEAKY_TEXT = f"boom {FAKE_SECRET} {FAKE_TOKEN_1} {FAKE_CLIENT_ID}"


def failure_cases():
    """(label, twitch responses, IGDB responses, expected code, expected IGDB calls)."""
    ok_token = token_response(FAKE_TOKEN_1)
    return [
        ("igdb timeout", [ok_token], [requests.Timeout(LEAKY_TEXT)], "igdb_timeout", 1),
        (
            "igdb connection error",
            [ok_token],
            [requests.ConnectionError(LEAKY_TEXT)],
            "igdb_unreachable",
            1,
        ),
        (
            "igdb other request error",
            [ok_token],
            [requests.RequestException(LEAKY_TEXT)],
            "igdb_unreachable",
            1,
        ),
        ("igdb 429", [ok_token], [FakeResponse(429)], "igdb_rate_limited", 1),
        (
            "igdb 500",
            [ok_token],
            [FakeResponse(500, {"message": LEAKY_TEXT})],
            "igdb_unavailable",
            1,
        ),
        ("igdb 502", [ok_token], [FakeResponse(502)], "igdb_unavailable", 1),
        ("igdb 503", [ok_token], [FakeResponse(503)], "igdb_unavailable", 1),
        (
            "igdb 400",
            [ok_token],
            [FakeResponse(400, {"message": LEAKY_TEXT})],
            "igdb_unavailable",
            1,
        ),
        ("igdb invalid json", [ok_token], [FakeResponse(200, None)], "igdb_unavailable", 1),
        ("igdb not a list", [ok_token], [FakeResponse(200, {"x": 1})], "igdb_unavailable", 1),
        (
            "igdb 401 twice",
            [ok_token, token_response(FAKE_TOKEN_2)],
            [FakeResponse(401), FakeResponse(401)],
            "igdb_misconfigured",
            2,
        ),
        ("igdb 403", [ok_token], [FakeResponse(403)], "igdb_misconfigured", 1),
        ("twitch 400", [FakeResponse(400, {"message": LEAKY_TEXT})], [], "igdb_misconfigured", 0),
        ("twitch 401", [FakeResponse(401)], [], "igdb_misconfigured", 0),
        ("twitch 403", [FakeResponse(403)], [], "igdb_misconfigured", 0),
        ("twitch 429", [FakeResponse(429)], [], "igdb_rate_limited", 0),
        ("twitch 500", [FakeResponse(500)], [], "igdb_unavailable", 0),
        ("twitch timeout", [requests.Timeout(LEAKY_TEXT)], [], "igdb_timeout", 0),
        ("twitch unreachable", [requests.ConnectionError(LEAKY_TEXT)], [], "igdb_unreachable", 0),
        ("twitch no token", [FakeResponse(200, {"expires_in": 100})], [], "igdb_unavailable", 0),
        ("twitch invalid json", [FakeResponse(200, None)], [], "igdb_unavailable", 0),
    ]


class CaptureLogs(logging.Handler):
    """Collects every log record from every logger, at every level."""

    def __enter__(self):
        self.records = []
        self.root = logging.getLogger()
        self.old_level = self.root.level
        self.root.addHandler(self)
        self.root.setLevel(logging.DEBUG)
        return self

    def __exit__(self, *exc):
        self.root.removeHandler(self)
        self.root.setLevel(self.old_level)

    def emit(self, record):
        self.records.append(self.format(record))


@override_settings(IGDB_CLIENT_ID=FAKE_CLIENT_ID, IGDB_CLIENT_SECRET=FAKE_SECRET)
class FailureMappingTests(SimpleTestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)

    def run_case(self, twitch, igdb_responses):
        fake = FakeHttp(twitch=twitch, igdb_responses=igdb_responses)
        with (
            CaptureLogs() as logs,
            mock.patch("games.igdb.requests.post", side_effect=fake),
            self.assertRaises(igdb.IgdbError) as raised,
        ):
            igdb.search_games("zelda", 1)
        return raised.exception, fake, logs.records

    def test_messages_are_exactly_the_prd_messages(self):
        self.assertEqual(igdb.MESSAGES, PRD_MESSAGES)

    def test_each_failure_maps_to_its_code_and_message_with_no_automatic_retry(self):
        for label, twitch, igdb_responses, code, igdb_calls in failure_cases():
            with self.subTest(label):
                cache.clear()
                error, fake, _ = self.run_case(twitch, igdb_responses)
                self.assertEqual(error.code, code)
                self.assertEqual(error.message, PRD_MESSAGES[code])
                self.assertEqual(str(error), PRD_MESSAGES[code])
                self.assertEqual(len(fake.igdb_calls), igdb_calls)
                # Only a 401 earns a second token; nothing else is retried.
                self.assertEqual(len(fake.twitch_calls), 2 if label == "igdb 401 twice" else 1)

    def test_no_secret_reaches_the_error_its_cause_logs_or_cache_keys(self):
        for label, twitch, igdb_responses, _code, _calls in failure_cases():
            with self.subTest(label):
                cache.clear()
                error, _, records = self.run_case(twitch, igdb_responses)
                exposed = [str(error), repr(error), repr(error.args), error.message]
                exposed += records
                exposed += [str(key) for key in caches["default"]._cache]
                # The original request exception (whose text holds secrets) is never
                # chained on, so tracebacks can't show it either.
                self.assertIsNone(error.__cause__)
                self.assertTrue(error.__context__ is None or error.__suppress_context__)
                for secret in (FAKE_SECRET, FAKE_TOKEN_1, FAKE_TOKEN_2):
                    for text in exposed:
                        self.assertNotIn(secret, text)

    def test_429_keeps_a_valid_retry_after_and_drops_anything_else(self):
        cases = [
            ("7", 7),
            ("0", 0),
            (" 30 ", 30),
            (None, None),
            ("", None),
            ("-1", None),
            ("2.5", None),
            ("Wed, 21 Oct 2026 07:28:00 GMT", None),
            ("９", None),
        ]
        for header, expected in cases:
            with self.subTest(header=header):
                cache.clear()
                headers = {} if header is None else {"Retry-After": header}
                error, fake, _ = self.run_case(
                    [token_response(FAKE_TOKEN_1)], [FakeResponse(429, headers=headers)]
                )
                self.assertEqual(error.code, "igdb_rate_limited")
                self.assertEqual(error.retry_after, expected)
                self.assertEqual(len(fake.igdb_calls), 1)

    def test_missing_credentials_raise_misconfigured_without_any_request(self):
        for client_id, secret in (("", FAKE_SECRET), (FAKE_CLIENT_ID, ""), ("  ", "  "), ("", "")):
            with (
                self.subTest(client_id=bool(client_id.strip()), secret=bool(secret.strip())),
                override_settings(IGDB_CLIENT_ID=client_id, IGDB_CLIENT_SECRET=secret),
                mock.patch("games.igdb.requests.post") as post,
                self.assertRaises(igdb.IgdbError) as raised,
            ):
                igdb.search_games("zelda", 1)
            self.assertEqual(raised.exception.code, "igdb_misconfigured")
            post.assert_not_called()


@override_settings(IGDB_CLIENT_ID=FAKE_CLIENT_ID, IGDB_CLIENT_SECRET=FAKE_SECRET)
class RequestAndParsingTests(SimpleTestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)

    def search(self, records, q="zelda", page=1):
        fake = FakeHttp(
            twitch=[token_response(FAKE_TOKEN_1)], igdb_responses=[FakeResponse(200, records)]
        )
        with mock.patch("games.igdb.requests.post", side_effect=fake):
            return igdb.search_games(q, page), fake

    def test_requests_use_a_timeout_and_credentials_stay_out_of_urls(self):
        _, fake = self.search([])
        twitch_call, igdb_call = fake.twitch_calls[0], fake.igdb_calls[0]
        self.assertEqual(twitch_call["timeout"], igdb.TIMEOUT_SECONDS)
        self.assertEqual(igdb_call["timeout"], igdb.TIMEOUT_SECONDS)
        self.assertNotIn("params", twitch_call)
        self.assertEqual(twitch_call["data"]["client_secret"], FAKE_SECRET)
        self.assertEqual(igdb_call["headers"]["Client-ID"], FAKE_CLIENT_ID)

    def test_query_body_for_page_1_and_quotes_in_the_search_text(self):
        _, fake = self.search([], q='Say "hi" \\ bye', page=1)
        lines = fake.igdb_bodies()[0].decode("utf-8").splitlines()
        self.assertEqual(lines[0], 'search "Say \\"hi\\" \\\\ bye";')
        self.assertIn(igdb.ELIGIBILITY_WHERE, lines)
        self.assertIn("limit 11;", lines)
        self.assertIn("offset 0;", lines)
        self.assertFalse(any(line.startswith("sort ") for line in lines))

    def test_records_become_games_with_dates_platforms_category_and_cover(self):
        games, _ = self.search(
            [
                {
                    "id": 880,
                    "name": "Resident Evil 2",
                    "first_release_date": 885254400,
                    "platforms": [{"id": 7, "name": "PlayStation"}, {"id": 6, "name": "PC"}],
                    "game_type": 11,
                    "cover": {"id": 1, "image_id": "co1abc"},
                },
                {"id": 1942, "name": "The Witcher 3: Wild Hunt", "game_type": 0},
                {"id": 1, "name": "Before 1970", "first_release_date": -86400},
                {"name": "No ID, dropped"},
                "not a record",
            ]
        )
        re2, witcher, old = games
        self.assertEqual(len(games), 3)
        self.assertEqual(re2.igdb_id, 880)
        self.assertEqual(re2.first_release_date, date(1998, 1, 20))
        self.assertEqual(re2.platforms, ("PlayStation", "PC"))
        self.assertEqual(re2.category_badge, "Port")
        self.assertEqual(re2.cover_image_id, "co1abc")
        self.assertEqual(witcher.category_badge, "")
        self.assertIsNone(witcher.first_release_date)
        self.assertEqual(witcher.platforms, ())
        self.assertEqual(witcher.cover_image_id, "")
        self.assertEqual(old.first_release_date, date(1969, 12, 31))
