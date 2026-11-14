"""Django starts with the IGDB credentials unset (PRD story 111)."""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

IGDB_VARIABLES = ("IGDB_CLIENT_ID", "IGDB_CLIENT_SECRET")

# Runs in a fresh interpreter: load settings, run the system checks, then report
# only whether each IGDB value is present. Values are never printed.
PROBE = """
import json, os
import django
django.setup()
from django.conf import settings
from django.core.management import call_command
call_command("check")
print(json.dumps({
    "environ_has_client_id": "IGDB_CLIENT_ID" in os.environ,
    "environ_has_client_secret": "IGDB_CLIENT_SECRET" in os.environ,
    "settings_has_client_id": bool(settings.IGDB_CLIENT_ID),
    "settings_has_client_secret": bool(settings.IGDB_CLIENT_SECRET),
}))
"""


class StartupWithoutIgdbCredentialsTests(SimpleTestCase):
    def test_settings_load_and_check_passes_with_igdb_variables_unset(self):
        # Keep everything Django needs from this environment (secret key, debug
        # flag, PATH and so on), but drop both IGDB variables.
        env = {k: v for k, v in os.environ.items() if k not in IGDB_VARIABLES}
        env["DJANGO_SETTINGS_MODULE"] = "config.settings"
        env.setdefault("DJANGO_SECRET_KEY", "startup-test-only-key")

        with tempfile.TemporaryDirectory() as tmp:
            # Point settings at an empty env file so the subprocess can't reload
            # the IGDB credentials from the developer's real .env.
            empty_env_file = Path(tmp) / "empty.env"
            empty_env_file.write_text("", encoding="utf-8")
            env["DJANGO_ENV_FILE"] = str(empty_env_file)

            result = subprocess.run(
                [sys.executable, "-c", PROBE],
                cwd=settings.BASE_DIR,
                env=env,
                capture_output=True,
                text=True,
                timeout=120,
            )

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        report = json.loads(result.stdout.strip().splitlines()[-1])
        self.assertEqual(
            report,
            {
                "environ_has_client_id": False,
                "environ_has_client_secret": False,
                "settings_has_client_id": False,
                "settings_has_client_secret": False,
            },
        )
