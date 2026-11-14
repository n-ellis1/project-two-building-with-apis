"""Search IGDB for games by title to verify that API access works.

Run from the repo root:

    uv run scripts/igdb_search.py "The Witcher 3"
    uv run scripts/igdb_search.py "The Witcher 3" --page 2

Credentials come from IGDB_CLIENT_ID and IGDB_CLIENT_SECRET, read from the
environment or from the repo's local .env file (see .env.example). Variables
already set in the environment take precedence over .env.

Exit codes: 0 = search completed (with or without results),
1 = credential, network, or API error, 2 = usage error.

Secrets policy: the client secret and access token are never printed,
logged, or included in error messages.
"""

import argparse
import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import requests
from dotenv import load_dotenv

TOKEN_URL = "https://id.twitch.tv/oauth2/token"
IGDB_GAMES_URL = "https://api.igdb.com/v4/games"
PAGE_SIZE = 10
TIMEOUT_SECONDS = 10
REPO_ROOT = Path(__file__).resolve().parent.parent
REQUIRED_VARS = ("IGDB_CLIENT_ID", "IGDB_CLIENT_SECRET")
UNIX_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


class ScriptError(Exception):
    """An expected failure whose message is safe to show (contains no secrets)."""


# ---------------------------------------------------------------------------
# Command-line input
# ---------------------------------------------------------------------------


def page_number(value: str) -> int:
    """argparse type for --page: a whole number of 1 or more."""
    try:
        page = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"must be a whole number, got {value!r}") from None
    if page < 1:
        raise argparse.ArgumentTypeError(f"must be 1 or higher, got {page}")
    return page


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Search IGDB for games by title (up to 10 results per page).",
    )
    parser.add_argument("title", nargs="+", help='game title, e.g. "The Witcher 3"')
    parser.add_argument(
        "--page",
        type=page_number,
        default=1,
        help="results page to show, starting at 1 (default: 1)",
    )
    args = parser.parse_args(argv)

    # Join the words and collapse any surrounding/internal runs of whitespace.
    args.title = " ".join(" ".join(args.title).split())
    if not args.title:
        parser.error("the game title must not be blank")
    return args


# ---------------------------------------------------------------------------
# Credentials
# ---------------------------------------------------------------------------


def load_credentials() -> tuple[str, str]:
    """Return (client_id, client_secret) from the environment or .env."""
    # override=False (the default) means variables already set in the shell
    # win over .env, which lets you test with temporary dummy values.
    load_dotenv(REPO_ROOT / ".env")
    values = {name: os.environ.get(name, "").strip() for name in REQUIRED_VARS}
    missing = [name for name, value in values.items() if not value]
    if missing:
        raise ScriptError(
            f"Missing {', '.join(missing)}. Copy .env.example to .env in the "
            "repo root and fill in your Twitch application credentials."
        )
    return values["IGDB_CLIENT_ID"], values["IGDB_CLIENT_SECRET"]


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------


def post(url: str, service: str, **kwargs) -> requests.Response:
    """POST with a timeout, turning network failures into safe messages.

    Exception text from requests is deliberately not shown: it can include
    request details, and our messages say everything the user needs.
    """
    try:
        return requests.post(url, timeout=TIMEOUT_SECONDS, **kwargs)
    except requests.Timeout:
        raise ScriptError(
            f"The request to {service} timed out after {TIMEOUT_SECONDS} seconds. Try again."
        ) from None
    except requests.ConnectionError:
        raise ScriptError(
            f"Could not connect to {service}. Check your internet connection and try again."
        ) from None
    except requests.RequestException:
        raise ScriptError(f"The request to {service} failed before a response arrived.") from None


def parse_json(response: requests.Response, service: str):
    try:
        return response.json()
    except ValueError:
        raise ScriptError(f"{service} sent an unexpected response (not valid JSON).") from None


# ---------------------------------------------------------------------------
# Twitch token
# ---------------------------------------------------------------------------


