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

- **Layout:** one project package, `config` (settings, root URLs), and one app, `games`, which holds models, views, API, IGDB client, save service, templates (`games/templates/games/`, auth pages in `games/templates/registration/`), static files and tests (`games/tests/`). Bootstrap 5.3.8 and HTMX 2.0.11 are vendored in `games/static/games/vendor/bootstrap-5.3.8/` and `games/static/games/vendor/htmx-2.0.11/` (each with a `SOURCE.md` recording origin and integrity). Every page extends `games/base.html`. The owner-scoped helpers (`owned_entries`, `get_owned_entry_or_404`), `parse_page`, `PAGE_SIZE` and the saved-entries query builder live in `games/queries.py`. Test data helpers are in `games/tests/factories.py`, including `csrf_client(user, page)` for POST tests that must enforce CSRF.
- **Shared validation:** `validate_tracking(game, values, stored_platform_played=...)` in `games/validation.py` is the one cross-field check (finish date not before start date; platform played blank, currently listed, or unchanged from the stored value, matched by exact name). It raises Django's `ValidationError` keyed by field name. `EntryForm` (`games/forms.py`) calls it from `clean()`; the Phase 10 serializer must call it too, with submitted values merged over the stored ones. Forms use `BootstrapFormMixin` and `games/_form_fields.html`, with `novalidate` so server errors show.
- **Covers:** `games/covers.py` is the one cover URL builder (`cover_url`, sizes, dimensions, placeholder path). Templates render covers only with `{% load game_covers %}{% cover_img game "small" %}` (or `"large"` on detail), which outputs a fixed-size, lazy `<img>`. Remote covers carry `data-cover-placeholder`; `games/static/games/js/cover-fallback.js` (deferred in `base.html`) swaps a failed one to `games/img/cover-placeholder.svg` once. The script has no automated test (no JS engine); the blocked-`images.igdb.com` browser check covers it. Covers are hotlinked, never downloaded.
- **Saved-entries query state:** request values → `parse_entry_query(user, params)` (forgiving: unknown status, sort or platform, a malformed theme, or another user's theme or platform is dropped) → frozen `EntryQuery` (`q`, `status`, `platform`, `favorite`, `theme` as an IGDB theme ID, `sort`) → `saved_entries(user, query)`, which applies `distinct()` for search and Theme before counting or paging. The seven sort values are the keys of `SORT_LABELS` (`added` is the default, then `title`, `title_desc`, `rating`, `release`, `hours`, `updated`). Missing values sort last; non-title sorts break ties by `Lower(title)` then ID, title sorts by ID. No sort may order by a many-to-many field (it would break `distinct()`). Every link is built with `saved_games_url(query, page)` or `EntryQuery.querystring(page)`, which leave out blanks, the default sort and page 1; Clear filters uses `query.without_filters()`. The Theme dropdown comes from `user_themes(user)`, the Platform Played dropdown from `user_platforms_played(user)`. The Phase 10 API adds a strict parser that produces the same `EntryQuery`.
- **Detail return link:** list rows link to `/games/<id>/` plus the list's query string and page, and the detail page rebuilds its My Saved Games link with `parse_entry_query` and `parse_page`, so only validated values are ever echoed.
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
  - My Saved Games swaps `#saved-games-region` (`games/_saved_games_region.html`), which holds the controls and the results, so they're always rendered together from one parsed query.
  - `is_htmx_swap()` in `games/views.py` gives the region only for `HX-Request` without `HX-History-Restore-Request`; normal requests and history restores get the full page. Partial responses set `HX-Push-Url` to the clean `saved_games_url(query, shown_page)`. Every response adds `Vary: HX-Request, HX-History-Restore-Request`.
  - Pages that show private entries set `hx-history="false"` outside the swapped region, so HTMX never stores entries or notes in localStorage; Back and Forward always restore from the server.
  - Search text triggers only on submit (Enter or Apply), because swapping the input while typing would lose the caret; selects trigger on change.
- **Messages:** users only see the PRD's fixed, safe messages. Exception details never appear.

## Credentials and secrets

- **Never** read, print, log or commit `.env`, IGDB credentials, Twitch tokens, API tokens or passwords. Keep them out of PROMPTS.md, docs and screenshots.
- `.env` is git-ignored, and `.env.example` holds placeholders only. Add new placeholders in the phase that first needs them.
- Settings load `.env` from the repo root, and variables already set in the shell win. IGDB credentials are optional, so Django starts without them. `DJANGO_SECRET_KEY` is required.
- `DJANGO_ENV_FILE` (optional, never in `.env`) makes settings load a different env file instead of `.env`. Tests use it to run Django without the developer's real credentials (`games/tests/test_startup.py`). Use it for manual "no IGDB credentials" checks too, because in Windows PowerShell 5.1 setting `$env:IGDB_CLIENT_ID = ""` deletes the variable and `.env` fills it back in. Check settings by printing presence booleans only, never values.
- Before staging, confirm `.env` isn't in `git diff --cached --name-only`.
- Throwaway scripts that call the live API go in the session scratchpad, not the repo, and must not print secrets.

## Per-phase workflow

Work on one phase at a time (`/implement` with the PRD and plan). Phases 1 to 6 are done (still pending in `docs/verification.md`: Phase 4's B1 before and after screenshots, and Phase 6's Reflection Question 4 Back-step screenshot).

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
