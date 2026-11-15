# PRD: Django Video Game Tracker

## Problem Statement

I play and plan to play a lot of games across several platforms, and I have no single place to keep track of them. I want to look a game up, save it to my own list, and record where I am with it: whether I want to play it, am playing it, finished it, paused or dropped it, which platform I play it on, when I started and finished, how many hours I've put in, what I'd rate it, and my own notes.

Game databases like IGDB have the facts (titles, platforms, release dates, covers, genres, themes), but they can't hold my personal tracking data, and I can't rely on them being reachable whenever I want to look at my list. Search results are also full of editions and bundles that are really the same game sold differently, which makes it easy to save near-duplicates. Once my list grows, I need to search it, filter it, sort it, and page through it without IGDB. And because the list is personal, other people using the same app must not be able to see or change it, whether through the website or the API.

## Solution

A Django website and REST API where a signed-in user can:

- **Search IGDB** for games by title. Editions (any record with a version parent), bundles, mods, packs and updates are left out. DLC, expansions, standalone expansions, episodes, seasons, remakes, remasters, expanded games, ports and forks stay in, each marked with a Game Category badge. Games the user has already saved are marked "Saved" and linked to their entry.
- **Save a game** to their own list. The app stores the game's IGDB details locally (title, summary, release date, platforms, genres, themes, cover reference, Game Category, IGDB link), so the list stays browsable when IGDB is down.
- **Track and edit** their own status, favorite flag, rating, notes, platform played, start and finish dates, and hours played.
- **Browse their saved games** with search across several fields, filters (Status, Platform Played, Favorite, Theme), seven sort options, and 10 entries per page, all from the local database.
- **Refresh** a saved game's details from IGDB when they want newer data.
- **Remove** a game from their list after a confirmation page.
- **Use the same data through a token-authenticated API** that supports list, create, retrieve, update and delete, plus a small command-line client that lists entries and updates an entry's status.

Saved entries are private: each user sees and changes only their own, and attempts to reach someone else's entry behave as if it doesn't exist. When IGDB or Twitch fails, the user sees a clear, safe message, and their saved games stay available.

## User Stories

### Accounts and access

1. As a visitor, I want to create an account with a username and password, so that I can start my own game list.
2. As a new user, I want to be signed in automatically after registering, so that I can start using the tracker straight away.
3. As a returning user, I want to sign in and land on My Saved Games, so that my list is the first thing I see.
4. As a signed-out visitor who opens a protected page, I want to be sent to the login page and then returned to the page I asked for, so that I don't lose my place.
5. As a signed-in user, I want to sign out with a button, so that nobody else using this browser can see my list.
6. As a signed-out visitor, I want IGDB search and game details to be unavailable to me, so that anonymous traffic can't use up the app's IGDB allowance.
7. As a user, I want my saved entries to be visible only to me, so that my notes and ratings stay private.
8. As a user, I want any attempt to open, edit, delete or refresh another user's entry by ID to show "not found", so that nobody can even tell whether that entry exists.
9. As a superuser, I want the Django admin available, so that I can inspect and fix data while developing.
10. As a superuser, I want imported game, platform, genre and theme data to be read-only in the admin, so that I don't accidentally change data that comes from IGDB.
11. As a superuser, I want to be able to edit entry tracking fields in the admin, so that I can debug problems.

### Finding games through IGDB

12. As a user, I want to search IGDB by game title, so that I can find the game I want to track.
13. As a user, I want editions (such as Game of the Year or Complete editions), bundles, mods, packs and updates left out of search results, so that I don't save near-duplicates or add-ons of the same game.
14. As a user, I want DLC, expansions, standalone expansions, episodes, seasons, remakes, remasters, expanded games, ports and forks kept in results, so that I can track them separately from the base game.
15. As a user, I want a Game Category badge such as "Expansion", "Remake", "Remaster" or "Port" on results that aren't main games, so that I can tell them apart at a glance.
16. As a user, I want each result to show its cover, title, release date and platforms, so that I can pick the right game.
17. As a user, I want results I've already saved to show a "Saved" link to my entry instead of a Save button, so that I don't try to save them twice.
18. As a user, I want up to 10 results per page with Previous and Next links, so that I can look past the first results for vague searches.
19. As a user, I want the Next link to appear only when there really are more results, so that I never land on an empty page by following it.
20. As a user, I want the pager links to keep my search text, so that I don't have to retype it.
21. As a user, I want each new search to start on page 1, so that I see the most relevant results first.
22. As a user, I want a search with no results to say "No matches.", so that I know to try a different title.
23. As a user, I want a later page with no results to say "No more results" and link back to page 1, so that I can get back to the results.
24. As a user, I want a mistyped or missing page number in the address to show page 1, so that a bad link still shows something useful.
25. As a user, I want IGDB errors to show a clear message instead of "No matches.", so that I don't think a game doesn't exist when the service is just down.
26. As a user, I want my search text kept in the search box when a search fails, so that I can retry by submitting again.

