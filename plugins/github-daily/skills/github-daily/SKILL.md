---
name: github-daily
description: Build a daily digest of GitHub's trending repositories. Pull today's trending repos, read each repo's README, and explain in plain simple English what every repo is and why it might be trending, then save it to a dated file. Also supports an on-demand deep dive into a single repo (full README plus file structure plus key source files). No API key needed. Use when the user runs /github-daily, or asks for "today's trending repos", "GitHub trending", "trending repos", "what's hot/popular on GitHub today", a daily GitHub catch-up, or to "deep dive into <repo>".
---

# GitHub Trending Daily (github-daily)

Scripts live next to this file. `{SKILL}` below is the absolute path of the folder this SKILL.md is in.

Two modes share one script (`fetch_gh.py`, stdlib only, no API key):

- **Digest** (default) — list today's trending repos and summarize each one in plain English from its README.
- **Deep dive** (only when the user asks) - go deep on one repo: full README, file tree, and key source files.

"Trending" means stars gained in the window (the `+N today` number), not total stars. A `GITHUB_TOKEN` is used automatically if a valid one is in the environment, and the script falls back to unauthenticated (60/hr, plenty here) on its own.

---

## Mode 1: Daily digest

### Steps

1. Get today's date:
   ```
   date +%F
   ```
   (gives `2026-06-19`, used for the file name and the header.)
   Uses the machine's timezone. `TZ=<zone> date +%F` if the user wants another one.

2. Pull the trending list (fast, no READMEs):
   ```
   python3 {SKILL}/fetch_gh.py
   ```
   Prints JSON: `since`, `count`, `new_count`, and `repos`. Each repo has `rank`, `full_name`, `owner`, `name`, `url`, `description`, `language`, `stars` (total), `forks`, `stars_period` (gained in the window), `period` (e.g. `today`), and `is_new` (true if it was not in the last digest).
   - This call records what was shown so the next run can mark new repos. Do not pass `--no-update` on a real run (that flag is for testing only).
   - Default is `--since daily`, all languages. `--since weekly|monthly` and `--language python` (etc.) change the window and language if the user asks.
   - If the command fails, say GitHub trending was unreachable and stop. Do not invent repos.

3. Fetch the READMEs for every repo in one call (pass all the slugs):
   ```
   python3 {SKILL}/fetch_gh.py --readmes owner1/repo1,owner2/repo2,...
   ```
   Returns `readmes` keyed by slug, each `{found, text, truncated}`. READMEs are truncated to ~3000 chars (enough to summarize). If a repo has no README (`found: false`), summarize from its trending description instead.

4. Summarize EVERY repo (all of them, not a selection) in SIMPLE ENGLISH from its README:
   - 1 short plain sentence per repo: what it is and why it might be trending today. Do not add a second sentence unless the repo truly needs it.
   - If a repo is well known, say so in a few words rather than explaining it.
   - Mark new repos with 🆕. Show the language and the stars gained.

5. Add a "⭐ For you" line near the top highlighting the repos that match the user's interests. Default to AI / LLMs / agents, developer tools, and open-source infrastructure unless the user has said otherwise. Use your judgment from the descriptions and READMEs; do not tag mechanically.

6. Show the digest in chat AND save it:
   - Write the same digest to: `$GH_DAILY_OUT/<date>.md`, where `GH_DAILY_OUT`
     defaults to `~/claude-digests/github` if it is not set. Create the folder if it is missing.
   - If a file for today already exists, overwrite it.

### Style rules (follow these)

- Simple, everyday English. Explain it to a smart friend who is not a programmer.
- Minimal words. Short sentences. Common words. If a technical term is needed, add a few plain words to explain it.
- No buzzwords, no hype. No em-dashes (use commas, periods, or parentheses).
- One short sentence per repo. No extra info: no background, no history, no "why this matters for the industry" - just what it is and why it's trending, then move on.

### Digest layout (follow this format)

```
# 🐙 GitHub Trending · <date>

⭐ For you: #1 timesfm (AI) · #6 codebase-memory-mcp (dev tool) · #9 kilocode (AI coding)
🆕 = new since your last digest  ·  (X new on the trending page today)
Window: today · sorted by stars gained

## 📈 Trending repos

**1. owner/repo** 🆕 `Python` · ⭐ 23.7k total · 🔥 +844 today
🔗 <url>
<one to three short plain sentences: what it is, what it does, why it is trending>

**2. owner/repo** `Rust` · ⭐ 10.1k total · 🔥 +369 today
🔗 <url>
<summary...>

...continue through every repo...
```

---

## Mode 2: Deep dive (only when the user asks)

Trigger when the user says something like "deep dive into <repo>", "tell me more about <repo>", or names one repo from the digest. Do NOT deep dive during the normal digest.

### Steps

1. Resolve the repo to an `owner/repo` slug (from the digest, or ask if ambiguous).

2. Full README (not truncated):
   ```
   python3 {SKILL}/fetch_gh.py --readmes owner/repo --full
   ```

3. File structure and metadata:
   ```
   python3 {SKILL}/fetch_gh.py --tree owner/repo
   ```
   Returns `default_branch`, `stars`, `homepage`, `topics`, and `files` (blob paths + sizes).

4. Read the key files. From the tree, pick the entry points and core source (e.g. `main.*`, `src/` entry, `package.json` / `pyproject.toml` / `Cargo.toml`, top-level config) and fetch each:
   ```
   python3 {SKILL}/fetch_gh.py --file owner/repo:path/to/file --full
   ```
   Read a handful (about 3 to 6), not the whole repo.

5. Write a deeper plain-English breakdown (still simple English, no hype, no em-dashes):
   - What it does and the problem it solves.
   - How it works (the main pieces, in plain words).
   - What it is built with (language, key dependencies).
   - How to install and run it.
   - Who it is for, and anything notable or unusual.
   - Show the deep dive in chat. Save it only if the user asks.

---

## Notes

- "Trending" = stars gained in the window (the 🔥 number), highest interest first; the page is already ordered by GitHub.
- New/seen tracking is stored in `~/.local/state/jod-skills/github-daily/seen.json`
  (keyed by repo name, `GH_DAILY_STATE` moves it).
- The trending page usually has 15 to 25 repos; summarize all of them.
- `GITHUB_TOKEN` is used automatically if valid and silently dropped if not; nothing to configure.
- This is a manual skill: the user runs it when they want it.

## Settings

| Env var | Default | What it does |
|---|---|---|
| `GH_DAILY_OUT` | `~/claude-digests/github` | where the digest file is saved |
| `GH_DAILY_STATE` | `~/.local/state/jod-skills/github-daily/seen.json` | the new/seen file |
| `GITHUB_TOKEN` | none | raises the API rate limit, optional |
| `TZ` | the machine's timezone | which day "today" means |