def get_access_token(client_id: str, client_secret: str) -> str:
    """Request a fresh app access token (client credentials grant).

    The credentials go in the form body, not the URL, so they cannot show up
    in URLs. The token is returned to the caller and kept only in memory.
    """
    response = post(
        TOKEN_URL,
        "Twitch",
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "grant_type": "client_credentials",
        },
    )
    if response.status_code in (400, 401, 403):
        raise ScriptError(
            f"Twitch rejected the credentials (HTTP {response.status_code}). "
            "Check IGDB_CLIENT_ID and IGDB_CLIENT_SECRET in your .env file."
        )
    if not response.ok:
        raise ScriptError(f"The Twitch token request failed (HTTP {response.status_code}).")

    data = parse_json(response, "Twitch")
    token = data.get("access_token") if isinstance(data, dict) else None
    if not token:
        raise ScriptError("Twitch's response did not include an access token.")
    return token


# ---------------------------------------------------------------------------
# IGDB search
# ---------------------------------------------------------------------------


def escape_query_string(text: str) -> str:
    """Escape backslashes and double quotes for an Apicalypse string literal."""
    return text.replace("\\", "\\\\").replace('"', '\\"')


def build_query(title: str, page: int) -> str:
    offset = (page - 1) * PAGE_SIZE
    return (
        f'search "{escape_query_string(title)}";\n'
        "fields name, first_release_date, platforms.name;\n"
        f"limit {PAGE_SIZE};\n"
        f"offset {offset};\n"
    )


def search_games(client_id: str, token: str, title: str, page: int) -> list[dict]:
    headers = {
        "Client-ID": client_id,
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "Content-Type": "text/plain; charset=utf-8",
    }
    response = post(
        IGDB_GAMES_URL, "IGDB", headers=headers, data=build_query(title, page).encode("utf-8")
    )
    if response.status_code in (401, 403):
        raise ScriptError(
            f"IGDB authorization failed (HTTP {response.status_code}). "
            "The Client ID or access token was not accepted."
        )
    if response.status_code == 429:
        raise ScriptError("IGDB rate limit reached (HTTP 429). Wait a moment and try again.")
    if not response.ok:
        raise ScriptError(f"The IGDB search failed (HTTP {response.status_code}).")

    data = parse_json(response, "IGDB")
    if not isinstance(data, list):
        raise ScriptError("IGDB sent an unexpected response (expected a list of games).")
    return data


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------


def format_release_date(timestamp) -> str:
    """Unix timestamp (seconds) -> 'YYYY-MM-DD' in UTC, or 'Unknown'.

    Uses epoch + timedelta instead of datetime.fromtimestamp so dates before
    1970 (negative timestamps) also work on Windows.
    """
    if isinstance(timestamp, bool) or not isinstance(timestamp, (int, float)):
        return "Unknown"
    try:
        return (UNIX_EPOCH + timedelta(seconds=timestamp)).strftime("%Y-%m-%d")
    except OverflowError, ValueError:
        return "Unknown"


def format_platforms(platforms) -> str:
    if not isinstance(platforms, list):
        return "Unknown"
    names = [p["name"] for p in platforms if isinstance(p, dict) and p.get("name")]
    return ", ".join(names) if names else "Unknown"


def format_results(games: list[dict], title: str, page: int) -> str:
    if not games:
        if page == 1:
            return f'No matches for "{title}".'
        return f'No results on page {page} for "{title}".'

    start = (page - 1) * PAGE_SIZE + 1
    end = start + len(games) - 1
    lines = [f'Results {start}-{end} for "{title}" (page {page}):', ""]
    for number, game in enumerate(games, start=start):
        lines += [
            f"{number}. {game.get('name') or 'Unknown'}",
            f"   IGDB ID:   {game.get('id', 'Unknown')}",
            f"   Released:  {format_release_date(game.get('first_release_date'))}",
            f"   Platforms: {format_platforms(game.get('platforms'))}",
            "",
        ]
    return "\n".join(lines).rstrip()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    # Game titles can contain characters the Windows console encoding lacks;
    # replace them instead of crashing.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")

    args = parse_args(argv)  # exits with code 2 on usage errors
    try:
        client_id, client_secret = load_credentials()
        token = get_access_token(client_id, client_secret)
        games = search_games(client_id, token, args.title, args.page)
    except ScriptError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1

    print(format_results(games, args.title, args.page))
    return 0


if __name__ == "__main__":
    sys.exit(main())
