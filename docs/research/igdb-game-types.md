# IGDB Game Types: Verification for the Game Category Rules

**Verified:** 2026-11-14 (official docs and live requests the same day)
**Status:** facts verified. **Keep/exclude allowlist and badge labels approved 2026-11-14** and carried into the PRD's Game Category rules and the plan. IGDB search ordering was **checked live in Phase 7 (2026-11-15)**: repeated identical searches are stable, but the order of some results depends on `limit` and `offset`; the query and order were kept as they are (section 5).
**Plan phase:** Phase 1 of [plans/video-game-tracker.md](../../plans/video-game-tracker.md)

## Summary

- **Field:** the game's type is `game_type`, a reference ID into the `/v4/game_types` endpoint. The old `category` field is marked deprecated in the docs ("DEPRECATED! Use `game_type` instead"), and live it's empty on every record (count of `category != null` = 0).
- **Values:** 15 game types, IDs 0–14. The live list matches the docs' old `category` enum one-to-one (same IDs, same order).
- **Editions need `version_parent`, not just `game_type`.** Some editions are typed **Main Game** and only their `version_parent` marks them as editions, for example *Dark Souls III: Day One Edition*. Others are typed **Bundle** *and* have a version parent, for example *The Witcher 3: Wild Hunt – Game of the Year Edition*.
- **The PRD's three checks pass** with `where version_parent = null & game_type != (3,5,13,14);`. The Witcher 3 keeps the base game and Blood and Wine and drops the GOTY Edition. Dark Souls III drops all three bundles. Resident Evil 2 drops its bundle, and Horror (19) and Survival (21) still come back as themes.
- **Approved:** keep Main Game, DLC, Expansion, Standalone Expansion, Episode, Season, Remake, Remaster, Expanded Game, Port and Fork. Exclude Bundle, Mod, Pack / Addon, Update, any future type until it's reviewed, and any record with a version parent. Badges use IGDB's labels, and Main Game has no badge.

## 1. Official documentation

Source: IGDB API docs, <https://api-docs.igdb.com/>, retrieved 2026-11-14 with a plain HTTP GET. Earlier automated fetches got HTTP 403, but this one returned the full page.

### 1.1 Game endpoint (`https://api.igdb.com/v4/games`)

Field table rows, quoted:

| field | type | description |
|---|---|---|
| `game_type` | Reference ID for Game Type | "The type of game" |
| `category` | Category Enum | "DEPRECATED! Use `game_type` instead" |
| `version_parent` | Reference ID for Game | "If a version, this is the main game" |
| `version_title` | String | "Title of this version (i.e Gold edition)" |
| `parent_game` | Reference ID for Game | "If a DLC, expansion or part of a bundle, this is the main game or bundle" |
| `bundles` | Array of Game IDs | "The bundles this game is a part of" |
| `game_status` | Reference ID for Game Status | "The status of the games release" |

The section's "Deprecated Fields" list also says: "`category`: DEPRECATED! Use `game_type` instead" and "`status`: DEPRECATED! Use `game_status` instead". The docs give no date for the deprecation.

### 1.2 Game Type endpoint

> Game Type — "The type that this game is"
> Request Path: `https://api.igdb.com/v4/game_types`

| field | type | description |
|---|---|---|
| `checksum` | uuid | Hash of the object |
| `created_at` | datetime | Date this was initially added to the IGDB database |
| `type` | String | *(no description in the docs)* |
| `updated_at` | datetime | The last date this entry was updated in the IGDB database |

### 1.3 Old `category` enum ("Game Enums → category")

`main_game` 0, `dlc_addon` 1, `expansion` 2, `bundle` 3, `standalone_expansion` 4, `mod` 5, `episode` 6, `season` 7, `remake` 8, `remaster` 9, `expanded_game` 10, `port` 11, `fork` 12, `pack` 13, `update` 14.

### 1.4 Filter syntax and the edition example

- Docs example, "Search games but exclude versions (editions)": `fields name, involved_companies; search "Assassins Creed"; where version_parent = null;` The docs add: "This will return search results with ID and name of the game but exclude editions such as 'Collectors Edition'."
- Filter postfixes (Filters section): `!= null` "The value is not null", `= null` "The value is null", `(V1,V2,...Vn)` "The value has any within the (comma separated) array (OR between values)", and `!(V1,V2,...Vn)` "The values must not exist within the (comma separated) array". The docs' own example uses the form `where themes != (42);`, which is the form verified live below.
- One docs example still filters on the deprecated field (`where category = 0 & platforms = 48;`). New code shouldn't copy it.

