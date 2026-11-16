# CLAUDE.md

## Project

A Django video game tracker. A signed-in user searches IGDB, saves games to a private list, and tracks status, favorite, rating, notes, platform played, dates and hours played. Saved game details are stored in SQLite, so the list stays browsable when IGDB is down. The same entries are available through a token-authenticated DRF API and a small command-line client. Entries are private: another user's entry ID always returns 404.

## Source documents (read before changing behavior)

- [prd/video-game-tracker.md](prd/video-game-tracker.md): approved PRD, the source of truth for behavior
- [plans/video-game-tracker.md](plans/video-game-tracker.md): approved 12-phase plan; the phase checklist is at the bottom
- [prototypes/saved-games-query-state.notes.md](prototypes/saved-games-query-state.notes.md): supersedes the prototype HTML (10 per page, Theme filter, badges only)
- [docs/research/game-api-comparison.md](docs/research/game-api-comparison.md): why IGDB, its limits and terms
- [docs/research/igdb-game-types.md](docs/research/igdb-game-types.md): verified `game_type` / `version_parent` rules
- [docs/research/igdb-popscore.md](docs/research/igdb-popscore.md): verified PopScore Visits query (`popularity_type = 1`) for the "Popular on IGDB" row
- `docs/verification.md`: manual verification record (created in Phase 2)
- [PROMPTS.md](PROMPTS.md): AI usage log, only written when asked (see its header)

## Stack

Python 3.14, uv, Django 6.1, SQLite, Bootstrap 5.3 and HTMX 2.x stored as static files (no CDN, no Node), Ruff (uv dev group, configured in `pyproject.toml`), and requests plus python-dotenv. Django REST Framework 3.18.3 with its `authtoken` app (added in Phase 10; PyPI declares Django 6.1 and Python 3.14 support, checked against Django 6.1.3 and Python 3.14.7).

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

**API token:** `uv run python manage.py drf_create_token <username>` prints a token once; store it in `.env` as `GAME_TRACKER_TOKEN` and never echo it (README shows PowerShell calls that read it from `.env`).

**Command-line client** (needs `runserver` and `GAME_TRACKER_TOKEN` in `.env`; `GAME_TRACKER_API_URL` is optional, default `http://127.0.0.1:8000/api/`):

```powershell
uv run scripts/entries_client.py list --q "dark souls" --status want_to_play --page 2
uv run scripts/entries_client.py update 13 Playing   # prints previous and updated status
```

## Conventions

