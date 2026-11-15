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

### Phase 5: Edit and delete entries

**Result: Pass (2026-11-15).** Automated checks: all five standard checks pass, 113 tests. Manual
steps run by the user in the browser with `uv run python manage.py runserver`, signed in as the
seeded demo users (password from `DEMO_PASSWORD`, value not recorded). The user reported: "editing
and Cancel, date and hours validation, keeping an unchanged stale platform and rejecting an unlisted
replacement, cross-user edit and delete 404s, and confirmed deletion that left the other user's
Witcher 3 entry intact." Steps the report didn't name are marked unverified. Entry IDs are from the
local seeded database before the deletion step: `demo_a` Alien: Isolation = 7, Dark Souls III: The
Ringed City = 13, The Witcher 3 = 15; `demo_b` The Witcher 3 = 16, Skyrim = 18 (the seeded stale
platform: "Nintendo Switch", no longer listed for the game), Celeste = 23.

| # | Step | Expected | Result | Date |
|---|---|---|---|---|
| A1–A3 | `demo_a`: Edit `/games/13/`, set Playing, favorite, rating 8, a platform, dates, 12.5 hours and notes, save | Back on detail with "Saved your changes to …"; every value shown | Pass ("editing") | 2026-11-15 |
| A4 | Set rating to "Not rated" and platform to "Not set", save | Both show "Not set" | Unverified in the browser (not separately reported). Automated: `test_blank_fields_clear_rating_favorite_platform_dates_and_hours` | 2026-11-15 |
| A5 | Edit, then Cancel | Back on detail, nothing changed | Pass ("editing and Cancel") | 2026-11-15 |
| B1 | Finish date before start date | "Finish date can't be before the start date." under Finish date; nothing saved | Pass | 2026-11-15 |
| B2 | Hours played `-1` | "Ensure this value is greater than or equal to 0."; nothing saved | Pass | 2026-11-15 |
| B3 | Blank start date with a finish date, status Completed | Saves | Unverified in the browser (not separately reported). Automated: `test_either_date_may_be_blank_for_any_status`, `test_finish_date_may_not_be_before_the_start_date` | 2026-11-15 |
| C1–C2 | `demo_b`: `/games/18/edit/` (Skyrim), change only the notes | Stale "Nintendo Switch (no longer listed for this game)" selected; save works and keeps it | Pass | 2026-11-15 |
| C3 | Change an option's value to `Nintendo 64` in DevTools and save | "Choose one of this game's platforms, or leave it blank."; entry unchanged | Pass | 2026-11-15 |
| C4 | Optional: switch to a listed platform, edit again | Stale option gone | Unverified in the browser (optional, not reported). Automated: `test_once_changed_to_a_current_platform_the_stale_value_is_no_longer_allowed` | 2026-11-15 |
| E1 | `demo_b`: open `/games/7/edit/` and `/games/7/delete/` (GET) | 404 with no game title | Pass ("cross-user edit and delete 404s") | 2026-11-15 |
| E2 | `demo_b`: the same URLs as form POSTs with B's valid CSRF token (form action changed in DevTools); then check `demo_a`'s `/games/7/` | 404; A's entry unchanged | Unverified in the browser (not separately confirmed). Automated: `test_another_users_entry_returns_404_for_a_csrf_valid_post_and_is_unchanged` in both `test_entry_edit.py` and `test_entry_delete.py` | 2026-11-15 |
| D1 | `demo_b`: Remove on `/games/16/` (The Witcher 3) | Confirmation names the game and says status, rating, notes and hours played will be deleted | Pass ("confirmed deletion") | 2026-11-15 |
| D2 | Cancel on the confirmation page | Back on `/games/16/`, entry still exists | Unverified in the browser (not separately confirmed; "Cancel" was reported with editing). Automated: `test_cancel_links_to_the_entry_detail_page`, `test_get_only_shows_the_confirmation_page` | 2026-11-15 |
| D3 | Remove from My Games | My Saved Games with "Removed The Witcher 3: Wild Hunt from My Games."; entry gone | Pass ("confirmed deletion") | 2026-11-15 |
| D4 | `demo_a`: `/games/15/` | A's Witcher 3 entry and the shared game details still exist | Pass | 2026-11-15 |