## 2. Live game-type list

`POST /v4/game_types` with `fields id,type,updated_at; sort id asc; limit 500;` returned 15 rows:

| ID | `type` | Old enum name | Games with this type | Of those, with a `version_parent` |
|---:|---|---|---:|---:|
| 0 | Main Game | main_game | 323,914 | 6,944 |
| 1 | DLC | dlc_addon | 17,844 | 23 |
| 2 | Expansion | expansion | 1,759 | 13 |
| 3 | Bundle | bundle | 7,290 | 964 |
| 4 | Standalone Expansion | standalone_expansion | 515 | 7 |
| 5 | Mod | mod | 10,314 | 12 |
| 6 | Episode | episode | 969 | 2 |
| 7 | Season | season | 873 | 0 |
| 8 | Remake | remake | 1,495 | 11 |
| 9 | Remaster | remaster | 1,423 | 33 |
| 10 | Expanded Game | expanded_game | 2,226 | 73 |
| 11 | Port | port | 8,446 | 23 |
| 12 | Fork | fork | 138 | 0 |
| 13 | Pack / Addon | pack | 9,100 | 1 |
| 14 | Update | update | 1,342 | 2 |

Counts come from `/v4/games/count` and will drift as IGDB grows. Other live counts:

- All games: 387,648. Games with `game_type = null`: **0**, so every record has a type today.
- Games with a `version_parent`: 8,108. Of those, **6,944 are typed Main Game**, so `game_type` alone can't detect editions.
- `game_type != (3,5,13,14)` (359,602) plus `game_type = (3,5,13,14)` (28,046) equals the total, so the `!= (...)` list filter behaves as documented.

## 3. Live search checks

Each title was searched with the existing script's plain search as the baseline (`scripts/igdb_search.py`, unchanged, exit 0), then with the same search plus type fields, then with a filter and `limit 11`. The first filtered run left out types 3, 5 and 14 only, so Pack / Addon records still appeared. The final run used the section 5 allow-list, which also drops Pack / Addon. The "Approved filter" column shows that final run. IDs are IGDB game IDs.

### 3.1 "The Witcher 3": matches the PRD

| ID | Name | `game_type` | `version_parent` | Approved filter |
|---:|---|---|---|---|
| 1942 | The Witcher 3: Wild Hunt | Main Game | none | **kept** |
| 13166 | …Blood and Wine | Expansion | none | **kept** |
| 12503 | …Hearts of Stone | Expansion | none | kept |
| 403150 | …Songs of the Past | Expansion | none | kept |
| 22439 | …Game of the Year Edition | **Bundle** | **1942** ("Game of the Year Edition") | **excluded** (on both counts) |
| 141472 | The Witcher 3: Wild Hunt + Dark Souls III | Bundle | none | excluded |
| 415005 | The Witcher 3: Wild Hunt Remastered | **Update** (parent game 1942) | none | excluded |
| 283715 | The Witcher 3: Enhanced Edition – Redux | Mod | none | excluded |

The filtered search also returned five Witcher 3 DLC quests (type DLC) that the plain top 10 didn't show. IGDB applies the `where` clause before the limit, which is what the "ask for 11, show 10" Next rule needs. 9 results came back, so this search has no page 2.

### 3.2 "Dark Souls III": matches the PRD

| ID | Name | `game_type` | `version_parent` | Approved filter |
|---:|---|---|---|---|
| 11133 | Dark Souls III | Main Game | none | kept |
| 141472 | The Witcher 3: Wild Hunt + Dark Souls III | Bundle | none | **excluded** |
| 28210 | Dark Souls III: The Fire Fades Edition | Bundle | 11133 | **excluded** |
| 47486 | Dark Souls III: Deluxe Edition | Bundle | 11133 | **excluded** |
| 89841 | Dark Souls III: Day One Edition | **Main Game** | **11133** | **excluded** (only by `version_parent`) |
| 194669, 188607 | Dark Souls III: Ascended / The Convergence | Mod | none | excluded |
| 321183 | Little Big Planet 3: Dark Souls 3 Costume pack | Pack / Addon | none | excluded |
| 26916, 23158 | The Ringed City / Ashes of Ariandel | Expansion | none | kept (appear once the filter clears the noise) |

### 3.3 "Resident Evil 2": matches the PRD, and Horror and Survival are still themes

