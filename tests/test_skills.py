"""Offline smoke tests for the skill scripts. No network, no gh login, no Claude."""
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLUGINS = ROOT / "plugins"
SKILLS = ["audit", "hn-daily", "github-daily", "oss-status"]
AUDIT = PLUGINS / "audit/skills/audit"
FETCH_SH = PLUGINS / "oss-status/skills/oss-status/fetch.sh"


def load_script(path, env=None):
    """Import a script by path, with env set while its top level runs."""
    old = dict(os.environ)
    os.environ.update(env or {})
    try:
        spec = importlib.util.spec_from_file_location(path.stem + "_under_test", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    finally:
        os.environ.clear()
        os.environ.update(old)


class Manifests(unittest.TestCase):
    def test_marketplace_lists_every_plugin(self):
        market = json.loads((ROOT / ".claude-plugin/marketplace.json").read_text())
        names = {p["name"] for p in market["plugins"]}
        self.assertEqual(names, set(SKILLS) | {"jod-skills"})
        for p in market["plugins"]:
            manifest = json.loads((ROOT / p["source"] / ".claude-plugin/plugin.json").read_text())
            self.assertEqual(manifest["name"], p["name"])

    def test_every_skill_has_a_named_skill_file(self):
        for name in SKILLS:
            head = (PLUGINS / name / "skills" / name / "SKILL.md").read_text().splitlines()[:3]
            self.assertIn(f"name: {name}", head)


class AuditSetup(unittest.TestCase):
    def test_setup_writes_project_json_and_gitignores_outputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "app.py").write_text("print('hi')\n")
            r = subprocess.run([sys.executable, str(AUDIT / "setup.py"), tmp],
                               capture_output=True, text=True, env={**os.environ, "HOME": tmp})
            self.assertEqual(r.returncode, 0, r.stderr)
            info = json.loads((Path(tmp) / ".audit/project.json").read_text())
            self.assertEqual(info["languages"], {".py": 1})
            ignored = (Path(tmp) / ".gitignore").read_text()
            self.assertIn(".audit/", ignored)
            self.assertIn("graphify-out/", ignored)


class HackerNews(unittest.TestCase):
    SCRIPT = PLUGINS / "hn-daily/skills/hn-daily/fetch_hn.py"

    def test_tags_match_whole_words_only(self):
        hn = load_script(self.SCRIPT)
        self.assertIn("AI", hn.tag_interests("Claude writes a compiler"))
        self.assertEqual(hn.tag_interests("The main street of Paris"), [])

    def test_interests_file_replaces_the_defaults(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json") as f:
            json.dump({"Rust": ["rust"]}, f)
            f.flush()
            hn = load_script(self.SCRIPT, {"HN_DAILY_INTERESTS": f.name})
        self.assertEqual(hn.tag_interests("Rust and Claude"), ["Rust"])


class GithubTrending(unittest.TestCase):
    def test_parse_trending_reads_stars_gained_not_total(self):
        gh = load_script(PLUGINS / "github-daily/skills/github-daily/fetch_gh.py")
        page = textwrap.dedent("""\
            <article class="Box-row">
              <h2><a href="/acme/widget">acme / widget</a></h2>
              <p class="col-9 color-fg-muted my-1 tmp-pr-4">Makes widgets</p>
              <span itemprop="programmingLanguage">Rust</span>
              <a href="/acme/widget/stargazers">12,345</a>
              <a href="/acme/widget/forks">67</a>
              <span class="d-inline-block float-sm-right">890 stars today</span>
            </article>""")
        repo = gh.parse_trending(page)[0]
        self.assertEqual(repo["full_name"], "acme/widget")
        self.assertEqual(repo["description"], "Makes widgets")
        self.assertEqual((repo["stars"], repo["stars_period"], repo["period"]), (12345, 890, "today"))


FAKE_GH = """#!/usr/bin/env bash
case "$1 $2" in
  "api user") [ -f "$FAKE/logged_out" ] || echo tester ;;
  "search prs") case "$*" in *"--author tester --state open"*) cat "$FAKE/search.json" ;; *) echo '[]' ;; esac ;;
  "search issues") echo '[]' ;;
  "pr view") cat "$FAKE/pr.json" ;;
  "api repos/acme/widget/pulls/7/comments") cat "$FAKE/threads.json" ;;
  *) exit 1 ;;
esac
"""

PR = {
    "title": "Fix the thing", "state": "OPEN", "isDraft": False, "mergeable": "MERGEABLE",
    "mergeStateStatus": "BLOCKED", "reviewDecision": "", "labels": [], "statusCheckRollup": [],
    "createdAt": "2026-01-01T00:00:00Z", "updatedAt": "2026-01-02T00:00:00Z",
    "additions": 1, "deletions": 1, "comments": [],
    "reviews": [{"author": {"login": "coderabbitai"}, "state": "COMMENTED"}],
}
THREADS = [
    {"user": {"login": "Copilot"}, "created_at": "2026-01-02T00:00:00Z", "path": "a.py", "body": "bot note"},
    {"user": {"login": "maintainer"}, "created_at": "2026-01-01T00:00:00Z", "path": "b.py", "body": "why this?"},
]


class OssStatus(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        gh = self.dir / "gh"
        gh.write_text(FAKE_GH)
        gh.chmod(0o755)
        (self.dir / "search.json").write_text(json.dumps([{"url": "https://github.com/acme/widget/pull/7"}]))
        (self.dir / "pr.json").write_text(json.dumps(PR))
        (self.dir / "threads.json").write_text(json.dumps(THREADS))
        self.env = {**os.environ, "PATH": f"{self.dir}:{os.environ['PATH']}", "FAKE": str(self.dir),
                    "HOME": str(self.dir), "OSS_STATE": str(self.dir / "state/state.json")}
        self.env.pop("OSS_ACCOUNT", None)

    def run_fetch(self):
        return subprocess.run(["bash", str(FETCH_SH)], capture_output=True, text=True, env=self.env)

    def test_logged_out_says_fatal_not_nothing_found(self):
        (self.dir / "logged_out").touch()
        r = self.run_fetch()
        self.assertEqual(r.returncode, 1)
        self.assertTrue(r.stdout.startswith("FATAL: gh is not logged in"), r.stdout)
        self.assertIn("FIX: gh auth login", r.stdout)

    def test_bots_are_not_counted_and_inline_threads_are_read(self):
        out = self.run_fetch().stdout
        self.assertIn("reviews_human: NONE", out)
        self.assertIn("reviews_bot: coderabbitai:COMMENTED", out)
        self.assertIn("thread_humans: maintainer", out)
        self.assertIn("last_thread: maintainer on 2026-01-01 in b.py: why this?", out)

    def test_second_run_marks_the_item_same(self):
        self.assertIn("change: NEW", self.run_fetch().stdout)
        self.assertIn("change: SAME", self.run_fetch().stdout)


if __name__ == "__main__":
    unittest.main()