The user's report paired "Cancel" with editing and didn't separately confirm the delete page's
Cancel (D2) or the DevTools cross-user POSTs (E2), so those stay unverified in the browser and rely
on the automated tests named in their rows. `demo_b`'s Witcher 3 entry was deleted in D3; rerunning
`seed_demo` recreates it with a new entry ID.

Automated coverage for the same behavior: `games/tests/test_validation.py` (shared validation:
blank, listed and unchanged-stale platforms accepted, an unlisted replacement rejected on
`platform_played`; missing, single, equal and later dates accepted, finish before start rejected on
`finish_date`), `games/tests/test_entry_edit.py` (form fields and platform dropdown with the stale
option, every field saves and shows on detail, all five statuses, clearing fields, either date
blank, finish-before-start, negative hours and out-of-range ratings rejected with nothing saved,
stale platform kept while notes change, unlisted replacement rejected, stale value not allowed once
replaced, cross-user GET 404 and CSRF-valid POST 404 with the entry unchanged, missing ID 404,
signed-out redirect) and `games/tests/test_entry_delete.py` (owner POST removes only their entry,
keeps the Game and the other user's entry, redirects with the message; GET only confirms; Cancel
link to detail; Edit and Remove links on detail; POST without a CSRF token is 403 and deletes
nothing; other methods 405; signed-out redirect; cross-user GET 404 and CSRF-valid POST 404 with the
entry and Game unchanged; missing ID 404). In the cross-user POST tests, the same token then works on
the user's own entry, so each 404 comes from the owner check, not CSRF.

No browser bugs or usability issues were found in Phase 5.

### Phase 6: Search, filters, Theme, sorts and pagination

**Result: no issues reported (2026-11-15); individual steps unverified in the browser.**
Automated checks: all five standard checks pass, 153 tests. HTMX 2.0.11 vendored with its integrity
checked (`games/static/games/vendor/htmx-2.0.11/SOURCE.md`).

The user ran the Phase 6 browser checklist with `uv run python manage.py runserver` and the seeded
demo users (password from `DEMO_PASSWORD`, value not recorded), and reported: "I tried the Phase 6
browser checklist and didn't notice any issues." The report covered the checklist as a whole and
didn't confirm individual steps, so, as the user asked, each row below is recorded as **unverified in
the browser** (no issue reported), with the automated test that covers the same behavior. Rows
marked "browser only" have no automated equivalent because they need JavaScript or DevTools.