### Saving games

27. As a user, I want to save a game from the search results, so that it's added to my list.
28. As a user, I want to go straight to the edit page after saving a new game, so that I can set my status and platform right away.
29. As a user, I want saving a game I already have to take me to my existing entry with "Already in your games", so that I don't end up with duplicates.
30. As a user, I want double-clicking Save, or saving from two tabs at once, never to create two entries for one game, so that my list stays clean.
31. As a user, I want saving a game someone else already saved to work even while IGDB is down, so that I can still add it to my list during an outage.
32. As a user, I want a failed save to return me to the same search results and page with an error message, so that I can try again without searching again.
33. As a user, I want to see the save error even if the search results can't be reloaded, so that I always know what went wrong.
34. As a user, I want a failed save to leave nothing half-saved, so that my list never contains broken entries.
35. As a user, I want excluded releases (editions, bundles, mods, packs, updates and any unreviewed type) refused when saving, even if their IDs are sent directly, so that the search filter can't be bypassed.

### Tracking my games

36. As a user, I want every new entry to start as "Want to Play" and not a favorite, so that I only fill in what I know.
37. As a user, I want to set my status to Want to Play, Playing, Completed, On Hold or Dropped, so that I can see where I am with each game.
38. As a user, I want to mark games as favorites, so that I can find my favorites quickly.
39. As a user, I want to rate a game from 1 to 10, or leave it unrated, so that I can record my opinion when I have one.
40. As a user, I want to write notes about a game, so that I can remember where I left off or what I thought.
41. As a user, I want to choose the platform I play on from that game's platforms, or leave it blank, so that my entry reflects how I play it.
42. As a user, I want to record start and finish dates, either of which may be left blank whatever my status, so that I can track when I played.
43. As a user, I want an error if my finish date is before my start date, so that my dates stay sensible.
44. As a user, I want to record hours played, and be prevented from entering a negative number, so that I can track my time.
45. As a user, I want the same validation rules on the website and through the API, so that data entered either way is equally valid.

### Browsing my saved games

46. As a user, I want My Saved Games to load entirely from the app's own database, so that I can browse it when IGDB is unavailable.
47. As a user, I want to search my saved games by title, summary, platform, genre, theme or my notes, so that I can find a game by whatever I remember about it.
48. As a user, I want each game to appear once in search results even when several of its details match, so that the list has no duplicates.
49. As a user, I want to filter by Status, so that I can see only games I'm playing, for example.
50. As a user, I want to filter by Platform Played, so that I can see what I play on a particular system.
51. As a user, I want to filter to favorites only, so that I can see my best games.
52. As a user, I want to filter by Theme (such as Horror or Survival), so that I can find games of a particular kind.
53. As a user, I want the Theme dropdown to list only themes from my own saved games, alphabetically, with All Themes as the default, so that every choice can produce results.
54. As a user, I want another user's saved games never to add themes to my Theme dropdown, so that I see nothing about their list.
55. As a user, I want to sort by Title A to Z, Title Z to A, Date Added (Newest First), Rating (Highest First), Release Date (Newest First), Hours Played (Most First) or Last Updated (Newest First), so that I can arrange my list the way I need.
56. As a user, I want Date Added (Newest First) to be the default sort, so that games I just saved appear at the top.
57. As a user, I want unrated games, unknown release dates and blank hours to sort last, so that games with real values come first.
58. As a user, I want ties broken the same way every time (title A to Z, then entry order), so that no game is repeated or skipped when I move between pages.
59. As a user, I want title sorting to ignore capital letters, so that "DOOM" and "Doom" sort together.
60. As a user, I want 10 games per page with links that keep my search, filters and sort, so that paging doesn't lose my view.
61. As a user, I want any change to the search, a filter or the sort to take me back to page 1, so that I start at the top of the new list.
62. As a user, I want Clear filters to reset every filter (including Theme) while keeping my search and sort and returning to page 1, so that I can widen my view without starting over.
63. As a user, I want a missing, non-numeric, zero or negative page number to show page 1, so that a bad link still works.
64. As a user, I want a page number past the end of my list to show the last page, so that an old bookmark still shows my games after I remove some.
65. As a user, I want an unknown sort value in the address to quietly use the default sort, so that a broken link still shows my list.
66. As a user, I want a malformed theme, or one that isn't in my saved games, to be ignored, so that a bad link still shows my list.
67. As a user, I want a clear empty message when my search and filters match nothing, so that I know to loosen them.
68. As a user, I want Game Category badges on My Saved Games too, so that I can tell an expansion from the base game in my list.

### Game details, covers and refresh

