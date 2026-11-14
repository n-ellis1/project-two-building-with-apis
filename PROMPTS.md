# PROMPTS.md — AI Usage Log

This file is the record of AI use on this codebase. At the end of every
agent session, direct the agent to write the session log with this prompt:

> Append a session log to PROMPTS.md at the repo root, under today's date,
> newest entry at the top. Record every prompt I gave you this session, in
> order, including any corrections. End the entry with a short summary:
> the outcome, any places where I deviated from a recommended answer or
> asked follow-up questions, and anything that went sideways.

Two rules:

- Entries are added only by that prompt, never unprompted.
- New entries go at the top. Never rewrite or delete an old entry — the
  log is part of your work, and an honest log of a session that went
  sideways is worth more than a tidy one.

Each entry has this shape:

    ## YYYY-MM-DD — <one-line summary>

    ### Prompts
    1. ...

    ### Summary
    - **Outcome:** what was built and what was kept
    - **Deviations:** recommendations overridden, follow-up questions asked
    - **Sideways:** failures, wrong turns, and how they were caught

## 2026-11-14 — Follow-up: align script --help wording with README

### Prompts
1. Change the script's --help text from "10 results per page" to "up to 10 results per page" so it matches the README. Run uv run scripts/igdb_search.py --help to confirm the wording, then restage the script. Show me git diff --cached --name-only again. Hold off on committing and pushing.
2. Append a short follow-up entry to PROMPTS.md under today's date, newest entry at the top. Record my prompt asking you to update the --help wording and verify it. Note that you changed it to "up to 10 results per page" and confirmed the output. Preserve the existing entry. Restage PROMPTS.md and show me git status --short. Leave the commit and push to me.

### Summary
- **Outcome:**
  - The `argparse` description in `scripts/igdb_search.py` now reads "Search IGDB for games by title (up to 10 results per page)."
  - `uv run scripts/igdb_search.py --help` printed the new wording.
  - The script and this log were restaged. Nothing was committed or pushed.
- **Deviations:** none. I had pointed out the mismatch as a leftover in the previous entry's session, and the user asked for it to be fixed.
- **Sideways:** none.

## 2026-11-14 — Game API research, IGDB decision, and IGDB verification script

