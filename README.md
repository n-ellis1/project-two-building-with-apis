# project-two-building-with-apis

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
