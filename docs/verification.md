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

### Phase 7: IGDB client and IGDB search page

**Result: Pass (2026-11-15), with reflection evidence pending:** the B2 and B3 before and after
screenshots. Automated checks: all five standard checks pass, 211 tests.

The user ran the Phase 7 browser checklist with live IGDB and reported that it "looked good" apart
from one search issue, B2 (`Dark Souls 3` found nothing on Search IGDB). B3 (the same on My Saved
Games) followed. Both were fixed and the user confirmed both fixes in the browser. The checklist
steps weren't reported one by one, so the table records them as unverified in the browser (no issue
reported), each with the automated test covering the same behavior.

| # | Step | Expected | Result | Date |
|---|---|---|---|---|
| 1 | Search `The Witcher 3` as `demo_a` | Base game (Saved) and Blood and Wine (Expansion); no GOTY Edition, bundle, Remastered update or Redux mod | Unverified in the browser (no issue reported). Automated: `SearchQueryBodyTests`, `test_results_show_cover_title_release_date_platforms_and_badge` | 2026-11-15 |
| 2 | Search `Dark Souls III`, `Resident Evil 2` | No bundles, editions, mods or packs; Port, Remake, Remaster badges | Unverified in the browser (no issue reported). Same tests as step 1 | 2026-11-15 |
| 3 | Search `Dark Souls 3` | Finds Dark Souls III | **Failed, then fixed: B2.** Retest **Pass** | 2026-11-15 |
| 4 | Broad search `star`, Next and Previous | Region swaps, URL updates, query kept; Next only when more | Unverified in the browser (no issue reported). Automated: `SearchPagerTests`, `SearchHtmxTests`. Ordering: see the live client check below | 2026-11-15 |
| 5 | Back/Forward; Local Storage | URL, results and page agree; no stored results | Unverified in the browser (no issue reported). Browser only; `hx-history="false"` checked by `test_full_page_opts_out_of_htmx_history_outside_the_swapped_region` | 2026-11-15 |
| 6 | `page=abc`, `page=500`, nonsense search | Page 1; "No more results" with a page-1 link; "No matches." | Unverified in the browser (no issue reported). Automated: `SearchPageStateTests` | 2026-11-15 |
| 7 | JavaScript disabled, Next and Previous | Full pages, same results | Unverified in the browser (no issue reported). Automated: `test_pager_links_work_without_javascript_and_swap_with_htmx` | 2026-11-15 |
| 8 | `demo_b` searches `Dark Souls III` | Shows as unsaved | Unverified in the browser (no issue reported). Automated: `SavedLinkTests` | 2026-11-15 |
| 9 | Dummy IGDB credentials | Misconfiguration message with a working My Saved Games link | Unverified in the browser (no issue reported). Automated: `SearchErrorTests`, `FailureMappingTests` | 2026-11-15 |
| 10 | Signed out, `/search/?q=zelda` | Redirected to login; no IGDB call | Unverified in the browser (no issue reported). Automated: `test_signed_out_visitors_are_redirected_and_igdb_is_never_called` | 2026-11-15 |
| 11 | My Saved Games: search `Dark Souls 3` | Finds Dark Souls III | **Failed, then fixed: B3.** Retest **Pass** | 2026-11-15 |

