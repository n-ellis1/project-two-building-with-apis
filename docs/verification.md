# Manual verification record

Evidence that the video game tracker meets the [PRD](../prd/video-game-tracker.md), following the
[implementation plan](../plans/video-game-tracker.md). Created in Phase 2, extended every phase, and
completed in Phase 12.

**Never** record tokens, passwords, secret keys or `.env` contents here or in screenshots.
Screenshots go in [`verification/screenshots/`](verification/screenshots/).

## Phase results

For each phase: the manual steps run, pass or fail, and the date. The standard automated checks
(`manage.py check`, `makemigrations --check --dry-run`, `manage.py test`, `ruff check .`,
`ruff format --check .`) pass before every manual run.

### Phase 2: Project skeleton, accounts and site layout

**Result: Pass (2026-11-14).** Automated checks: all five standard checks pass, 18 tests. Manual
steps run by the user in the browser with `uv run python manage.py runserver`.

| # | Step | Expected | Result | Date |
|---|---|---|---|---|
| 1 | Open `http://127.0.0.1:8000/` while signed out | Redirected to `/accounts/login/`; page styled with Bootstrap | Pass (reported with the login redirects) | 2026-11-14 |
| 2 | Sign up a new user, including mismatched passwords | Field errors and no account for bad input; a valid sign-up signs in and lands on My Saved Games (empty state) with the username in the nav | Pass: validation and automatic login worked | 2026-11-14 |
| 3 | Log out, open `/games/` directly, sign in | Login URL has `?next=/games/`; returned to `/games/` | Pass (reported with the login redirects) | 2026-11-14 |
| 4 | Open `/accounts/logout/` in the address bar while signed in | 405, still signed in | Pass: GET returned 405 | 2026-11-14 |
| 4b | Click the Log out button | Signed out, on the login page | Pass | 2026-11-14 |
| 5 | Sign in with `?next=https://example.com/` | Lands on My Saved Games, not the other site | Pass (reported with the login redirects) | 2026-11-14 |
| 6 | Signed out, open `/search/` | Redirected to login with `?next=/search/` | Pass (reported with the login redirects) | 2026-11-14 |
| 7 | Footer on login, sign-up, My Saved Games and Search IGDB | "Game data and cover art from IGDB.com", linking to igdb.com | Pass | 2026-11-14 |
| 8 | Wi-Fi off, hard reload | Styling still loads (local static files, no CDN) | Pass | 2026-11-14 |
| 9 | Restart with no IGDB credentials (temporary `DJANGO_ENV_FILE` with no IGDB lines, throwaway secret key in the shell) | Both presence checks print `False`; site starts; login and My Saved Games work | Pass: both printed `False`; logged in and opened My Saved Games | 2026-11-14 |
| 10 | Narrow window (phone width) | Nav wraps without horizontal scrolling | Pass. The optional JavaScript-off nav check wasn't reported | 2026-11-14 |

Step 9 needed `DJANGO_ENV_FILE` because in Windows PowerShell 5.1 `$env:IGDB_CLIENT_ID = ""` deletes
the variable, and settings would then reload it from `.env`. The check printed presence booleans only,
never values.

No browser bugs or usability issues were found in Phase 2.

Note: the vendored Bootstrap 5.3.8 files had their trailing `sourceMappingURL` comment removed (see
`games/static/games/vendor/bootstrap-5.3.8/SOURCE.md`), so DevTools doesn't request missing `.map`
files.

### Phase 3: Models, admin, demo seed and a basic My Saved Games list

**Result: Pass (2026-11-15).** Automated checks: all five standard checks pass, 63 tests. Manual
steps run by the user in the browser and PowerShell with `uv run python manage.py runserver`, after
adding `DEMO_PASSWORD` to `.env` (its value isn't recorded) and running `migrate`.

| # | Step | Expected | Result | Date |
|---|---|---|---|---|
| 1 | `uv run python manage.py seed_demo`, then run it again | First run creates 2 demo users, 27 games and 28 entries; the rerun reports `0 created` on every line | Pass: expected users, games and entries created; rerun created nothing | 2026-11-15 |
| 2 | Sign in as `demo_a`, page 1 | "Showing 1–10 of 15", Page 1 of 2, Next link; Game Category badges (Port, Remake, Remaster, Expansion) on non-main games only | Pass: badges displayed correctly | 2026-11-15 |
| 3 | `demo_a`: click Next | Page 2 with the remaining 5 entries (including DLC and Standalone Expansion badges), Previous link, no Next | Pass | 2026-11-15 |
| 4 | `/games/?page=0`, `?page=abc`, `?page=-1`, then `?page=99` | Page 1 for the first three; the last page for 99 | Pass | 2026-11-15 |
| 5 | Sign in as `demo_b`; check pages 1, 2 and 99 | Only B's 13 entries; none of A's own games (Dark Souls III, Resident Evil 2, Silent Hill 2, Dead Space). The Witcher 3 appears because both users saved it | Pass: each demo account showed only its own entries | 2026-11-15 |
| 6 | `changepassword demo_a`, rerun `seed_demo`, sign in | Only the new password works; the seed doesn't reset it | Pass | 2026-11-15 |
| 7 | Run `seed_demo` with a throwaway `DJANGO_ENV_FILE` that has no `DEMO_PASSWORD` | Stops with "DEMO_PASSWORD is not set … Nothing was created." and creates nothing | Pass | 2026-11-15 |
| 8 | `/admin/` as a superuser: open a Game, a Platform/Genre/Theme, and an Entry | Imported data is view-only (no Save, no Add); Entry status and other tracking fields save; owner and game aren't editable | Pass | 2026-11-15 |

Automated coverage for the same behavior: `games/tests/test_models.py` (defaults, unique
(owner, game), rating and hours constraints, Game kept on entry delete, badges),
`games/tests/test_queries.py` (page helper table, owner-scoped 404),
`games/tests/test_seed_demo.py` (rerun gives identical rows, passwords and edited entries kept,
missing `DEMO_PASSWORD`, an unrelated account with a demo username stops the seed untouched, no
network, seeded data properties, demo A page 2 and demo B isolation on pages 1, 2 and 99),
`games/tests/test_saved_games.py` (isolation, order, tie-breakers, 10 per page, bad and past-the-end
pages, badges, empty state, no network) and `games/tests/test_admin.py`.

The demo fixture (`games/demo_data/seed.json`) holds real IGDB records fetched once on 2026-11-15
by a throwaway scratchpad script that printed no credentials. The seed command and tests never
contact IGDB.

No browser bugs or usability issues were found in Phase 3.

## Browser bugs and usability fixes (Reflection Question 5)

Each entry: ID, phase, exact reproduction steps, expected vs actual, **before** screenshot, the fix
(file and line references), **after** screenshot taken by repeating the same steps, and the test added
(where practical).

_No entries yet._

## Back/Forward query state (Reflection Question 4)

Filled in during Phase 6: the Back/Forward walk on My Saved Games (URL sequence, what agreed at each
step, screenshots of one Back step) with file and line references to where the query is parsed, the
controls are rendered, `hx-push-url` is set and history-restore requests get the full page.

_Not started (Phase 6)._

## IGDB outage saves

Filled in during Phase 8: the repeatable outage save check (search term, the "existing" and "new"
games with their IGDB IDs, results of each run).

_Not started (Phase 8)._

## Acceptance criteria sweep

Filled in during Phase 12: each PRD acceptance criterion mapped to its steps and a pass/fail result.

_Not started (Phase 12)._