| # | Step | Expected | Result | Date |
|---|---|---|---|---|
| S1 | `demo_a`: Theme → Horror | Region updates without a full reload; URL `/games/?theme=19`; 9 entries, all Horror | Unverified in the browser (no issue reported). Automated: `FilterTests.test_each_filter_alone`; partial swap: `PartialResponseTests` | 2026-11-15 |
| S2 | Theme → Survival | URL `/games/?theme=21`; only Survival games | Unverified in the browser (no issue reported). Automated: `FilterTests.test_each_filter_alone` | 2026-11-15 |
| S3 | Search `LICKER`, then `PlayStation` | `LICKER`: Resident Evil 2 via its notes (case ignored). `PlayStation`: every game on a PlayStation platform, each listed once | Unverified in the browser (no issue reported). Automated: `SearchTests` (each field, case ignored, one row per entry) | 2026-11-15 |
| S4 | Status, Platform Played and Favorite, alone and combined | Results match; URL lists only the chosen values | Unverified in the browser (no issue reported). Automated: `FilterTests`, `test_pushed_url_is_clean_and_uses_the_page_actually_shown` | 2026-11-15 |
| W1 | Back/Forward walk (Reflection Question 4 below), HTMX on | URL, controls and results agree at every step | Unverified in the browser (no issue reported). Browser only; server side covered by `PartialResponseTests` | 2026-11-15 |
| W2 | Walk again with a hard reload partway through | Same agreement | Unverified in the browser (no issue reported). Browser only | 2026-11-15 |
| C1 | Clear filters from walk step 5, then Back | Search and sort kept, filters reset, page 1; Back restores the filters | Unverified in the browser (no issue reported). Automated: `test_clear_filters_keeps_search_and_sort_and_returns_to_page_1`, `test_clear_filters_keeps_search_and_sort_only`; Back is browser only | 2026-11-15 |
| D1 | From a searched, filtered, sorted page 2, open an entry, click **← My Saved Games** | Returns to the same URL, controls and results | Unverified in the browser (no issue reported). Automated: `ReturnToSavedGamesStateTests` | 2026-11-15 |
| F1 | Hand-edit `sort=bogus`, `theme=abc`, `page=0`, `page=99` | List still shows: default sort, theme ignored, page 1, last page | Unverified in the browser (no issue reported). Automated: `test_bad_values_are_ignored_and_never_echoed`, `test_a_page_past_the_end_shows_the_last_filtered_page`, `ForgivingParseTests` | 2026-11-15 |
| I1 | `demo_b`: Theme dropdown; `/games/?theme=19`; search `licker` | No Horror or Survival; theme ignored; no matches | Unverified in the browser (no issue reported). Automated: `QueryStateIsolationTests` | 2026-11-15 |
| N1 | JavaScript disabled: repeat W1 using **Apply** | Full page loads; URL, controls and results agree (URL includes blank fields) | Unverified in the browser (no issue reported). Automated: the normal-request case in `PartialResponseTests`; Back/Forward is browser only | 2026-11-15 |
| E1 | Search a word that matches nothing | "No saved games match your search and filters." | Unverified in the browser (no issue reported). Automated: `test_empty_state_when_nothing_matches` | 2026-11-15 |
| P1 | DevTools → Application → Local Storage after W1 | No `htmx-history-cache` key holding entries or notes | Unverified in the browser (no issue reported). Browser only; the `hx-history="false"` attribute is checked by `test_full_page_opts_out_of_htmx_history_snapshots_and_loads_htmx_locally` | 2026-11-15 |

No browser bugs or usability issues were reported in Phase 6.

**Screenshots:** none present. Checked on 2026-11-15: `docs/verification/screenshots/` contains only
`.gitkeep`. The Reflection Question 4 Back-step screenshot is **pending** (see below).

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
- **Phase 6 update:** the line references above are from the Phase 4 fix. The list rows moved to
  `games/templates/games/_saved_games_region.html:83` and `:86`, `saved_games_url()` moved to
  `games/queries.py:215`, and the detail view now rebuilds the full list state through
  `parse_entry_query` (`games/views.py:106`, return link built at `:121`). Tests:
  `ReturnToSavedGamesStateTests` in `games/tests/test_entry_detail.py`.
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

The Back/Forward walk on My Saved Games, signed in as `demo_a` (15 seeded entries), with HTMX on.
**Browser run (2026-11-15):** the user ran the Phase 6 checklist, which includes this walk, and
reported no issues. The steps weren't confirmed one by one, so the rows below are recorded as
unverified in the browser (no issue reported).

### How the URL stays the single source of query state

1. **Parse:** every request's query string goes through one forgiving parser,
   `parse_entry_query()` (`games/queries.py:141`), into an `EntryQuery` (`games/queries.py:100`).
   Unknown or another user's values are dropped. The page is parsed by `parse_page()` and clamped by
   `Paginator.get_page()`.
