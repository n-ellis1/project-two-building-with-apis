# Plan: Django Video Game Tracker

> Source PRD: [prd/video-game-tracker.md](../prd/video-game-tracker.md) (approved)
> Also carried forward: [prototypes/saved-games-query-state.notes.md](../prototypes/saved-games-query-state.notes.md) (supersedes the prototype HTML) and [docs/research/game-api-comparison.md](../docs/research/game-api-comparison.md)
> Planned: 2026-11-14

## How to use this plan

- **Before the first `/implement` phase:** create the initial root `CLAUDE.md` (see "Before implementation" below). Phase 1 stays a live verification and documentation checkpoint and doesn't use `/implement`.
- Implement one phase at a time with the `implement` skill (`@prd/video-game-tracker.md @plans/video-game-tracker.md implement phase <N>`).
- Story numbers refer to the PRD's User Stories list.
- Owner isolation and IGDB-outage behavior are not left to the end: every phase that touches entries or IGDB adds its own isolation/outage tests. Phase 12 re-runs the PRD's acceptance criteria as a single sweep.

### Phase workflow

1. Implement the phase (`/implement`, which runs `/tdd` where it fits).
2. Run the standard automated checks plus the phase's own checks until they pass.
3. Manual (browser) verification, done by me, using the phase's steps.
4. **Bug evidence (Reflection Question 5).** When manual verification turns up a real browser bug or usability issue:
   1. Before asking for a fix, write the exact steps that reproduce it and take a **before** screenshot.
   2. Record both in `docs/verification.md` under "Browser bugs and usability fixes". Each entry gets an ID, the phase, the steps, expected vs actual behavior, the before screenshot, the fix (with file and line references), and the after screenshot.
   3. After the fix, repeat the **same** steps and take an **after** screenshot.
   4. Then rerun the automated checks. Where it's practical, add a test that would have caught the bug.
   - Screenshots go in `docs/verification/screenshots/`. They must not show tokens, passwords or `.env` contents.
5. I confirm that manual verification passed.
6. Update `CLAUDE.md` if the phase changed anything it records: commands, layout, conventions, or new rules that came up during the phase. Do this in the same commit.
7. Mark the phase complete here, update `docs/verification.md` with the phase's results, and update PROMPTS.md.
8. **One implementation commit for that phase**, then push.

### Standard automated checks (every phase from Phase 2 on)

```powershell
uv run python manage.py check
uv run python manage.py makemigrations --check --dry-run   # no missing migrations
uv run python manage.py test                                # Django test runner; IGDB mocked at the client module boundary
uv run ruff check .
uv run ruff format --check .
```

No automated test calls the real IGDB or Twitch APIs. Phase-specific checks are listed under each phase.

### Verification record: `docs/verification.md`

Created in Phase 2 and extended in every phase after that. Phase 12 completes it. Sections:

- **Phase results:** for each phase, the manual steps run, pass or fail, and the date.
- **Browser bugs and usability fixes (Reflection Question 5):** reproduction steps with before and after screenshots, as described in the phase workflow.
- **Back/Forward query state (Reflection Question 4):** the Phase 6 browser example, with file and line references.
- **IGDB outage saves:** the Phase 8 repeatable check.
- **Acceptance criteria sweep:** each PRD acceptance criterion mapped to steps and a result (Phase 12).

It never includes tokens, passwords or `.env` contents.

### Before implementation: initial root `CLAUDE.md`

After this plan is approved, and before Phase 2 (the first `/implement` phase), add a root `CLAUDE.md` in its own commit. It covers:

