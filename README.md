# jod-skills

Four skills for [Claude Code](https://claude.com/claude-code). Install them once,
then use them from any project.

| Skill | What it does |
|---|---|
| [`audit`](plugins/audit) | Finds bugs in a codebase without reading every line. Builds a call graph, runs free checkers, reads only the risky functions, verifies every finding, then asks you what to fix. |
| [`hn-daily`](plugins/hn-daily) | Your morning Hacker News digest. Picks what is worth your time, reads the comments, writes it in plain English. |
| [`github-daily`](plugins/github-daily) | Today's GitHub trending repos, each explained in one plain sentence from its README. Can also deep dive into any one repo. |
| [`oss-status`](plugins/oss-status) | What is waiting on you across your open GitHub work. Reads inline review threads, so a question buried in code review is not missed. |

## Install

Inside Claude Code:

```
/plugin marketplace add jayhemnani9910/jod-skills
/plugin install jod-skills@jod-skills
```

That installs all four. To pick one instead:

```
/plugin install audit@jod-skills
/plugin install hn-daily@jod-skills
/plugin install github-daily@jod-skills
/plugin install oss-status@jod-skills
```

Restart Claude Code. Then run a skill by name: `/audit .`, `/hn-daily`,
`/github-daily`, `/oss-status`.

To update later: `/plugin update jod-skills`.

## What each skill needs

| Skill | Needs |
|---|---|
| `hn-daily` | Python 3. No API key. |
| `github-daily` | Python 3. No API key. `GITHUB_TOKEN` only raises the rate limit. |
| `oss-status` | [`gh`](https://cli.github.com) (logged in) and [`jq`](https://jqlang.github.io/jq/). |
| `audit` | Python 3 and [graphify](https://github.com/Graphify-Labs/graphify): `uv tool install graphifyy`. Any checker you already have (ruff, pyright, eslint, tsc, go vet, clippy, semgrep, gitleaks) gets used, missing ones are skipped and reported. Browser testing is optional: `cd <skill folder> && npm i && npx playwright install chromium`. |

## Settings

Nothing is required. Every default is safe. Set these if you want something else:

| Env var | Default | Skill |
|---|---|---|
| `HN_DAILY_OUT` | `~/claude-digests/news` | hn-daily |
| `HN_DAILY_STATE` | `~/.local/state/jod-skills/hn-daily/seen.json` | hn-daily |
| `HN_DAILY_INTERESTS` | built-in AI / Startup / Dev lists | hn-daily |
| `GH_DAILY_OUT` | `~/claude-digests/github` | github-daily |
| `GH_DAILY_STATE` | `~/.local/state/jod-skills/github-daily/seen.json` | github-daily |
| `OSS_ACCOUNT` | whoever `gh` is logged in as | oss-status |
| `OSS_STALE_DAYS` | `14` | oss-status |
| `OSS_STATE` | `~/.local/state/jod-skills/oss-status/state.json` | oss-status |
| `TZ` | the machine's timezone | hn-daily, github-daily |

History files live outside the plugin folder on purpose. A plugin update
replaces that folder, and your history should survive it.

## Install without plugins

If you would rather drop the skills straight into `~/.claude/skills/`:

```bash
git clone https://github.com/jayhemnani9910/jod-skills.git
cp -r jod-skills/plugins/*/skills/* ~/.claude/skills/
```

Skip the `jod-skills` bundle folder, it is only a copy of the other four.

## Working on these

The per-skill plugins under `plugins/<name>/` are the source of truth. The
`jod-skills` bundle is generated. After editing a skill:

```bash
./scripts/sync-bundle.sh
```

Then commit what it changed. Check a manifest with `claude plugin validate .`.

## License

MIT. See [LICENSE](LICENSE).