- **Layout:** one project package, `config` (settings, root URLs, the offline `test_runner.py`), and one app, `games`, which holds models, views, API, IGDB client, save service, templates (`games/templates/games/`, auth pages in `games/templates/registration/`), static files and tests (`games/tests/`). Bootstrap 5.3.8 and HTMX 2.0.11 are vendored in `games/static/games/vendor/bootstrap-5.3.8/` and `games/static/games/vendor/htmx-2.0.11/` (each with a `SOURCE.md` recording origin and integrity). Every page extends `games/base.html`. The owner-scoped helpers (`owned_entries`, `get_owned_entry_or_404`), `parse_page`, `PAGE_SIZE`, the saved-entries query builder and the search-term fallback (`roman_numeral_variant`, `resolve_saved_search`) live in `games/queries.py`. The IGDB client is `games/igdb.py`. Test data helpers are in `games/tests/factories.py`, including `csrf_client(user, page)` for POST tests that must enforce CSRF. Fake HTTP for client tests (`FakeHttp`, `FakeResponse`, `token_response`, fake credentials, `CaptureLogs`, `failure_cases()`) is in `games/tests/test_igdb_client.py`.
- **Save service:** `save_game(user, igdb_id)` in `games/saving.py` is the one way to save (the website's `/search/save/` and the API's create). The API passes optional `tracking` values: they are checked with `validate_tracking()` inside the write transaction (after the IGDB fetch and the Game's links), so invalid tracking raises Django's `ValidationError` and rolls back every row, and they are never applied to an existing entry. It returns `SaveResult(entry, created)`; `created=False` means already in the user's games. Order: the user's own entry (via `owned_entries`) first, then a stored Game (no IGDB call), then `igdb.fetch_game`. `is_eligible(game_category, version_parent)` in `games/models.py` is the one Python eligibility rule and runs before any write on both paths. Expected failures raise `IgdbError` with the PRD code (including `game_category_excluded` and `igdb_game_not_found`). The new Game, its links and the Entry are written in one transaction. Only an `IntegrityError` can be a duplicate, and only when the requesting user's entry is confirmed after the rollback; any other database error raises `SaveFailed` (`GENERIC_SAVE_MESSAGE`). A colliding new-Game insert is retried once as a stored Game. Race tests are a `TransactionTestCase` using `committed_elsewhere()` (`games/tests/test_save_service.py`), which commits the other request's write on a second thread; `fetched()` and `row_counts()` there build fetched records and count every table a save writes.
- **Refresh:** `refresh_game(game)` in `games/saving.py` is the one way to refresh a stored Game. It calls `igdb.fetch_game` first, outside any transaction, so a failed fetch writes nothing. It then writes the `REFRESHED_FIELDS` (both classification fields included, even a missing `game_type`, which is why `Game.game_category` is nullable since migration `0002`), the platform, genre and theme links (the same `_link_game` as saving) and `last_fetched_at` in one transaction. A database error rolls it all back and raises `RefreshFailed` (`GENERIC_REFRESH_MESSAGE`). It never checks eligibility, never touches entries, and never renames existing Platform, Genre or Theme rows (a rename would make other users' platform played values stale). The POST-only `views.entry_refresh` (`/games/<id>/refresh/`) does the owner-scoped lookup first, then the throttle, then the refresh: `cache.add(refresh_attempt_key(igdb_id), True, REFRESH_THROTTLE_SECONDS)` (`igdb:refresh_attempt:<igdb_id>`, 600 seconds, per game across all users, kept after a failure so attempts count). Throttled: `REFRESH_THROTTLED_MESSAGE`, no link, no IGDB call. It always redirects to the detail page with the validated list state (`parse_entry_query` + `parse_page`); the detail page's Refresh form posts that state as `list_querystring`. The detail page's stale-platform warning (`platform_played_stale`) matches by exact name, like the shared validation. Refresh tests (`games/tests/test_refresh.py`) control cache expiry with `CacheClock`, which swaps `time` only in Django's cache `base` and `locmem` modules.
- **Messages:** `base.html` styles messages by `message.level_tag`. A message with the extra tag `saved-games-link` (`SAVED_GAMES_LINK_TAG` in `games/views.py`) gets a "Go to My Saved Games" link; use it for upstream, configuration and unexpected failures, not for "excluded" or "not found".
- **Shared validation:** `validate_tracking(game, values, stored_platform_played=...)` in `games/validation.py` is the one cross-field check (finish date not before start date; platform played blank, currently listed, or unchanged from the stored value, matched by exact name). It raises Django's `ValidationError` keyed by field name. `EntryForm` (`games/forms.py`) calls it from `clean()`; the API serializer (`EntrySerializer.validate`) calls it with the submitted values merged over the stored ones (validation only; `update()` saves only the submitted fields with `update_fields`), and the save service calls it on create. Forms use `BootstrapFormMixin` and `games/_form_fields.html`, with `novalidate` so server errors show.
- **Covers:** `games/covers.py` is the one cover URL builder (`cover_url`, sizes, dimensions, placeholder path). Templates render covers only with `{% load game_covers %}{% cover_img game "small" %}` (or `"large"` on detail), which outputs a fixed-size, lazy `<img>`. Remote covers carry `data-cover-placeholder`; `games/static/games/js/cover-fallback.js` (deferred in `base.html`) swaps a failed one to `games/img/cover-placeholder.svg` once. The script has no automated test (no JS engine); the blocked-`images.igdb.com` browser check covers it. Covers are hotlinked, never downloaded.
- **Saved-entries query state:** request values → `parse_entry_query(user, params)` (forgiving: unknown status, sort or platform, a malformed theme, or another user's theme or platform is dropped) → frozen `EntryQuery` (`q`, `status`, `platform`, `favorite`, `theme` as an IGDB theme ID, `sort`) → `saved_entries(user, query)`, which applies `distinct()` for search and Theme before counting or paging. The seven sort values are the keys of `SORT_LABELS` (`added` is the default, then `title`, `title_desc`, `rating`, `release`, `hours`, `updated`). Missing values sort last; non-title sorts break ties by `Lower(title)` then ID, title sorts by ID. No sort may order by a many-to-many field (it would break `distinct()`). Every link is built with `saved_games_url(query, page)` or `EntryQuery.querystring(page)`, which leave out blanks, the default sort and page 1; Clear filters uses `query.without_filters()`. The Theme dropdown comes from `user_themes(user)`, the Platform Played dropdown from `user_platforms_played(user)`. The API uses `parse_entry_query_strict(user, params)` instead: same `EntryQuery`, but a bad value raises Django's `ValidationError` keyed by parameter (blank means no filter; `favorite` is `true`/`false`/`1`/`0`; theme and platform must be on the user's own entries). Both parsers share `clean_saved_search()` for `q`.
- **Search-term fallback (B2/B3):** `roman_numeral_variant(q)` is the one rule: a final standalone 2–9 becomes a Roman numeral (`Dark Souls 3` → `Dark Souls III`), anything else gives `""`. The typed term always runs first, and the variant is tried once only when the typed term finds nothing.
  - **Search IGDB:** only for an empty page 1, never after an error. If the variant finds results, the matched term becomes the search for the box, the pager and `HX-Push-Url`, with a "No matches for … Showing results for …" notice.
  - **My Saved Games:** `resolve_saved_search(user, query)` decides it with `.exists()` on the user's whole filtered list, before paging. The URL, controls and links keep the **typed** term, and only the results and notice use the matched one.
  - **API:** `EntryViewSet.list()` runs `resolve_saved_search()` exactly like My Saved Games.
- **Popular on IGDB row:** `igdb.popular_games()` makes two requests: the top 50 PopScore Visits primitives, then those games with `ELIGIBILITY_WHERE & id = (…)` and `limit 50` (IGDB's default is 10). It restores PopScore order, skips missing records and anything failing `is_eligible()`, and keeps 10. `igdb.cached_popular_games()` caches that shared list for `POPULAR_CACHE_SECONDS` (1 hour) under `igdb:popular_games` and never caches a failure. `views.popular_row(user)` adds Saved links per request with `with_saved_entries` (never cached) and returns `[]` on any `IgdbError`. `search` calls it only for a full, blank page (never for `q` or an HTMX swap). `games/_popular_row.html` sits outside `#search-region`: a CSS-only scroller where cover and title are one link to `games:igdb_game`, and any Saved link sits below that link.
- **IGDB game page:** `views.igdb_game` (`games/igdb_game.html`) reads a stored Game from SQLite (no IGDB call) or calls `fetch_game` once, never storing it. Unknown ID → 404 with the fixed message. Other failures → the fixed message (My Saved Games link per `NO_LINK_CODES`), left out when the same text is already a queued flash message (B4). It links to my entry (owner-scoped), or shows Save only when `is_eligible()`, otherwise the excluded message. Search result titles link here too. `igdb.category_badge()` is the one badge label rule for `IgdbGame` and `IgdbGameDetails`.
- **Save return target:** the game page's Save form posts `return_to=igdb_game` (`RETURN_TO_IGDB_GAME`). `search_save` then sends failures to `reverse("games:igdb_game", args=[igdb_id])` with the validated ID. Anything else, including a posted URL, `next` or an invalid ID, uses `search_url(q, page)`. Never redirect to a posted value.
- **Detail return link:** list rows link to `/games/<id>/` plus the list's query string and page, and the detail page rebuilds its My Saved Games link with `parse_entry_query` and `parse_page`, so only validated values are ever echoed.
- **Demo seed:** `seed_demo` loads `games/demo_data/seed.json` (real IGDB records gathered once, entries made up). It only touches accounts marked with a `DemoAccount` row, and stops before any change if `demo_a` or `demo_b` belongs to another account. It never resets passwords or changes existing Games or entries. To regenerate the fixture, use a throwaway scratchpad script (never commit it).
- **Saved-entry API:** `games/api.py` holds `EntryViewSet` (DRF `ModelViewSet`, registered as `api-entry` on a `DefaultRouter` in `config/urls.py`), `EntrySerializer`, the read-only nested `GameSerializer` (cover URL from `cover_url(..., "large")`) and `EntryPagination` (10 per page, `last_page_strings = ()`, set on the viewset because a settings default pointing at `games.api` is a circular import). Settings: Token then Session authentication (no credentials → 401 with `WWW-Authenticate: Token`; session writes need CSRF), `IsAuthenticated`, and `COERCE_DECIMAL_TO_STRING = False`. `get_queryset()` starts from `owned_entries()`, so every detail method on another user's entry is 404. `create()` calls `save_game(request.user, igdb_id, tracking)` and maps failures with `save_error_response()`: `CLIENT_ERROR_CODES` and `duplicate_entry` (website's `ALREADY_SAVED_MESSAGE`) → 400, other `IgdbError` codes → 503 (`Retry-After` only for `igdb_rate_limited` with a valid value), `SaveFailed` → 500 `save_failed`; all as `{"detail", "code"}`. `igdb_id` is required on create and rejected on update (`IGDB_ID_UNCHANGEABLE`); PUT fills omitted tracking fields from `put_defaults()` (model defaults) before validation. API tests live in `games/tests/test_api_*.py` (`APITestCase`; tokens are created in the test database only).
- **Command-line client:** `scripts/entries_client.py` uses only `requests` and `python-dotenv` and must never import Django, DRF or `games` code (`NoDjangoImportTests` checks this). It reads `GAME_TRACKER_TOKEN` and `GAME_TRACKER_API_URL` with `load_dotenv(ENV_FILE)` (the shell wins) and sends every request through `api_request()`, which adds the token header and a timeout and turns every `requests` exception into a fixed "Server unavailable" or similar message (`from None`). `check_response()` handles failures: 401 is a token error, 400 shows the API's field errors (`validation_messages()`), 404 uses the caller's message, any other failure is `HTTP <code>`. `update` checks the GET before sending the PATCH. `main()` passes every printed message through `redact()` as a last defense. `STATUS_LABELS` copies `Entry.Status` (`StatusLabelsMatchModelTests` keeps them in sync); `normalize_status()` accepts labels or values and sends anything else unchanged, so the API's validation decides. Exit codes: 0, 1 (configuration, request or API error), 2 (argparse). Unit tests (`games/tests/test_entries_client.py`) load the script by path and run inside `client_env()`, which removes the real `GAME_TRACKER_*` values that `manage.py test` loads from `.env` and stubs `load_dotenv`, with `FakeHttp` patched over `requests.request`. The end-to-end tests (`test_entries_client_live.py`, `LiveServerTestCase`) run it as a subprocess with a test-database token and no `GAME_TRACKER_*` or `IGDB_*` variables inherited.
- **Routes:**
  - `/games/` My Saved Games; `/games/<id>/` plus `edit/`, `delete/` and `refresh/`, where `<id>` is the **Entry** ID
  - `/search/` and `/search/save/`, and `/search/games/<igdb_id>/` (`games:igdb_game`), the IGDB game page by **IGDB** ID
  - `/api/entries/` and `/api/entries/<id>/`
  - `/accounts/…` and `/admin/`
- **Ownership:** every entry lookup on the website and API goes through the one owner-scoped helper, so another user's entry returns 404. The owner always comes from the authenticated user.
- **IGDB boundary:**
  - IGDB is called only through the client module, and only from the server.
  - Tests mock IGDB at that boundary. No automated test calls the real IGDB or Twitch APIs.
  - Search uses `where version_parent = null & game_type = (0,1,2,4,6,7,8,9,10,11,12);` (`ELIGIBILITY_WHERE`). Fetching one game by ID (`fetch_game`, for save and refresh) asks for `where id = N;` only, with no eligibility clause, so an excluded ID gets `game_category_excluded` rather than `igdb_game_not_found`, and refresh can store a reclassification. The save service applies the eligibility rule in Python to every fetched and stored Game.
  - `games/igdb.py` raises `IgdbError` with a PRD `code`, its fixed `message` (from `MESSAGES`, checked word for word against the PRD) and `retry_after` (a valid 429 `Retry-After` in seconds, else `None`). Exception text from `requests` is never chained (`from None`).
  - **Token:** the Twitch token is cached under `igdb:access_token` (no secrets in the key) for `expires_in` − 300 seconds. An IGDB 401 deletes it, fetches one fresh token and resends the same body once. A second 401, any 403, or Twitch rejecting the credentials raises `igdb_misconfigured`. Missing credentials raise it with no request. Timeouts, connection errors, 429 and 5xx are never retried.
  - **Refresh** uses the same `fetch_game` (by ID, no eligibility clause), so a game that has become ineligible can still be refreshed to store its new classification.
  - **Search:** `search_games(q, page)` asks for 11 results at offset (page − 1) × 10 with no `sort`. The view shows 10, and Next appears only if an 11th came back. Repeated identical searches are stable, but IGDB orders some equally ranked results differently depending on `limit` and `offset`, so a duplicate or skipped result at a page boundary is possible (none observed; kept as a known limitation, see the research note section 5).
  - **Client tests** patch `games.igdb.requests.post` with `FakeHttp`. **View, save-service and refresh tests** patch `games.igdb.search_games`, `games.igdb.fetch_game` and `games.igdb.popular_games`. The cache is cleared before and after each client test.
  - **Offline test guard:** `manage.py test` loads the real `.env`, so `TEST_RUNNER` is `config.test_runner.OfflineTestRunner`. It blanks `IGDB_CLIENT_ID` and `IGDB_CLIENT_SECRET` for every test, so an unmocked client raises `igdb_misconfigured` with no request (pages then behave as "not set up"). It also replaces `requests.post` for the whole run, so a test with fake credentials but no HTTP mock fails with "A test tried to make a real HTTP request". Tests that need the client still use `override_settings` with fake credentials and their own patch, which nest over the guard. Keep it: any blank Search IGDB page reaches the popular feed.
- **Shared logic:** one saved-entries query builder (forgiving on the website, strict in the API), one shared validation function, and one save service. Page size is 10 everywhere.
- **Front end:** pages work without JavaScript. HTMX is used only for the My Saved Games list and the IGDB search pager, with `hx-push-url`.
  - Search IGDB swaps `#search-region` (`games/_search_region.html`: messages, results, Saved links and the pager) with the same rules as My Saved Games: region plus a clean `HX-Push-Url` (from `search_url(q, page)`) for ordinary swaps, the full page for normal requests and history restores, `Vary` on every response, and `hx-history="false"` outside the region because Saved links reveal entry IDs. The search form itself is ordinary navigation, so a new search starts on page 1. Saved links come from one owner-scoped query per page (`with_saved_entries`).
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

Work on one phase at a time (`/implement` with the PRD and plan). Phases 1 to 11 and the follow-up after Phase 8 ("Popular on IGDB" row and IGDB game detail page) are done (still pending in `docs/verification.md` as evidence: the B1 before and after screenshots from Phase 4, the Reflection Question 4 Back-step screenshot from Phase 6, the B2 and B3 before and after screenshots from Phase 7, and the Phase 11 lesson-checkpoint terminal screenshots of `list` and `update`). Next is Phase 12.

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
