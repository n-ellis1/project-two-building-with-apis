"""End to end: `scripts/entries_client.py` as a subprocess against Django's live server.

The test database and a token created in it are the only credentials involved. The
child process gets GAME_TRACKER_API_URL (the live server) and GAME_TRACKER_TOKEN (the
test token) explicitly. Those win over the developer's `.env`, which the script's
`load_dotenv()` never overrides. IGDB and other GAME_TRACKER_* variables are left
out of the child's environment. Nothing here contacts IGDB.
"""

import os
import re
import subprocess
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

from django.test import LiveServerTestCase
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from games.models import Entry
from games.tests.factories import make_entry, make_game, make_user

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "entries_client.py"
TRACKING = [
    "status",
    "favorite",
    "rating",
    "notes",
    "platform_played",
    "start_date",
    "finish_date",
    "hours_played",
]


def tracking(entry_id: int) -> dict:
    entry = Entry.objects.get(pk=entry_id)
    return {name: getattr(entry, name) for name in TRACKING}


class EntriesClientLiveServerTests(LiveServerTestCase):
    def setUp(self):
        self.user = make_user("cli_owner")
        self.token = Token.objects.create(user=self.user).key
        # 11 entries at Want to Play (two pages) and one at Playing.
        self.waiting = [
            make_entry(self.user, make_game(f"Queue Game {n:02d}"), status="want_to_play")
            for n in range(1, 12)
        ]
        self.target = make_entry(
            self.user,
            make_game("Hollow Knight", platforms=["PC", "Nintendo Switch"]),
            status="want_to_play",
            favorite=True,
            rating=9,
            notes="Bench at the Forgotten Crossroads.",
            platform_played="Nintendo Switch",
            start_date=date(2026, 11, 1),
            hours_played=Decimal("12.5"),
        )
        make_entry(self.user, make_game("Celeste"), status="playing")
        self.other = make_entry(make_user("cli_other"), make_game("Other Game"), status="dropped")

    def run_client(self, *args: str, token=None, api_url=None) -> subprocess.CompletedProcess:
        """Run the script with the test token (or `token`) against the live server (or
        `api_url`). Asserts the token never appears in the output."""
        token = token or self.token
        env = {
            key: value
            for key, value in os.environ.items()
            if not key.startswith(("GAME_TRACKER_", "IGDB_"))
        }
        env |= {
            "GAME_TRACKER_API_URL": api_url or f"{self.live_server_url}/api/",
            "GAME_TRACKER_TOKEN": token,
            "PYTHONIOENCODING": "utf-8",
        }
        result = subprocess.run(
            [sys.executable, str(SCRIPT), *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=env,
            cwd=REPO_ROOT,
            timeout=60,
        )
        self.assertNotIn(token, result.stdout)
        self.assertNotIn(token, result.stderr)
        return result

    def api_list(self, **params) -> dict:
        client = APIClient()
        client.force_authenticate(self.user)
        response = client.get("/api/entries/", params)
        self.assertEqual(response.status_code, 200)
        return response.json()

    def listed_ids(self, output: str) -> list[int]:
        return [int(match) for match in re.findall(r"(?m)^\s+(\d+)\s{2}", output)]

    def test_list_matches_the_api_for_the_same_search_and_status(self):
        for args, params in [
            (["list"], {}),
            (["list", "--status", "want_to_play"], {"status": "want_to_play"}),
            (
                ["list", "--q", "queue", "--status", "Want to Play"],
                {"q": "queue", "status": "want_to_play"},
            ),
        ]:
            with self.subTest(args):
                result = self.run_client(*args)
                self.assertEqual(result.returncode, 0, result.stderr)
                expected = self.api_list(**params)
                self.assertIn(f"Total matches: {expected['count']}", result.stdout)
                self.assertEqual(
                    self.listed_ids(result.stdout), [entry["id"] for entry in expected["results"]]
                )
                more = "yes" if expected["next"] else "no"
                self.assertIn(f"Another page: {more}", result.stdout)

    def test_list_second_page_and_invalid_page(self):
        result = self.run_client("list", "--status", "want_to_play", "--page", "2")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Total matches: 12", result.stdout)
        self.assertEqual(len(self.listed_ids(result.stdout)), 2)
        self.assertIn("Another page: no", result.stdout)

        result = self.run_client("list", "--page", "9")
        self.assertEqual(result.returncode, 1)
        self.assertIn("Page 9 not found (invalid page)", result.stderr)

    def test_update_prints_before_and_after_and_changes_only_status(self):
        before = tracking(self.target.pk)

        result = self.run_client("update", str(self.target.pk), "Playing")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(f"Entry {self.target.pk}: Hollow Knight", result.stdout)
        self.assertIn("Previous status: Want to Play", result.stdout)
        self.assertIn("Updated status:  Playing", result.stdout)
        self.assertEqual(tracking(self.target.pk), before | {"status": "playing"})

    def test_update_failures_change_nothing(self):
        other_before = tracking(self.other.pk)
        target_before = tracking(self.target.pk)

        for entry_id in (self.other.pk, 999999):
            with self.subTest(entry_id=entry_id):
                result = self.run_client("update", str(entry_id), "Playing")
                self.assertEqual(result.returncode, 1)
                self.assertEqual(result.stdout, "")
                self.assertIn(f"Entry {entry_id} not found", result.stderr)

        result = self.run_client("update", str(self.target.pk), "finished")
        self.assertEqual(result.returncode, 1)
        self.assertIn("status:", result.stderr)
        self.assertIn("is not a valid choice", result.stderr)

        self.assertEqual(tracking(self.other.pk), other_before)
        self.assertEqual(tracking(self.target.pk), target_before)

    def test_bad_token_and_stopped_server(self):
        result = self.run_client("list", token="invalid-token-for-test")
        self.assertEqual(result.returncode, 1)
        self.assertIn("rejected GAME_TRACKER_TOKEN (HTTP 401)", result.stderr)

        # Nothing listens on port 9 (discard) of 127.0.0.1 on a dev machine.
        result = self.run_client("list", api_url="http://127.0.0.1:9/api/")
        self.assertEqual(result.returncode, 1)
        self.assertIn("Server unavailable", result.stderr)
