"""List your saved games and update an entry's status through the REST API.

Run from the repo root while the Django server is running:

    uv run scripts/entries_client.py list
    uv run scripts/entries_client.py list --q "dark souls" --status want_to_play --page 2
    uv run scripts/entries_client.py update 7 Playing

Settings come from the environment or from the repo's local .env file (see
.env.example). Variables already set in the environment take precedence over .env.

    GAME_TRACKER_TOKEN    required: your API token (manage.py drf_create_token <username>)
    GAME_TRACKER_API_URL  optional: the API root (default http://127.0.0.1:8000/api/)

Exit codes: 0 = success, 1 = configuration, request or API error, 2 = usage error.

Secrets policy: the token is sent only in the Authorization header and is never
printed. Every message is also scrubbed of the token before it is shown.

This script deliberately imports no Django code, so it tests the API from outside.
"""

import argparse
import os
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

DEFAULT_API_URL = "http://127.0.0.1:8000/api/"
TIMEOUT_SECONDS = 10
REPO_ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = REPO_ROOT / ".env"

# The API's status values and their labels (games.models.Entry.Status). A test keeps
# this copy in step with the model, because this script can't import Django.
STATUS_LABELS = {
    "want_to_play": "Want to Play",
    "playing": "Playing",
    "completed": "Completed",
    "on_hold": "On Hold",
    "dropped": "Dropped",
}


class ClientError(Exception):
    """An expected failure whose message is safe to show (contains no secrets)."""


# ---------------------------------------------------------------------------
# Command-line input
# ---------------------------------------------------------------------------


def positive_int(value: str) -> int:
    """argparse type for IDs and pages: a whole number of 1 or more."""
    try:
        number = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"must be a whole number, got {value!r}") from None
    if number < 1:
        raise argparse.ArgumentTypeError(f"must be 1 or higher, got {number}")
    return number


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="List your saved games or update an entry's status through the API.",
    )
    commands = parser.add_subparsers(dest="command", required=True, metavar="{list,update}")

    list_parser = commands.add_parser("list", help="list your saved games (10 per page)")
    list_parser.add_argument(
        "--q",
        "--search",
        dest="q",
        default="",
        help="search text: title, summary, platform, genre, theme or notes (as on the site)",
    )
    list_parser.add_argument(
        "--status", default="", help='status filter, e.g. want_to_play or "Want to Play"'
    )
    list_parser.add_argument(
        "--page", type=positive_int, default=1, help="page to show, starting at 1 (default: 1)"
    )

    update_parser = commands.add_parser("update", help="change one entry's status")
    update_parser.add_argument("entry_id", type=positive_int, help="the entry ID")
    update_parser.add_argument(
        "status",
        nargs="+",
        help='new status, e.g. Playing, completed or "Want to Play"',
    )

    args = parser.parse_args(argv)
    if args.command == "update":
        args.status = " ".join(args.status)
    return args


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


def load_config() -> tuple[str, str]:
    """Return (api_url, token) from the environment or .env.

    The API URL always ends with a slash, so endpoint paths can be appended.
    """
    # override=False (the default): variables already set in the shell win over .env.
    load_dotenv(ENV_FILE)
    token = os.environ.get("GAME_TRACKER_TOKEN", "").strip()
    if not token:
        raise ClientError(
            "Missing GAME_TRACKER_TOKEN. Create a token with "
            "`uv run python manage.py drf_create_token <username>` and store it in .env "
            "as GAME_TRACKER_TOKEN (see README)."
        )
    api_url = os.environ.get("GAME_TRACKER_API_URL", "").strip() or DEFAULT_API_URL
    if not api_url.endswith("/"):
        api_url += "/"
    return api_url, token


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------


def api_request(method: str, url: str, token: str, **kwargs) -> requests.Response:
    """Send one request with the token header and a timeout.

    Exception text from requests is never shown or chained: our messages say
    everything the user needs.
    """
    headers = {"Authorization": f"Token {token}", "Accept": "application/json"}
    try:
        return requests.request(method, url, headers=headers, timeout=TIMEOUT_SECONDS, **kwargs)
    except requests.Timeout:
        raise ClientError(
            f"Server unavailable: no response from {url} within {TIMEOUT_SECONDS} seconds."
        ) from None
    except requests.ConnectionError:
        raise ClientError(
            f"Server unavailable: could not connect to {url}. "
            "Start it with `uv run python manage.py runserver`, or check GAME_TRACKER_API_URL."
        ) from None
    except requests.RequestException:
        raise ClientError("The request failed before a response arrived.") from None


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


def normalize_status(text: str) -> str:
    """A typed status -> the API value, ignoring case, spaces, hyphens and underscores
    ("Playing", "want_to_play", "Want to Play"). Anything unrecognized is sent as
    typed, so the API's own validation error is what the user sees."""
    key = "_".join(text.lower().replace("-", " ").replace("_", " ").split())
    return key if key in STATUS_LABELS else text.strip()


def status_label(value) -> str:
    """An API status value -> its label (an unexpected value is shown as sent)."""
    if not isinstance(value, str):
        return str(value)
    return STATUS_LABELS.get(value, value)


