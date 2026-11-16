# project-two-building-with-apis

## Django game tracker (in progress)

From the repo root in PowerShell, after `uv sync` and creating `.env` from `.env.example` (see step 2 below):

1. Set `DJANGO_SECRET_KEY` in `.env` to a long random string (`.env.example` shows a command that generates one) and `DJANGO_DEBUG=True` for local development. The IGDB variables are optional for the site.
2. Create the database and start the server:

   ```powershell
   uv run python manage.py migrate
   uv run python manage.py runserver   # http://127.0.0.1:8000/
   ```

Optional: `uv run python manage.py createsuperuser` for `/admin/`. Full setup docs are completed in Phase 12.

### Demo data

`seed_demo` creates two demo accounts, `demo_a` and `demo_b`, with different saved games, from data stored in `games/demo_data/seed.json` (real IGDB records, so it works offline and never contacts IGDB). `demo_a` has Horror and Survival games and more than one page of entries. `demo_b` has neither theme.

1. Add a password for the demo accounts to `.env`: `DEMO_PASSWORD=<a password of your choice>`. If it's missing, the command stops with a message and creates nothing.
2. Run the command, then sign in as `demo_a` or `demo_b` with that password:

   ```powershell
   uv run python manage.py seed_demo
   ```

It's safe to rerun. It only adds what's missing. Existing demo accounts keep their passwords (even if `DEMO_PASSWORD` changes), and existing games and entries are never changed. If `demo_a` or `demo_b` already belongs to an account the command didn't create, it stops without changing anything.

### Saved-entry REST API

