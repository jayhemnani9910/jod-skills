# hn-daily

A daily Hacker News digest, written in plain English.

```
/plugin marketplace add jayhemnani9910/jod-skills
/plugin install hn-daily@jod-skills
```

Then: `/hn-daily`

## What you get

- The front page curated down to about 8 to 12 stories worth your time.
- One short line per story saying what it is and why it matters.
- What people are actually arguing about in the comments.
- New stories marked, so a second run the same day is not a re-read.
- Everything else listed as one-line skims, so nothing is hidden.

The digest shows in chat and gets saved to `~/claude-digests/news/<date>.md`.

## Needs

Python 3. No API key, no account.

## Settings

| Env var | Default | What it does |
|---|---|---|
| `HN_DAILY_OUT` | `~/claude-digests/news` | where the digest is saved |
| `HN_DAILY_STATE` | `~/.local/state/jod-skills/hn-daily/seen.json` | the new/seen history |
| `HN_DAILY_INTERESTS` | built-in AI / Startup / Dev lists | a JSON file of your own tags: `{"Tag": ["keyword", ...]}` |
| `TZ` | the machine's timezone | which day "today" means |