def validation_messages(response: requests.Response) -> list[str]:
    """DRF's 400 body as "field: message" lines (field-less errors without a prefix).

    Only the API's own messages are shown; `main` still scrubs the token from them.
    """
    try:
        body = response.json()
    except ValueError:
        return []
    if not isinstance(body, dict):
        return []
    lines = []
    for field, messages in body.items():
        if field == "code":  # the machine code that accompanies "detail"
            continue
        if not isinstance(messages, list):
            messages = [messages]
        prefix = "" if field in ("detail", "non_field_errors") else f"{field}: "
        lines += [f"{prefix}{message}" for message in messages]
    return lines


def check_response(response: requests.Response, not_found: str) -> requests.Response:
    """Return the response if it succeeded, else raise a safe, fixed message
    (for 400, the API's field errors)."""
    code = response.status_code
    if code == 401:
        raise ClientError(
            "The API rejected GAME_TRACKER_TOKEN (HTTP 401). Check the token in .env, or "
            "create a new one with `uv run python manage.py drf_create_token -r <username>`."
        )
    if code == 400:
        lines = validation_messages(response)
        if not lines:
            raise ClientError("The API rejected the request (HTTP 400).")
        raise ClientError(
            "The API rejected the request:\n" + "\n".join(f"  {line}" for line in lines)
        )
    if code == 404:
        raise ClientError(not_found)
    if not response.ok:
        raise ClientError(f"The API request failed (HTTP {code}).")
    return response


def parse_json(response: requests.Response) -> dict:
    """The response body, which must be a JSON object."""
    try:
        body = response.json()
    except ValueError:
        raise ClientError("The API sent an unexpected response (not valid JSON).") from None
    if not isinstance(body, dict):
        raise ClientError("The API sent an unexpected response (not a JSON object).")
    return body


def entry_title(entry) -> str:
    game = entry.get("game") if isinstance(entry, dict) else None
    name = game.get("name") if isinstance(game, dict) else None
    return name or "Unknown title"


def run_list(api_url: str, token: str, args: argparse.Namespace) -> str:
    """GET one page of the user's entries with the given search, status and page.

    Blank options are left out (no filter); page 1 is the API's default.
    """
    params = {}
    if args.q.strip():
        params["q"] = args.q.strip()
    if args.status.strip():
        params["status"] = normalize_status(args.status)
    if args.page != 1:
        params["page"] = args.page

    not_found = (
        f"Page {args.page} not found (invalid page): there aren't that many pages of "
        "results. Try a lower --page."
    )
    response = api_request("GET", f"{api_url}entries/", token, params=params)
    data = parse_json(check_response(response, not_found))
    results, count = data.get("results"), data.get("count")
    if not isinstance(results, list) or not isinstance(count, int):
        raise ClientError("The API sent an unexpected response (no count or results).")

    lines = [f"Total matches: {count}"]
    if results:
        lines += [f"Page {args.page}:", "", f"{'ID':>6}  {'Status':<12}  Title"]
        for entry in results:
            entry = entry if isinstance(entry, dict) else {}
            entry_id = entry.get("id", "?")
            label = status_label(entry.get("status"))
            lines.append(f"{entry_id:>6}  {label:<12}  {entry_title(entry)}")
        lines.append("")
    else:
        lines.append("No saved games match." if args.page == 1 else f"Page {args.page} is empty.")
    if data.get("next"):
        lines.append(f"Another page: yes (run again with --page {args.page + 1})")
    else:
        lines.append("Another page: no")
    return "\n".join(lines)


def run_update(api_url: str, token: str, args: argparse.Namespace) -> str:
    """GET the entry, PATCH only its status, and report both statuses as the
    server returned them (before from the GET, after from the PATCH response)."""
    url = f"{api_url}entries/{args.entry_id}/"
    # The API answers 404 for a missing ID and for another user's entry alike.
    not_found = f"Entry {args.entry_id} not found. It doesn't exist or isn't one of your entries."
    before = parse_json(check_response(api_request("GET", url, token), not_found))
    patch = api_request("PATCH", url, token, json={"status": normalize_status(args.status)})
    after = parse_json(check_response(patch, not_found))
    return "\n".join(
        [
            f"Entry {args.entry_id}: {entry_title(after)}",
            f"Previous status: {status_label(before.get('status'))}",
            f"Updated status:  {status_label(after.get('status'))}",
        ]
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def redact(text: str, token: str) -> str:
    """Last line of defense: never show the token, whatever a message contains."""
    return text.replace(token, "[hidden]") if token else text


def main(argv: list[str] | None = None) -> int:
    # Game titles can contain characters the Windows console encoding lacks;
    # replace them instead of crashing.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")

    args = parse_args(argv)  # exits with code 2 on usage errors
    token = ""
    try:
        api_url, token = load_config()
        command = run_list if args.command == "list" else run_update
        output = command(api_url, token, args)
    except ClientError as error:
        print(redact(f"Error: {error}", token), file=sys.stderr)
        return 1

    print(redact(output, token))
    return 0


if __name__ == "__main__":
    sys.exit(main())
