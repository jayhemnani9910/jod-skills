# Contributing

I try to reply to issues within a few days.

## Setup

You need Python 3, bash and `jq`. No packages to install for the tests.

```bash
git clone https://github.com/jayhemnani9910/jod-skills.git
cd jod-skills
```

To try your changes inside Claude Code, add your clone as a marketplace:

```bash
claude plugin marketplace add "$PWD"
claude plugin install jod-skills@jod-skills
```

## Tests and checks

These are the same steps CI runs:

```bash
python3 -m unittest discover -s tests -v
ruff check --select E9,F,B .
shellcheck scripts/sync-bundle.sh plugins/oss-status/skills/oss-status/fetch.sh
claude plugin validate .
```

The tests are offline. They use a fake `gh` and never call Hacker News, GitHub
or Claude.

## Editing a skill

Edit the skill under `plugins/<name>/skills/<name>/`, never under
`plugins/jod-skills/`. That bundle is generated. After editing, run:

```bash
./scripts/sync-bundle.sh
```

and commit what it changed. CI fails if the bundle is out of sync.

## Style

- Python: standard library only, so the skills run with a bare Python 3.
- Python must pass the ruff check above, shell must pass shellcheck.
- Match the voice of the `SKILL.md` you are editing: short lines, plain words.

## Pull requests

Branch from `main`, one change per PR, and say how you tested it. Add a test
under `tests/` if you fix a bug in a script.

## Bug reports

Open an issue with the skill name, what you ran, what you expected, what you
got, your OS and your Claude Code version (`claude --version`). Paste the
script output if a fetch script failed.
