# CLAUDE.md

## Project

A Django video game tracker. A signed-in user searches IGDB, saves games to a private list, and tracks status, favorite, rating, notes, platform played, dates and hours played. Saved game details are stored in SQLite, so the list stays browsable when IGDB is down. The same entries are available through a token-authenticated DRF API and a small command-line client. Entries are private: another user's entry ID always returns 404.

## Source documents (read before changing behavior)

- [prd/video-game-tracker.md](prd/video-game-tracker.md): approved PRD, the source of truth for behavior
- [plans/video-game-tracker.md](plans/video-game-tracker.md): approved 12-phase plan; the phase checklist is at the bottom
- [prototypes/saved-games-query-state.notes.md](prototypes/saved-games-query-state.notes.md): supersedes the prototype HTML (10 per page, Theme filter, badges only)
- [docs/research/game-api-comparison.md](docs/research/game-api-comparison.md): why IGDB, its limits and terms
- [docs/research/igdb-game-types.md](docs/research/igdb-game-types.md): verified `game_type` / `version_parent` rules
- `docs/verification.md`: manual verification record (created in Phase 2)
- [PROMPTS.md](PROMPTS.md): AI usage log, only written when asked (see its header)

## Stack

Python 3.14, uv, Django 6.1, SQLite, Bootstrap 5.3 and HTMX 2.x stored as static files (no CDN, no Node), Ruff (uv dev group, configured in `pyproject.toml`), and requests plus python-dotenv. Django REST Framework arrives in Phase 10, after checking that it supports Django 6.1 and Python 3.14.

## Commands (PowerShell, from the repo root)

**Work now** (Django needs `DJANGO_SECRET_KEY` in `.env`, and `DJANGO_DEBUG=True` so runserver serves static files):

```powershell
uv sync                                          # install dependencies
uv run python manage.py migrate
uv run python manage.py runserver                # http://127.0.0.1:8000/
uv run scripts/igdb_search.py "The Witcher 3"    # live IGDB check (needs .env), exit 0 on success
uv run scripts/igdb_search.py "The Witcher 3" --page 2
git check-ignore -v -- .env                      # must print the .gitignore rule
```

**Standard automated checks** (every phase from Phase 2 on):

```powershell
uv run python manage.py check
uv run python manage.py makemigrations --check --dry-run
uv run python manage.py test
uv run ruff check .
uv run ruff format --check .
```

Ruff skips `*.md` (`extend-exclude` in `pyproject.toml`), because Ruff 0.17 would otherwise reformat Python samples in the docs.

**Demo data** (needs `DEMO_PASSWORD` in `.env`; offline, safe to rerun):

```powershell
uv run python manage.py seed_demo                # creates demo_a and demo_b from games/demo_data/seed.json
```

**Later:** `uv run python manage.py drf_create_token <username>` (Phase 10), and `uv run scripts/entries_client.py list|update` (Phase 11).

## Conventions

- **Layout:** one project package, `config` (settings, root URLs), and one app, `games`, which holds models, views, API, IGDB client, save service, templates (`games/templates/games/`, auth pages in `games/templates/registration/`), static files and tests (`games/tests/`). Bootstrap 5.3.8 is vendored in `games/static/games/vendor/bootstrap-5.3.8/` (see its `SOURCE.md`). Every page extends `games/base.html`. The owner-scoped helpers (`owned_entries`, `get_owned_entry_or_404`), `parse_page` and `PAGE_SIZE` live in `games/queries.py`. Test data helpers are in `games/tests/factories.py`.
- **Demo seed:** `seed_demo` loads `games/demo_data/seed.json` (real IGDB records gathered once, entries made up). It only touches accounts marked with a `DemoAccount` row, and stops before any change if `demo_a` or `demo_b` belongs to another account. It never resets passwords or changes existing Games or entries. To regenerate the fixture, use a throwaway scratchpad script (never commit it).
- **Routes:**
  - `/games/` My Saved Games; `/games/<id>/` plus `edit/`, `delete/` and `refresh/`, where `<id>` is the **Entry** ID
  - `/search/` and `/search/save/`
  - `/api/entries/` and `/api/entries/<id>/`
  - `/accounts/…` and `/admin/`
- **Ownership:** every entry lookup on the website and API goes through the one owner-scoped helper, so another user's entry returns 404. The owner always comes from the authenticated user.
- **IGDB boundary:**
  - IGDB is called only through the client module, and only from the server.
  - Tests mock IGDB at that boundary. No automated test calls the real IGDB or Twitch APIs.
  - Search and import use `where version_parent = null & game_type = (0,1,2,4,6,7,8,9,10,11,12);`, and the save service applies the same rule to fetched and stored Games.
- **Shared logic:** one saved-entries query builder (forgiving on the website, strict in the API), one shared validation function, and one save service. Page size is 10 everywhere.
- **Front end:** pages work without JavaScript. HTMX is used only for the My Saved Games list and the IGDB search pager, with `hx-push-url`.
- **Messages:** users only see the PRD's fixed, safe messages. Exception details never appear.

## Credentials and secrets

- **Never** read, print, log or commit `.env`, IGDB credentials, Twitch tokens, API tokens or passwords. Keep them out of PROMPTS.md, docs and screenshots.
- `.env` is git-ignored, and `.env.example` holds placeholders only. Add new placeholders in the phase that first needs them.
- Settings load `.env` from the repo root, and variables already set in the shell win. IGDB credentials are optional, so Django starts without them. `DJANGO_SECRET_KEY` is required.
- `DJANGO_ENV_FILE` (optional, never in `.env`) makes settings load a different env file instead of `.env`. Tests use it to run Django without the developer's real credentials (`games/tests/test_startup.py`). Use it for manual "no IGDB credentials" checks too, because in Windows PowerShell 5.1 setting `$env:IGDB_CLIENT_ID = ""` deletes the variable and `.env` fills it back in. Check settings by printing presence booleans only, never values.
- Before staging, confirm `.env` isn't in `git diff --cached --name-only`.
- Throwaway scripts that call the live API go in the session scratchpad, not the repo, and must not print secrets.

## Per-phase workflow

Work on one phase at a time (`/implement` with the PRD and plan). Phases 1 to 3 are done.

1. Implement the phase, using `/tdd` where it fits.
2. Run the standard checks and the phase's own checks until they pass.
3. Stop for the user's manual (browser) verification, using the phase's steps.
4. **Browser bugs (Reflection Question 5):** before a fix, record the reproduction steps and a before screenshot in `docs/verification.md`. After the fix, repeat the same steps, take an after screenshot, rerun the checks, and add a test where practical. Screenshots go in `docs/verification/screenshots/` and must show no secrets.
5. The user confirms that manual verification passed.
6. Update this file if the phase changed commands, layout or conventions.
7. Mark the phase complete in the plan, update `docs/verification.md`, and update PROMPTS.md when asked.
8. One implementation commit per phase.

## Git

- **Never** stage, commit or push without the user's explicit go-ahead. Stage only the files they name.
- One commit per phase, using the commit message given in the plan.
