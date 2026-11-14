# Video Game API Comparison for the Django Game Tracker

**Sources accessed:** 2026-11-14 (every URL below was fetched that day unless marked otherwise)

## Decision

**Chosen API: IGDB (decided 2026-11-14).** IGDB was chosen for a personal video game tracker because it provides the game metadata the app needs (title, stable ID, platforms, release date, cover art and summary from one search call [1, Search; Expander]) and its official FAQ explicitly allows local storage: "Am I allowed to store/cache the data locally? Yes. In fact, we prefer if you store and serve the data to your end users" [1, Business FAQ #3]. **RAWG** was the alternative considered (see §2 and §6). **Still open:** the Twitch Developer Services Agreement's 24-hour caching rule and whether it applies to IGDB (see §1.3 and §1.5 item 1).

## Summary

**Recommendation: use IGDB as the primary API and RAWG as the backup.** One IGDB search call can return the title, ID, platforms, release date, cover and summary together, because IGDB lets you pull fields from related records in the same request ("expansion") [1, Expander; Search]. IGDB's FAQ also says plainly that storing and caching data locally is allowed and preferred [1, FAQ "Am I allowed to store/cache the data locally?"]. That covers the requirement that saved games stay available during an outage. IGDB already blocks browser calls, so a server-side Django design is the only way to use it, and that keeps credentials off the client. The costs: the setup has more steps (Twitch account, 2FA, client ID and secret, a token that expires after about 60 days). There is also a real conflict in the terms: the general Twitch Developer Services Agreement IGDB points to has a 24-hour caching rule [2, Schedule 1 §C]. RAWG is the simplest to start with (one API key in a query string). Its search results include everything except the description, which needs a second call per game. Its free tier carries a "hyperlink on every page" attribution rule and its terms say nothing about caching. CheapShark is a price-comparison API for PC game deals, not a game database, so it is not suitable as the main source. TheGamesDB looks workable but its terms could not be verified.

---

## Comparison table

| | **IGDB** | **RAWG** | **CheapShark** | **TheGamesDB** |
|---|---|---|---|---|
| **Title search** | `POST https://api.igdb.com/v4/games` with body `search "zelda"; fields ...;` [1] | `GET https://api.rawg.io/api/games?key=KEY&search=zelda` [3][4] | `GET https://www.cheapshark.com/api/1.0/games?title=batman` [5] | `GET https://api.thegamesdb.net/v1.1/Games/ByGameName?apikey=KEY&name=...` [6] |
| **Fields in one search call** | All of them: name, id, slug, platforms (expandable to names), `first_release_date` (Unix), cover (expandable to `image_id`), summary [1] | id, slug, name, released, background_image, platforms. **No description** (needs `/games/{id}`) [4] | gameID, steamAppID, title (`external`), cheapest price, thumb. **No platforms, release date or description** [5] | id, game_title, release_date, platform; `overview` via `fields=`, boxart via `include=` [6] |
| **Auth** | Twitch OAuth2 client credentials. Client ID and secret give a bearer token; the token lasts about 60 days, max 25 active [1] | API key as a `key` query parameter [3] | None (descriptive User-Agent required) [5] | API key as an `apikey` query parameter [6] |
| **Limits** | 4 requests/sec; up to 8 open requests at a time [1, Rate Limits] | Free: 20,000 requests/month [3] | Undisclosed rate limit; 429 + `Retry-After` [5] | Monthly allowance (amount not stated; example shows `remaining_monthly_allowance`) [6] |
| **Commercial** | Docs say free non-commercial under the Twitch DSA; FAQ says free for commercial too, via partnership [1] | Pricing says Free = "Non-commercial projects only"; ToS allows free commercial use under 100k MAU [3] | Free; you may not use your own store affiliate links [5] | Not verified |
| **Browser use** | Blocked (no CORS) because it "would leak your access token" [1] | Possible, but the key would be visible in the query string (docs silent) [3] | Fully supports CORS; browser calls are encouraged [5] | Not verified |
| **Local storage** | FAQ: "Yes. In fact, we prefer if you store..." [1]. **Conflicts with** the Twitch DSA 24-hour cache rule [2] | Silent. "No data redistribution" / "No cloning" [3][4] | Discourages "automated requests to build a cached catalog" [5] | Not verified |
| **Attribution** | DSA: "clear path to the source... Appropriately attribute" [2]; FAQ: visible, static attribution (stated for partnerships) [1] | "attribute RAWG as the source... active hyperlink from every page where the data of RAWG is used" [3] | Not required, "appreciated"; deal links must go through CheapShark redirect [5] | Not verified |
| **Cover art** | `https://images.igdb.com/igdb/image/upload/t_{size}/{image_id}.jpg`, 10 sizes plus `_2x` [1] | `background_image` URL (a background/screenshot image, not necessarily box art) [4] | `thumb` URL hosted on third-party store CDNs [5] | `https://cdn.thegamesdb.net/images/{size}/...` [6] |

---

## 1. IGDB (Internet Game Database)

### 1.1 Search and fields
- **Endpoint and syntax:** Base URL `https://api.igdb.com/v4`. "Most of the requests to the API will use the POST method", and the query language (Apicalypse) goes in the request body [1, Requests]. Search: "The search string is then entered in the body of the request by typing search, blank space followed by the string you wish to search for", e.g. address `https://api.igdb.com/v4/games/`, body `search "zelda";` Results "are sorted by similarity to the given search string" [1, Search].
- **One-call example** (built from the documented Fields, Expander and Search syntax [1]):
  ```
  POST https://api.igdb.com/v4/games
  Client-ID: <client id>
  Authorization: Bearer <access_token>

  search "zelda";
  fields name, slug, first_release_date, summary, platforms.name, cover.image_id;
  where version_parent = null;
  limit 20;
  ```
  The `where version_parent = null` filter appears in the docs' own example for leaving out editions/versions [1, examples].
- **Fields (Game endpoint)** [1, Game]: `id`; `name`; `slug`; `first_release_date`, a "Unix Time Stamp" for "The first release date for this game"; `platforms`, an "Array of Platform IDs"; `cover`, a "Reference ID for Cover"; `summary`, "A description of the game"; also `storyline`, `url`, `genres`, `total_rating`, etc.
- **One call or follow-ups:** `platforms` and `cover` are only IDs by default. The Expander lets you "access more information from them in the same query, instead of having to do multiple queries" (e.g. `genres.name`) [1, Expander]. FAQ #5: "An empty request will only yield a list of IDs... you should expand your request. Ex: `fields *, cover.*;`" [1, Technical FAQ]. Default limit is 10, max 500 [1, Pagination].
- **Cover art URL:** `https://images.igdb.com/igdb/image/upload/t_{size}/{hash}.jpg`, where "hash is the id of the image" [1, Images]. Sizes: `cover_small` 90x128, `cover_big` 264x374, `thumb` 90x90, `micro` 35x35, `screenshot_med/big/huge`, `logo_med`, `720p`, `1080p`. Append `_2x` for retina. The FAQ notes the API returns a `t_thumb` URL by default and you should "manually create your own image url using the image_id" [1, Technical FAQ #2].

### 1.2 Signup, auth, free tier
- **Signup** [1, Account Creation]: you need a Twitch account, "Ensure you have Two Factor Authentication enabled", register an app in the Twitch Developer Portal (`https://dev.twitch.tv/console/apps`), set the OAuth Redirect URL to `localhost` ("not used by IGDB"), and set Client Type to **Confidential** to generate a Client Secret.
- **Auth** [1, Authentication]: `POST https://id.twitch.tv/oauth2/token?client_id=...&client_secret=...&grant_type=client_credentials` returns `access_token`, `expires_in` (seconds) and `token_type: bearer`. Send the headers `Client-ID: <id>` and `Authorization: Bearer <token>`. FAQ #4: "Your Access Token is only active for 60 days and your application can only have 25 active Access Tokens at one time, going over this limit starts to inactivate older tokens" [1, Technical FAQ]. **Implication:** don't request a new token on every request. Cache it and refresh when it expires or on a 401.
- **Rate limits** (IGDB API docs, "Rate Limits" section, https://api-docs.igdb.com/ [1]):
  - **4 requests per second.** Going over returns HTTP 429 Too Many Requests.
  - **Up to 8 open requests at a time** ("Up to 8 open requests at any moment in time").
  - No monthly quota is stated.
  - *Source note:* quoted from the docs as fetched on 2026-11-14. A later re-check that day got HTTP 403 for automated fetching, so if you need to cite it in coursework, confirm the section in a browser.
- **Commercial:** "The IGDB.com API is free for non-commercial usage under the terms of the Twitch Developer Service Agreement" [1, Account Creation]. The FAQ also says "The API is free for both non-commercial and commercial projects", with commercial use through a partnership [1, Business FAQ #1–2]. A class demo is non-commercial.
- **Browser vs server:** "The IGDB API does not support browser requests, CORS, for security reasons. This is because the request would leak your access token! We suggest that you create a backend proxy" [1, Technical FAQ #3]. Django views calling IGDB server-side is the intended pattern.
- **Credential confidentiality:** "All activities that occur using your Keys are your responsibility. Keep them secret. Also, you may not sell, transfer, or sub-license them" [2, §IV]. So never commit the secret to the public repo.

### 1.3 Local storage / caching
- **IGDB FAQ:** "Am I allowed to store/cache the data locally? Yes. In fact, we prefer if you store and serve the data to your end users. You remain in control over your user experience, while alleviating pressure on the API itself" [1, Business FAQ #3]. Also: "You are allowed to keep all data you retrieve from the API and we will not ask you to remove the data in case of partnership termination" [1, Business FAQ #5, about partnerships].
- **Twitch DSA (last modified 12/04/2024), Schedule 1 §C "Storage of Program Materials/Twitch Content":** "Do not store copies of Twitch Content or Program Materials, unless you: (a) obtain prior written authorization from Twitch (through these terms or otherwise); (b) control the rights associated with such content; or (c) cache such information for only a twenty-four hour time period without further sharing it with third parties." It adds "Re-syndication and re-distribution ... is prohibited" and you must "update cached results" and "delete Program Materials ... when Twitch reports them as deleted" [2]. §VII.B: "You must update Program Materials used in Your Services frequently" [2]. §IX: on termination you "must cease use of all Program Materials and delete all Twitch Data" [2].
- **Reading:** The IGDB FAQ is arguably the "prior written authorization ... (through these terms or otherwise)" that exception (a) allows, and the IGDB docs also say "the API is free... under the terms of" the DSA. Schedule 1 also says it applies to "Twitch APIs" at `https://dev.twitch.tv` [2], and it is unclear whether `api.igdb.com` counts. **See Unclear list.** For a class demo, a reasonable approach is: store what the user saves, add a "refresh from IGDB" action, and keep the `fetched_at` timestamp.

### 1.4 Attribution and cover art
- **Non-commercial attribution:** No IGDB-specific wording was found for free/non-commercial use. The DSA §VII.C requires: "You must ensure that there is a clear path to the source from displays of Program Materials in Your Services. Appropriately attribute uses of Program Materials or Twitch Content" [2]. The FAQ (in the partnership context) expects "attribution that is visible to your users and located in a static location (e.g. not in a change log)" [1, Business FAQ #4]. **Practical choice:** a footer on every page, "Game data and images provided by IGDB.com", linking to `https://www.igdb.com`, plus a link to each game's IGDB `url` on its detail page.
- **Images:** The docs give only the URL format and sizes [1, Images]. I found nothing in the IGDB docs about hotlinking or downloading cover images, or who holds the copyright. The DSA says Twitch, "its licensors, and its end users retain all ... rights" in Program Materials [2, §III], and you must not "remove, modify, or obscure any copyright ... or attribution notices" [2, §II].

### 1.5 Unclear / unverified (IGDB)
1. **Caching conflict:** IGDB FAQ ("we prefer if you store") vs DSA Schedule 1 §C (24-hour cache unless authorized). It is unclear whether the FAQ counts as the "written authorization", and whether Schedule 1 (defined as the APIs at dev.twitch.tv) covers IGDB at all.
2. **No explicit attribution wording for non-commercial users.** The FAQ guidance is framed around commercial partnerships.
3. **Image rights and hotlinking:** the docs are silent on whether `images.igdb.com` may be hotlinked indefinitely or images may be downloaded and stored.
4. **"Non-commercial" vs "free for commercial":** the docs say both, in different sections [1].
5. The Twitch Developer Agreement page at `https://www.twitch.tv/p/legal/developer-agreement/` redirects to `https://legal.twitch.com/legal/developer-agreement/`, which is the version quoted here.

---

## 2. RAWG

### 2.1 Search and fields
- **Endpoint:** `GET https://api.rawg.io/api/games` with parameters `search` ("Search query"), `search_precise` ("Disable fuzziness"), `search_exact` ("Mark the search query as exact"), `page_size` [4, /games]. The apidocs page shows the key goes in the query string, `?key=YOUR_API_KEY`, and gives the example `https://api.rawg.io/api/games?search=303%20squadron&search_precise=true` [3, Latest updates].
- **Example:** `GET https://api.rawg.io/api/games?key=$RAWG_API_KEY&search=hollow%20knight&page_size=10`
- **Fields in search results** (`Game` schema) [4]: `id` (integer), `slug`, `name`, `released` (date), `tba`, `background_image` (URI), `rating`, `metacritic`, `playtime`, `updated`, `esrb_rating`, `platforms` (array of `{platform: {id, slug, name}, released_at, requirements}`).
- **Follow-up needed for the description:** `description` is only in the `GameSingle` schema from `GET /games/{id}` [4]. That means one extra request per saved game (fine: do it once at save time).
- **Cover art:** The only image field is `background_image`. The spec doesn't describe sizes or formats [4]. Whether it is box art or a screenshot isn't documented (unverified).

### 2.2 Signup, auth, free tier
- **Key:** "Get API Key" on `https://rawg.io/apidocs` (requires a RAWG account). "You must include an API key with every request" [3]. The spec adds: "If you don't provide it, we may ban your requests" [4, info].
- **Free tier:** "For personal and hobby projects... Non-commercial projects only... up to 20,000 requests per month... Required backlinks to RAWG from pages where the data is used" [3, Pricing]. Business is listed at $149/month with 50,000 requests [3, Pricing]. The page layout makes that price easy to misread as Free's, but it belongs to Business.
- **Commercial:** The ToS on the same page say "Free for commercial use for startups and hobby projects with not more than 100,000 monthly active users or 500,000 page views per month" [3, Terms of Service]. The pricing table says the opposite ("Non-commercial projects only"). The general site Terms (last updated 08/04/2019) say you may not use RAWG "including ... APIs ... other than for private, non-commercial purposes" [7]. A class demo is non-commercial either way.
- **Browser vs server:** The docs don't cover this. Because the key is a URL query parameter, any browser call would expose it in DevTools. Call RAWG only from Django views.
- **No per-second rate limit** is documented [3][4].

### 2.3 Local storage / caching
- The API terms don't mention caching, storage duration or refresh. The relevant clauses: "No data redistribution... you may use the data with your API access only for your projects" [3, Terms of Service], and "No cloning... if you used our API to launch a clone of RAWG" [4, info, Terms of Use]. The site Terms say content is subject to "database rights" and may be used "only as strictly required for permitted personal, non-commercial purposes" [7, Intellectual Property].
- **Reading:** saving a few user-selected games for personal tracking doesn't look like redistribution or cloning, but nothing explicitly permits it.

### 2.4 Attribution and cover art
- **Required:** "Free for personal use as long as you attribute RAWG as the source of the data and/or images and add an active hyperlink from every page where the data of RAWG is used" [3, Terms of Service]. No exact wording is prescribed. Placement: **every page** that shows RAWG data, with an active link (so a site-wide footer link works).
- **Images:** "We do not claim ownership of any of the images or data provided by the API. We remove infringing content when properly notified... You are prohibited from using the images and/or data in connection with libelous, defamatory, obscene, pornographic, abusive or otherwise offensive content" [3, API Legal Notice]. Nothing on hotlinking vs downloading.

### 2.5 Unclear / unverified (RAWG)
1. Commercial terms contradict each other: Pricing says "Non-commercial only", the API ToS allow free commercial use under 100k MAU, and the site Terms (2019) say private non-commercial only [3][7].
2. No caching or storage rule at all.
3. No rule on hotlinking vs downloading `background_image`, and RAWG disclaims owning the images, so rights sit with third parties.
4. No documented rate limit apart from the monthly quota. What happens past 20,000 requests isn't stated.
5. "API key-based requests signing. The old method of signing with User Agent string will be slowly deprecated" [3]. It's unclear whether a User-Agent is still expected.

---

## 3. CheapShark

### 3.1 Search and fields
- **Endpoint:** "List of Games": `GET https://www.cheapshark.com/api/1.0/games?title=batman`. Parameters: `title` ("Search for a game by title, case insensitive"), `steamAppID`, `limit` (default and max 60), `exact` [5, Games]. It "Response includes the cheapest current deal for each game" [5].
- **Fields** (documented example response) [5]: `gameID`, `steamAppID`, `cheapest`, `cheapestDealID`, `external` (the title), `internalName`, `thumb` (an image URL on store CDNs, e.g. `cdn.fanatical.com`). "Game Lookup" (`/games?id=`) adds `cheapestPriceEver` and a `deals` list [5].
- **Missing:** no platforms (it covers "digital PC Games" only), no description, and no release date on the Games endpoints. Deal records do have `releaseDate` ("All date fields (releaseDate, lastChange, etc.) are returned in Unix Timestamp format") [5, Deals].

### 3.2 Signup, auth, free tier
- "The API is completely public, no authorization or API Key is needed." You must send a User-Agent, "ideally ... descriptive and specific to your application", optionally with a contact email [5, Authorization, Rate Limiting & Caching]. (Don't put a personal email in a public repo; use a generic project UA.)
- Rate limit: undisclosed. Too many requests get a 429 and a temporary block, with `Retry-After` giving the remaining time. "All API clients are subject to the same limits" [5].
- Terms: "The API is completely free, the only condition being that you use CheapShark links when sending users to deals... you may not make use of our API if you use your own affiliate links for ANY of the stores we track" [5, Important Usage Notes].
- Browser: "The API fully supports CORS, so requests should come directly from the user's browser or app (whenever possible)" [5]. No key, so nothing can leak.

### 3.3 Local storage / caching
- "The API is designed to be called directly in response to user input... Excessive automated requests to build a cached catalog of data will run into rate limiting issues (including a permenant block) and should be avoided" [5]. That targets bulk crawling. Storing a few user-selected games isn't addressed. Prices change "about once per hour" [5, Deals], so stored prices go stale quickly.

### 3.4 Attribution and cover art
- Attribution: "while not a requirement, it is always appreciated if you mention somewhere that your app or site is making use of the CheapShark API" [5]. Deal links must use `https://www.cheapshark.com/redirect?dealID={id}`, which "is not an API endpoint and will block automated access" [5, Deals].
- Images: `thumb` URLs point to third-party store CDNs [5]. The docs say nothing about image rights.

### 3.5 Unclear / unverified (CheapShark)
1. The actual numeric rate limit.
2. Whether storing a few user-selected game records counts as the discouraged "cached catalog".
3. Rights to `thumb` images hosted by stores.
4. **Fit:** it's a deals API, so it can't supply platforms, summary or a reliable release date from a title search. Only useful as an optional "current best price" add-on.

---

## 4. TheGamesDB (additional candidate)

### 4.1 Search and fields
- `GET https://api.thegamesdb.net/v1.1/Games/ByGameName?apikey=KEY&name=sonic&fields=overview&include=boxart,platform` [6]. v1.1 "Supports optional `mode=natural` for full-text natural language search" [6].
- Search returns `id`, `game_title`, `release_date`, `platform` (ID). `overview` (description) via `fields=`; boxart via `include=boxart`, which returns `base_url` entries for `original`, `small`, `thumb`, `cropped_center_thumb`, `medium`, `large` at `https://cdn.thegamesdb.net/images/{size}/` [6]. So one call gets everything; platform names come via `include=platform`.

### 4.2 Auth, limits, terms
- `apikey` query parameter, required [6]. Responses include `remaining_monthly_allowance`, `extra_allowance` and `allowance_refresh_timer: 2592000` (30 days). 403 means "bad API key or hit rate-limit cap" [6]. The real allowance size isn't documented (the example shows 249 remaining).
- The spec's `license` is "GNU General Public License v3.0" (the API code repository) [6]. That isn't a data-use license.
- **Key request, terms of use, attribution and image rules: not verified.** The forum where keys are requested (`forums.thegamesdb.net`) returned 401/unauthorized when fetched.

### 4.3 Unclear / unverified (TheGamesDB)
1. How to get a key and how long approval takes. 2. Terms of use, caching and attribution. 3. Image rights. 4. Monthly allowance size.

---

## 5. Excluded candidates

- **Giant Bomb API:** The official pages (`giantbomb.com/api/`, `/api/documentation/`, `/terms-of-service`) returned HTTP 403 to automated fetching, so nothing could be verified. Secondary sources only (unverified): free for non-commercial use, about 200 requests per resource per hour, keys not to be shared [search results; third-party directories and a Giant Bomb forum thread]. Excluded because nothing could be checked against primary sources.
- **MobyGames API:** The official `mobygames.com/info/api` returned HTTP 403. Search snippets (unverified) say there is a free API for not-for-profit use with a key from your profile page, commercial use by email request, and that a paid MobyPro subscription doubles the rate limit. Excluded for the same reason. Also, any key-holder benefit tied to a paid tier is a longevity concern for a free student project.
- **Steam Web API / Storefront:** The Steam Web API Terms allow "one hundred thousand (100,000) calls ... per day" and require "keep your Steam Web API key confidential", but they "do not mention" a search-by-title endpoint [8]. I found no official documentation for a Storefront title-search endpoint (unverified), and Steam only covers Steam/PC titles. Excluded.

---

## 6. Recommendation and decision

**First choice: IGDB. Backup: RAWG.** **Decision (2026-11-14): IGDB was chosen**, with RAWG kept as the alternative considered (see [Decision](#decision)). The Twitch agreement question below is still unresolved.

| Factor | IGDB | RAWG |
|---|---|---|
| Ease of auth for a student | Harder: Twitch account + 2FA, confidential app, client-credentials token, refresh about every 60 days [1] | Easy: one key in the query string [3] |
| Fields from one search call | Complete with expansion (title, ID, platforms, date, cover, summary) [1] | All except description; one extra `/games/{id}` call per saved game [4] |
| Storage for the outage requirement | Explicitly allowed by the IGDB FAQ [1], but the general DSA has a 24-hour cache rule [2] (flagged) | Silent; only "no redistribution / no cloning" [3][4] |
| Attribution burden | Low and loosely defined: "clear path to the source", visible static attribution [1][2] | Specific and strict: active hyperlink on **every page** showing RAWG data [3] |
| Public-repo credential handling | Two secrets (ID + secret) in `.env`. The API blocks browser use, which keeps you server-side [1] | One key, but it sits in URLs, so watch logs, error pages, and never call it from templates/JS |
| Longevity / stability | Docs and auth are under the Twitch Developer Services Agreement; the DSA lets Twitch terminate "for any reason or no reason at all" [2] | Site Terms last updated 2019 [7]; commercial terms contradict each other [3]. Long-term stability not verifiable from primary sources |

**Why IGDB first:** it's the only option where (a) one request returns every field the model needs and (b) the provider's own docs say "we prefer if you store and serve the data". That fits saving games locally and showing them during an outage. The extra auth setup is a one-time cost of about 20 lines of Django code (fetch the token, cache it, retry once on a 401).

**When to pick RAWG instead:** if Twitch signup or 2FA is a blocker, or you want a working search in the first hour. Plan for the second call at save time and a site-wide "Data from RAWG.io" footer link.

**Decision points for the user:** if you want zero ambiguity on storage, email IGDB/Twitch support to confirm the FAQ overrides the DSA 24-hour rule for non-commercial use, or keep a "Refresh from API" button and `fetched_at` so data can be refreshed regularly.

---

## 7. Practical notes for Django

### 7.1 Suggested model fields (SQLite)
```python
class Game(models.Model):            # cached API data
    source        = models.CharField(max_length=20, default="igdb")   # "igdb" | "rawg"
    external_id   = models.CharField(max_length=50)                   # IGDB id / RAWG id
    slug          = models.SlugField(max_length=255, blank=True)
    title         = models.CharField(max_length=255)
    platforms     = models.JSONField(default=list, blank=True)        # ["PC", "Nintendo Switch"]
    release_date  = models.DateField(null=True, blank=True)           # convert IGDB Unix ts
    summary       = models.TextField(blank=True)
    cover_image_id = models.CharField(max_length=100, blank=True)     # IGDB image_id
    cover_url     = models.URLField(blank=True)                       # built URL / RAWG background_image
    source_url    = models.URLField(blank=True)                       # IGDB `url` / rawg.io/games/<slug>, for attribution
    fetched_at    = models.DateTimeField(auto_now=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=["source", "external_id"], name="uniq_source_game")]

class Entry(models.Model):           # the user's own data
    user, game (FK), status (choices), rating (1-10, nullable), notes, created_at, updated_at
```
Keep the user's own fields (status, rating, notes) separate from cached API data. Those are user-generated and not subject to the provider's terms, and you can refresh `Game` without touching them.

### 7.2 Image URLs vs downloaded files
- **Store URLs (and the IGDB `image_id`), don't download files.** None of the providers grants a right to download and re-host images. IGDB publishes a URL scheme for its own image server [1]. RAWG disclaims owning the images [3]. CheapShark thumbs are third-party store CDN images [5]. Storing the `image_id` lets you rebuild any size (`t_cover_big`, `t_cover_small_2x`) later.
- **Outage behavior:** text fields come from SQLite and stay available. Images load from the provider's CDN, which is separate from the API, but if it's down too, show a local placeholder (`<img ... onerror="this.src='{% static "img/no-cover.png" %}'">`). Downloading images to survive an outage isn't clearly permitted by any of these terms (see Unclear lists).

### 7.3 Environment variables (`.env`, gitignored; commit a `.env.example` with blank values)
```
DJANGO_SECRET_KEY=
DJANGO_DEBUG=True
IGDB_CLIENT_ID=
IGDB_CLIENT_SECRET=
RAWG_API_KEY=
CHEAPSHARK_USER_AGENT=GameTrackerClassProject/1.0
```
- Don't put the IGDB **access token** in `.env`. Fetch it at runtime with the client ID and secret, then cache it (Django cache or a small DB row) until `expires_in`, because tokens expire after about 60 days and only 25 can be active [1].
- Call every API from views or service functions, never from templates or JS. IGDB blocks browser calls anyway [1], and RAWG keys in URLs would be exposed.
- Respect IGDB's 4 requests/sec and 8-open-request limits [1, Rate Limits] (one search per form submit is fine; don't fan out parallel calls). Keep RAWG under 20,000 requests a month [3] by not re-fetching saved games on every page view.
- Add a site-wide footer: "Game data and cover art from IGDB.com" (or "Data from RAWG.io"), linked, on every page [2][3].

---

## Sources
1. IGDB API Documentation (Getting Started, Account Creation, Authentication, Requests, Rate Limits, Game endpoint, Images, Fields, Expander, Search, Pagination, Partnership, FAQ, License): https://api-docs.igdb.com/ (rate limits are in the "Rate Limits" section; storage permission is in the FAQ's "Am I allowed to store/cache the data locally?")
2. Twitch Developer Services Agreement, last modified 12/04/2024 (§II, §III, §IV, §VII, §IX, Schedule 1 §B–C): https://legal.twitch.com/legal/developer-agreement/ (linked from IGDB docs as https://www.twitch.tv/p/legal/developer-agreement/)
3. RAWG API landing page (Adding the API key, Pricing, Terms of Service, API Legal Notice, Latest updates): https://rawg.io/apidocs
4. RAWG API reference / OpenAPI spec (info "Terms of Use", `/games`, `Game` and `GameSingle` schemas): https://api.rawg.io/docs/ (spec: https://api.rawg.io/docs/?format=openapi)
5. CheapShark API docs (Important Usage Notes; Authorization, Rate Limiting & Caching; Deals; Games): https://apidocs.cheapshark.com/ (content from the published Postman collection: https://documenter.gw.postman.com/api/collections/530355/RWTspajP?segregateAuth=true&versionTag=latest)
6. TheGamesDB API spec (`/v1/Games/ByGameID`, `/v1/Games/ByGameName`, `/v1.1/Games/ByGameName`): https://api.thegamesdb.net/ (spec: https://api.thegamesdb.net/spec.yaml)
7. RAWG Terms of Use, last updated 08/04/2019 (use restrictions, Intellectual Property): https://rawg.io/terms
8. Steam Web API Terms of Use: https://steamcommunity.com/dev/apiterms
9. Attempted but blocked (HTTP 403/401, not used for any claim): https://www.giantbomb.com/api/, https://giantbomb.com/terms-of-service, https://www.mobygames.com/info/api/, https://forums.thegamesdb.net/