| ID | Name | `game_type` | Platforms | Themes | Approved filter |
|---:|---|---|---|---|---|
| 167078 | Resident Evil 2 + Resident Evil 3 Bundle | Bundle | | Action | **excluded** |
| 880 | Resident Evil 2 | Main Game | PS1, PC, Dreamcast, GameCube, PS3, PSP | Action, Science fiction, **Horror, Survival** | kept |
| 19686 | Resident Evil 2 | Remake | PS4/5, Xbox, PC, Switch 2, … | Action, **Horror, Survival** | kept |
| 396728 | Resident Evil 2 | Remaster | PC | Action, Science fiction, Horror, Survival | kept |
| 287844 | Resident Evil 2 | Port | **Nintendo 64** | Action, Horror, Survival | kept |
| 186400, 217953, 347128 | Resident Evil 2 | Port | Game.com / Handheld LCD / PS4+PS5 | various | kept |
| 164773 | Resident Evil 2: Extra DLC Pack | Pack / Addon | | | excluded |

The live themes are still Horror (19) and Survival (21), as recorded in the PRD's Further Notes.

## 4. Treatment of every type (approved 2026-11-14)

"Badge" is the label shown on search results and My Saved Games. Main Game has no badge. The badge text is IGDB's own `type` name. Every row was approved as proposed. Any type IGDB adds in future is excluded until it's reviewed.