69. As a user, I want an entry detail page showing the large cover, game details and my tracking information, so that I can see everything about a game in one place.
70. As a user, I want small covers on lists and search results, sharp on high-resolution screens, so that games are easy to recognize.
71. As a user, I want the page layout to stay steady while covers load, so that content doesn't jump around.
72. As a user, I want a placeholder image when a game has no cover or the cover fails to load, so that pages never show broken images.
73. As a user, I want titles, platforms and my tracking data to show even when covers fail, so that an image outage doesn't hide my information.
74. As a user, I want a "Refresh from IGDB" button on my entry's detail page, so that I can update a game whose details have changed (for example, a newly announced release date).
75. As a user, I want a failed refresh to keep the existing details and show the usual error message, so that a refresh never damages my data.
76. As a user, I want repeated refreshes of the same game limited to one every 10 minutes across all users, so that the app doesn't use up its IGDB allowance.
77. As a user, I want "Data from IGDB" with a link and the last successful refresh time on the detail page, so that I know where the data came from and how fresh it is.
78. As a user, I want my entry and tracking data kept if a refresh makes the game ineligible for new saves (for example, it becomes an edition or an excluded type), so that I never lose my history.
79. As a user, I want my saved platform kept, with a warning, if a refresh removes it from the game's platforms, so that my data isn't silently changed.
80. As a user, I want to keep editing my other tracking fields while that stale platform is kept, and to have to pick a currently listed platform (or blank) if I change it, so that I'm never forced to fix something just to edit notes.

### Removing games

81. As a user, I want a confirmation page before a game is removed that names the game and explains that my status, rating, notes and hours played will be deleted, so that I don't remove a game by mistake.
82. As a user, I want a Cancel link on that page back to the entry, so that I can back out easily.
83. As a user, I want removal to return me to My Saved Games with a confirmation message, so that I know it worked.
84. As a user, I want removing my entry to leave the shared game and other users' entries untouched, so that my action affects only my own list.

### API

85. As an API client, I want to authenticate with a token in the Authorization header, so that scripts can use the API without a browser.
86. As a signed-in developer, I want the browsable API to work with my website session, so that I can explore it in the browser.
87. As an API client, I want unauthenticated requests rejected with 401, so that I know to supply a token.
88. As an API client, I want to list my entries with q, status, platform (Platform Played), favorite, theme, sort and page parameters that mean the same as on the website, so that one query means the same thing in both places.
89. As an API client, I want list responses to include count, next, previous and results, with 10 entries per page, so that I can page through all my entries.
90. As an API client, I want invalid filter, theme or sort values rejected with 400 and invalid or out-of-range pages with 404, so that my script gets clear errors instead of guesses.
91. As an API client, I want to create an entry by sending an IGDB ID and optional tracking fields, so that I can save games from a script.
92. As an API client, I want each entry returned with its tracking fields and nested, read-only game details (including platforms, genres, themes, Game Category and cover URL), so that one response tells me everything about the entry.
93. As an API client, I want PATCH to change only the fields I send while still checking them against the stored values, so that partial updates stay valid.
94. As an API client, I want PUT to replace all tracking fields, resetting omitted optional fields to blank or their defaults, so that full replacement behaves predictably.
95. As an API client, I want changing the IGDB ID on update rejected, so that an entry always tracks the game it was created for.
96. As an API client, I want DELETE to return 204 and keep the shared game, so that removing an entry behaves like the website.
97. As an API client, I want 503 with a {"detail", "code"} body when IGDB or Twitch prevents a save, and IGDB's Retry-After passed on for rate limits, so that I know to try again later.
98. As an API client, I want 400 with a {"detail", "code"} body for an unknown IGDB ID, an excluded release, or a duplicate entry, so that I know to change my request.
99. As an API client, I want field-level validation errors in DRF's standard format, so that I can see which field is wrong.
100. As a developer, I want documented example create and PATCH requests and responses, so that I can use the API without reading its code.

### Command-line client

101. As a developer, I want a client script that lists my entries with optional search, status and page options, showing each entry's ID, title and status, the total count, and whether another page exists, so that I can check the API from the terminal.
102. As a developer, I want the client to update an entry's status by fetching it first, changing only its status, and printing the previous and updated status, so that I can see exactly what changed.
103. As a developer, I want the client to read the API URL (with a local default) and my token from my ignored environment file, so that no secrets end up in code.
104. As a developer, I want the client never to print my token, so that it can't leak into screenshots or logs.
105. As a developer, I want clear client errors for an invalid token, a server that isn't running, validation errors, and a missing entry or invalid page, so that I know how to fix the problem.
106. As a developer, I want documented steps to create a token for my user and store it safely, so that I can set up the client.

### IGDB connection and configuration

107. As the app operator, I want the IGDB access token reused until shortly before it expires, so that the app doesn't request a new token for every search or exceed Twitch's active-token limit.
108. As the app operator, I want a rejected token discarded, replaced and the request retried once, so that an expired token recovers without the user noticing.
109. As the app operator, I want a second authentication failure to show a safe configuration message without further retries, so that misconfiguration doesn't cause a loop of requests.
110. As the app operator, I want timeouts and rate limits reported to the user without automatic retries, so that a bad moment doesn't multiply requests.
111. As the app operator, I want Django to start, and saved games to stay browsable, even when IGDB credentials are missing, so that a missing secret only affects IGDB features.
112. As the app operator, I want credentials and tokens kept out of logs, messages, cache keys, source code and the prompt log, so that secrets never leak.
113. As a user, I want specific, plain-language messages for timeouts, unreachable servers, rate limits, IGDB problems and server misconfiguration, so that I know whether to retry or wait.
114. As a user, I want outage and configuration messages to include a link to My Saved Games, so that I can keep using my list when IGDB isn't available.
115. As every visitor, I want "Game data and cover art from IGDB.com" linked in the footer of every page, so that the data source is credited.

