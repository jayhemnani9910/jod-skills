---
name: audit
description: Audit one codebase without reading it line by line. Builds a function-level graph with graphify, runs free checkers (ruff, pyright, eslint, tsc, go vet, clippy, semgrep, gitleaks), splits the repo into modules, has reader sub-agents read only the risky function bodies, verifies every finding, then stops and asks you which ones to fix. Fixes go on a branch and get tested. Big repos are done a few modules per run and resume next time. Use when the user runs /audit <path>, or says "audit this project", "find bugs in", "check this codebase", "what is wrong with this repo", "is this project healthy".
argument-hint: <project path> [--n N] [--quick] [--reset] [--budget T]
---

# /audit

One project at a time. Graph first, checkers second, read only what those point
at, verify, list, stop. Fix only what the user picks.

Scripts live next to this file. `{SKILL}` below is the absolute path of the
folder this SKILL.md is in. Call them as `python3 {SKILL}/<name>.py`.
Every output lands in `<project>/.audit/` and is gitignored.

## These hold at every node

TRUTH
  never load graphify-out/graph.json into context, it is bigger than the code
  never read a file the pack did not give you, use `audit.py body` instead
  a checker hit is a lead, a graph flag is a lead, only a read line is proof
  the list is ranked, not complete, say so in every report
  say plainly which tools were missing and which files graphify could not parse
  never say "no bugs", say "nothing found in what was read"

SAFETY
  nothing is edited before the user says which findings to fix
  never loosen, skip or delete a test to make it pass
  on main or master? branch first, `audit/<yyyy-mm-dd>`
  a run command tagged GUESS is not run until the user confirms it
  a command that needs keys, a database or docker is not run, it is reported

VOICE
  short lines, everyday words
  every finding is `file:line`, what is wrong, why, how sure
  no em-dashes, no buzzwords, no closing summary

## The flow

```
START
  path missing? -> ask which project, offer the folders under the working directory
  --reset given? -> python3 audit.py reset <path>
  -> SETUP

SETUP
  python3 setup.py <path>
  show: languages, tools missing, run + test commands, notes
  run or test says GUESS or UNKNOWN? -> ask the user, give the options the script found
  tool missing? -> say which, carry on without it
  -> GRAPH

GRAPH
  python3 audit.py graph <path>
  show the first 12 lines of structure.md, not more
  unparsed files listed? -> say how many, they will be read whole in READ if small
  -> CHECK

CHECK
  python3 check.py <path>
  show the per-tool lines and the total
  -> SPLIT

SPLIT
  python3 audit.py next <path> --n N        (N from --n, default 3)
  say: modules total, done, which ones this run covers
  ALL DONE? -> say so, offer --reset, -> END
  -> READ

READ                     (one sub-agent per module, at most 3 at a time)
  for each module M:
    fill reader.md placeholders, append the page 1 pack, write it to <path>/.audit/prompt-M.md
      python3 audit.py pack <path> M > pack   (--budget from flag, default 12000)
    spawn a general-purpose sub-agent told to `cat` that prompt file and follow it
    do not paste the pack into your own context, the file is the hand-off
    {MODE} is QUICK if --quick was given, else FULL
    FULL: the sub-agent pulls every later page itself. QUICK: page 1 only, riskiest code
    the sub-agent returns JSON
  a sub-agent failed or returned junk? -> retry once, then mark the module "not read", carry on
  -> VERIFY

VERIFY
  fill verify.md, append every .audit/reader-M.json, write .audit/prompt-verify.md
  one general-purpose sub-agent told to `cat` it and follow it
  it writes .audit/verify.json with kept / dropped / unverified
  -> WRITE

WRITE
  python3 audit.py report <path> M1 M2 ...     renders .audit/findings.md from verify.json
  python3 audit.py done <path> M               for each module read
  -> STOP

STOP
  show the findings, numbered
  ask the user which numbers to fix, give options: all high, pick numbers, none
  none, or no answer? -> END
  -> FIX

FIX
  git repo and on main or master? -> git checkout -b audit/<yyyy-mm-dd>
  not a git repo? -> say so, ask before touching anything
  fix only the chosen findings, smallest change each, nothing else
  -> TEST

TEST                     (up to 5 rounds)
  python3 check.py <path>       error count must not go up
  test command from setup, if any and sure
  BROWSE, if the project has a page:
    static site (html at root)  -> node {SKILL}/browse.js <path>
    app with a sure npm start   -> start it in the background, wait for its port,
                                   node {SKILL}/browse.js <path> --url http://localhost:<port>, then stop it
    no .audit/browse.json yet?  -> write one: the buttons and inputs a user would hit, in order
    any error line, exception, console error or failed step -> it is a failure, fix it
    the screenshot .audit/browse.png is there if a look is needed
  other run command from setup, if sure and needs no keys or services, give it 20s, then stop it
  all good           -> SHIP
  something failed   -> fix that, back to TEST
  same failure twice -> stop, show the error, ask the user
  round 5 failed     -> stop, show what is left, ask the user

SHIP
  git add only the files the fixes touched, never -A
  commit: "audit: fix <n> findings" with the file:line list in the body
  push the branch
  -> REPORT

REPORT
  what was fixed, file:line each
  what was skipped and why
  branch name, tests result, run result
  modules left for next time, if any
  -> END
```

## Filling the prompts

`reader.md` and `verify.md` have placeholders: `{PROJECT}` absolute path,
`{MODULE}` module id, `{SKILL}` this skill's folder, `{MODE}` is FULL or QUICK.
Paste the page 1 pack output under the reader prompt. Sub-agents get no other context.

Token honesty: FULL mode reads about as many tokens as the module's source,
because every function body gets read once. The savings come from checkers
finding bugs for free, from QUICK mode reading only the riskiest page, and from
resume, which never re-reads a finished module. Say which mode was used in the report.

## Reading the outputs

| File | What it is |
|---|---|
| `.audit/project.json` | languages, run and test commands with sure or guess, tools present |
| `.audit/structure.md` | entry points, hubs, never-called, import cycles, unparsed files |
| `.audit/graph.json` | trimmed graph, for scripts only |
| `.audit/checkers.json` | every checker hit, flat, with severity error, security, warn |
| `.audit/modules.json` | modules ranked by risk, files in each |
| `.audit/progress.json` | modules already read, this is what makes resume work |
| `.audit/findings.md` | what the user reads |

## Notes

- Small repos, under 40 source files, are one module called `all`.
- A module bigger than the budget comes in pages. The reader is told to fetch them.
- End lines come from ctags for Python and Go, and from the next symbol for the rest. Both were checked against real files. A range can overshoot by a blank line, never undershoot.
- graphify labels decorated, exported and component functions as hooks and never calls them dead. Anything else "never called" still needs a human eye.
- `browse.js` needs Playwright and Chromium, installed once inside the skill folder
  (`cd {SKILL} && npm i && npx playwright install chromium`). `.audit/browse.json` holds
  the click steps per project. No spec means every visible button gets clicked once.
- `/loop 7d /audit <path>` re-runs this on a timer if the user wants it.
- To start over on a project: `/audit <path> --reset`.