| ID | Type | Decision | Badge | Evidence |
|---:|---|---|---|---|
| 0 | Main Game | **Keep** (already agreed) | none | |
| 1 | DLC | **Keep** (already agreed) | DLC | Witcher 3 quests, Skyrim Dawnguard, Sims 4 Spa Day |
| 2 | Expansion | **Keep** (already agreed) | Expansion | Blood and Wine, Ringed City, Sims 4 Seasons |
| 3 | Bundle | **Exclude** (already agreed) | | GOTY Edition, the DS3 Fire Fades and Deluxe editions, RE2+RE3 bundle |
| 4 | Standalone Expansion | **Keep** (already agreed) | Standalone Expansion | Half-Life 2: Episode One/Two, Spider-Man: Miles Morales, Uncharted: The Lost Legacy |
| 8 | Remake | **Keep** (already agreed) | Remake | RE2 (2019), The Last of Us Part I, Black Mesa |
| 9 | Remaster | **Keep** (already agreed) | Remaster | Dark Souls: Remastered, Skyrim Special Edition, RE2 (2024 PC) |
| 11 | Port | **Keep** | Port | **Excluding ports would remove real games and platforms.** "Minecraft" (135400), the Bedrock game most players mean, is typed Port (of *Minecraft: Java Edition*). RE2's Nintendo 64 port (287844) is a separate record, and Nintendo 64 isn't in the main game's platform list, so an N64 player couldn't record their platform without it. Same for Skyrim on Switch (37034) and Skyrim VR (37088). Cost: some searches show several same-named records (4 RE2 ports), which the Port badge tells apart. |
| 10 | Expanded Game | **Keep** | Expanded Game | Persona 5 Royal (114283), Mario Kart 8 Deluxe, Skyrim Anniversary Edition (165192). Players often track these separately from the original. Retail editions *of* them (P5R Launch and Limited Editions) have a `version_parent` and are already excluded. |
| 6 | Episode | **Keep** | Episode | Deltarune chapters 1–7, Minecraft: Story Mode episodes, BioShock Infinite: Burial at Sea 1–2. These are separately released, playable parts. |
| 7 | Season | **Keep** (closest call) | Season | Championship Manager: Season 03/04 and 99/00 are separate retail games. Against it: a "Fortnite" search with the approved filter shows 6 Fortnite Seasons in 11 results. Only 873 records exist, so it rarely matters outside live-service games. |
| 12 | Fork | **Keep** (not in the PRD's list) | Fork | Only 138 records, all separately run games: Predecessor (from Paragon), APB Reloaded, Mir Tankov (from World of Tanks), Etterna. Not near-duplicates. |
| 5 | Mod | **Exclude** | | Fan-made, not official releases, and they crowd searches for popular games. "Half-Life 2" plain search: **9 of 11 results are mods**, with the base game 4th. "Hollow Knight": 6 of 10. "Skyrim": 4 of 10. Cost: notable total conversions like *Enderal* and *Portal Stories: Mel* can't be saved. |
| 13 | Pack / Addon | **Exclude** | | Cosmetic and content packs: "Fortnite: May 2024 Fortnite Crew Pack" (top Fortnite result), Minecraft skin packs, Sims "Stuff" packs, "Persona 5 Royal Persona Set", and a LittleBigPlanet 3 costume pack that shows up in a Dark Souls III search. Real Sims expansions and game packs are typed Expansion or DLC, so they stay. |
| 14 | Update | **Exclude** | | Mostly near-duplicates of the base game: "The Witcher 3: Wild Hunt Remastered" (the 2026 next-gen update, parent 1942), "Sekiro – Game of the Year Edition", Minecraft "Village & Pillage" and "Caves & Cliffs Part II" (listed twice, once per parent). Cost: free content updates like *Hollow Knight: Godmaster* and *Lifeblood* can't be saved separately, but they come with the base game. |
| | *any type* with a `version_parent` | **Exclude** (already agreed: "editions") | | 8,108 records. Includes editions typed Main Game (DS3 Day One, Persona 5 Ultimate, P5R Launch Edition). |

## 5. Approved `where` clause

Search and import (fetch by ID) both use:

```
where version_parent = null & game_type = (0,1,2,4,6,7,8,9,10,11,12);
```

- **Allow-list, not deny-list.** Live, the allow-list returns the same 352,473 games as `version_parent = null & game_type != (3,5,13,14);`, and the same results for all three test searches. The difference is in the future: if IGDB adds a new type, an allow-list leaves it out until it's reviewed (and given a badge), instead of showing it with no label.
- **One rule in two places.** The save service applies the same rule in Python, both to a newly fetched record and to a Game already stored locally: `version_parent` must be empty and `game_type` must be in the allowed set. That way an excluded ID posted directly is rejected (PRD stories 35 and 98), with the message "This release can't be saved. Search for the base game or a supported release." The search adds the clause to every query, so the "ask for 11, show 10" Next rule stays accurate.
- **Search ordering (checked live in Phase 7, 2026-11-15).** In Phase 1, the deny-list run and the logically equivalent allow-list run for "Resident Evil 2" returned the main-game, remake, remaster and port records in a different order, so Phase 7 checked ordering with the real client (`games.igdb.search_games`: this `where` clause, `limit 11`, offset (page − 1) × 10). Full record: [docs/verification.md](../verification.md), "Live client ordering check".
  - **Repeated searches are stable.** Three repeated runs of the same `star` search returned identical ordered IDs on page 1 and on page 2, and none of the 10 IDs shown on page 1 appeared among the 10 shown on page 2.
  - **Changing `limit` or `offset` changed the order of some results.** Compared with one wide request (offset 0, limit 30), the page requests (limit 11) returned some pairs in the other order: positions 2–3, 11–12 (page 1's hidden 11th result, 17030, came back second on page 2), 19–20, and 27–29 against page 3. The sets of shown IDs per page still matched the wide request's positions 1–10, 11–20 and 21–30.
  - **Consequence:** a duplicate or skipped result at a page boundary is **possible** if two such results straddle positions 10 and 11. **Neither was observed in this check.** The Next rule is unaffected, because it only counts whether an 11th result came back.
  - **Decision (user, 2026-11-15):** keep the query and IGDB's relevance order, with no `sort` added, and document this as a known limitation.

## 6. Decisions carried downstream (approved 2026-11-14)

1. **Model:** `Game` stores `game_type` as IGDB's integer ID, with labels from section 4, **and** the `version_parent` IGDB ID (nullable). The stored-classification rule needs both, because an edition like DS3 Day One is typed Main Game and only its version parent excludes it.
2. **Saving:** both checks run when importing a new game **and** when saving a game already stored locally (without calling IGDB in the second case).
3. **Refresh:** a successful refresh updates both `game_type` and `version_parent`. If the game becomes ineligible, existing entries and their tracking data are kept, and only new saves are refused.
4. **Message:** `game_category_excluded` is "This release can't be saved. Search for the base game or a supported release."
5. **PRD and plan:** the PRD's Game Category rules, stories 13–15, 35, 78 and 98, the save-service, refresh, error-table and acceptance sections, and the plan's architectural decisions and Phases 1, 7, 8 and 9 were updated to match.

## 7. Method and secrets

- The live queries ran from throwaway scripts in the session scratchpad (not in the repo). They reused `scripts/igdb_search.py`'s credential loading, token request and HTTP error handling. No credentials or tokens were printed, logged or written to this note. The committed script is unchanged, and `uv run scripts/igdb_search.py "The Witcher 3"` still exits 0 (8 results).
- Requests were sent one at a time with a 0.3-second pause, which stays under IGDB's 4 requests per second.
