# github-daily

Today's GitHub trending repos, each explained in one plain sentence.

```
/plugin marketplace add jayhemnani9910/jod-skills
/plugin install github-daily@jod-skills
```

Then: `/github-daily`, or "deep dive into `<repo>`" for one repo.

## What you get

- Every trending repo, summarized from its README, not its tagline.
- Stars gained today, not total stars, so you see what is actually moving.
- New repos marked since your last digest.
- A "for you" line pointing at the ones that match your interests.

The digest shows in chat and gets saved to `~/claude-digests/github/<date>.md`.

Deep dive mode reads the full README, the file tree, and a handful of key source
files, then explains what the project is, how it works, and how to run it.

## Needs

Python 3. No API key. `GITHUB_TOKEN` is used if it happens to be set, only to
raise the rate limit.

## Settings

| Env var | Default | What it does |
|---|---|---|
| `GH_DAILY_OUT` | `~/claude-digests/github` | where the digest is saved |
| `GH_DAILY_STATE` | `~/.local/state/jod-skills/github-daily/seen.json` | the new/seen history |
| `GITHUB_TOKEN` | none | optional, raises the API rate limit |
| `TZ` | the machine's timezone | which day "today" means |