### Demo data and verification

116. As a developer, I want a demo seeding command that creates two users with different saved entries and themes from stored data, without contacting IGDB, so that I can check privacy rules repeatably and offline.
117. As a developer, I want the seeding command to be safe to rerun, never duplicating entries or overwriting existing accounts or their data, so that I can run it whenever I need.
118. As a developer, I want demo passwords read from my ignored environment file, with the command stopping with a clear message if the password is missing, so that no real credentials are committed.
119. As a developer, I want a documented manual verification checklist, so that I can record evidence that each requirement works.

## Implementation Decisions

### Stack and structure

- Django with Django REST Framework, SQLite, uv for dependencies and running commands, and Ruff for linting and formatting (configured in the project's pyproject settings, run in a uv dev group).
- One Django project package and one app (`games`) containing the models, website views, API, IGDB client and save service. Templates and static files live in the app.
- Dependencies: Django, Django REST Framework, requests and python-dotenv. Ruff is a dev dependency.
- Settings read the Django secret key, debug flag and IGDB credentials from the ignored environment file. The example environment file gets placeholders for the Django secret key, debug flag, API token, API URL and demo password, alongside the existing IGDB placeholders.
- Tests use Django's built-in test runner. IGDB is mocked at the IGDB client module boundary, and no automated test calls the real API.

### Data model

- **Game**: one row per IGDB game, shared by all users. Fields: IGDB ID (unique), name, slug, summary, first release date (nullable date converted from IGDB's Unix timestamp), Game Category (IGDB's `game_type` ID), version parent (nullable IGDB game ID from `version_parent`), cover image ID, IGDB URL, and last-fetched timestamp. Read-only to users.
- **Platform**, **Genre**, **Theme**: each with a unique IGDB ID and a name, linked to Game by many-to-many relationships. Stored locally so search and filters work offline.
- **Entry**: the user's tracking data. Fields: owner (user), game, status, favorite, rating, notes, platform played, start date, finish date, hours played, and automatic created and updated timestamps.
  - Status uses text choices with five values: Want to Play (default), Playing, Completed, On Hold, Dropped.
  - Favorite defaults to false.
  - Rating is an optional integer from 1 to 10.
  - Notes, platform played, both dates and hours played are optional. Hours played can't be negative.
  - Platform played is a plain text value chosen from the game's stored platform names, not a foreign key.
  - A database unique constraint allows only one entry per user and game.
- Deleting an entry never deletes the Game, even if it was the last entry for that game.

### Shared validation

- One validation function used by both the website form and the API serializer (DRF serializers don't run model clean methods):
  - If both dates are set, the finish date must be on or after the start date. Either date may be blank for any status.
  - Platform played is valid if it is blank, one of the game's current platforms, or unchanged from the stored value. This lets an entry keep a platform a refresh has removed while other fields are edited, and lets a PUT resend the same stale value.
- For partial updates, submitted values are combined with the entry's stored values before validation.

### Ownership and permissions

- All website pages, IGDB search and game details require sign-in.
- Every entry list and lookup on the website and in the API starts from the signed-in user's own entries (one shared helper). Another user's entry ID returns 404 for view, edit, delete and refresh on the website, and for every API method.
- The owner is always set from the authenticated user on create, never from submitted data.
- Signed-out website visitors are redirected to login. Unauthenticated API requests return 401.

### Authentication

- Sign-up uses Django's user creation form and signs the new user in. Login uses Django's built-in view, and logout uses POST only. The default login redirect is My Saved Games, and safe `next` URLs are honored. No password reset.
- API authentication classes, in order: token authentication, then session authentication, so unauthenticated requests get 401 rather than 403. Authentication is required by default for every API endpoint.
- API tokens are generated with DRF's built-in token management command for an existing user. They are stored only in the ignored environment file and never in source code, logs or the prompt log.

### IGDB client

- A single IGDB client module used by search, import and refresh, built on the verified script's request, timeout and error-mapping approach. It raises a typed error carrying a safe message and an error code instead of exiting.
- The Twitch app access token is cached in Django's local-memory cache, with a timeout slightly shorter than the `expires_in` Twitch returns. Cache keys contain nothing secret.
- On an IGDB 401: discard the cached token, fetch a new one, and retry the original request once. A second failure, or Twitch rejecting the credentials, is a configuration error. No automatic retries for timeouts or rate limits.
- Missing credentials don't stop Django from starting. IGDB actions report the configuration error, and saved-game browsing is unaffected.
- IGDB is called only from the server. Requests use a timeout and respect IGDB's rate limits (one request per search page or import, no parallel fan-out).

### Game Category rules

- **Verified 2026-11-14** (see [docs/research/igdb-game-types.md](../docs/research/igdb-game-types.md)): the type field is `game_type`, a reference to the `/v4/game_types` endpoint. The older `category` field is deprecated and empty.
- **Eligibility rule (allowlist).** A game is eligible for search and new saves only if **both** are true:
  - `version_parent` is empty (records with a version parent are editions), and
  - `game_type` is one of the kept types below.

  Excluded: Bundle (3), Mod (5), Pack / Addon (13), Update (14), and any type IGDB adds in future until it's reviewed.

  | ID | IGDB label | Treatment | Badge |
  |---:|---|---|---|
  | 0 | Main Game | Keep | none |
  | 1 | DLC | Keep | DLC |
  | 2 | Expansion | Keep | Expansion |
  | 4 | Standalone Expansion | Keep | Standalone Expansion |
  | 6 | Episode | Keep | Episode |
  | 7 | Season | Keep | Season |
  | 8 | Remake | Keep | Remake |
  | 9 | Remaster | Keep | Remaster |
  | 10 | Expanded Game | Keep | Expanded Game |
  | 11 | Port | Keep | Port |
  | 12 | Fork | Keep | Fork |
  | 3 | Bundle | Exclude | |
  | 5 | Mod | Exclude | |
  | 13 | Pack / Addon | Exclude | |
  | 14 | Update | Exclude | |

- IGDB search and import both use `where version_parent = null & game_type = (0,1,2,4,6,7,8,9,10,11,12);`. The save service applies the same rule in Python to a fetched record and to a Game already stored locally.
- The UI calls this "Game Category" (and "Game Categories" for the group). Badges use IGDB's labels, and Main Game has no badge. Badges appear on the search and saved-games pages. There is no Game Category filter.

### IGDB search page

- Requests up to 11 results and shows up to 10. The offset is (page − 1) × 10. Next appears only if an 11th result came back, and Previous appears when page > 1. No page cap.
- Pager links keep the query, and a new search starts on page 1. Missing, non-numeric, zero or negative page values are treated as page 1.
- An empty page 1 shows "No matches.". An empty later page shows "No more results" with a link to page 1. Errors are shown separately from either empty message.
- Results the user has already saved show a "Saved" link to their entry, found with one local query per results page.

### Save service

- The website save form and API create both accept an IGDB ID and use the same save service.
- If the Game already exists locally, it is reused with no IGDB call, so saving works during an outage.
- **Stored-classification rule:** if the stored Game is ineligible (its stored version parent is set, or its stored Game Category isn't on the allowlist, for example after a refresh reclassified it), new saves are rejected using the stored values, without calling IGDB. Existing entries for that game are untouched.
- For a new game: fetch it from IGDB by ID, apply the eligibility rule (both the version parent and the Game Category checks), then save the Game with its platform, genre and theme links and the Entry in one database transaction. The fetch happens first, so an IGDB failure leaves nothing saved.
- Duplicates: on the website, link or redirect to the existing entry with "Already in your games". In the API, return 400.
- Simultaneous saves: if creating the Entry raises a database integrity error, the service re-checks for an existing entry belonging to **the same user for the same game**. Only when that entry is confirmed is the request treated as a duplicate (with the duplicate responses above). Any other database error, including an integrity error with no such entry, is not reported as a duplicate. It is handled as an unexpected server error and shown to the user only as a generic safe message.
- After a successful new save on the website, redirect to the entry's edit page.
- On a website save failure, return to the same search query and page with the error message. The error is still shown if reloading the results also fails.

### Refresh

- A POST-only action on the entry detail page, requiring sign-in and an owner-scoped entry lookup.
- Fetches by IGDB ID. On success, updates the Game's metadata, platform, genre and theme links, and last-fetched time in one transaction. On failure, keeps the existing data and shows the agreed error message.
- A successful refresh updates both the Game Category and the version parent. If the game becomes ineligible, the new values are stored and existing entries and their tracking data are kept. New saves of that game are then rejected under the stored-classification rule.
- If a user's platform played is no longer listed, it is kept and a warning is shown on the entry.
- Throttled to one refresh attempt per game per 10 minutes across all users, tracked in the cache by attempt (not success), so failing refreshes are throttled too.
- The detail page shows "Data from IGDB" with a link to the game's IGDB page and the last successful refresh time.

### Errors and messages

| Code | Message | API status |
|---|---|---|
| `igdb_timeout` | IGDB took too long to respond. Try again in a moment. | 503 |
| `igdb_unreachable` | Couldn't reach IGDB. Try again in a moment. | 503 |
| `igdb_rate_limited` | IGDB is receiving too many requests. Wait a few seconds and try again. | 503 (passes on a valid Retry-After) |
| `igdb_unavailable` | IGDB is having problems right now. Try again later. | 503 |
| `igdb_misconfigured` | Game search and imports aren't set up on this server. Your saved games are still available. | 503 |
| `igdb_game_not_found` | IGDB has no game with that ID. | 400 |
| `game_category_excluded` | This release can't be saved. Search for the base game or a supported release. | 400 |
| duplicate entry | (existing-entry message) | 400 |

- Import and duplicate API errors use a `{"detail": "...", "code": "..."}` body. Tracking-field validation uses DRF's standard field-error format.
- On the website, upstream and configuration messages include a link to My Saved Games. Only these fixed, safe messages reach users. Exception details, credentials and tokens never appear.

### My Saved Games (website)

- Search: a case-insensitive match combined with Q objects across game title, summary, platform names, genre names, theme names and the user's notes. Distinct results are applied wherever joins can return the same entry more than once (search and Theme filter), before sorting and pagination.
- Filters:
  - **Status**.
  - **Platform Played** (the user's chosen platform; a platform search term still matches every platform the game is available on).
  - **Favorite**.
  - **Theme**: single-select by IGDB theme ID, default All Themes. Lists only themes on the current user's saved games, alphabetically, regardless of other active filters.
- Sorts are whitelisted: Title A to Z, Title Z to A, Date Added (Newest First, default), Rating (Highest First), Release Date (Newest First), Hours Played (Most First), Last Updated (Newest First). Missing values sort last. Non-title sorts break ties by title A to Z, then entry ID. Title sorts break ties by entry ID. Title sorting is case-insensitive.
- 10 entries per page, using a `page` parameter.
- Website (forgiving) behavior:
  - Clear filters clears Status, Platform Played, Favorite and Theme, keeps search and sort, and returns to page 1.
  - Changing the search, any filter or the sort returns to page 1.
  - Pagination links preserve search, filters and sort.
  - A missing, non-numeric, zero or negative page shows page 1. A positive page past the end shows the last page. A small page-parsing helper turns anything that isn't a positive integer into 1 before Django's `get_page()` is called, because `get_page()` alone sends 0 and negative values to the last page (verified on Django 6.1.3).
  - An unknown sort silently uses Date Added (Newest First). A malformed theme, or one not on the user's saved games, is ignored.
  - A valid combination that matches nothing shows the normal empty state.
- Game Category badges are shown on non-main games.

### Website pages

| Page | Behavior |
|---|---|
| Home | Redirects to My Saved Games when signed in, otherwise to login |
| Sign up, login, logout | As described under Authentication; logout is POST only |
| My Saved Games | Search, filters, sorts, pagination as above |
| Entry detail (by entry ID) | Large cover, game details, tracking data, "Data from IGDB" with the last refresh time, Refresh button, stale-platform warning |
| Entry edit (by entry ID) | Tracking-field form with the shared validation; the landing page after a new save |
| Entry delete (by entry ID) | GET shows a confirmation page with the game title, explaining that status, rating, notes and hours played will be deleted, with a Cancel link to detail and a "Remove from My Games" button. Only a CSRF-protected POST removes the entry, then redirects to My Saved Games with a confirmation message. Both GET and POST are owner-scoped. |
| Entry refresh (by entry ID) | POST only; redirects back to detail with a message |
| IGDB search | Query and page parameters, Previous/Next, Saved links, Game Category badges |
| Save from search | POST only; carries the IGDB ID plus the current query and page so errors return to the same results |

- The base template has navigation (My Saved Games, Search IGDB, the signed-in username, a Logout button), a messages area, and a footer reading "Game data and cover art from IGDB.com", linked to IGDB, on every page.

### Covers

- Built from the stored cover image ID on IGDB's image server by one shared URL builder, used by templates and by the API's cover URL field.
- Search results and My Saved Games use the small cover size with a high-DPI variant. The detail page uses the large cover size.
- Every cover has fixed dimensions (to reserve space), lazy loading and the game name as alt text.
- One local placeholder image is used when there's no cover ID or when a load fails. Failures are handled by a static JavaScript file that switches to the placeholder, clears the high-DPI source set, and doesn't retry if the placeholder itself fails.
- Cover files are not downloaded or re-hosted.

### Saved-entry API

| Method | Resource | Behavior |
|---|---|---|
| GET | Entry collection | List the user's entries, 10 per page, returned as count, next, previous, results |
| POST | Entry collection | Create from an IGDB ID through the save service |
| GET | Single entry | Retrieve one of the user's entries |
| PUT | Single entry | Replace the tracking fields; omitted optional fields reset to blank or defaults |
| PATCH | Single entry | Change only the submitted fields, validated together with stored values |
| DELETE | Single entry | Remove the entry, return 204, keep the Game |

- A DRF model viewset on a router, with the queryset scoped to the authenticated user.
- Response fields:
  - Entry: ID, status, rating, notes, platform played, start date, finish date, hours played, favorite, created and updated timestamps.
  - Nested read-only game: IGDB ID, name, first release date, Game Category, platforms, genres, themes, cover URL, IGDB URL. Served from SQLite.
- The IGDB ID is required on create and rejected on update. Anything submitted inside the nested game object is ignored.
- List parameters: `q`, `status`, `platform` (Platform Played), `favorite`, `theme`, `sort`, `page`, with the same meanings, sort options, tie-breakers and search fields as the website.
- API (strict) behavior: an invalid status, theme (malformed or not on the user's saved games) or sort value returns 400. An invalid or out-of-range page returns 404 (DRF's standard page-number pagination).
- Example create and PATCH requests and responses are documented.

### Command-line client

- A second script, separate from the IGDB verification script, using requests and python-dotenv only. It doesn't import any Django code, so it tests the API from outside.
- Reads the API base URL from the environment (default: the local development server's API root) and the token from the ignored environment file. Sends the token in the Authorization header with a request timeout. The token never appears in output or logs.
- **list** accepts optional search, status and page options, sends them as query parameters, and prints each entry's ID, game title and status, the total match count, and whether another page exists.
- **update** accepts an entry ID and a new status. It GETs the entry, PATCHes only the status field, then prints the previous status and the updated status from the PATCH response.
- Clear error messages for an invalid or missing token (401), a server that can't be reached, validation errors (400), and a missing entry (404 on update) or invalid page (404 on list). Exit codes follow the verification script's convention (0 success, 1 request or API error, 2 usage error).

### Demo seeding command

- A management command that creates two demo users with distinct saved entries and distinct themes from stored fixture data, without contacting IGDB.
- Safe to rerun: it never duplicates entries and never overwrites existing accounts, passwords or their data.
- Demo passwords come from the ignored environment file. If the variable is missing, the command stops with a clear message instead of using a built-in password.
- Its documentation covers running it and signing in, with no real credentials committed.

### Documentation

- The README covers setup, environment variables, token generation and storage, the seeding command, the client's two commands, and example API requests and responses.
- Manual verification results go in a verification checklist document, never including tokens or passwords.

## Out of Scope

- Public, shared or per-entry visibility of saved lists. Entries are private only.
- Password reset, email, and account management beyond sign-up, login and logout.
- JWT or other API authentication schemes.
- Editing shared IGDB metadata (titles, summaries, platforms, genres, themes, covers) by users, through the website or API.
- A Game Category filter on My Saved Games, and a Game Category filter or toggle on IGDB search (excluded releases are always left out).
- Multi-select theme filtering, tags, and a separate games API endpoint.
- A user-selectable page size, and a page cap or numbered pages (with totals) for IGDB search.
- Downloading or re-hosting cover images, and offline cover display.
- Automatic metadata refresh and a refresh management command.
- Changing which game an entry tracks after creation.
- Full CRUD in the command-line client (the client covers list and status update; the API itself supports full CRUD).
- Other game data providers (RAWG was the considered alternative).
- Deployment to a public server.

## Acceptance Criteria

### Owner isolation

- With two seeded demo users, signed in as user B:
  - **GET** user A's entry detail, edit and delete confirmation pages by entry ID each return 404.
  - **POST** to user A's delete and refresh URLs each return 404, and A's entry, tracking data and shared Game are unchanged (no deletion, no IGDB call, no refresh attempt recorded).
  - Refresh stays POST-only: signed in as the owner, a GET to **their own** entry's refresh URL is rejected with 405 and changes nothing (no IGDB call, no refresh attempt recorded).
- With user B's token or session, GET, PUT, PATCH and DELETE on user A's entry through the API return 404, and A's entry is unchanged.
- User B's saved-games list and API list never include A's entries, including when searching for terms that appear only in A's notes.
- User B's Theme dropdown never lists a theme that appears only on A's saved games. A theme ID taken from A's games is ignored on B's website list and returns 400 from B's API list.
- Creating an entry through either interface sets the owner to the authenticated user even if another owner is submitted.
- An unauthenticated API request returns 401. A signed-out website visitor opening a protected page is redirected to login and returned to that page after signing in.

### Browsing saved games during an IGDB outage

- With IGDB unreachable, or credentials missing, My Saved Games loads and shows titles, platforms, Game Category badges and tracking data. Search across all agreed fields, all four filters, all seven sorts and pagination work.
- Entry detail and edit pages load and save tracking changes during the outage. Covers that fail to load show the placeholder without hiding any text.
- The API list and retrieve endpoints return saved entries during the outage.
- IGDB search and refresh show the agreed message with a link to My Saved Games. Saving a game that already exists locally still succeeds. Saving a new game fails with the agreed message (503 in the API) and leaves nothing partially saved.
- Django starts without IGDB credentials.

### Command-line client before-and-after status update

- Given an entry whose status is, for example, Want to Play, running the client's update command with that entry's ID and Playing prints the previous status (Want to Play) and the updated status (Playing) taken from the PATCH response.
- Afterwards, the entry's detail page and My Saved Games on the website show Playing, and no other tracking field has changed.
- Running update with another user's entry ID, or an ID that doesn't exist, prints a clear "not found" error and changes nothing. An invalid status prints the validation error. A bad token prints a token error. A stopped server prints a "server unavailable" error. None of these print the token.
- The client's list command shows the same total count and first-page entries as the API list for the same search and status.

### Other verification carried from the design

- Before implementation: verify the IGDB Game Category field and values against the official docs and a live request, using the existing script's plain search as the baseline. A "The Witcher 3" search keeps the base game and Blood and Wine and excludes the Game of the Year Edition. A separate "Dark Souls III" search excludes the bundle. Then settle the remaining types. **Done 2026-11-14:** all three outcomes matched, and the types were settled (see Game Category rules).
- Repeating the exact same IGDB search returns consistent IDs across pages 1 and 2 (no repeats or gaps), or the difference is recorded. **Checked in Phase 7 (2026-11-15):** three repeated `star` runs returned identical ordered IDs on pages 1 and 2 with no overlap. Separately, changing the `limit` or `offset` changed the order of some results, so a duplicate or skipped result at a page boundary is possible; neither was observed in this check. The query and order were kept (see Further Notes).
- The browsable API works with a signed-in browser session, and the client works with a token.
- A search where several related values (for example, a platform and a genre) match one entry shows that entry once.
- Reversing the title sort with the same search and filters changes the order but not the total count. Ties across a page boundary repeat or skip no entries.
- The page-parsing helper returns page 1 for missing, empty, non-numeric, decimal, zero and negative values, the requested page for valid values, and the last page (via `get_page()`) for values past the end.
- Token handling: a cached token is reused, a new one is fetched after cache expiry, a 401 triggers one refresh and retry, a second 401 isn't retried, and saved games work without credentials.
- Covers: a working cover, a missing cover and a blocked image request each display correctly.
- PATCH validation checks a new finish date against the stored start date. Stale-platform rules hold on both the website and API.
- A refresh that makes a game ineligible (a version parent appears, or its Game Category leaves the allowlist) stores both new values, keeps existing entries and their tracking data, and a later save attempt for that game is rejected using the stored values without calling IGDB.

## Further Notes

- **Source of record for prototype changes:** the saved-games query-state prototype notes record what changed after the prototype was tried. They supersede the prototype HTML (which still shows 12 per page and a Game Category filter switch). That covers 10 entries per page on both the website and API, a Theme filter (for values like Horror and Survival) instead of a release-type filter, and Game Category badges (Expansion, Remake, Remaster and so on) kept as labels only.
- **Verified 2026-11-14:** Horror (IGDB theme 19) and Survival (theme 21) are IGDB themes, not genres. The genre list contains neither. A live "Resident Evil 2" search returned both as themes and also returned a bundle, another real case for the bundle exclusion.
- **Verified 2026-11-14:** Django 6.1.3's `Paginator.get_page()` sends 0 and −1 to the last page, which is why the website needs its own page-parsing step.
- **Unresolved: Twitch storage terms.** The IGDB FAQ says local storage is allowed and preferred, but the Twitch Developer Services Agreement it points to has a 24-hour caching clause. It isn't clear whether the FAQ counts as the written authorization that clause allows, or whether the clause covers IGDB at all. The design stores saved metadata, keeps a last-fetched time, and offers manual refresh. The question stays documented as open (see the API comparison research).
- **Verified and decided 2026-11-14:** the Game Category field is `game_type` (15 values, IDs 0–14), and editions are identified by `version_parent`, because some editions are typed Main Game (for example *Dark Souls III: Day One Edition*). The keep/exclude allowlist is in the Game Category rules. Evidence: [docs/research/igdb-game-types.md](../docs/research/igdb-game-types.md).
- **Checked 2026-11-15 (Phase 7): IGDB search ordering.** Two logically equivalent "Resident Evil 2" queries had returned the same records in a different order in Phase 1. In Phase 7, three repeated runs of the same `star` search through the app's IGDB client returned identical ordered IDs on pages 1 and 2, with no overlap between the pages. Separately, changing the `limit` or `offset` changed the order of some results (IGDB appears to order equally ranked results by request window). A duplicate or skipped result at a page boundary is therefore possible, though neither was observed in this check. **Decision:** keep the query and IGDB's relevance order (no `sort`), and treat this as a known limitation. Evidence: [docs/research/igdb-game-types.md](../docs/research/igdb-game-types.md) section 5 and `docs/verification.md`.
- **To confirm during planning:** the styling and interactivity choices from the lesson (for example, the CSS approach and any front-end interactivity beyond the cover-fallback script) aren't decided in this PRD and must be confirmed before implementation.
- Covers are hotlinked rather than downloaded because none of the providers clearly allows re-hosting images.
- IGDB's limits (4 requests per second, 8 open requests, 25 active tokens, about 60-day token life) shaped the one-request-per-page search, token caching, the single 401 retry and the refresh throttle.
