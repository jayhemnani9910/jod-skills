# oss-status

Answers one question: of everything you have open on GitHub, what is waiting on you.

```
/plugin marketplace add jayhemnani9910/jod-skills
/plugin install oss-status@jod-skills
```

Then: `/oss-status`

## What you get

- A short to-do list of only the things you can act on today.
- A table of every open PR, issue, and review request, and who each one waits on.
- What changed since your last check, marked. Old news is not sold as movement.
- Stale items flagged, with what to do: ping, close, or let it sit.

It reads inline review threads, not just the conversation tab. A maintainer
question buried in code review is the one people miss.

Bots are never counted as people. A CI bot commenting is not someone reviewing
your work.

## Needs

- [`gh`](https://cli.github.com), logged in (`gh auth login`)
- [`jq`](https://jqlang.github.io/jq/)

## Settings

| Env var | Default | What it does |
|---|---|---|
| `OSS_ACCOUNT` | whoever `gh` is logged in as | which account to report on |
| `OSS_STALE_DAYS` | `14` | idle days before something counts as stale |
| `OSS_STATE` | `~/.local/state/jod-skills/oss-status/state.json` | the new/changed history |

Open items always show. Closed ones only from the last 14 days; pass a date to
widen it: `/oss-status since 2026-08-19`.
