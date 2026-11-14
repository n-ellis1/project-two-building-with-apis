# Saved-games query-state prototype: decisions

Prototype: [saved-games-query-state.html](saved-games-query-state.html) (kept as-is; it still uses 12 per page and a Game Category filter switch, both superseded below).

Recorded 2026-11-14 for the PRD and implementation plan.

## Decided after trying the prototype

- **Page size: 10** for both the saved-games website and the Django saved-entry API (`?page=`). Replaces the earlier choice of 12. Why: preferred after trying it.
- **No Game Category filter.** Expansion, Remake and Remaster (and other non-main Game Categories) stay as badges on the search and saved-games pages only.
- **New filter: IGDB themes** (for example Horror, Survival) instead of the release-type filter. Field to use: verified below.
- The rest of the prototype's agreed logic held up: Q search across title, summary, platform names, genre names and notes with `distinct()`; seven whitelisted sorts; missing values last; tie-breakers (title A to Z, then entry ID; title sorts use ID only); case-insensitive title sort.

## Verification: Horror and Survival are IGDB themes, not genres

Live request on 2026-11-14 (`/v4/genres`, `/v4/themes`, `/v4/games`):

- `/genres` (23 values) contains neither Horror nor Survival.
- `/themes` contains **Horror (id 19)** and **Survival (id 21)**, alongside Action, Fantasy, Science fiction, Thriller, Historical, Stealth, Comedy, Business, Drama, Non-fiction, Sandbox, Educational, Kids, Open world, Warfare, Party, 4X, Erotic, Mystery, Romance.
- `search "Resident Evil 2"` → genres `Shooter, Adventure`; themes `Action, Science fiction, Horror, Survival`. The same search also returned a "Resident Evil 2 + Resident Evil 3 Bundle", another case for the bundle exclusion.

Implication: the filter must read IGDB `themes`, so the import query needs `themes.name` and the app needs a local theme store (design pending).

## Prototype behaviours chosen (Option A: forgiving website, strict API)

Website:
1. **Clear filters** clears every filter (Status, Platform Played, Favorite, Theme), keeps search and sort, returns to page 1.
2. **Changing search, any filter, or sort** returns to page 1.
3. **Pagination links** preserve the current search, filters and sort.
4. **Missing, non-numeric, zero or negative `page`** shows page 1. **A positive page past the end** shows the last page.
5. **Unknown `sort`** silently uses Date Added (Newest First).

API (saved entries):
- Invalid or out-of-range `page` → **404**. Unknown sort value → **400**.
- 10 entries per page, same as the website.

Filters and labels:
- **Theme filter** backed by locally stored IGDB themes (Horror, Survival, …).
- Genres stay in Q search. Expansion, Remake, Remaster stay as badges only.

Why: the website forgives hand-edited or stale URLs, while API clients (scripts) get explicit errors instead of guesses. "Back to page 1" after any change, because a new search or order is a new list.

## Theme filter details

- `Theme` model (unique `igdb_id`, `name`), many-to-many from `Game`, imported from IGDB `themes.name`.
- Single-select dropdown, default **All Themes**. Lists only themes on the **current user's** saved games, alphabetical, regardless of other active filters.
- URL uses the theme's IGDB ID: `?theme=19`.
- Q search also matches theme names. `distinct()` wherever joins can duplicate entries (search and theme filter).
- Valid theme with no combined matches → normal empty state.
- Malformed theme ID, or one not on the user's saved games → website ignores it; API returns 400.
- Verify: another user's saved games never populate the dropdown.

## Verification: Django `Paginator.get_page()` (Django 6.1.3, 27 items, 10 per page)

| `page` | `get_page()` result |
|---|---|
| missing, `''`, `abc`, `2.5` | 1 |
| `0`, `-1` | **3 (last page)** |
| `2` | 2 |
| `99` | 3 |

**`get_page()` alone does not meet rule 4**: numbers below 1 go to the last page. Normalize first with a small helper (any value that is not a positive integer → 1), then call `get_page()`, which handles past-the-end. Unit-test the helper with `None`, `''`, `abc`, `2.5`, `0`, `-1`, `2`, `99`.