The same private saved entries are available at `/api/entries/` (Django REST Framework). Every request needs authentication: a token in the `Authorization` header, or your website session (signed in, open <http://127.0.0.1:8000/api/entries/> for the browsable API). Without either, the API returns `401`. Another user's entry ID always returns `404`.

| Method | URL | Does |
|---|---|---|
| `GET` | `/api/entries/` | List your entries, 10 per page: `count`, `next`, `previous`, `results` |
| `POST` | `/api/entries/` | Save a game by `igdb_id`, with optional tracking fields (through the same save service as the website) |
| `GET` | `/api/entries/<id>/` | One of your entries |
| `PATCH` | `/api/entries/<id>/` | Change only the fields you send, checked together with the stored values |
| `PUT` | `/api/entries/<id>/` | Replace all tracking fields; omitted ones reset to blank or their default |
| `DELETE` | `/api/entries/<id>/` | Remove the entry (`204`); the shared game stays |

`<id>` is the entry ID (the same as in `/games/<id>/`), not the IGDB ID.

**Tracking fields:** `status` (`want_to_play`, `playing`, `completed`, `on_hold`, `dropped`), `favorite` (true/false), `rating` (1–10 or null), `notes`, `platform_played` (blank or one of the game's platforms; a value a refresh removed may stay unchanged), `start_date` and `finish_date` (`YYYY-MM-DD`, finish not before start), `hours_played` (not negative). Each entry also has a read-only nested `game`. `igdb_id` is required on create and rejected on update, and anything sent inside `game` is ignored.

**List parameters** (same meaning as on My Saved Games): `q` (title, summary, platform, genre, theme or your notes, with the same "Dark Souls 3" → "Dark Souls III" fallback), `status`, `platform` (a Platform Played on your entries), `favorite` (`true`, `false`, `1`, `0`), `theme` (an IGDB theme ID on your saved games, for example `19` for Horror), `sort` (`added` (default), `title`, `title_desc`, `rating`, `release`, `hours`, `updated`) and `page`. Unlike the website, an invalid value returns `400` keyed by the parameter, and a bad or out-of-range page returns `404`.

**Errors when saving** use a `{"detail", "code"}` body:

| Status | `code` |
|---|---|
| `503` | `igdb_timeout`, `igdb_unreachable`, `igdb_rate_limited` (with `Retry-After` when IGDB sent a valid one), `igdb_unavailable`, `igdb_misconfigured` |
| `400` | `igdb_game_not_found`, `game_category_excluded`, `duplicate_entry` |
| `500` | `save_failed` (an unexpected error; nothing was saved) |

Tracking-field problems use DRF's standard field-error format, for example `{"finish_date": ["Finish date can't be before the start date."]}`.

#### Create a token

```powershell
uv run python manage.py drf_create_token <username>
```

The command prints the new token once. Copy it straight into `.env` as `GAME_TRACKER_TOKEN=<token>`, then clear the terminal (`Clear-Host`). Never commit it, paste it into docs or show it in screenshots. To replace a token, run the command again with `-r`.

#### Call it from PowerShell without echoing the token

```powershell
$token = (Select-String -Path .env -Pattern '^GAME_TRACKER_TOKEN=(.+)$').Matches[0].Groups[1].Value
$headers = @{ Authorization = "Token $token" }
$api = "http://127.0.0.1:8000/api/entries/"

# No token: 401
try { Invoke-RestMethod $api } catch { $_.Exception.Response.StatusCode.value__ }

# With the token: 200
Invoke-RestMethod $api -Headers $headers | Select-Object count, next
Invoke-RestMethod "${api}?status=playing&sort=title" -Headers $headers |
    ForEach-Object { $_.results } | Select-Object id, status, @{ n = "title"; e = { $_.game.name } }

Remove-Variable token, headers
```

#### Example: create

```http
POST /api/entries/
Authorization: Token <your token>
Content-Type: application/json

{"igdb_id": 1942, "status": "playing", "platform_played": "PC (Microsoft Windows)", "start_date": "2026-11-01"}
```

`201 Created`:

```json
{
  "id": 42,
  "game": {
    "igdb_id": 1942,
    "name": "The Witcher 3: Wild Hunt",
    "first_release_date": "2015-05-19",
    "game_category": 0,
    "game_category_label": "Main Game",
    "platforms": ["PC (Microsoft Windows)", "PlayStation 4", "Xbox One"],
    "genres": ["Role-playing (RPG)", "Adventure"],
    "themes": ["Action", "Fantasy", "Open world"],
    "cover_url": "https://images.igdb.com/igdb/image/upload/t_cover_big/<cover id>.jpg",
    "igdb_url": "https://www.igdb.com/games/the-witcher-3-wild-hunt"
  },
  "status": "playing",
  "favorite": false,
  "rating": null,
  "notes": "",
  "platform_played": "PC (Microsoft Windows)",
  "start_date": "2026-11-01",
  "finish_date": null,
  "hours_played": null,
  "created_at": "2026-11-15T18:04:12.345678Z",
  "updated_at": "2026-11-15T18:04:12.345678Z"
}
```

Saving the same game again returns `400` with `{"detail": "Already in your games", "code": "duplicate_entry"}`. With IGDB unreachable, saving a game nobody has saved before returns `503` with `{"detail": "Couldn't reach IGDB. Try again in a moment.", "code": "igdb_unreachable"}`. A game already stored in the app still saves.

#### Example: PATCH

```http
PATCH /api/entries/42/
Authorization: Token <your token>
Content-Type: application/json

{"status": "completed", "finish_date": "2026-11-14", "hours_played": 96.5}
```

`200 OK` returns the whole entry with those three fields changed and everything else as it was (`"status": "completed"`, `"finish_date": "2026-11-14"`, `"hours_played": 96.5`, `"start_date": "2026-11-01"`, …).

A finish date before the stored start date is refused, even though `start_date` wasn't sent:

```http
PATCH /api/entries/42/
Content-Type: application/json

{"finish_date": "2026-10-01"}
```

`400 Bad Request`, and nothing changes:

```json
{"finish_date": ["Finish date can't be before the start date."]}
```

In PowerShell: `Invoke-RestMethod "${api}42/" -Method Patch -Headers $headers -ContentType "application/json" -Body '{"status": "completed"}'`.

## IGDB verification script

`scripts/igdb_search.py` searches [IGDB](https://www.igdb.com) for games by title and prints each match's title, IGDB ID, release date (UTC) and platforms, up to 10 results per page. It confirms that real API requests work before the Django game tracker is designed. Background research is in [docs/research/game-api-comparison.md](docs/research/game-api-comparison.md).

### Requirements

- [uv](https://docs.astral.sh/uv/). The project requires Python 3.14 (`.python-version`), and uv uses an installed 3.14 or downloads one.
- A Twitch account with a registered application (IGDB uses Twitch for authentication).

### 1. Register a Twitch application

These steps follow IGDB's [Account Creation](https://api-docs.igdb.com/#account-creation) guide:

1. Sign up for a Twitch account at <https://www.twitch.tv> if you don't have one.
2. Turn on **Two-Factor Authentication** for the account. Twitch requires it before you can register applications.
3. Open the Twitch Developer Console at <https://dev.twitch.tv/console/apps> and click **Register Your Application**.
4. Fill in the form:
   - **Name:** any unique name, for example `yourname-game-tracker-dev`.
   - **OAuth Redirect URLs:** `http://localhost`. IGDB doesn't use it, but the form requires one.
   - **Category:** pick the closest match.
   - **Client Type:** **Confidential**. This type gives you a Client Secret.
5. Click **Create**, then **Manage** on the new application.
6. Copy the **Client ID**, then click **New Secret** and copy the **Client Secret**. Keep the secret private. Twitch shows it only once, and generating a new one invalidates the old one.

### 2. Set the environment variables

The script reads two variables:

| Variable | Value |
|---|---|
| `IGDB_CLIENT_ID` | Your Twitch application's Client ID |
| `IGDB_CLIENT_SECRET` | Your Twitch application's Client Secret |

From the repo root in PowerShell:

```powershell
uv sync                          # create .venv and install dependencies from uv.lock
Copy-Item .env.example .env      # create your local, git-ignored .env
notepad .env                     # replace both placeholders with your real values, then save
git check-ignore -v -- .env      # confirm .env is ignored (prints the matching .gitignore rule)
```

Never commit `.env` or paste its contents anywhere. The script gets a new access token on every run and keeps it in memory only. It never prints the token or the client secret.

### 3. Run the script

From the repo root in PowerShell:

```powershell
uv run scripts/igdb_search.py "The Witcher 3"
uv run scripts/igdb_search.py "The Witcher 3" --page 2
uv run scripts/igdb_search.py --help
```

Exit codes: `0` means the search completed (including searches with no matches), `1` means a credential, network or API error, and `2` means a usage error, such as a blank title or `--page 0`. Run `$LASTEXITCODE` right after a command to see its exit code.

### 4. Verify the three outcomes

**Successful search** (uses your real `.env`):

```powershell
uv run scripts/igdb_search.py "The Witcher 3"
$LASTEXITCODE   # expect 0
```

You should see a header like `Results 1-N for "The Witcher 3" (page 1):`, where N is the number of matches on the page (up to 10), followed by numbered blocks with `IGDB ID:`, `Released:` and `Platforms:` lines. Missing dates or platforms show `Unknown`. If there are more results, `--page 2` shows them numbered from 11. If page 2 has no results, it prints `No results on page 2 for "The Witcher 3".` instead.

**Search with no matches** (uses your real `.env`):

```powershell
uv run scripts/igdb_search.py "qzxjvkqzxjvk"
$LASTEXITCODE   # expect 0
```

Expect `No matches for "qzxjvkqzxjvk".` IGDB's search is fuzzy, so if a nonsense title happens to match something, try a different string. To see the empty-page message instead, ask for a page past the end of the results, for example `uv run scripts/igdb_search.py "The Witcher 3" --page 50`, which should print `No results on page 50 for "The Witcher 3".`

**Failed request** (temporary dummy credentials, leaves `.env` alone):

Variables set in your PowerShell session take precedence over `.env`, so you can override the real values for this session only:

```powershell
$env:IGDB_CLIENT_ID = "dummy-client-id"
$env:IGDB_CLIENT_SECRET = "dummy-client-secret"
uv run scripts/igdb_search.py "The Witcher 3"
$LASTEXITCODE   # expect 1
```

Expect `Error: Twitch rejected the credentials (HTTP 400). Check IGDB_CLIENT_ID and IGDB_CLIENT_SECRET in your .env file.` The status code may be 400 or 403, depending on which value Twitch rejects first.

**Remove the temporary overrides** so the script goes back to using `.env`:

```powershell
Remove-Item Env:IGDB_CLIENT_ID, Env:IGDB_CLIENT_SECRET
Test-Path Env:IGDB_CLIENT_ID       # expect False
Test-Path Env:IGDB_CLIENT_SECRET   # expect False
```

Closing the PowerShell window also clears them, because `$env:` changes only last for the current session.
