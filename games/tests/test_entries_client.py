"""Unit tests for `scripts/entries_client.py`, with HTTP mocked.

The script isn't a package and imports no Django code, so it's loaded by file path.
`manage.py test` loads the developer's real `.env` into `os.environ`, so every test
runs inside `client_env()`, which removes the real GAME_TRACKER_* values, sets fake
ones and stubs `.env` loading. No test here makes a network request.
"""

import contextlib
import importlib.util
import io
import os
from pathlib import Path
from unittest import mock

from django.test import SimpleTestCase

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "entries_client.py"
_spec = importlib.util.spec_from_file_location("entries_client", SCRIPT)
entries_client = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(entries_client)

FAKE_TOKEN = "fake-token-0123456789abcdef"
API_URL = "http://testserver.invalid/api/"


class FakeResponse:
    def __init__(self, status_code: int, body=None):
        self.status_code = status_code
        self._body = body

    @property
    def ok(self) -> bool:
        return self.status_code < 400

    def json(self):
        if self._body is None:
            raise ValueError("no JSON body")
        return self._body


class FakeHttp:
    """Stands in for `requests.request`: records every call and replays queued
    responses (or raises queued exceptions) in order."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, method, url, **kwargs):
        self.calls.append({"method": method, "url": url, **kwargs})
        if not self.responses:
            raise AssertionError(f"Unexpected extra request: {method} {url}")
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response


@contextlib.contextmanager
def client_env(token: str | None = FAKE_TOKEN, api_url: str | None = API_URL):
    """Fake GAME_TRACKER_* values only, with `.env` loading stubbed out."""
    with mock.patch.dict(os.environ):
        os.environ.pop("GAME_TRACKER_TOKEN", None)
        os.environ.pop("GAME_TRACKER_API_URL", None)
        if token is not None:
            os.environ["GAME_TRACKER_TOKEN"] = token
        if api_url is not None:
            os.environ["GAME_TRACKER_API_URL"] = api_url
        with mock.patch.object(entries_client, "load_dotenv") as load_dotenv:
            yield load_dotenv


def run_client(argv, http: FakeHttp, **env) -> tuple[int, str, str]:
    """Run `main(argv)` with fake settings and fake HTTP; return (code, stdout, stderr)."""
    stdout, stderr = io.StringIO(), io.StringIO()
    with (
        client_env(**env),
        mock.patch.object(entries_client.requests, "request", http),
        contextlib.redirect_stdout(stdout),
        contextlib.redirect_stderr(stderr),
    ):
        code = entries_client.main(argv)
    return code, stdout.getvalue(), stderr.getvalue()


def entry_body(entry_id: int, status: str, title: str = "Hollow Knight") -> dict:
    """An API entry, trimmed to what the client reads plus a few other fields."""
    return {
        "id": entry_id,
        "game": {"igdb_id": 14593, "name": title},
        "status": status,
        "favorite": False,
        "rating": None,
        "notes": "",
    }


class UpdateReportsServerStatusBeforeAndAfterTests(SimpleTestCase):
    """TDD behavior 1: update GETs first, PATCHes only status, and prints the
    previous status from the GET and the updated status from the PATCH response."""

    def test_gets_then_patches_only_status_and_prints_both_labels(self):
        http = FakeHttp(
            FakeResponse(200, entry_body(7, "want_to_play")),
            FakeResponse(200, entry_body(7, "playing")),
        )

        code, out, err = run_client(["update", "7", "Playing"], http)

        self.assertEqual(code, 0, err)
        self.assertEqual([call["method"] for call in http.calls], ["GET", "PATCH"])
        self.assertEqual(http.calls[0]["url"], API_URL + "entries/7/")
        self.assertEqual(http.calls[1]["url"], API_URL + "entries/7/")
        self.assertEqual(http.calls[1]["json"], {"status": "playing"})
        self.assertIn("Previous status: Want to Play", out)
        self.assertIn("Updated status:  Playing", out)
        self.assertEqual(err, "")

    def test_labels_come_from_the_get_and_patch_responses_not_the_input(self):
        # The server reports values that differ from what was typed: the output must
        # show what the server returned (On Hold before, Completed after).
        http = FakeHttp(
            FakeResponse(200, entry_body(7, "on_hold")),
            FakeResponse(200, entry_body(7, "completed")),
        )

        code, out, err = run_client(["update", "7", "playing"], http)

        self.assertEqual(code, 0, err)
        self.assertEqual([call["method"] for call in http.calls], ["GET", "PATCH"])
        self.assertEqual(http.calls[1]["json"], {"status": "playing"})
        self.assertIn("Previous status: On Hold", out)
        self.assertIn("Updated status:  Completed", out)
        self.assertNotIn("Playing", out)


class UpdateMissingEntryChangesNothingTests(SimpleTestCase):
    """TDD behavior 2: a 404 from the GET stops update before any PATCH.

    The API answers 404 both for an ID that doesn't exist and for another user's
    entry (owner-scoped queryset), so both get the same not-found error."""

    def test_404_from_get_prints_not_found_and_sends_no_patch(self):
        for case, entry_id in [("missing ID", "999999"), ("another user's entry", "12")]:
            with self.subTest(case):
                # A PATCH success is queued after the 404 so that a client which
                # wrongly carries on is caught by the assertions below.
                http = FakeHttp(
                    FakeResponse(404, {"detail": "No Entry matches the given query."}),
                    FakeResponse(200, entry_body(int(entry_id), "playing")),
                )

                code, out, err = run_client(["update", entry_id, "Playing"], http)

                self.assertEqual(code, 1)
                self.assertEqual([call["method"] for call in http.calls], ["GET"])
                self.assertEqual(http.calls[0]["url"], f"{API_URL}entries/{entry_id}/")
                self.assertEqual(out, "")
                self.assertEqual(
                    err.strip(),
                    f"Error: Entry {entry_id} not found. "
                    "It doesn't exist or isn't one of your entries.",
                )


class TokenNeverPrintedTests(SimpleTestCase):
    """TDD behavior 3: the fake token goes in the Authorization header, and never
    reaches stdout or stderr on any failure, even when the server's error body or
    the requests exception text contains it. Each failure still exits 1 with a
    useful message."""

    def test_failures_send_the_token_but_never_print_it(self):
        ok_patch = FakeResponse(200, entry_body(7, "playing"))
        cases = [
            # (case, queued responses, text the error must contain)
            (
                "401 invalid token",
                [FakeResponse(401, {"detail": f"Invalid token {FAKE_TOKEN}."}), ok_patch],
                "The API rejected GAME_TRACKER_TOKEN (HTTP 401)",
            ),
            (
                "400 validation error echoing the token",
                [
                    FakeResponse(200, entry_body(7, "want_to_play")),
                    FakeResponse(400, {"status": [f'"{FAKE_TOKEN}" is not a valid choice.']}),
                ],
                "is not a valid choice.",
            ),
            (
                "connection failure mentioning the token",
                [entries_client.requests.ConnectionError(f"refused; header Token {FAKE_TOKEN}")],
                "Server unavailable",
            ),
            (
                "404 with the token in the body",
                [FakeResponse(404, {"detail": f"Not found for {FAKE_TOKEN}."}), ok_patch],
                "Entry 7 not found",
            ),
        ]
        for case, responses, expected in cases:
            with self.subTest(case):
                http = FakeHttp(*responses)

                code, out, err = run_client(["update", "7", "Playing"], http)

                self.assertEqual(code, 1)
                self.assertEqual(http.calls[0]["headers"]["Authorization"], f"Token {FAKE_TOKEN}")
                self.assertIn(expected, err)
                self.assertTrue(err.startswith("Error: "), err)
                self.assertNotIn(FAKE_TOKEN, out)
                self.assertNotIn(FAKE_TOKEN, err)


# ---------------------------------------------------------------------------
# Further behavior (ordinary tests, written alongside the code)
# ---------------------------------------------------------------------------


def page_body(entries, count=None, next_url=None) -> dict:
    return {
        "count": len(entries) if count is None else count,
        "next": next_url,
        "previous": None,
        "results": entries,
    }


class ListTests(SimpleTestCase):
    def test_sends_supplied_options_as_query_parameters(self):
        http = FakeHttp(FakeResponse(200, page_body([])))

        code, _, err = run_client(
            ["list", "--q", "  dark souls ", "--status", "Want to Play", "--page", "2"], http
        )

        self.assertEqual(code, 0, err)
        self.assertEqual(len(http.calls), 1)
        call = http.calls[0]
        self.assertEqual(call["method"], "GET")
        self.assertEqual(call["url"], API_URL + "entries/")
        self.assertEqual(call["params"], {"q": "dark souls", "status": "want_to_play", "page": 2})
        self.assertEqual(call["headers"]["Authorization"], f"Token {FAKE_TOKEN}")
        self.assertEqual(call["timeout"], entries_client.TIMEOUT_SECONDS)

    def test_search_alias_and_blank_options_are_left_out(self):
        for argv, params in [
            (["list"], {}),
            (["list", "--q", "  ", "--status", "", "--page", "1"], {}),
            (["list", "--search", "zelda"], {"q": "zelda"}),
        ]:
            with self.subTest(argv):
                http = FakeHttp(FakeResponse(200, page_body([])))
                run_client(argv, http)
                self.assertEqual(http.calls[0]["params"], params)

    def test_prints_ids_titles_statuses_count_and_another_page(self):
        entries = [
            entry_body(7, "want_to_play", "Hollow Knight"),
            entry_body(12, "on_hold", "Dark Souls III"),
        ]
        http = FakeHttp(FakeResponse(200, page_body(entries, count=11, next_url="http://x/?p=2")))

        code, out, err = run_client(["list"], http)

        self.assertEqual(code, 0, err)
        self.assertIn("Total matches: 11", out)
        self.assertRegex(out, r"\b7\s+Want to Play\s+Hollow Knight")
        self.assertRegex(out, r"\b12\s+On Hold\s+Dark Souls III")
        self.assertIn("Another page: yes (run again with --page 2)", out)
        self.assertEqual(err, "")

    def test_last_page_says_no_other_page(self):
        http = FakeHttp(FakeResponse(200, page_body([entry_body(7, "playing")], count=11)))

        code, out, _ = run_client(["list", "--page", "2"], http)

        self.assertEqual(code, 0)
        self.assertIn("Page 2:", out)
        self.assertIn("Another page: no", out)

    def test_no_matches(self):
        http = FakeHttp(FakeResponse(200, page_body([])))

        code, out, _ = run_client(["list", "--q", "nothing"], http)

        self.assertEqual(code, 0)
        self.assertIn("Total matches: 0", out)
        self.assertIn("No saved games match.", out)
        self.assertIn("Another page: no", out)

    def test_invalid_page_404(self):
        http = FakeHttp(FakeResponse(404, {"detail": "Invalid page."}))

        code, out, err = run_client(["list", "--page", "99"], http)

        self.assertEqual(code, 1)
        self.assertEqual(out, "")
        self.assertIn("Error: Page 99 not found (invalid page)", err)

    def test_invalid_status_shows_the_api_validation_error(self):
        http = FakeHttp(
            FakeResponse(400, {"status": ["Select a valid status: want_to_play, playing."]})
        )

        code, out, err = run_client(["list", "--status", "finished"], http)

        self.assertEqual(code, 1)
        self.assertEqual(http.calls[0]["params"], {"status": "finished"})
        self.assertEqual(out, "")
        self.assertIn("The API rejected the request:", err)
        self.assertIn("status: Select a valid status: want_to_play, playing.", err)

    def test_unexpected_success_body(self):
        for body in [None, ["not", "an", "object"], {"detail": "no results key"}]:
            with self.subTest(body=body):
                http = FakeHttp(FakeResponse(200, body))
                code, out, err = run_client(["list"], http)
                self.assertEqual(code, 1)
                self.assertEqual(out, "")
                self.assertIn("unexpected response", err)


class UpdateMoreTests(SimpleTestCase):
    def test_typed_status_is_normalized_or_sent_as_typed(self):
        for typed, sent in [
            (["Want", "to", "Play"], "want_to_play"),
            (["want-to-play"], "want_to_play"),
            (["ON_HOLD"], "on_hold"),
            (["  Dropped "], "dropped"),
            (["finished"], "finished"),  # unknown: the API's validation decides
        ]:
            with self.subTest(typed):
                http = FakeHttp(
                    FakeResponse(200, entry_body(7, "playing")),
                    FakeResponse(200, entry_body(7, "playing")),
                )
                run_client(["update", "7", *typed], http)
                self.assertEqual(http.calls[1]["json"], {"status": sent})

    def test_invalid_status_prints_validation_error_and_no_success_output(self):
        http = FakeHttp(
            FakeResponse(200, entry_body(7, "want_to_play")),
            FakeResponse(400, {"status": ['"finished" is not a valid choice.']}),
        )

        code, out, err = run_client(["update", "7", "finished"], http)

        self.assertEqual(code, 1)
        self.assertEqual(out, "")
        self.assertIn('status: "finished" is not a valid choice.', err)

    def test_other_failed_responses_exit_1_without_patching_after_a_failed_get(self):
        for status_code in (403, 500, 503):
            with self.subTest(status_code):
                http = FakeHttp(
                    FakeResponse(status_code, {"detail": "nope"}),
                    FakeResponse(200, entry_body(7, "playing")),
                )
                code, out, err = run_client(["update", "7", "Playing"], http)
                self.assertEqual(code, 1)
                self.assertEqual([call["method"] for call in http.calls], ["GET"])
                self.assertEqual(out, "")
                self.assertIn(f"The API request failed (HTTP {status_code}).", err)

    def test_400_body_without_fields_gets_a_fixed_message(self):
        http = FakeHttp(
            FakeResponse(200, entry_body(7, "want_to_play")),
            FakeResponse(400, None),
        )

        code, _, err = run_client(["update", "7", "Playing"], http)

        self.assertEqual(code, 1)
        self.assertIn("The API rejected the request (HTTP 400).", err)

    def test_timeout_and_other_request_errors_are_fixed_messages(self):
        requests = entries_client.requests
        for error, expected in [
            (requests.Timeout(f"read timed out {FAKE_TOKEN}"), "Server unavailable: no response"),
            (requests.RequestException(f"boom {FAKE_TOKEN}"), "failed before a response"),
        ]:
            with self.subTest(type(error).__name__):
                code, out, err = run_client(["update", "7", "Playing"], FakeHttp(error))
                self.assertEqual(code, 1)
                self.assertEqual(out, "")
                self.assertIn(expected, err)
                self.assertNotIn(FAKE_TOKEN, err)


class StatusLabelsMatchModelTests(SimpleTestCase):
    def test_client_status_labels_match_entry_status_choices(self):
        from games.models import Entry

        self.assertEqual(entries_client.STATUS_LABELS, dict(Entry.Status.choices))


class ConfigurationTests(SimpleTestCase):
    def test_reads_the_repo_env_file(self):
        http = FakeHttp(FakeResponse(200, page_body([])))
        with (
            client_env() as load_dotenv,
            mock.patch.object(entries_client.requests, "request", http),
        ):
            with contextlib.redirect_stdout(io.StringIO()):
                entries_client.main(["list"])
        load_dotenv.assert_called_once_with(SCRIPT.parent.parent / ".env")

    def test_api_url_defaults_to_local_server(self):
        http = FakeHttp(FakeResponse(200, page_body([])))

        run_client(["list"], http, api_url=None)

        self.assertEqual(http.calls[0]["url"], "http://127.0.0.1:8000/api/entries/")

    def test_api_url_override_with_or_without_trailing_slash(self):
        for api_url in ("http://example.invalid:9000/v/api", "http://example.invalid:9000/v/api/"):
            with self.subTest(api_url):
                http = FakeHttp(
                    FakeResponse(200, entry_body(3, "playing")),
                    FakeResponse(200, entry_body(3, "dropped")),
                )
                run_client(["update", "3", "dropped"], http, api_url=api_url)
                self.assertEqual(
                    http.calls[0]["url"], "http://example.invalid:9000/v/api/entries/3/"
                )

    def test_blank_api_url_uses_default(self):
        http = FakeHttp(FakeResponse(200, page_body([])))

        run_client(["list"], http, api_url="   ")

        self.assertEqual(http.calls[0]["url"], "http://127.0.0.1:8000/api/entries/")

    def test_missing_or_blank_token_exits_1_without_a_request(self):
        for token in (None, "", "   "):
            with self.subTest(token=token):
                http = FakeHttp()
                code, out, err = run_client(["list"], http, token=token)
                self.assertEqual(code, 1)
                self.assertEqual(http.calls, [])
                self.assertEqual(out, "")
                self.assertIn("Missing GAME_TRACKER_TOKEN", err)


class UsageErrorTests(SimpleTestCase):
    def test_usage_errors_exit_2_without_a_request(self):
        for argv in [
            [],
            ["delete", "7"],
            ["update"],
            ["update", "7"],
            ["update", "seven", "Playing"],
            ["update", "0", "Playing"],
            ["list", "--page", "0"],
            ["list", "--page", "two"],
        ]:
            with self.subTest(argv):
                http = FakeHttp()
                with self.assertRaises(SystemExit) as raised:
                    run_client(argv, http)
                self.assertEqual(raised.exception.code, 2)
                self.assertEqual(http.calls, [])

    def test_successful_commands_exit_0(self):
        code, _, _ = run_client(["list"], FakeHttp(FakeResponse(200, page_body([]))))
        self.assertEqual(code, 0)


class NoDjangoImportTests(SimpleTestCase):
    def test_script_imports_no_django_code(self):
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertNotRegex(source, r"(?m)^\s*(import|from)\s+(django|rest_framework|games)\b")