Browser bugs found: [B2](#b2-phase-7-dark-souls-3-finds-nothing-while-dark-souls-iii-finds-the-game)
and [B3](#b3-phase-7-my-saved-games-search-for-dark-souls-3-finds-nothing).

#### Live client ordering check (2026-11-15)

Run from a throwaway scratchpad script (not committed) through the Phase 7 client
(`games.igdb.search_games`, the approved `where` clause, `limit 11`, offsets 0 and 10) with the
user's real `.env`. It printed IGDB IDs and error codes only; no credentials or tokens were printed.
Requests were sent one at a time with a 0.5-second pause.

Search `star`, pages 1 and 2, three runs:

| Run | Page 1 (offset 0, 11 returned; the 11th only signals Next) | Page 2 (offset 10, 11 returned) |
|---|---|---|
| 1 | 119305, 305275, 45529, 137, 158, 71780, 1232, 64921, 194604, 262535, *(17030)* | 84839, 17030, 303280, 69258, 136107, 285677, 10204, 298942, 39822, 18902, *(67202)* |
| 2 | identical to run 1 | identical to run 1 |
| 3 | identical to run 1 | identical to run 1 |

- **Repeated runs:** the three repeated `star` runs returned identical ordered IDs on page 1 and on
  page 2, with no overlap: none of the 10 IDs shown on page 1 appears among the 10 shown on page 2.
- **Separately, changing `limit` or `offset` changed the order of some results.** Page 1's hidden
  11th result (17030) is page 2's *second* result, not its first. Two follow-up requests through the
  same client show the pattern:

  | Positions | One wide request (offset 0, limit 30) | Page requests (limit 11) |
  |---|---|---|
  | 2–3 | 45529, 305275 | page 1: 305275, 45529 |
  | 11–12 | 84839, 17030 | page 1's 11th: 17030; page 2: 84839, 17030 |
  | 19–20 | 18902, 39822 | page 2: 39822, 18902 |
  | 27–29 | 399219, 475, 2681 | page 3 (offset 20): 2681, 399219, 475 |

  The **sets** of shown IDs still match exactly (page 1 = wide positions 1–10, page 2 = 11–20,
  page 3 = 21–30). Results that IGDB apparently ranks equally are ordered differently depending on
  `limit` and `offset`.
- **Consequence:** a duplicate or skipped result at a page boundary is **possible** if two such
  results straddle positions 10 and 11. **Neither was observed in this check.** The Next rule is
  unaffected (it only counts whether an 11th result came back).
- **Decision (user, 2026-11-15, Option 1):** keep the IGDB query and the current search order (no
  `sort`), and record this as a known limitation in the research note (section 5) and the PRD.

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

### B2 (Phase 7): "Dark Souls 3" finds nothing, while "Dark Souls III" finds the game

- **Found:** 2026-11-15, during Phase 7 manual verification (live IGDB, the user's real `.env`).
- **Reproduction:**
  1. `uv run python manage.py runserver`, sign in (any user), open **Search IGDB**.
  2. Search `Dark Souls 3` (URL `/search/?q=Dark+Souls+3`).
  3. Then search `Dark Souls III` (URL `/search/?q=Dark+Souls+III`).
- **Expected:** step 2 finds Dark Souls III, because players commonly type the sequel number as a
  digit.
- **Actual:** step 2 shows "No matches."; step 3 finds Dark Souls III. IGDB's `search` matches the
  title's own spelling, and the title uses the Roman numeral.
- **Before screenshot:** **pending reflection evidence.** Not captured before the fix (checked
  2026-11-15: not in the repo). Expected as `verification/screenshots/phase7-b2-before.png` (step 2's
  "No matches." page, no secrets visible). Captured now, it would be a recreation of the old
  behavior and labelled **reproduction**.
- **Agreed fix (user, 2026-11-15):** the exact search always runs first. Only when page 1 of the
  exact search returns no results (not an error) and the text ends in a standalone number from 2
  to 9, the search is tried once more with that number as a Roman numeral (`Dark Souls 3` →
  `Dark Souls III`). If that finds results, the page says which term matched, and the pager links
  use the matched term so Next doesn't jump back to the original search. Both requests carry the
  eligibility `where` clause. If the original request errors, the existing error message is shown
  and no second request is made.
- **Fix:** `roman_numeral_variant()` (`games/queries.py:229`, moved there from `games/views.py`
  in B3 so My Saved Games shares it) turns a final standalone 2–9 into its Roman numeral. The
  `search` view (`games/views.py:177`) runs the exact search first and, only for an empty page 1
  with such a variant, makes one more request (`games/views.py:204`). When that
  finds results, the matched term becomes the search for the box, the pager links and
  `HX-Push-Url`, and the notice "No matches for “…”. Showing results for “…”." is shown
  (`games/templates/games/_search_region.html:17`). Both requests go through
  `igdb.search_games`, so both carry the eligibility clause. An error on the exact search is shown
  with no second request.
- **After screenshot:** **pending reflection evidence.** Expected as
  `verification/screenshots/phase7-b2-after.png` (checked 2026-11-15: not in the repo).
- **Retest after the fix (2026-11-15):** **Pass.** The user repeated the steps and confirmed that
  `Dark Souls 3` now works on Search IGDB. (The user confirmed the outcome; the individual retest
  checklist steps weren't reported one by one.)
- **Tests:** `RomanNumeralFallbackTests` and `RomanNumeralFallbackRequestTests` in
  `games/tests/test_search.py`: fallback once with the notice and the matched term in the box; an
  exact match makes no fallback request; Next and Previous use the matched term, and following Next
  searches it directly; HTMX pushes the matched term; an exact-search error shows the error with no
  fallback; a fallback error shows the error with the original text kept; neither term matching
  shows "No matches."; no fallback for page 2, `zelda`, `Halo 1`, `Final Fantasy 10`, `Doom3`, `3`
  or a number that isn't last; each digit 2–9 maps correctly; and, through the real client with HTTP
  mocked, both requests carry the eligibility clause, `limit 11` and `offset 0`. All five standard
  checks pass (203 tests).

### B3 (Phase 7): My Saved Games search for "Dark Souls 3" finds nothing

- **Found:** 2026-11-15, by the user while retesting B2, on My Saved Games (SQLite only).
- **Reproduction:**
  1. `uv run python manage.py runserver`, sign in as `demo_a` (who has Dark Souls III saved).
  2. On My Saved Games (`/games/`), search `Dark Souls 3` and press Enter.
- **Expected:** Dark Souls III is listed, the same as Search IGDB after B2.
- **Actual:** "No saved games match your search and filters." The search is a case-insensitive
  substring match, and the saved title spells the number as "III".
- **Before screenshot:** **pending reflection evidence.** The user's `/games/` screenshot of step 2
  is the before evidence (user's choice), but it isn't in the repo yet (checked 2026-11-15).
  Expected as `verification/screenshots/phase7-b3-before.png`.
- **Agreed fix (user, 2026-11-15):** reuse the B2 trailing-number rule. Search the typed term first;
  only if it has no matches under the active filters, try the Roman-numeral form once. Decide this
  on the whole filtered list before paging, so an empty or out-of-range page can't switch the search.
  Stay in SQLite and scoped to the signed-in user's entries, keep filters, sorting and paging, and say
  which term matched.
- **Fix:**
  - The rule moved to `games/queries.py` so both pages share it: `roman_numeral_variant()`
    (`:229`) and the new `resolve_saved_search()` (`:242`), which tries the typed term under the
    active filters and, only if it matches nothing, the Roman-numeral form, each with `.exists()`
    on the user's own filtered entries. Search IGDB imports the same function.
  - `saved_games_context()` paginates the resolved query (`games/views.py:64`). The URL, the
    search box, the pager, Clear filters, detail links and `HX-Push-Url` keep the **typed** term, so
    URL, controls and results still agree on every request (Reflection Question 4) and every page of
    the same URL resolves the same way.
  - The notice "No matches for “…”. Showing results for “…”." is shown above the results
    (`games/templates/games/_saved_games_region.html:75`).
- **After screenshot:** **pending reflection evidence.** Expected as
  `verification/screenshots/phase7-b3-after.png` (checked 2026-11-15: not in the repo).
- **Retest after the fix (2026-11-15):** **Pass.** The user retested `Dark Souls 3` on My Saved Games
  and confirmed the fix works. (The user confirmed the outcome; the filter, return-link, Back/Forward
  and `demo_b` steps of the retest checklist weren't reported one by one, so they rely on the tests
  listed below.)
- **Tests:** `games/tests/test_saved_games_search_fallback.py`: a typed-term match takes priority
  (a notes match beats a Roman-numeral title); the fallback finds Dark Souls III with the notice and
  the typed term kept in the box and detail links; another user's notes and entries neither decide the
  fallback nor appear; the fallback is decided under the active Status filter; paging and the Title Z
  to A sort keep the typed term, page 2 and an out-of-range page show the same fallback search; HTMX
  pushes the typed term; neither term matching shows the normal empty state; terms without a final
  2–9 never switch. IGDB is patched to fail if called.
- **Other title searches checked:** Search IGDB uses the same rule (B2). The Django admin search
  (`search_fields` in `games/admin.py`) is a superuser debugging tool for finding exact rows, so it
  was left unchanged. `scripts/igdb_search.py` stays unchanged as the Phase 1 baseline. The Phase 10
  API search is recorded in the plan to reuse `resolve_saved_search()`.

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