### Prompts
1. `/research` Compare external video game APIs for a Django app that would let users search for games, save selected games to a local SQLite database, and track their own play status, ratings, and notes. Start with IGDB, RAWG, and CheapShark, and include another provider if it looks like a better fit. Use official documentation and terms to compare: how users can search by game title and which fields the API returns, such as title, stable ID, platforms, release date, cover art, and description; signup, authentication, and free-tier limits for building and demonstrating a small app; rules for storing game information locally so saved entries stay available during an API outage; attribution requirements and any separate rules for displaying or storing cover art. The code will be published in a public GitHub repository, with credentials kept in environment variables. Flag anything the official sources leave unclear. Save the cited findings in a Markdown file in the repo. Recommend a first choice and a backup, and explain the tradeoffs so I can decide.
2. (Ran `/context`.) Hold off on committing and pushing. Update docs/research/game-api-comparison.md with IGDB's documented limits of 4 requests per second and up to 8 open requests at a time. Cite the official IGDB docs. Record that I chose IGDB for a personal video game tracker because it provides the game metadata I need and its official FAQ explicitly allows local storage. Keep RAWG as the alternative I considered and keep the unresolved Twitch agreement question documented. Tell me what you changed, then stop so I can start /grill-me.
3. `/grill-me` Help me plan a small standalone Python script for a future Django video game tracker. I chose IGDB, and I want to verify that I can make a real request before designing the app. Ask me one question at a time and wait for my approval before writing code. The script should live in scripts/ and use uv for its Python environment and dependencies. It should accept a game title from me, search IGDB, and print matching games with their title, IGDB ID, release date, and platforms when available. It should give useful messages for no matches and failed requests. Use Twitch application credentials from an ignored local .env file. Track a .env.example with placeholders only. Keep real credentials and access tokens out of source code, terminal output, and PROMPTS.md. I will enter the real values locally. Wait to commit or push until I have run the script and reviewed the staged files.
4. I choose Option B. Use a minimal uv project at the repo root so the verification script and the future Django app can share one environment. For now, only plan the dependencies needed to run the IGDB script. Leave Django setup and app layout for later. Check which Python version uv already sees on my machine before proposing a version or assuming Python needs to be installed. Continue the interview with the next question before writing code.
5. I choose Option A. Set requires-python to ">=3.14" in pyproject.toml and use 3.14 in .python-version so uv selects Python 3.14 locally. Use the Python 3.14 installation uv already found. We'll verify Django and DRF compatibility when we add those dependencies. Continue the interview with the next question before writing code.
6. I choose Option A. Use requests for the Twitch token and IGDB search requests, and python-dotenv to load the local .env file. Add both dependencies to the root uv project when we implement the script. Use explicit request timeouts and give clear error messages without printing credentials or access tokens. Continue the interview with the next question before writing code.
7. I choose Option A. Use argparse with nargs="+" for the game title. Join the words, trim surrounding whitespace, and reject a blank title with a clear usage message before making any API requests. Use a quoted title like "The Witcher 3" in the README example. Continue the interview with the next question before writing code.
8. I choose Option A. Request a fresh Twitch app access token each time the script runs, keep it in memory, and use it for the IGDB search. Keep both the token and client secret out of terminal output, error messages, and logs. Give me a clear message if the token request fails. We'll decide how to reuse tokens when we design the Django app. Continue the interview with the next question before writing code.
9. Use a plain IGDB title search and keep editions in the results. Keep the limit at 10 results per request, but add an optional --page argument that defaults to 1. Use offset = (page - 1) * 10 so I can run the same search with --page 2 to see results 11–20. Reject page numbers below 1. Keep the agreed fields and query escaping. Continue the interview or recap our decisions before writing code.
10. I choose Option B. Show each game as a numbered block with its title, IGDB ID, release date, and platforms. Convert release timestamps to UTC dates in YYYY-MM-DD format. Show "Unknown" when the release date or platform list is missing. Continue numbering across pages so page 2 starts at 11. If there are no results on a later page, say there are no results on that page. Continue with the next question if there is one. Otherwise, recap our decisions and wait for my approval before writing code.
11. I approve the plan, including the proposed details. Build the IGDB verification script and keep this phase scoped to the script and its setup. Verify that .env is ignored with git check-ignore -v -- .env. I'll create and fill in my real .env locally. In the README, include the official Twitch app registration steps, the environment variable names, and the exact PowerShell commands to run the script from the repo root. Show me how to verify a successful search, a search with no matches, and an actual failed request using temporary dummy credentials without editing my real .env or exposing any secrets. Include how to remove the temporary overrides afterward. Run the checks you outlined and tell me what passed. Then walk me through how the script gets the token, sends the IGDB search, and prints the results. Hold off on committing and pushing.
12. I ran all three live checks from the repo root. The Witcher 3 search returned eight IGDB results with IDs, release dates, and platforms. The search for "zzzxqv-no-such-game-984726" printed "No matches". The dummy-credential test returned HTTP 400 and exit code 1. After cleanup, both Test-Path checks returned False. I also confirmed that git check-ignore -v -- .env showed the .gitignore rule. Update the README to say "up to 10 results per page." The successful-search example should allow fewer than 10 matches, and page 2 starts at 11 only when it contains results. Append a session log to PROMPTS.md under today's date, newest entry at the top. Record every prompt I gave you this session in order, including corrections, and summarize the outcome, deviations, and anything that went sideways. Include the live verification results above and keep credentials out of the log. Stage the intended research notes, IGDB script, uv project files, .env.example, README.md, and PROMPTS.md. Verify that .env is ignored and absent from the staged list. Show me git status --short and git diff --cached --name-only. Wait for my review before committing or pushing.

