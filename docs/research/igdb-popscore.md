# IGDB PopScore: Verification for the "Popular on IGDB" Row

**Verified:** 2026-11-15 (official docs and one live run the same day)
**Status:** facts verified. Used by the follow-up after Phase 8 in [plans/video-game-tracker.md](../../plans/video-game-tracker.md).

## Summary

- **Endpoint:** `POST https://api.igdb.com/v4/popularity_primitives`. Each primitive is one game's value for one popularity type. It carries `game_id` only, so titles and covers need a second request to `/v4/games`.
- **Visits is `popularity_type = 1`.** It's named "Visits", and its source is 121 (IGDB). This matches the docs' example and the live `/v4/popularity_types` list.
- **Query used:** `fields game_id,value,popularity_type,calculated_at; sort value desc; limit 50; where popularity_type = 1;`. This is the docs' "top 10 games based on IGDB visits" example with a larger limit.
- **Refresh rate:** the docs say PopScore is "Updated every 24 hours". Live, all 50 primitives had the same `calculated_at` (2026-11-15T00:17:55Z). A one-hour cache is therefore never more than an hour behind IGDB's own data.
- **Eligibility matters:** 49 of the top 50 passed `ELIGIBILITY_WHERE`. Rank 28, *Web Dashers* (417220), is a Mod (`game_type` 5), so it was dropped and the next ranks filled in.

## 1. Official documentation

Source: IGDB API docs, <https://api-docs.igdb.com/>, retrieved 2026-11-15 with a plain HTTP GET (the automated fetch tool got HTTP 403 again, as in [igdb-game-types.md](igdb-game-types.md)).

### 1.1 PopScore section (quoted)

> IGDB PopScore offers "popularity primitives" from sources like IGDB page visits and list additions […] Updated every 24 hours […]
>
> "IGDB Visits": Game page visits on IGDB.com.

The section lists the other primitives too: IGDB Want to Play, Playing and Played; Steam 24hr Peak Players, Positive, Negative and Total Reviews, and Global Top Sellers; Most Wishlisted Upcoming; and Twitch Hours Watched.

Its example `popularity_types` result starts with `{ "id": 1, "popularity_source": 121, "name": "Visits" }`.

Use case 1, quoted:

> As an API user I'd like to fetch the top 10 games based on IGDB visits.
> `fields game_id,value,popularity_type; sort value desc; limit 10; where popularity_type = 1;`

The example result's top game is `game_id` 121 (Minecraft).

### 1.2 Popularity Primitive fields

Request path: `https://api.igdb.com/v4/popularity_primitives`

| field | type | description |
|---|---|---|
| `calculated_at` | datetime | |
| `checksum` | uuid | Hash of the object |
| `created_at` | datetime | Date this was initially added to the IGDB database |
| `external_popularity_source` | Reference ID for External Game Source | |
| `game_id` | Integer | |
| `popularity_source` | Popularity Source Enum | DEPRECATED! Use external_popularity_source instead |
| `popularity_type` | Reference ID for Popularity Type | |
| `updated_at` | datetime | The last date this entry was updated in the IGDB database |
| `value` | bigdecimal | |

### 1.3 Popularity Type fields

Request path: `https://api.igdb.com/v4/popularity_types`. Fields: `checksum`, `created_at`, `external_popularity_source`, `name`, `popularity_source` (deprecated), `updated_at`.

## 2. Live run (2026-11-15)

A throwaway scratchpad script (not committed) used the real `.env`. It printed only whether the credentials were present, plus IDs, names and counts. All requests returned HTTP 200.

### 2.1 `/v4/popularity_types` (`sort id asc`)

| id | name | source |
|---|---|---|
| 1 | Visits | 121 (IGDB) |
| 2 | Want to Play | 121 |
| 3 | Playing | 121 |
| 4 | Played | 121 |
| 5–10 | 24hr Peak Players, "Postitive Reviews" (IGDB's spelling), Negative Reviews, Total Reviews, Global Top Sellers, Most Wishlisted Upcoming | 1 (Steam) |
| 34 | 24hr Hours Watched | 14 (Twitch) |

### 2.2 `/v4/popularity_primitives` for type 1

- 50 records came back, with the keys `calculated_at`, `game_id`, `id`, `popularity_type` and `value`.
- `value` was in descending order, and every record had the same `calculated_at`.

### 2.3 Games for those IDs

`fields name, game_type, version_parent, cover.image_id; where version_parent = null & game_type = (0,1,2,4,6,7,8,9,10,11,12) & id = (…50 IDs…); limit 50;`

- 49 of the 50 were eligible. The one excluded game was 417220, *Web Dashers* (`game_type` 5, Mod, no version parent).
- **`limit 50` is required.** IGDB's default limit is 10, so without it most of the IDs would silently go missing.
- IGDB doesn't return the games in the order of the `id = (…)` list. The client puts them back in PopScore order.
- The top 10 eligible games, in rank order, all had covers:

| rank | IGDB ID | name | `game_type` |
|---|---|---|---|
| 1 | 405460 | The Legend of Zelda: Ocarina of Time | 8 (Remake) |
| 2 | 17269 | Roblox | 0 |
| 3 | 416015 | Rob Run | 0 |
| 4 | 87622 | Free Fire | 0 |
| 5 | 123 | World of Warcraft | 0 |
| 6 | 52189 | Grand Theft Auto VI | 0 |
| 7 | 1020 | Grand Theft Auto V | 0 |
| 8 | 135400 | Minecraft | 11 (Port) |
| 9 | 394401 | CAPTCHA Hell | 0 |
| 10 | 403310 | Call of Duty: Modern Warfare 4 | 0 |

## 3. Decisions for the row

- Ask for 50 Visits primitives, then fetch those games in one request with `ELIGIBILITY_WHERE`, `id = (…)` and `limit 50`. Keep PopScore order and the first 10 eligible games. That's two IGDB requests per refresh.
- Cache the finished row (IDs, titles, cover IDs, Game Category) under `igdb:popular_games` (no secrets in the key) for one hour. Never cache a failure.
- The row is a "what people are looking at" list, not a quality ranking. Entries such as *CAPTCHA Hell* and *Rob Run* are expected.