- **Project and sources:** a one-paragraph summary, with links to the PRD, this plan, the prototype notes, the research, `docs/verification.md` and PROMPTS.md.
- **Stack and commands:** uv, Python 3.14, Django, DRF later, and the standard automated checks above. Commands are written for PowerShell from the repo root.
- **Conventions:** one `games` app; the `/games/` and `/api/entries/` routes; every entry lookup goes through the owner-scoped helper (404 for another user's entry); IGDB is called only through the client module and mocked at that boundary in tests; Bootstrap and HTMX are stored as static files; pages work without JS.
- **Secrets:** never read, print, log or commit `.env`, tokens or passwords; keep them out of PROMPTS.md and screenshots.
- **Workflow:** one phase at a time, stop for manual verification, record bug evidence, one commit per phase, and no committing or pushing without my go-ahead.

It's kept short and updated as part of the phase workflow (step 6) when phases change commands or conventions.

---

## Architectural decisions

Durable decisions that apply across all phases:

- **Stack**: Django 6.1 (6.1.3 verified in the prototype notes), Python 3.14, SQLite, uv, Ruff (uv dev group, configured in `pyproject.toml`). Django REST Framework, requests, python-dotenv. DRF is added in Phase 10, after checking that it supports Django 6.1 and Python 3.14.
- **Owning app**: one project package plus one app, `games`, which holds models, website views, API, IGDB client, save service, templates and static files.
- **Styling (confirmed during planning)**: **Bootstrap 5.3**, with its CSS and JS bundle stored in the app's static files (exact version recorded when added). No CDN and no Node build step, so pages look the same offline and during an IGDB outage.
- **Interactivity (confirmed during planning)**: **HTMX 2.x**, stored as one static file and used only as an optional layer:
  - **My Saved Games**: changing the search, a filter or the sort, Clear filters, and pager links swap in just the results region and update the address bar (`hx-push-url`). The URL stays the single source of query state.
  - **IGDB search pager**: Previous and Next swap in just the results region and update the address bar.
  - **Not used** for Save (it must redirect to the edit page), delete (it needs a confirmation page), Refresh (POST, then a redirect with a message), or the edit form. These stay normal forms.
  - Every page works without JavaScript. A view returns the results partial for HTMX requests and the full page otherwise, from the same query logic. HTMX only issues GET requests, so no CSRF header setup is needed.
  - The cover-placeholder script stays plain JavaScript. It listens for image `error` events in the capture phase on the document, so it also covers HTMX-swapped content.
- **URLs** (all website URLs namespaced `games:` except auth and admin):
  - `/` → redirect to My Saved Games when signed in, otherwise to login
  - `/accounts/signup/`, `/accounts/login/`, `/accounts/logout/` (logout is POST only)
  - `/games/` My Saved Games (`q`, `status`, `platform`, `favorite`, `theme`, `sort`, `page`)
  - `/games/<int:id>/` detail · `/games/<int:id>/edit/` · `/games/<int:id>/delete/` (GET confirm, POST remove) · `/games/<int:id>/refresh/` (POST only)
  - `/search/` IGDB search (`q`, `page`) · `/search/save/` (POST only; `igdb_id`, `q`, `page`)
  - `/api/entries/`, `/api/entries/<int:id>/` (DRF router)
  - `/admin/`
  - `<id>` in `/games/<id>/` is the **Entry** ID (the user's saved entry), not the Game's or IGDB's ID. Every entry lookup goes through one owner-scoped helper, so another user's entry ID returns 404.
- **Models** (in `games`):
  - `Game`: unique IGDB ID, name, slug, summary, first release date (nullable date), Game Category (IGDB `game_type` ID, labels and allowlist fixed in Phase 1), version parent (nullable IGDB game ID from `version_parent`), cover image ID, IGDB URL, last-fetched timestamp. Many-to-many to `Platform`, `Genre` and `Theme`, each with a unique IGDB ID and a name.
  - `Entry`: owner (FK to user), game (FK to `Game`, deleting an entry never deletes the Game), status (text choices, default Want to Play), favorite (default false), rating (nullable 1–10), notes, platform played (plain text, not an FK), start and finish dates (nullable), hours played (nullable, not negative), created and updated timestamps. Unique constraint on (owner, game).
- **Auth**: Django sessions for the website (sign-up signs you in, login lands on My Saved Games, safe `next` is honored). For the API, DRF `TokenAuthentication` then `SessionAuthentication`, with `IsAuthenticated` by default, so a missing token gives 401. Owner is always set from the authenticated user.
- **Query logic shared by website and API**: one saved-entries query builder (search, filters, sorts, tie-breakers, distinct). The website parses parameters **forgivingly** and the API **strictly** (prototype Option A). Page size is **10** in both.
- **Shared validation**: one validation function, used by the website form and the API serializer, covering dates and platform played (including the rule that a stale value may stay unchanged).
- **IGDB boundary**: one client module, called only from the server. It raises a typed error carrying a safe message and one of the PRD's error codes. The Twitch token is cached in Django's local-memory cache. The Phase 1 eligibility rule goes in the IGDB query's `where` clause, not in a filter after the results come back, so the "ask for 11, show 10" Next rule stays accurate: `where version_parent = null & game_type = (0,1,2,4,6,7,8,9,10,11,12);`. The same rule, as one Python function, checks fetched records and stored Games in the save service.
- **Game Category (approved in Phase 1)**: keep Main Game (0, no badge), DLC (1), Expansion (2), Standalone Expansion (4), Episode (6), Season (7), Remake (8), Remaster (9), Expanded Game (10), Port (11) and Fork (12), with IGDB's labels as badges. Exclude Bundle (3), Mod (5), Pack / Addon (13), Update (14), any future type until reviewed, and any record with a version parent. Excluded message: "This release can't be saved. Search for the base game or a supported release."
- **Environment (`.env`, git-ignored; `.env.example` placeholders added in the phase that first needs them)**: `DJANGO_SECRET_KEY`, `DJANGO_DEBUG` (Phase 2), demo password (Phase 3), `GAME_TRACKER_API_URL` (optional, default `http://127.0.0.1:8000/api/`) and `GAME_TRACKER_TOKEN` for `scripts/entries_client.py` (Phase 11), alongside the existing `IGDB_CLIENT_ID` and `IGDB_CLIENT_SECRET`.

---

## Phase 1: Verify IGDB game types (before any category rules)

**User stories**: groundwork for 13–15, 35, 68, 78 (resolves the PRD's "Open until verified" items)

**Goal**: Replace the PRD's expected Game Category field and values with verified facts, and get my decision on how every remaining type is treated, before any model or IGDB query depends on it.

**Dependencies**: None. Uses the existing `scripts/igdb_search.py` and my local `.env`. No Django code.

### What to build

A short verification note in `docs/research/` that:

1. Quotes the official IGDB docs for the games field that holds the type (expected `game_type`) and the game-types endpoint, including whether the older `category` field is deprecated.
2. Records a live list of all game-type values (ID and name), retrieved from the endpoint.
3. Records live checks, with the existing script's plain search as the baseline:
   - "The Witcher 3": the base game and Blood and Wine are kept, and the Game of the Year Edition is excluded (it has a version parent).
   - "Dark Souls III": the bundle is excluded.
   - "Resident Evil 2": the bundle found during the prototype is excluded, and Horror (19) and Survival (21) still come back as themes.
4. Proposes the keep or exclude treatment for every type, starting from the PRD's working suggestion (keep ports, expanded games, episodes and seasons; exclude mods, packs and updates) and covering any type the PRD doesn't list. Also proposes the badge label for each kept non-main type.
5. Proposes the exact `where` clause the IGDB search and import will use.

After my decision, update the PRD's "Open until verified" items with the confirmed answers.

The live queries run from a one-off script kept in the session scratchpad, which is not committed and never prints credentials or tokens. The committed script stays unchanged.

### Acceptance criteria

- [x] The field name and full value list are confirmed from both the docs and a live request (or the note marks clearly which source was blocked).
- [x] The Witcher 3, Dark Souls III and Resident Evil 2 outcomes match the PRD (or the differences are written down for my decision).
- [x] Every game type has a keep or exclude decision and a badge label, and I have approved them.
- [x] The PRD's open items are updated. No credentials or tokens appear in the note or the PRD. (PROMPTS.md is checked when the session log is written.)

**Result (2026-11-14):** see [docs/research/igdb-game-types.md](../docs/research/igdb-game-types.md). The decisions are recorded under "Game Category (approved in Phase 1)" in the architectural decisions above. A possible IGDB search-ordering issue is recorded as unconfirmed and gets checked in Phase 7 (done: see the Phase 7 result).

### Automated checks

- `uv run scripts/igdb_search.py "The Witcher 3"` still exits 0 (baseline unchanged).
- `git status` shows no `.env` and no scratch script staged.

### Manual verification

- Read the note's type table and the three search outcomes, and approve the keep/exclude list.
- Optionally, look up The Witcher 3 GOTY and Blood and Wine on igdb.com in the browser to cross-check their types.

### Commit

`Verify IGDB game types and settle Game Category rules` (docs and PRD update only).

---

## Phase 2: Project skeleton, accounts and site layout

**User stories**: 1, 2, 3, 4, 5, 9, 111 (Django starts without IGDB credentials), 115

**Goal**: A running Django site with Bootstrap styling where I can sign up, sign in, sign out, and reach an empty, login-protected My Saved Games page.

**Dependencies**: None (it can run in parallel with Phase 1, but is committed after it).

### What to build

Add Django and Ruff (dev group) to the uv project. Create the project package and the `games` app. Settings read the secret key and debug flag from `.env`. IGDB credentials are optional, so Django starts without them. Add the `.env.example` placeholders.

Base template with Bootstrap 5.3 from static files: navigation (My Saved Games, Search IGDB, the signed-in username, a Logout POST button), a messages area, and the footer "Game data and cover art from IGDB.com" linked to IGDB on every page, including the auth pages.

Sign-up with Django's user creation form (signs the new user in), Django's login view (lands on My Saved Games, honors safe `next`), POST-only logout. `/` redirects as the architecture section describes. `/games/` requires login and shows an empty state. Create `docs/verification.md` with the sections listed above. `/search/` exists as a login-protected placeholder so the nav works. Admin enabled.

### Acceptance criteria

- [x] Signing up creates the user, signs them in and lands on My Saved Games.
- [x] Login lands on My Saved Games. Opening `/games/` while signed out redirects to login and returns there afterwards. An off-site `next` is ignored.
- [x] Logout works only by POST (GET is rejected) and leaves you signed out.
- [x] `/search/` redirects signed-out visitors to login.
- [x] The footer attribution appears on every page.
- [x] `runserver` and the test suite start with the IGDB variables unset.

**Result (2026-11-14):** all standard checks pass (18 tests), and the manual steps passed (see [docs/verification.md](../docs/verification.md)). The project package is `config`. `DJANGO_ENV_FILE` lets tests and manual checks load a different env file instead of `.env` (documented in CLAUDE.md).

### Automated checks

Standard checks, plus tests for: sign-up signs in and redirects, login redirect and safe/unsafe `next`, logout GET rejected and POST works, home redirect both ways, protected pages redirect when signed out, footer present on public and protected pages, settings load with no IGDB variables.

### Manual verification (browser)

1. `uv run python manage.py runserver`, open `http://127.0.0.1:8000/`. You're redirected to login, and the page is styled with Bootstrap.
2. Sign up a new user. You're signed in on My Saved Games and the username shows in the nav.
3. Log out, open `/games/` directly, sign in, and you're returned to `/games/`.
4. Check the footer link on login, sign-up and My Saved Games.
5. Turn off Wi-Fi and reload. The styling still loads (static files, no CDN).
6. Rename `.env`'s IGDB lines temporarily (or override them as empty in PowerShell), restart, and the site still starts.

### Commit

`Add Django project, accounts and Bootstrap layout`

---

## Phase 3: Models, admin, demo seed and a basic My Saved Games list

**User stories**: 7, 9, 10, 11, 36, 46, 60 (pagination part), 63, 64, 68, 116, 117, 118

**Goal**: Real saved data in SQLite. Two seeded demo users, each seeing only their own entries on a paginated My Saved Games list (10 per page, newest first) that never contacts IGDB.

**Dependencies**: Phase 1 (Game Category values), Phase 2.

### What to build

`Game`, `Platform`, `Genre`, `Theme` and `Entry` with migrations and the constraints from the architecture section. Admin: imported game, platform, genre and theme data is read-only, and entry tracking fields are editable.

A demo seeding management command that loads stored fixture data, built from real IGDB records gathered in Phase 1. It creates two demo users with distinct entries and distinct themes: one user has Horror and Survival games, the other doesn't, and enough entries exist to fill more than one page. User A has at least one Horror game with status Playing (for the Phase 6 Back/Forward walk). At least one stored Game is saved by A but not by B (for the Phase 8 outage check). It's safe to rerun (no duplicate entries, existing accounts and passwords never overwritten). It reads the demo password from `.env` and stops with a clear message if it's missing. It never contacts IGDB.

The owner-scoped entry helper. My Saved Games lists the user's entries with title, platforms, status, favorite and Game Category badge (non-main games only), sorted Date Added (Newest First) with the PRD's tie-breakers, 10 per page, with Previous/Next. A page-parsing helper turns anything that isn't a positive integer into 1 before `get_page()`, which then handles past-the-end. Empty-list state for a user with no entries.

### Acceptance criteria

- [x] The unique (owner, game) constraint rejects a second entry for the same user and game. Deleting an entry keeps the Game.
- [x] New entries default to Want to Play and not favorite. Hours below 0 and ratings outside 1–10 are rejected at model level.
- [x] Running the seed command twice gives the same rows. Changing a demo user's password and rerunning doesn't reset it. A missing password variable stops with a clear message and creates nothing.
- [x] Demo user B's list never contains A's entries.
- [x] The page helper returns 1 for `None`, `''`, `abc`, `2.5`, `0` and `-1`, the requested page for `2`, and the last page for `99` (prototype verification table).
- [x] Badges appear only on non-main games.
- [x] The admin shows imported data read-only and entry tracking fields editable.

**Result (2026-11-15):** all standard checks pass (63 tests), and the manual steps passed (see [docs/verification.md](../docs/verification.md)). The demo password variable is `DEMO_PASSWORD` (the PRD and plan didn't name it). The command is `seed_demo`, the demo users are `demo_a` and `demo_b`, and the fixture is `games/demo_data/seed.json`. A `DemoAccount` marker model was added, so the seed stops without changes if a demo username belongs to an account it didn't create. Shared helpers are in `games/queries.py`.

### Automated checks

Standard checks, plus model/constraint tests, seed command tests (idempotent, never overwrites, missing-password error, no network: the IGDB client patched to fail if called), page-helper unit tests, list tests for isolation, order, 10 per page, and bad/past-the-end page values.

### Manual verification (browser)

1. Add the demo password (`DEMO_PASSWORD`) to `.env`, run the seed command twice, and confirm the output reports nothing duplicated.
2. Sign in as demo user A: 10 entries on page 1, Next goes to page 2, badges show on expansions/remakes.
3. Try `/games/?page=0`, `?page=abc` and `?page=-1` (page 1), then `?page=99` (last page).
4. Sign in as demo user B: none of A's games appear.
5. As a superuser in `/admin/`: Game fields can't be edited, and an Entry's status can be.

### Commit

`Add game and entry models, admin, demo seed and saved-games list`

---

## Phase 4: Entry detail page and covers

**User stories**: 8 (view), 69, 70, 71, 72, 73, 77 (attribution and last-fetched display)

**Goal**: Open any of my entries to see the large cover, game details and tracking data, with covers that never break the layout.

**Dependencies**: Phase 3.

### What to build

`/games/<id>/` through the owner-scoped helper: large cover, title, summary, release date, platforms, genres, themes, Game Category badge, all tracking fields, and "Data from IGDB" with the IGDB link and last-fetched time. The Refresh button comes in Phase 9.

One shared cover URL builder (stored image ID → IGDB image server, small size with a `_2x` high-DPI source set for lists, large for detail). Fixed width and height, lazy loading, game name as alt text. Local placeholder image when there's no cover ID. The plain-JS fallback switches a failed image to the placeholder, clears `srcset`, and doesn't retry if the placeholder itself fails. List rows link to their detail page.

### Acceptance criteria

- [x] The owner sees the full detail page. Another user's entry ID returns 404, the same as an ID that doesn't exist.
- [x] Cover URLs come from one builder. List covers have a 2x source set and detail uses the large size.
- [x] Every cover `<img>` has width, height, `loading="lazy"` and the game name as alt.
- [x] A game with no cover ID renders the placeholder without needing JS.
- [x] When covers fail, every title, platform and tracking field is still shown.

Functional verification passed on 2026-11-15 (`docs/verification.md`, Phase 4 and B1). The B1 before and after screenshots are still pending as reflection evidence.

### Automated checks

Standard checks, plus tests for: owner detail 200, other user's entry ID 404, missing ID 404, signed-out redirect, URL builder output for each size and for a missing ID, required `<img>` attributes, placeholder for no cover ID.

### Manual verification (browser)

1. As demo user A, open an entry and check the large cover, details, tracking data and the "Data from IGDB" link and time.
2. On My Saved Games at a high-DPI zoom, small covers look sharp. In DevTools (Network → throttle "Slow 3G"), the layout doesn't jump while covers load.
3. DevTools → Network → block request domain `images.igdb.com` and reload the list and detail pages. Placeholders show and all text is still there. Console shows no repeating errors.
4. Open a seeded game with no cover ID: placeholder.
5. As demo user B, paste A's entry URL: 404.

### Commit

`Add entry detail page with covers and placeholder fallback`

---

## Phase 5: Edit and delete entries

**User stories**: 8 (edit, delete), 37, 38, 39, 40, 41, 42, 43, 44, 45 (website half), 80 (rule, using seeded stale data), 81, 82, 83, 84

**Goal**: Change my tracking data with sensible validation, and remove an entry after a clear confirmation, without touching anyone else's data.

**Dependencies**: Phase 4.

### What to build

The shared validation function (finish date on or after start date when both are set; platform played blank, one of the game's current platforms, or unchanged from the stored value). It's written so the API can reuse it in Phase 10 with merged stored values.

`/games/<id>/edit/`: status, favorite, rating (1–10 or unrated), notes, platform played (dropdown of the game's platforms, plus the stored stale value when present, plus blank), start date, finish date, hours played. Bootstrap form styling with field errors. Saves redirect to detail with a message.

`/games/<id>/delete/`: GET confirmation names the game, explains that status, rating, notes and hours played will be deleted, has a Cancel link to detail and a "Remove from My Games" button. A CSRF-protected POST removes the entry and redirects to My Saved Games with a confirmation message. Edit and delete (both methods) go through the owner-scoped helper.

### Acceptance criteria

- [x] All five statuses, favorite, rating (blank or 1–10), notes, platform, dates and hours save and display.
- [x] Finish before start gives a form error. Either date may be blank for any status. Negative hours are rejected.
- [x] A platform not on the game (and not the stored value) is rejected. An entry with a stale stored platform can still have its notes edited without changing the platform. Changing it later requires a current platform or blank.
- [x] Delete GET only confirms. POST removes the entry, keeps the Game and other users' entries, and shows the message.
- [x] Another user's entry ID returns 404 for edit GET/POST and delete GET/POST, and their entry is unchanged.

**Result (2026-11-15):** all standard checks pass (113 tests), and the manual steps passed (see [docs/verification.md](../docs/verification.md)). The shared validation is `validate_tracking` in `games/validation.py`. It raises Django's `ValidationError` keyed by field (`platform_played`, `finish_date`), which DRF converts in Phase 10; the API must merge stored values before calling it. The edit form is `EntryForm` in `games/forms.py`. The seeded stale platform is `demo_b`'s Skyrim ("Nintendo Switch"). Messages: "Saved your changes to <game>." and "Removed <game> from My Games."

### Automated checks

Standard checks, plus unit tests for the shared validation function (each date and platform case, including the stale-unchanged case), edit view tests, delete view tests (GET doesn't delete, POST deletes, Game kept, message), and isolation tests for all four method/URL combinations.

### Manual verification (browser)

1. Edit an entry: set Playing, favorite, rating 8, notes, a platform, dates and hours. Check they appear on detail.
2. Enter a finish date before the start date: error on the form, nothing saved. Enter `-1` hours: error.
3. Open a seeded entry with a stale platform, change only the notes, and save. It works. Try picking a non-listed platform by editing the form in DevTools: rejected.
4. Delete: the confirmation names the game, Cancel returns to detail, Remove returns to My Saved Games with the message. Another demo user who saved the same game still has their entry.
5. As B, open A's `/edit/` and `/delete/` URLs: 404.

### Commit

`Add entry editing with shared validation and delete confirmation`

---

## Phase 6: Search, filters, Theme, sorts and pagination on My Saved Games

**User stories**: 47, 48, 49, 50, 51, 52, 53, 54, 55, 56, 57, 58, 59, 60, 61, 62, 63, 64, 65, 66, 67, 68

**Goal**: Find anything in my list by search, Status, Platform Played, Favorite and **Theme (for example Horror and Survival)**, in any of the seven sorts, 10 entries per page, all from SQLite, with HTMX updates that never lose query state.

**Dependencies**: Phase 5.

### What to build

The shared saved-entries query builder (reused by the API in Phase 10):

- Case-insensitive search across title, summary, platform names, genre names, theme names and the user's notes, with `distinct()` wherever joins can duplicate entries (search and Theme), applied before sorting and pagination.
- Filters:
  - **Status**.
  - **Platform Played** (the user's chosen value).
  - **Favorite**.
  - **Theme**: by IGDB theme ID (`?theme=19`). The dropdown lists only themes on the current user's saved games, alphabetically, regardless of other filters, with All Themes as the default.
- The seven whitelisted sorts, default Date Added (Newest First). Missing rating, release date and hours sort last. Non-title sorts break ties by title A to Z then entry ID, and title sorts by entry ID only. Title sorting is case-insensitive.

Forgiving website parsing: bad page → 1, past the end → last page, unknown sort → default, malformed or not-owned theme → ignored. Any change to search, a filter or the sort returns to page 1. Pager links keep search, filters and sort. Clear filters resets Status, Platform Played, Favorite and Theme, keeps search and sort, and returns to page 1. Empty-state message when nothing matches.

HTMX: add the HTMX static file. The filter form and pager target the results region with `hx-push-url`, so the address bar always matches the list. HTMX requests get the partial, and everything else gets the full page.

Back and Forward have to keep the URL, the visible controls and the results in agreement:

- The swapped region includes the search, filter and sort controls as well as the results. The server renders them from the same parsed query, so a restored page can't show old control values next to new results.
- A history restore that misses HTMX's cache (the `HX-History-Restore-Request` header) gets the full page, not the partial.
- The Theme dropdown, Clear filters link and pager links are rebuilt on every swap.

### Acceptance criteria

- [x] Each search field finds its entry. An entry matching on several joined values (for example a platform and a genre) appears once.
- [x] Each filter works alone and combined. The Theme dropdown shows only the user's own themes, alphabetically. Horror and Survival filter correctly for demo user A, and neither appears for demo user B.
- [x] All seven sorts order correctly, with missing values last. Reversing the title sort with the same search and filters changes the order but not the count. No entry is repeated or skipped across a page boundary on a tie.
- [x] `?sort=bogus` uses the default. `?theme=abc` and a theme only on another user's games are ignored.
- [x] Changing anything returns to page 1. Pager links keep state. Clear filters behaves as specified.
- [x] With JavaScript disabled, the same URLs give the same results as full pages.
- [x] After changing the search, a filter, the sort and the page, each Back and Forward step shows a URL, visible controls (search box, Status, Platform Played, Favorite, Theme, sort, current page) and results that all agree, with or without HTMX's history cache.
- [x] Notes text that appears only in user A's entries finds nothing for user B.
- [x] `docs/verification.md` has the Reflection Question 4 browser example, with file and line references to the code that parses the query, renders the controls, pushes the URL and handles history restores.

**Result (2026-11-15):** all standard checks pass (153 tests). The user ran the browser checklist and reported no issues; individual steps weren't confirmed one by one, so `docs/verification.md` records them as unverified in the browser alongside their automated tests. The Reflection Question 4 screenshot is still pending. Query state flows through `parse_entry_query` → `EntryQuery` → `saved_entries` in `games/queries.py`; sort URL values are `added` (default), `title`, `title_desc`, `rating`, `release`, `hours`, `updated`. HTMX 2.0.11 is vendored with its integrity checked. Ordinary HTMX requests get the `_saved_games_region.html` partial with a clean `HX-Push-Url`; normal requests and history restores get the full page, which sets `hx-history="false"` so entries and notes are never stored in localStorage.

### Automated checks

Standard checks, plus query-builder tests (each field, distinct, each filter, theme dropdown contents and isolation, each sort with nulls and tie-breakers, case-insensitive title), view tests for forgiving parameters and page-1 resets in links, Clear filters link contents, full-page vs HTMX-partial responses for the same query (`HX-Request` header), a full page for `HX-History-Restore-Request`, and the partial containing controls whose selected values match the query.

### Manual verification (browser)

1. As demo user A, choose Theme → Horror. The list updates without a full reload, the URL shows `theme=19`, and only Horror games appear. Repeat for Survival.
2. **Back/Forward walk (Reflection Question 4).** Starting from `/games/` as demo user A, change one thing at a time and note each URL:
   1. Next (page 2 of the full list)
   2. Sort → Title A to Z (back to page 1)
   3. Theme → Horror
   4. Status → Playing
   5. Search a word from one seeded Horror game's title or notes

   Then press **Back** five times and **Forward** five times. At every step, check that:
   - the address bar shows the URL noted for that step,
   - the search box, Status, Theme and sort controls show the same values as the URL,
   - the results and page number match.

   Repeat once after a hard reload partway through (this clears HTMX's history cache), so a full-page restore is checked too.
3. Record step 2 in `docs/verification.md` as the Reflection Question 4 example: the URL sequence, what agreed at each step, screenshots of one Back step, and file and line references to where the query is parsed, the controls are rendered from it, `hx-push-url` is set, and history-restore requests get the full page.
4. Click Clear filters: search and sort stay, filters reset, page 1. Press Back: the filters return in the controls, the URL and the results.
5. Hand-edit the URL with `sort=bogus`, `theme=abc`, `page=0` and `page=99`. The list still shows, using the forgiving rules.
6. Sign in as demo user B: the Theme dropdown has no Horror or Survival, and `?theme=19` is ignored.
7. Disable JavaScript in DevTools and repeat step 2: full page loads, same agreement between URL, controls and results.
8. Search for a word that matches no entry: empty-state message.

### Carried over from Phase 4 (bug B1 in `docs/verification.md`)

Detail links on My Saved Games carry the list's page (`/games/<id>/?page=2`), and the detail page's "My Saved Games" link returns to that page. It is built only from the saved-games route and a page validated by `parse_page`, and it defaults to page 1. Phase 6 extends the same return link to keep the search, filters (Status, Platform Played, Favorite, Theme) and sort, and must validate each value the same way the list does (unknown values dropped, never echoed). Add tests that a detail page opened from a searched, filtered, sorted page returns to that exact list state, and that another user's theme ID or an invalid sort isn't carried over. Repeat the B1 browser steps from a searched, filtered, sorted page 2.

### Commit

`Add search, filters, Theme, sorts and pagination to My Saved Games`

---

## Phase 7: IGDB client and IGDB search page

**User stories**: 6, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 107, 108, 109, 110, 111, 112, 113, 114

**Goal**: Search IGDB from the site, with only eligible releases shown (the Phase 1 allowlist, with no version parent), badges, "Saved" links, a correct pager, and clear, safe messages when Twitch or IGDB fails.

**Dependencies**: Phase 1 (approved rules and `where` clause), Phase 3 (models and owner helper for Saved links).

### What to build

The IGDB client module, built on the verification script's request, timeout and error-mapping approach:

- **Token**: cached in local memory with a timeout shorter than `expires_in`, under a cache key that contains no secrets. On a 401: discard, fetch a new token, retry once. A second 401, or Twitch rejecting the credentials, raises `igdb_misconfigured`.
- **Failures**: timeouts, connection errors, 429s and 5xx map to the PRD codes with no automatic retry. A 429 keeps a valid Retry-After for the API.
- **Missing credentials**: raise `igdb_misconfigured` without making a request.
- **Errors**: one typed error with a safe message and a code. Exception details and secrets never reach logs, messages or responses.

`/search/` (login required): `q` and `page`. Asks for 11 results at offset (page − 1) × 10 with the Phase 1 `where` clause, shows up to 10. Each result shows cover (small, with the 2x set), title, release date and platforms, plus a Game Category badge for non-main games. Already-saved games show a "Saved" link to the user's entry, found with one local query per page. Next only if an 11th result came back, Previous when page > 1. Links keep `q`, and a new search starts at page 1. A bad page counts as 1. "No matches." on an empty page 1, "No more results" with a page-1 link on an empty later page. Error messages appear separately, with a link to My Saved Games, and the search text stays in the box. The Save button posts to `/search/save/`, which arrives in Phase 8 (until then it is hidden). HTMX pager swaps with `hx-push-url`.

### Acceptance criteria

- [x] A cached token is reused. A new one is fetched after cache expiry. A 401 triggers exactly one refresh and retry, and a second 401 isn't retried and shows the misconfiguration message.
- [x] Timeout, unreachable, 429 and 5xx each show their exact PRD message, with no retry and with the My Saved Games link.
- [x] The outgoing query contains exactly the Phase 1 `where` clause, limit 11 and the correct offset.
- [x] **IGDB ordering check (live, resolves the unconfirmed ordering issue):** repeating the exact same search returns the same IDs in the same order on page 1 and on page 2, and no ID appears on both pages. The result is recorded in `docs/verification.md` and the verification note. If ordering isn't stable, the difference is written down for my decision before Phase 7 is committed (for example, adding a `sort` to the query).
- [x] Next appears only when 11 results came back. The empty-page messages are correct. Errors never show "No matches.".
- [x] Saved results link to the current user's entry only (another user's saved game shows as unsaved for me).
- [x] Signed-out visitors are redirected to login and IGDB is never called.
- [x] Tests check that a fake secret and fake token never appear in responses, messages, log output or cache keys.

**Result (2026-11-15):** all standard checks pass (211 tests). The user ran the browser checklist with live IGDB; individual steps weren't reported one by one, so `docs/verification.md` records them as unverified in the browser (no issue reported) alongside their automated tests. The client is `games/igdb.py`: `search_games(q, page)`, `IgdbError` (`code`, fixed `message`, `retry_after`), the token under the cache key `igdb:access_token` for `expires_in` − 300 seconds. A 401 gets one fresh token and one resend of the same body; a second 401, or any 403, raises `igdb_misconfigured` with no retry (403 rule added by the user). The search page is `games/views.py` `search` with `_search_region.html`, using the same HTMX rules as My Saved Games.
- **Ordering:** three repeated `star` runs returned identical ordered IDs on pages 1 and 2 with no overlap. Separately, changing `limit` or `offset` changed the order of some results, so a duplicate or skipped result at a page boundary is possible; neither was observed. The user chose to keep the query and order (no `sort`) and record it as a known limitation (research note section 5, PRD).
- **Browser bugs B2 and B3 (both fixed and retested by the user):** `Dark Souls 3` found nothing on Search IGDB or My Saved Games because titles use "III". The shared rule `roman_numeral_variant()` in `games/queries.py` tries a final standalone 2–9 as a Roman numeral once, only when the typed term finds nothing. Search IGDB does this for an empty page 1 and then uses the matched term for the box and pager. My Saved Games decides it with `resolve_saved_search()` on the whole filtered list before paging and keeps the typed term in the URL and controls. Phase 10's API search must reuse it (noted under Phase 10). The B2 and B3 before and after screenshots are pending reflection evidence.

### Automated checks

Standard checks, plus client tests with mocked HTTP (token caching and expiry, one 401 retry, second 401, Twitch credential rejection, timeout, connection error, 429 with and without Retry-After, 5xx, missing credentials, query body contents, secret-leak checks) and search view tests with the client mocked at its module boundary (pager rules, empty messages, error messages, query kept, Saved links scoped to owner, signed-out redirect, HTMX partial).

### Manual verification (browser, live IGDB with my real `.env`)

1. Search "The Witcher 3": the base game and Blood and Wine (with an Expansion badge) appear. The Game of the Year Edition, the Witcher 3 + Dark Souls III bundle, "Wild Hunt Remastered" (an Update) and the Enhanced Edition Redux mod don't.
2. Search "Dark Souls III" and "Resident Evil 2": no bundles, editions, mods or packs. RE2's ports, remake and remaster show Port, Remake and Remaster badges.
   - **Ordering check:** search a term with more than 10 eligible results (for example "Resident Evil 2" or "star") and note the IGDB IDs on page 1 and page 2. Repeat exactly the same two requests (same text, same pages) two more times. Record whether the IDs and their order match each time and whether any ID appears on both pages. Do the same in a scratch script with the exact query body if the browser view isn't enough to compare IDs.
3. Page through a vague search ("star"). Next disappears on the last page, Previous works, the URL updates, and the query stays in the box.
4. Hand-edit `page=abc` (page 1) and a large page (No more results, with a page-1 link). Search nonsense: "No matches.".
5. As demo user A, a seeded game shows "Saved" with a link to A's entry. As B, the same game shows as unsaved.
6. Stop the server, set dummy IGDB credentials in PowerShell, restart, and search: the misconfiguration message with the My Saved Games link. That link works and the list loads. Remove the overrides afterwards.
7. Log out and open `/search/?q=zelda`: redirected to login.

### Commit

`Add IGDB client with token caching and the IGDB search page`

---

## Phase 8: Save a game from search

**User stories**: 17 (now with a live Save button), 27, 28, 29, 30, 31, 32, 33, 34, 35, 36

**Goal**: Save a search result to my list in one click, with no duplicates, nothing half-saved, and saving a game someone else already has still working during an IGDB outage.

**Dependencies**: Phase 7.

### What to build

The save service (reused by the API in Phase 10):

1. **Game already stored**: if its stored version parent is set or its stored Game Category isn't on the allowlist, reject with `game_category_excluded` without calling IGDB. Otherwise reuse it.
2. **New game**: fetch by IGDB ID and apply both eligibility checks (version parent empty, Game Category on the allowlist), so an excluded ID sent directly is rejected. then save the Game, its platform, genre and theme links, and the Entry in one transaction. The fetch happens first, so a failure saves nothing.
3. **Unknown ID**: `igdb_game_not_found`.
4. **Integrity error on Entry create**: re-check for an entry belonging to **the same user for the same game**. Only a confirmed entry counts as a duplicate. Anything else is an unexpected error shown only as a generic safe message.

`/search/save/` (POST only, login required): `igdb_id`, `q`, `page`.

- **New save**: redirect to the entry's edit page.
- **Duplicate**: redirect to the existing entry with "Already in your games".
- **Failure**: redirect back to `/search/?q=…&page=…` with the error message, which still shows if reloading the results then fails too.

### Acceptance criteria

- [x] A new save creates the Game, its links, and an entry with Want to Play and not favorite, then lands on edit.
- [x] Saving again gives "Already in your games" on the existing entry. A simulated simultaneous save (integrity error) never creates two entries and is reported as a duplicate only when the same user's entry exists.
- [x] With the IGDB client failing, saving a game already stored by another user succeeds with no IGDB call, and saving a new game shows the error and leaves no Game, link or Entry rows.
- [x] Posting an excluded IGDB ID directly is rejected with "This release can't be saved. Search for the base game or a supported release." Test cases: a version-parent edition typed Main Game (DS3 Day One Edition), a Bundle, a Mod, a Pack / Addon, an Update, and an unknown future type ID. A stored Game with a stored version parent, or a stored Game Category off the allowlist, is also rejected (without an IGDB call).
- [x] Failure redirects keep `q` and `page`, and the message shows even when the results reload also fails.
- [x] GET on `/search/save/` is rejected. Signed-out POST redirects to login. The owner always comes from the session.

**Result (2026-11-15):** all standard checks pass (241 tests). The user ran the browser checklist and reported that it looked good; individual steps weren't reported one by one, so `docs/verification.md` records them as unverified in the browser (no issue reported) alongside their automated tests, and the outage-save run's new game title and ID as not recorded.
- **Save service** `games/saving.py` (`save_game` → `SaveResult(entry, created)`, `SaveFailed` with a generic message). The user's existing entry is checked first ("Already in your games", before eligibility; user decision). The shared rule `is_eligible()` (`games/models.py`) runs before any write on both the stored and the fetched path.
- **Fetch by ID** (`igdb.fetch_game`) asks for `where id = N;` only, with no eligibility clause, so an excluded ID gets the excluded message rather than "not found", and Phase 9 can fetch a reclassified game. Search keeps the clause. Recorded in the PRD and CLAUDE.md (user decision).
- **Failures:** only an `IntegrityError` can be a duplicate, and only when the requesting user's entry is confirmed after the rollback; other database errors give the generic message. A colliding new-Game insert is retried once as a stored Game (eligibility rechecked, no second IGDB call). Race tests use a `TransactionTestCase` with the other request committed on a second thread.

### Automated checks

Standard checks, plus save-service tests (new, reuse, stored-excluded, excluded on fetch, not found, each upstream error leaves no rows, integrity-error duplicate vs non-duplicate) and view tests (redirect targets, messages, kept query/page, double failure, method and auth). One test mirrors the repeatable outage check: render B's search results containing one stored game and one new game, then make the IGDB client fail and POST both. The stored game saves with the client uncalled. The new game shows the error, and the Game, link and Entry row counts are unchanged.

### Manual verification (browser)

1. Search "Hollow Knight" and click Save: you land on edit, and after saving the new game appears at the top of My Saved Games.
2. Go back to the search: it now shows "Saved". Re-submit the old form from a second tab: "Already in your games", still one entry.
3. Double-click Save quickly on a new result: one entry.
4. **Repeatable outage save check** (recorded in `docs/verification.md` under "IGDB outage saves"):
   1. **Setup, while IGDB is reachable.** Sign in as demo user B and search for a title whose results include:
      - **Existing:** an eligible game already stored locally because demo user A saved it, and B hasn't. It must not show "Saved" for B.
      - **New:** an eligible game not stored locally at all.

      Pick the search term from the seed data (for example a franchise name where A saved one game) and record it in `docs/verification.md`, along with both games' titles and IGDB IDs.
   2. **Confirm before the outage.** In `/admin/` (superuser, in a separate browser profile or private window), confirm the "existing" game is in Games and the "new" game's IGDB ID is not.
   3. **Keep the forms.** Leave B's results page open in its tab, so both Save forms are loaded.
   4. **Simulate the outage** without reloading that tab. Turn off Wi-Fi (the dev server keeps running locally). As a second variant, restart the server with dummy IGDB credentials, then press Back to the open results page (no reload).
   5. **Save the existing game.** You land on its edit page as a new entry for B, with Want to Play and not favorite, and no IGDB call was made.
   6. **Save the new game.** Back on the results page (from Back, or the error redirect), click Save on it. You return to the search URL with the clear outage or configuration message and the My Saved Games link. The message shows even though the results can't reload.
   7. **Check for no partial save.** My Saved Games for B shows only the existing game added. In admin, the new game's IGDB ID is still absent from Games, and there are no new Platform, Genre or Theme rows from it.
   8. **Reset for the next run.** Restore Wi-Fi (or remove the dummy credential overrides), then delete B's entry for the existing game through the confirmation page. The shared Game stays, so the check can be repeated with the same search.
5. In DevTools, change a Save form's `igdb_id` to The Witcher 3 GOTY's ID (22439) and submit: "This release can't be saved. Search for the base game or a supported release." Repeat with Dark Souls III: Day One Edition (89841, typed Main Game but with a version parent).

### Commit

`Add saving games from IGDB search through the save service`

---

## Follow-up after Phase 8: "Popular on IGDB" row and IGDB game detail page

**Recorded 2026-11-15. Complete (2026-11-15):** implemented after the Phase 8 commit and before Phase 9, and verified in the browser by the user.

**User request**: on the blank Search IGDB page, show the games most visited on IGDB, and let me open any IGDB game (saved or not) inside the tracker and save it from there.

**Dependencies**: Phase 7 (client, covers, search page), Phase 8 (`fetch_game`, save service, `/search/save/`).

### What to build

- **"Popular on IGDB" row** on `/search/`, only when there is no search term (`q` blank after cleaning), directly under the search box. One horizontally scrollable row of up to 10 cards, in rank order.
  - **Data:** IGDB PopScore, the **visits** ranking (`popularity_primitives` with the IGDB Visits popularity type). It returns game IDs only, so the client asks for more primitives than needed (for example 30–50), then fetches those games in one request with `ELIGIBILITY_WHERE` plus `id = (…)`, keeps PopScore's order, drops ineligible ones, and keeps the first 10. That's two IGDB requests per refresh, made through the one client module (same token, errors and secrets rules).
  - **Cards:** the real cover (`{% cover_img game "small" %}`, with the existing placeholder for a missing or failed cover) and the title. The cover and title together are one link to the IGDB game detail page.
  - **Cache:** the finished row (IDs, titles, cover IDs) in Django's cache under a key with no secrets, for a fixed time (proposed: 1 hour). One shared row for every user, so the cache holds no per-user data. A failed refresh is not cached as a result.
  - **Failure:** if the feed fails (any `IgdbError`) or returns nothing eligible, the row is simply left out (or replaced by a quiet one-line note); the search box and the rest of the page work as now. Never an error banner that blocks searching.
  - **Scrolling:** CSS only (`overflow-x: auto`, fixed card width), keyboard reachable links, no JavaScript needed. Covers lazy-load as everywhere else.
- **IGDB game detail page** by IGDB ID (login required), proposed route `/search/games/<int:igdb_id>/` (named `games:igdb_game`), so it can't be confused with `/games/<entry id>/`.
  - **Shows:** large cover, title, Game Category badge, summary, release date and platforms.
  - **Data source:** a stored Game is read from SQLite (works during an outage). An unstored game is fetched with `igdb.fetch_game` (one request; an unknown ID → 404 page with the fixed message; an outage → the fixed message with the My Saved Games link and the Search IGDB link).
  - **Actions:** if I already saved it, a link to **my** entry (owner-scoped lookup, the same as Saved links). Otherwise, if it is eligible, a Save button posting to the existing `/search/save/` flow. An ineligible game shows no Save button, only the excluded message. Always a link back to Search IGDB.
  - **Save from detail:** `/search/save/` gains an optional, validated return target, so a failed save from this page comes back to the detail page with the message (the target is rebuilt from the posted IGDB ID on our own route, never echoed from the request). New saves and duplicates behave as in Phase 8.
- **Search results** may link their titles to the same detail page (optional; decide during implementation). **Decided:** yes, and the Save and Saved controls stay on each result (user decision).

### Acceptance criteria

All seven are covered by automated tests. The user's browser walkthrough passed on 2026-11-15. The per-behavior record is in the Result below and in `docs/verification.md`.

- [x] With no search term, the row shows up to 10 eligible games in PopScore visits order, each with its cover (or the placeholder) and title as one link to the detail page. With a search term, the row isn't rendered and no popularity request is made.
- [x] Ineligible games in the PopScore list are skipped, and the row still fills from the following ranks.
- [x] A second blank-page load within the cache time makes no IGDB request. After expiry, the row is fetched again.
- [x] When the feed fails (timeout, unreachable, rate limit, misconfigured, unavailable), the page returns 200 with a working search box and no row; the failure isn't cached.
- [x] The detail page shows cover, summary, release date and platforms for both a stored and an unstored game. Mine shows a link to my entry; another user's saved game shows Save for me; an ineligible game shows no Save.
- [x] Saving from the detail page uses the save service: a new save lands on edit, a duplicate on my entry with "Already in your games", a failure returns to the detail page with the message.
- [x] Signed-out visitors are redirected to login for both the search page and the detail page, and IGDB is never called.

**Result (2026-11-15):** all standard checks pass (263 tests). The user's browser walkthrough passed. The record matches `docs/verification.md`, where the step numbers differ from the manual steps below, so behaviors are named here:
- **Confirmed by the user:**
  - the popular cover row scrolled sideways
  - cards opened the IGDB game page
  - Save from that page landed on the edit page
  - the reopened card showed Saved, and the game page offered "Open my entry"
  - a title search hid the row, and clearing the search brought it back
  - search result titles opened the same game page
- **Not reported** (covered by automated tests):
  - phone width
  - the placeholder for a missing or failed cover
  - each detail-page field one by one
  - the Save and Saved controls staying on search results
- **Not run** (optional, covered by automated tests):
  - the other demo user seeing Save instead of the first user's entry
  - the Wi-Fi-off check (blank search page without the row, stored game page from SQLite) PopScore was verified against the docs and one live run ([docs/research/igdb-popscore.md](../docs/research/igdb-popscore.md)). Three approved TDD cycles were run:
- **Ranking and eligibility:** `igdb.popular_games()`.
- **Cache and feed failure:** `igdb.cached_popular_games()`, one hour, `igdb:popular_games`, and `views.popular_row()`, which resolves Saved links per user.
- **Save return:** `search_save` accepts `return_to=igdb_game` and rebuilds the detail URL from the validated ID.

The rest was built normally: the detail page `views.igdb_game` with `igdb_game.html`, the row template `_popular_row.html`, result title links, the one-hour expiry test with a fake cache clock, and `igdb.category_badge()` shared by both IGDB record types.
- **Offline test guard:** after Cycle 2, a regression run likely made real Twitch and IGDB calls, because `manage.py test` loads `.env` and a blank-search test reached the new feed. `config/test_runner.py` (`OfflineTestRunner`) now blanks the credentials and blocks `requests.post` for every test (recorded in PROMPTS.md and CLAUDE.md).
- **Duplicate error alert (found and fixed during implementation):** after a failed save from the detail page, an unstored game's page showed the same message twice, once as the flash message and once as its own alert. The page now leaves out its own alert when the same message is already queued. A regression test was written first and seen failing (`2 != 1`), recorded in `docs/verification.md`.

### Automated checks

Standard checks, plus client tests with mocked HTTP (PopScore query body, rank order kept, eligibility filter, fewer than 10 eligible, each failure mapping, no secrets in cache keys), view tests with the client mocked at its boundary (row only on a blank search, cached second load, feed failure leaves search working, detail page for stored/unstored/unknown/outage, Saved-entry link scoped to the owner, Save return target), and template checks for the cover link and placeholder markup.

### Before implementing (to confirm)

- [x] Verify the PopScore endpoint, the visits `popularity_type` ID and the response shape against the official IGDB docs and one live request from a throwaway scratchpad script (IDs and counts only, no credentials printed), and record it in `docs/research/`. **Done:** `docs/research/igdb-popscore.md`.
- [x] Confirm the cache time, and whether results' titles should link to the detail page. **Done:** one hour; titles link (user decisions).
- [x] Add a short PRD addendum (a new user story for the popular row and the IGDB detail page; it stays within the existing storage and Twitch terms notes, caching only IDs, titles and cover IDs). **Done:** stories 120–126, plus "Popular on IGDB and the IGDB game page" under Implementation Decisions.

### Manual verification (browser, live IGDB)

1. Open Search IGDB with no term: the row shows up to 10 covers and titles, scrolls horizontally (including at phone width), and each card opens the detail page.
2. Search a title: the row disappears. Clear the search: it returns (and loads from cache).
3. Open the detail page for an unsaved game and click Save: lands on edit. Open it again: the link to my entry replaces Save.
4. As the other demo user, open the same game: Save is shown, not a link to the first user's entry.
5. Turn off Wi-Fi with the cache cleared (restart the server): the blank search page loads with a working search box and no row. A stored game's detail page still shows its details.
6. Search a title, then click a result's title: it opens the same detail page. The result's Save or Saved control is still on the results page.

### Commit

`Add Popular on IGDB row and IGDB game detail page`

---

## Phase 9: Refresh from IGDB

**User stories**: 8 (refresh), 74, 75, 76, 77, 78, 79, 80

**Goal**: Update a saved game's details on demand, safely: throttled, all-or-nothing, keeping my tracking data and my platform choice.

**Dependencies**: Phase 8 (fetch by ID with category rules), Phase 5 (stale-platform rule).

### What to build

A "Refresh from IGDB" button on the detail page that POSTs to `/games/<id>/refresh/` (owner-scoped, POST only).

- **Throttle**: one attempt per game per 10 minutes across all users, recorded in the cache per attempt (failures count too). A throttled refresh shows a message and makes no IGDB call.
- **Success**: updates Game metadata, platform, genre and theme links, and last-fetched in one transaction.
- **Failure**: keeps everything and shows the PRD message with the My Saved Games link.
- **Eligibility fields**: every successful refresh updates both the Game Category and the version parent.
- **Becomes ineligible**: stores the new values and keeps all entries and their tracking data. Later saves are rejected by the Phase 8 stored-classification rule.

A detail-page warning appears when the entry's platform played is no longer in the game's platforms. The value is kept.

### Acceptance criteria

- [x] A successful refresh updates the details and the "last refreshed" time, and the entry's tracking fields are unchanged.
- [x] A failed refresh changes nothing and shows the right message.
- [x] A second refresh of the same game within 10 minutes (by any user, even after a failure) is throttled, with no IGDB call.
- [x] A refresh that makes the game ineligible (a version parent appears, or the Game Category leaves the allowlist) stores both new values and keeps entries and tracking data. A later save of that game is rejected without an IGDB call.
- [x] A removed platform is kept on the entry with a warning, and editing other fields still works.
- [x] As the owner, GET on the refresh URL returns 405, with no IGDB call and no attempt recorded. Another user's POST returns 404, with no IGDB call, no attempt recorded and A's data unchanged.

### Automated checks

Standard checks, plus refresh tests with the client mocked: success, each failure, throttle by attempt and across users, reclassification plus stored-classification save rejection, stale-platform warning, 405 on GET, and 404 on another user's POST with the client asserted uncalled and the throttle key absent.

### Manual verification (browser, live IGDB)

1. Open an entry and click Refresh: a success message, and "Data from IGDB" shows a new time.
2. Click Refresh again: a throttled message.
3. As the other demo user, refresh the same game within 10 minutes: throttled.
4. With dummy credentials, refresh a different game: the error message, and the details are unchanged.
5. A seeded entry with a stale platform shows the warning, and you can still edit its notes.

### Commit

`Add Refresh from IGDB with throttling and safe reclassification`

---

## Phase 10: Saved-entry REST API

**User stories**: 45 (API half), 85, 86, 87, 88, 89, 90, 91, 92, 93, 94, 95, 96, 97, 98, 99, 100

**Goal**: The same saved entries, rules and privacy through a token-authenticated API, explorable in the browsable API with my website session.

**Dependencies**: Phase 6 (query builder), Phase 8 (save service), Phase 5 (shared validation).

### What to build

Add DRF and its token app (confirm DRF supports Django 6.1 and Python 3.14 first, and record the result). Authentication is Token then Session, permission is IsAuthenticated, and pagination is page-number with 10 per page.

A model viewset on a router at `/api/entries/` with the queryset scoped to the authenticated user:

- **List**: strict `q`, `status`, `platform`, `favorite`, `theme`, `sort` and `page` through the shared query builder. Invalid status, favorite, theme or sort returns 400. A bad or out-of-range page returns 404. Responses include `count`, `next`, `previous` and `results`.
  - **Search fallback (added in Phase 7, bugs B2/B3):** the `q` search must reuse the website's local fallback, `resolve_saved_search()` in `games/queries.py`: the typed term first, and only if it matches nothing under the active filters, its Roman-numeral form once (`Dark Souls 3` → `Dark Souls III`), decided on the whole filtered list before pagination, from the user's own entries. Add API tests for a typed-term match taking priority, the fallback, and another user's entries staying private.
- **Create**: through the save service with `igdb_id` and optional tracking fields. The owner comes from the request. Upstream errors return 503 with `{"detail", "code"}` (and Retry-After for rate limits). Not found, excluded and duplicate return 400 with `{"detail", "code"}`.
- **Retrieve and update**: PATCH merges stored values before the shared validation. PUT resets omitted optional fields. Changing `igdb_id` on update is rejected, and nested game input is ignored.
- **Delete**: returns 204 and keeps the Game.
- **Response shape**: the tracking fields plus a nested read-only game (IGDB ID, name, first release date, Game Category, platforms, genres, themes, cover URL from the shared builder, IGDB URL).

Document example create and PATCH requests and responses in the README.

### Acceptance criteria

- [x] No credentials gives 401. A valid token and a website session both work.
- [x] List parameters mean the same as on the website, including the Roman-numeral search fallback from Phase 7. Invalid values give 400, and bad pages give 404.
- [x] Create sets the owner from the token even if another owner is posted. Each error returns the specified status and body.
- [x] PATCH with a finish date before the stored start date gives a 400 field error. Stale-platform rules hold for PATCH and PUT.
- [x] PUT resets omitted optional fields. Changing `igdb_id` gives 400.
- [x] With user B's token or session, GET, PUT, PATCH and DELETE on A's entry return 404 and A's entry is unchanged. B's list (including a search for A-only notes) has none of A's entries. A theme only on A's games gives 400 for B.
- [x] With the IGDB client failing, list and retrieve still work, and creating a new game returns 503.

### Automated checks

Standard checks, plus API tests with `APIClient`: auth (401, token, session), each list parameter and strict errors, pagination shape and 404s, create success and every error code/status (client mocked), PATCH merge validation, PUT reset, `igdb_id` change rejected, nested game read-only, DELETE 204 with Game kept, the full owner-isolation matrix, and outage list/retrieve.

### Manual verification (browser and terminal)

1. Signed in on the website, open `http://127.0.0.1:8000/api/entries/`: the browsable API lists your entries, 10 per page, with `next`.
2. Try `?theme=19&sort=title`, then `?sort=bogus` (400) and `?page=99` (404).
3. In the browsable API, PATCH one of your entries' status. Check the website detail page shows the change.
4. Signed in as demo user B, open A's `/api/entries/<id>/`: 404.
5. Create a token for a demo user (`uv run python manage.py drf_create_token <username>`), store it in `.env`, and in PowerShell run `Invoke-RestMethod` without a token (401) and with `Authorization: Token …` (200), without echoing the token.

### Commit

`Add token-authenticated saved-entry REST API`

---

## Phase 11: Command-line client (lesson checkpoint: list and before-and-after status update)

**User stories**: 101, 102, 103, 104, 105, 106

**Goal**: A separate lesson checkpoint showing that the API works from outside Django. A second Python script lists my entries and updates one entry's status, printing the status before and after.

**Dependencies**: Phase 10.

### What to build

A second script, `scripts/entries_client.py`, separate from the IGDB verification script, using only requests and python-dotenv and importing no Django code. It reads `GAME_TRACKER_API_URL` from the environment or `.env` (default `http://127.0.0.1:8000/api/`) and `GAME_TRACKER_TOKEN` from the ignored `.env`. Add placeholders for both to `.env.example`. It sends `Authorization: Token …` with a timeout and never prints the token.

- **`list`**: optional search, status and page options. Prints each entry's ID, game title and status, the total count, and whether another page exists.
- **`update <id> <status>`**: GETs the entry, PATCHes only `status`, then prints the previous status and the updated status from the PATCH response.
- **Errors**: clear messages for 401 (invalid or missing token), connection failure ("server unavailable"), 400 validation, and 404 (entry not found on update, invalid page on list).
- **Exit codes**: 0 success, 1 request or API error, 2 usage error (the verification script's convention).

The README covers creating a token for a user with DRF's token command, storing it as `GAME_TRACKER_TOKEN` in `.env`, optionally setting `GAME_TRACKER_API_URL`, and running both `scripts/entries_client.py` commands.

### Acceptance criteria

- [x] **Checkpoint:** for an entry at Want to Play, `update <id> Playing` prints the previous status (Want to Play) and the updated status (Playing) from the PATCH response. The website detail page and My Saved Games then show Playing, and no other tracking field changed.
- [x] `list` shows the same total count and first-page entries as `/api/entries/` for the same search and status, and reports whether another page exists.
- [x] Another user's entry ID or a missing ID prints "not found" and changes nothing. An invalid status prints the validation error. A bad token prints a token error. A stopped server prints "server unavailable". None of these print the token.
- [x] Exit codes match the convention.

### Automated checks

Standard checks (Ruff covers the script), plus:

- Unit tests for `scripts/entries_client.py` with mocked HTTP: output formatting, every error path, exit codes, the `GAME_TRACKER_API_URL` default and override, a missing `GAME_TRACKER_TOKEN`, and a fake token never appearing in stdout or stderr.
- One end-to-end test with Django's live server running `scripts/entries_client.py` as a subprocess against a test database (with `GAME_TRACKER_API_URL` pointed at the live server and a test token in `GAME_TRACKER_TOKEN`). It checks `list` and the before-and-after `update`, then confirms the database shows the new status and unchanged other fields.

### Manual verification (terminal and browser, recorded as checkpoint evidence)

1. Start `runserver`. Note one demo entry at Want to Play in the browser.
2. `uv run scripts/entries_client.py list`, then `uv run scripts/entries_client.py list --status want_to_play` (exact status spelling as documented). Compare with `/api/entries/?status=…` in the browser.
3. `uv run scripts/entries_client.py update <id> Playing`: shows Want to Play → Playing. `$LASTEXITCODE` is 0.
4. Reload the entry's detail page and My Saved Games: Playing, with the other fields unchanged.
5. Run update with the other demo user's entry ID and with `999999` (not found, exit 1), an invalid status (validation error), a temporarily wrong token via `$env:GAME_TRACKER_TOKEN = "invalid-token"` (token error), and with the server stopped (server unavailable). The token never appears. Remove the override afterwards with `Remove-Item Env:GAME_TRACKER_TOKEN`.
6. Take terminal screenshots of steps 2–3 for the lesson checkpoint. Check that no token is visible.

### Commit

`Add API command-line client for listing entries and updating status`

---

## Phase 12: Final acceptance sweep, owner isolation, IGDB outage and documentation

**User stories**: 119, plus re-verification of the PRD's Acceptance Criteria (owner isolation, browsing during an IGDB outage, CLI before-and-after, and the other verification items)

**Goal**: Prove the whole app against the PRD's acceptance criteria in one pass, and leave complete setup and verification documentation.

**Dependencies**: Phases 1–11.

### What to build

- A consolidated owner-isolation test module that walks the PRD's isolation matrix in one place (website GET/POST on detail, edit, delete and refresh; refresh 405 for the owner; API GET/PUT/PATCH/DELETE; list and search leakage; Theme dropdown and theme IDs; owner set on create; 401 and login redirect).
- A consolidated outage test module that makes the IGDB client fail in each mode (unreachable, timeout, rate limit, credentials missing) and exercises My Saved Games (all search fields, four filters, seven sorts, pagination), detail, edit, API list and retrieve, IGDB search and refresh messages, existing-game save success, and new-game save failure with no rows written.
- README completed: setup, every environment variable, token creation and storage, the seeding command and signing in, both `scripts/entries_client.py` commands (with `GAME_TRACKER_API_URL` and `GAME_TRACKER_TOKEN`), and API example requests and responses.
- `docs/verification.md` completed. The acceptance criteria sweep section maps each PRD acceptance criterion to steps and a pass/fail result. The Reflection Question 4 and 5 sections and the outage-save record are checked for completeness. It contains no tokens or passwords.
- Fix any gaps the sweep finds, inside the existing PRD scope.

### Acceptance criteria

- [ ] Every PRD acceptance criterion has an automated test, an entry in `docs/verification.md`, or both, and all pass.
- [ ] With the network off (or credentials missing), every saved-games feature works, and IGDB features show the agreed messages with a link to My Saved Games.
- [ ] README and `docs/verification.md` are complete, and a fresh clone can be set up by following the README alone.
- [ ] No secrets appear in the repo, docs, PROMPTS.md or test output (`git grep` for the `GAME_TRACKER_TOKEN` value and the IGDB secret value, run locally, finds nothing).

### Automated checks

Standard checks (the full suite, including the two consolidated modules), plus `git status` and `git diff --cached --name-only` showing that `.env` isn't staged.

### Manual verification (browser, recorded in `docs/verification.md`)

1. **Owner isolation:** as demo user B, open A's detail, edit and delete URLs (404). Submit a refresh form for A's entry ID (404, A unchanged). Check the Theme dropdown and `?theme=19`. Search for a word only in A's notes. Repeat the API checks in the browsable API.
2. **IGDB outage:** turn off Wi-Fi with `runserver` still running. Browse My Saved Games with search, each filter, each sort and paging. Open detail (placeholders, all text visible). Edit and save an entry. Use the API list. Try IGDB search and refresh (messages with the link). Rerun the Phase 8 repeatable outage save check with the recorded search term. Turn Wi-Fi back on.
3. **Missing credentials:** restart with the IGDB variables empty. The site starts and the list works.
4. **CLI before-and-after:** rerun the Phase 11 checkpoint with `uv run scripts/entries_client.py update <id> Playing` on a fresh entry.
5. **Remaining items:** covers (working, missing, blocked), the title-sort reverse count check, and the browsable API with a session and `scripts/entries_client.py` with `GAME_TRACKER_TOKEN`.
6. Fill in `docs/verification.md` with the results. Check that every Reflection Question 5 bug entry has its reproduction steps, before and after screenshots, and fix references.

### Commit

`Add acceptance sweep tests, README and verification record`

---

## Phase checklist

- [x] Phase 1: Verify IGDB game types (live verification and documentation checkpoint)
- [x] Initial root `CLAUDE.md` (before the first `/implement` phase; commit `f0750a4`)
- [x] Phase 2: Project skeleton, accounts and site layout
- [x] Phase 3: Models, admin, demo seed and basic My Saved Games
- [x] Phase 4: Entry detail page and covers (functional verification complete; B1 screenshots pending)
- [x] Phase 5: Edit and delete entries
- [x] Phase 6: Search, filters, Theme, sorts and pagination (no browser issues reported; RQ4 screenshot pending)
- [x] Phase 7: IGDB client and IGDB search page (ordering kept as a known limitation; B2 and B3 screenshots pending)
- [x] Phase 8: Save a game from search (browser steps not reported individually)
- [x] Follow-up after Phase 8: "Popular on IGDB" row and IGDB game detail page (recorded and completed 2026-11-15, before Phase 9)
- [x] Phase 9: Refresh from IGDB (browser walkthrough passed 2026-11-15; optional outage step not confirmed in the browser)
- [x] Phase 10: Saved-entry REST API (browser and token walkthrough passed 2026-11-15, reported as one overall pass)
- [x] Phase 11: Command-line client (lesson checkpoint; walkthrough passed 2026-11-15, with the filtered list and the entry 13 update confirmed individually; terminal screenshots pending)
- [ ] Phase 12: Final acceptance sweep and documentation
