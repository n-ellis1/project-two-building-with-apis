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

### Phase 4: Entry detail page and covers

**Result: Functional verification passed (2026-11-15). Reflection evidence pending:** the B1 before
and after screenshots. Automated checks: all five standard checks pass, 82 tests. Manual steps run by the user in Chrome with `uv run python manage.py runserver`, signed in as
the seeded demo users (password from `DEMO_PASSWORD`, value not recorded). The user reported "The
Phase 4 browser checks passed" for steps A to D as given; optional steps that weren't separately
reported are marked unverified. Entry IDs are from the local seeded database: `demo_a` Alien: Isolation = 7,
`demo_b` The Witcher 3 = 16, `demo_b` Scuffed Rocket League = 28.

| # | Step | Expected | Result | Date |
|---|---|---|---|---|
| A1–A3 | `demo_a` My Saved Games; inspect a list cover | Small 90×128 cover per row; `t_cover_small` `src`, `t_cover_small_2x … 2x` `srcset`, `loading="lazy"`, title as `alt`, `data-cover-placeholder` | Pass | 2026-11-15 |
| A4 | Zoom to 200% | Covers stay sharp (2x source) | Pass | 2026-11-15 |
| A5 | Optional: Disable cache + Slow 3G reload | Rows don't shift while covers load | Unverified (optional, not reported) | 2026-11-15 |
| A6–A7 | Open Alien: Isolation (`/games/7/`); inspect the cover | Large 264×374 `t_cover_big` cover with no `srcset`; details, tracking data, "Data from IGDB" link and last-refreshed time | Pass | 2026-11-15 |
| B1–B3 | `demo_b`: Scuffed Rocket League on the list and at `/games/28/` | Local placeholder at 90×128 and 264×374, no `srcset`, no `data-cover-placeholder`; all text shown | Pass | 2026-11-15 |
| B4 | Optional: JavaScript disabled, reload | Placeholder still shown | Unverified (optional, not reported) | 2026-11-15 |
| C1–C7 | Block `images.igdb.com` (Disable cache on), hard reload My Saved Games; inspect The Witcher 3 cover | Every cover switches to the placeholder; `srcset` and `data-cover-placeholder` removed; `width`, `height` and `alt` unchanged; all titles, badges, statuses and platforms shown; no repeating console errors | Pass | 2026-11-15 |
| C8 | Same, hard reload `/games/16/` | Large placeholder at 264×374; all details and tracking fields shown | Pass | 2026-11-15 |
| C9 | Unblock, untick Disable cache, hard reload | Real covers return | Pass | 2026-11-15 |
| D1–D2 | `demo_b` opens `/games/7/` (A's entry) and `/games/999999/` | The same 404 page for both; no game title shown | Pass | 2026-11-15 |
| D3 | Optional: `demo_a` opens `/games/28/` | 404 | Unverified (optional, not reported) | 2026-11-15 |
| D4 | Signed out, open `/games/7/` | Redirected to login with `?next=/games/7/` | Pass | 2026-11-15 |

One usability issue was found during these checks and fixed: [B1](#b1-phase-4-my-saved-games-link-on-the-detail-page-loses-the-list-page).

Automated coverage for the same behavior: `games/tests/test_covers.py` (URL builder for each size
and a missing ID, small cover attributes and `2x` `srcset`, placeholder without `srcset` or JS, the
fallback marker on remote covers only, the fallback script as a local deferred static file on every
page), `games/tests/test_entry_detail.py` (owner 200, other user's and missing entry 404, signed-out
redirect, large 264×374 cover without `srcset`, large placeholder, details and tracking fields,
"Not set" for blanks, the B1 return-link tests) and `games/tests/test_saved_games.py` (detail links,
small covers and placeholder on the list).

The fallback script's runtime behavior (switching a failed cover, removing `srcset`, leaving a failed
placeholder alone) has no automated test, because the stack has no JavaScript engine. Steps C1–C8
are its verification. A deliberately unrelated broken image wasn't tested; the temporary test page
for it was skipped by the user's choice.

## Browser bugs and usability fixes (Reflection Question 5)

Each entry: ID, phase, exact reproduction steps, expected vs actual, **before** screenshot, the fix
(file and line references), **after** screenshot taken by repeating the same steps, and the test added
(where practical).

### B1 (Phase 4): My Saved Games link on the detail page loses the list page

- **Found:** 2026-11-15, during Phase 4 manual verification.
- **Reproduction:**
  1. Sign in as `demo_a` and open My Saved Games.
  2. Click **Next** to go to page 2 (`/games/?page=2`).
  3. Click **Alien: Isolation** to open its detail page.
  4. Click **← My Saved Games**.
- **Expected:** back on page 2 (`/games/?page=2`), where the entry was opened from.
- **Actual:** page 1 (`/games/`). The detail link carried no page, and the return link always
  pointed at the bare saved-games route.
- **Before screenshot:** **pending reflection evidence.** Not captured before the fix; checked on
  2026-11-15 and no file exists. The user will capture the original behavior separately as
  `verification/screenshots/phase4-b1-before.png` (to be labelled as a reproduction, see below).
- **Fix:** list rows link to `/games/<id>/?page=N` when on page 2 or later
  (`games/templates/games/saved_games.html:16` and `:19`). The detail view passes `?page` through
  `parse_page` and builds the return link from the `games:saved_games` route with
  `saved_games_url()` (`games/views.py:37`, used at `games/views.py:58`). The link is rendered at
  `games/templates/games/entry_detail.html:5`. Anything that isn't a positive whole number, including
  an outside URL or markup, falls back to page 1 and is never echoed. The entry is still looked up
  with `get_owned_entry_or_404`. Phase 6 extends the same link to keep search, filters and sort (noted
  in the plan).
- **Retest after the fix (2026-11-15):**

  | Step | Expected | Result |
  |---|---|---|
  | Repeat the reproduction steps 1–4 | Back on `/games/?page=2` | **Pass**: the user confirmed that opening Alien: Isolation from page 2 and clicking My Saved Games returns to page 2 |
  | Open `/games/7/` directly, click **← My Saved Games** | `/games/` (page 1) | **Pass**: the user confirmed it returns to page 1 |
  | Optional: `/games/7/?page=https://example.com/`, hover the link | Points at `/games/` | Not verified in the browser (covered by an automated test) |

- **After screenshot:** **pending reflection evidence.** Checked on 2026-11-15: no B1 image exists
  in `verification/screenshots/` or anywhere else in the repo. Expected as
  `verification/screenshots/phase4-b1-after.png`.
- **Screenshot note:** if the before image is captured now that the fix is in place, it must be a
  recreation of the old behavior and will be labelled **reproduction** here. The return link wasn't
  changed for any screenshot so far.
- **Tests:** `games/tests/test_entry_detail.py:55` (`ReturnToSavedGamesPageTests`): opening an entry
  from page 2 returns to page 2; direct entry returns to page 1; empty, `1`, `0`, `-1`, `abc`, `2.5`,
  an outside URL and injected markup all return to page 1; page-1 links carry no page; another user's
  entry with `?page=2` is still 404. All five standard checks pass (82 tests).

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
