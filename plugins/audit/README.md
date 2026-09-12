# audit

Finds bugs in a codebase without reading every line of it.

```
/plugin marketplace add jayhemnani9910/jod-skills
/plugin install audit@jod-skills
```

Then: `/audit <path to a project>`

## How it works

1. Builds a function-level call graph of the project (graphify).
2. Runs every free checker you already have: ruff, pyright, eslint, tsc, go vet,
   clippy, semgrep, gitleaks. Missing ones are skipped and named in the report.
3. Splits the repo into modules and ranks them by risk.
4. Sub-agents read only the function bodies the graph and the checkers point at,
   never whole files.
5. A second pass verifies every finding, so false alarms get dropped.
6. It stops and shows you a numbered list. Nothing is edited until you pick.
7. Fixes you pick go on a branch, get tested, and get committed.

Big repos are done a few modules per run and resume where they left off.

## Needs

- Python 3
- [graphify](https://github.com/Graphify-Labs/graphify): `uv tool install graphifyy`
- Optional, for clicking through a web page during testing:
  `cd <this skill folder> && npm i && npx playwright install chromium`

Checkers are all optional. Whatever is installed gets used.

## Flags

| Flag | What it does |
|---|---|
| `--n N` | how many modules to do this run (default 3) |
| `--quick` | read only the riskiest page of each module |
| `--reset` | start the project over from scratch |
| `--budget T` | tokens per reader pack (default 12000) |

Output lands in `<project>/.audit/` and is added to that project's `.gitignore`.