### Summary
- **Outcome:**
  - **Research:** a background agent wrote `docs/research/game-api-comparison.md`, comparing IGDB, RAWG, CheapShark and TheGamesDB from official sources with citations. Giant Bomb, MobyGames and Steam were excluded, with reasons given.
  - **Decision:** IGDB was chosen for a personal video game tracker (metadata coverage, plus the official FAQ allowing local storage). RAWG was recorded as the alternative considered. The IGDB rate limits (4 requests/sec, 8 open requests) were added with citations, and the Twitch agreement storage question was kept as unresolved.
  - **Planning:** a `/grill-me` interview settled the plan for the verification script.
  - **Build:** created a bare uv project at the repo root (`pyproject.toml`, `.python-version` 3.14, `uv.lock`, with `requests` and `python-dotenv`), `scripts/igdb_search.py`, a placeholder-only `.env.example`, and a README section covering Twitch app registration, environment variables, PowerShell run commands, the three test outcomes and removing the overrides.
  - **Agent checks:**
    - `git check-ignore -v -- .env` showed `.gitignore:153`.
    - 6 of 6 usage-error checks passed (exit code 2 before any request).
    - 70 of 70 offline checks with fake HTTP responses passed, including that a fake secret and token never appeared in output.
    - Missing credentials gave a clear error and exit code 1.
    - Dummy credentials sent to Twitch gave HTTP 400 and exit code 1.
    - The README's PowerShell override and cleanup steps worked as written.
  - **Live checks by the user, with their real local `.env`:**
    - The "The Witcher 3" search returned 8 results with IDs, release dates and platforms.
    - "zzzxqv-no-such-game-984726" printed "No matches".
    - The dummy-credential test returned HTTP 400 and exit code 1.
    - Both `Test-Path` checks returned False after cleanup.
    - `git check-ignore -v -- .env` showed the ignore rule.
  - **README fix:** after the live run, the README was changed to say "up to 10 results per page" and to cover pages with fewer than 10 results or an empty page 2. The files were staged for review and are not yet committed.
- **Deviations:**
  - **Q1 (environment):** chose a root uv project (Option B) over the recommended single-file script with inline metadata (Option A), so the script and future Django app share one environment. Also asked me to check which Python uv sees before proposing a version.
  - **Q2:** added that Django/DRF compatibility will be verified when those dependencies are added.
  - **Q4:** added a quoted `"The Witcher 3"` README example.
  - **Q6 (query):** kept the recommended plain search with editions, but added an optional `--page` argument (offset = (page − 1) × 10, pages below 1 rejected) beyond the recommendation.
  - **Q7:** added numbering that continues across pages and a separate "no results on page N" message.
  - **After the live run:** asked for the README to reflect pages with fewer than 10 results.
- **Sideways:**
  - **Python:** I first said no system Python was installed, but only the Bash shell's `python` command failed. `uv python list` showed CPython 3.14.7, and I corrected the claim before proposing a version.
  - **Blocked fetches:** Giant Bomb and MobyGames returned HTTP 403, and the TheGamesDB forum returned 401, so their terms couldn't be verified and they were marked unverified. A re-check of the IGDB docs while adding the rate-limit citation also got HTTP 403, so that citation relies on the research agent's earlier fetch the same day, and the file says so.
  - **Offline test:** one test failed at first because my hand-calculated expected date for a pre-1970 timestamp was a day off. The script was correct, and I fixed the test.
  - **README wording:** the README originally implied every page has exactly 10 results. The live run returned 8, and the wording was corrected.
  - **Unconfirmed syntax:** the way the script escapes quotes inside IGDB search text hasn't been checked against the IGDB docs (the docs fetch was blocked). The live searches worked, but neither tested a title containing quotes.