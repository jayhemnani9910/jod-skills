---
name: oss-status
description: Say what is waiting on the user right now across their open GitHub work. Covers pull requests and issues they opened, and pull requests where someone asked them to review. Reads inline review threads, not just the conversation tab, so a maintainer question buried in code review is not missed. Marks what changed since the last check and flags anything gone stale. Use when the user runs /oss-status, or says "check my contributions", "status of my PRs", "any updates", "did anyone reply", "what do I owe anyone", "check my github", or asks what to do next on his open work.
---

# OSS status

Answers one question: of everything the user has open on GitHub, what is waiting
on them today.

The script lives next to this file. `{SKILL}` below is the absolute path of the
folder this SKILL.md is in.

## These hold at every node

TRUTH
  a bot is not a person
  never report a bot review as someone looking at the work
  never say "nothing found" when the real problem was login
  never guess an item's state, say plainly that it failed to read
  a `SAME` item is not news, do not dress it up as movement

VOICE
  this gets read on a phone
  short sentences, everyday words
  say "no one has looked at it yet", not "awaiting maintainer triage"
  say "the tests passed", not "CI is green"
  name the person who replied, "mikemikimike replied" beats "a comment was added"
  no em-dashes, no buzzwords, no preamble, no closing summary

## The flow

```
START
  run the script, pass a date only if the user gave one
    {SKILL}/fetch.sh
    {SKILL}/fetch.sh 2026-08-19
  -> CHECK

CHECK
  output starts with FATAL? -> LOGIN BROKE
  no blocks at all?         -> say "nothing open, nothing closed in this window", stop
  else                      -> READ

LOGIN BROKE
  show the FIX: line, as is
  say nothing about their contributions, you did not see any
  -> END

READ                    (once per block)
  blocks left? -> JUDGE
  none left?   -> WRITE

JUDGE
  block says ERROR?
    keep it, mark "could not read this one", -> READ
  who is it waiting on?
    a check failed                  -> USER
    merge is CONFLICTING            -> USER
    CHANGES_REQUESTED               -> USER
    a person asked something, in comments or a review thread -> USER
    the CLA is unsigned             -> USER
    kind is REVIEW-REQUEST          -> USER
    anything else                   -> THEM
  bots only? -> THEM, and never name the bot as a reviewer
  block says stale: yes? -> mark it stale
  -> READ

WRITE
  first, what to do today
    only things the user can act on now, most urgent first
    one line each, say the thing to do, not the state
    nothing on them? -> one line saying so, then carry on
  then the table, newest first
    | What | Where | Waiting on | Status |
  then stale, only if any
    one line each, and what to do: ping, close, or let it sit
  -> CHECKLIST

CHECKLIST
  every block in the output appears once, errors included
  no bot named as a person reviewing
  every row says who it waits on
  changed items marked, unchanged ones not sold as news
  the to-do list has only things the user can do today
  something off? -> WRITE
  clean         -> END
```

## Reading a block

| Field | What it tells you |
|---|---|
| `kind` | `PR`, `ISSUE`, or `REVIEW-REQUEST`. A review request is always on the user. |
| `change` | `NEW`, `CHANGED`, or `SAME` since the last run. Lead with what changed. |
| `reviews_human` | `NONE` means no real person has reviewed. Bots do not count. |
| `commenters_human` | Who has spoken, other than the user, in the conversation tab. |
| `thread_humans` | Who has spoken in inline code review. This is the one people miss. |
| `last_thread` | The most recent inline comment, and who left it. |
| `checks` | Anything not `SUCCESS` is the user's problem. |
| `merge` | `CONFLICTING` is the user's problem. `BLOCKED` usually just means no approval yet. |
| `reviewDecision` | `CHANGES_REQUESTED` is the user's problem. |
| `claim_signals` | Someone else said they are already fixing this issue. |
| `idle_days`, `stale` | How long untouched, and whether that crossed the line. |

## Notes

- The script writes `state.json` under `~/.local/state/jod-skills/oss-status/`.
  That is how `change` works. If it is missing, everything reads `NEW` and that
  is correct, not a bug.
- Open items always show. The window, the last 14 days unless the user says
  otherwise, only limits closed ones. Review requests are open ones only.
- Stale line is 14 days idle. `OSS_STALE_DAYS=7 fetch.sh` to move it.
- Skip nothing. If the user cannot act on it and nobody has touched it, it still
  gets a table row, just not a to-do line.
- Needs `gh` (logged in) and `jq`.

## Settings

| Env var | Default | What it does |
|---|---|---|
| `OSS_ACCOUNT` | whoever `gh` is logged in as | which GitHub account to report on |
| `OSS_STALE_DAYS` | `14` | how many idle days counts as stale |
| `OSS_STATE` | `~/.local/state/jod-skills/oss-status/state.json` | the NEW / CHANGED / SAME file |