2. **Query and render:** `saved_games_context()` (`games/views.py:44`) runs `saved_entries()`
   (`games/queries.py:189`) and builds the controls, results, pager, Clear filters and detail links
   from that one `EntryQuery`. The controls are in the swapped region with the results
   (`games/templates/games/_saved_games_region.html`: search box `:19`, Status `:27`, Platform
   Played `:36`, Favorite `:44`, Theme `:52`, sort `:60`, Clear filters `:67`, pager `:105` and
   `:109`). A swap therefore replaces the controls and results together.
3. **Push the URL:** the region carries `hx-target`, `hx-swap="outerHTML"` and `hx-push-url="true"`
   (`_saved_games_region.html:8-9`), and the form and links use `hx-get`. The view answers an
   ordinary HTMX request with only the region and an `HX-Push-Url` header holding the clean URL of
   what is actually shown (`games/views.py:97`, built by `saved_games_url()` at
   `games/queries.py:215`).
4. **History restores:** the page sets `hx-history="false"` outside the region
   (`games/templates/games/saved_games.html:11`), so HTMX never snapshots private entries or notes
   into localStorage. Every Back or Forward is a cache miss, which HTMX 2.0.11 answers by requesting
   the URL with `HX-Request` and `HX-History-Restore-Request`. `is_htmx_swap()`
   (`games/views.py:71`) treats that as a full-page request, so the restored body is rendered fresh
   from the URL. `Vary: HX-Request, HX-History-Restore-Request` (`games/views.py:101`) stops the
   browser cache from handing a partial to a full-page load.

Automated coverage: `games/tests/test_saved_games_htmx.py` (full page, region-only partial and
full-page restore for the same URL, all showing matching controls and results; clean `HX-Push-Url`
including a clamped page; no push header on full pages; `Vary`; `hx-history="false"` outside the
region; HTMX loaded locally). Browser Back/Forward needs JavaScript, so it is checked manually.

### Walk (step 2 of the plan's Phase 6 manual verification)

| Step | Action | Expected URL | Expected controls | Expected results | Result |
|---|---|---|---|---|---|
| 0 | Open My Saved Games | `/games/` | Blank search, all filters "All", Date Added | 10 of 15, Page 1 of 2 | Unverified in the browser (no issue reported) |
| 1 | **Next** | `/games/?page=2` | Same as step 0 | 11–15 of 15, Page 2 of 2 | Unverified in the browser (no issue reported) |
| 2 | Sort → Title A to Z | `/games/?sort=title` | Sort: Title A to Z | 10 of 15, Page 1 of 2, starting Alien: Isolation | Unverified in the browser (no issue reported) |
| 3 | Theme → Horror | `/games/?theme=19&sort=title` | Theme: Horror | 9 entries, one page | Unverified in the browser (no issue reported) |
| 4 | Status → Playing | `/games/?status=playing&theme=19&sort=title` | Status: Playing | Resident Evil 2, Silent Hill 2 | Unverified in the browser (no issue reported) |
| 5 | Search `licker`, press Enter | `/games/?q=licker&status=playing&theme=19&sort=title` | Search box: licker | Resident Evil 2 (notes match) | Unverified in the browser (no issue reported) |
| Back ×5 | | Steps 4, 3, 2, 1, 0 in turn | Match that step | Match that step | Unverified in the browser (no issue reported) |
| Forward ×5 | | Steps 1–5 in turn | Match that step | Match that step | Unverified in the browser (no issue reported) |
| Reload | Hard reload at step 3, then Back and Forward again | As above | As above | As above | Unverified in the browser (no issue reported) |

**Screenshot of one Back step: pending.** Checked on 2026-11-15: no file exists in
`docs/verification/screenshots/`. Expected as `verification/screenshots/phase6-rq4-back-step.png`
(captured by the user, with no secrets visible).


## IGDB outage saves

Filled in during Phase 8: the repeatable outage save check (search term, the "existing" and "new"
games with their IGDB IDs, results of each run).

_Not started (Phase 8)._

## Acceptance criteria sweep

Filled in during Phase 12: each PRD acceptance criterion mapped to its steps and a pass/fail result.

_Not started (Phase 12)._
