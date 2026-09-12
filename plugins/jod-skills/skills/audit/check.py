#!/usr/bin/env python3
"""Checker side of /audit. Stdlib only. Runs whatever free checkers fit the
project and are installed, and writes one flat list to .audit/checkers.json:

  {"tools": {"ruff": "ok 12 hits" | "missing" | "skipped: why" | "failed: why"},
   "findings": [{"file", "line", "tool", "code", "msg", "severity"}]}

severity: "error" (will crash or is wrong), "security", "warn" (smell).

  check.py <project>
"""
import json
import os
import re
import shutil
import subprocess
import sys

TIMEOUT = 600
SKIP = {"node_modules", ".git", "venv", ".venv", "env", "dist", "build", "target",
        "graphify-out", ".audit", "__pycache__", "vendor", ".next", "coverage"}
PATH_EXTRA = [os.path.expanduser("~/.local/bin"), os.path.expanduser("~/go/bin"),
              os.path.expanduser("~/.cargo/bin")]


def have(tool):
    return shutil.which(tool) is not None


def run(cmd, cwd, timeout=TIMEOUT):
    try:
        r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
        return r.returncode, r.stdout, r.stderr
    except subprocess.TimeoutExpired:
        return -1, "", f"timeout after {timeout}s"
    except OSError as e:
        return -1, "", str(e)


def langs(project):
    found = set()
    for _root, dirs, files in os.walk(project):
        dirs[:] = [d for d in dirs if d not in SKIP and not d.startswith(".")]
        for fn in files:
            ext = os.path.splitext(fn)[1]
            if ext == ".py":
                found.add("py")
            elif ext in (".js", ".jsx", ".mjs", ".cjs"):
                found.add("js")
            elif ext in (".ts", ".tsx"):
                found.add("ts")
            elif ext == ".go":
                found.add("go")
            elif ext == ".rs":
                found.add("rs")
    return found


def rel(project, path):
    try:
        return os.path.relpath(os.path.abspath(os.path.join(project, path)), project)
    except ValueError:
        return path


class Out:
    def __init__(self):
        self.tools = {}
        self.findings = []

    def add(self, tool, file, line, code, msg, severity="warn"):
        self.findings.append({"file": file, "line": int(line or 0), "tool": tool,
                              "code": code or "", "msg": (msg or "").strip()[:300], "severity": severity})

    def status(self, tool, s):
        self.tools[tool] = s
        print(f"  {tool:10s} {s}")


# ---------------------------------------------------------------- python

RUFF_ERROR = re.compile(r"^(F8|F6|F7|E9|PLE|B0|S)")


def ruff(project, out):
    if not have("ruff"):
        return out.status("ruff", "missing: uv tool install ruff")
    rc, so, se = run(["ruff", "check", ".", "--output-format", "json", "--select", "F,E9,B,S,PLE",
                      "--exclude", ",".join(SKIP), "--no-cache"], project)
    try:
        items = json.loads(so or "[]")
    except ValueError:
        return out.status("ruff", f"failed: {se[-200:]}")
    for it in items:
        code = it.get("code") or ""
        sev = "security" if code.startswith("S") else ("error" if RUFF_ERROR.match(code) else "warn")
        out.add("ruff", rel(project, it["filename"]), it["location"]["row"], code, it.get("message"), sev)
    out.status("ruff", f"ok {len(items)} hits")


def pyright(project, out):
    if not have("pyright"):
        return out.status("pyright", "missing: uv tool install pyright")
    rc, so, se = run(["pyright", "--outputjson", "."], project)
    try:
        data = json.loads(so)
    except ValueError:
        return out.status("pyright", f"failed: {(se or so)[-200:]}")
    n = 0
    for d in data.get("generalDiagnostics", []):
        if d.get("severity") != "error":
            continue
        msg = d.get("message", "")
        if "could not be resolved" in msg or "Stub file not found" in msg:
            continue  # deps not installed, not a code bug
        n += 1
        out.add("pyright", rel(project, d["file"]), d["range"]["start"]["line"] + 1, d.get("rule", ""), msg, "error")
    out.status("pyright", f"ok {n} errors (import-not-found dropped)")


# ---------------------------------------------------------------- js / ts

ESLINT_CFG = ("eslint.config.js", "eslint.config.mjs", "eslint.config.cjs", ".eslintrc", ".eslintrc.js",
              ".eslintrc.cjs", ".eslintrc.json", ".eslintrc.yml", ".eslintrc.yaml")


def eslint(project, out):
    if not any(os.path.exists(os.path.join(project, c)) for c in ESLINT_CFG):
        return out.status("eslint", "skipped: no eslint config in project")
    if not os.path.isdir(os.path.join(project, "node_modules")):
        return out.status("eslint", "skipped: node_modules missing, run npm install first")
    cmd = ["npx", "--no-install", "eslint", ".", "-f", "json"]
    rc, so, se = run(cmd, project)
    try:
        data = json.loads(so)
    except ValueError:
        return out.status("eslint", f"failed: {(se or so)[-200:]}")
    n = 0
    for f in data:
        for m in f.get("messages", []):
            if m.get("severity") != 2:
                continue
            n += 1
            rule = m.get("ruleId") or ""
            sev = "error" if rule in ("no-undef", "no-unreachable", "no-dupe-keys", "no-unsafe-finally",
                                      "no-const-assign", "no-func-assign", "no-import-assign",
                                      "no-use-before-define", "no-redeclare", "use-isnan", "valid-typeof") or rule == "" else "warn"
            out.add("eslint", rel(project, f["filePath"]), m.get("line"), rule, m.get("message"), sev)
    out.status("eslint", f"ok {n} errors")


TSC_LINE = re.compile(r"^(.+?)\((\d+),\d+\): error (TS\d+): (.*)$")


def tsc(project, out):
    if not os.path.exists(os.path.join(project, "tsconfig.json")):
        return out.status("tsc", "skipped: no tsconfig.json")
    if not os.path.isdir(os.path.join(project, "node_modules")):
        return out.status("tsc", "skipped: node_modules missing, run npm install first")
    local = os.path.join(project, "node_modules", ".bin", "tsc")
    cmd = [local] if os.path.exists(local) else (["tsc"] if have("tsc") else None)
    if cmd is None:
        return out.status("tsc", "missing: npm i -g typescript")
    rc, so, se = run(cmd + ["--noEmit", "--pretty", "false", "-p", "."], project)
    n = 0
    for line in so.splitlines():
        m = TSC_LINE.match(line)
        if m:
            n += 1
            out.add("tsc", rel(project, m.group(1)), m.group(2), m.group(3), m.group(4), "error")
    out.status("tsc", f"ok {n} errors")


# ---------------------------------------------------------------- go / rust

GO_LINE = re.compile(r"^(.+?\.go):(\d+):\d+: (.*)$")


def govet(project, out):
    if not have("go"):
        return out.status("go vet", "missing")
    if not os.path.exists(os.path.join(project, "go.mod")):
        return out.status("go vet", "skipped: no go.mod at project root")
    rc, so, se = run(["go", "vet", "./..."], project)
    n = 0
    for line in se.splitlines():
        m = GO_LINE.match(line.strip())
        if m:
            n += 1
            out.add("go vet", rel(project, m.group(1)), m.group(2), "", m.group(3), "error")
    out.status("go vet", f"ok {n} hits" if rc in (0, 1) or n else f"failed: {se[-200:]}")


def clippy(project, out):
    if not have("cargo"):
        return out.status("clippy", "missing")
    if not os.path.exists(os.path.join(project, "Cargo.toml")):
        return out.status("clippy", "skipped: no Cargo.toml at project root")
    rc, so, se = run(["cargo", "clippy", "-q", "--message-format=json"], project)
    n = 0
    for line in so.splitlines():
        try:
            m = json.loads(line)
        except ValueError:
            continue
        if m.get("reason") != "compiler-message":
            continue
        msg = m["message"]
        lvl = msg.get("level")
        if lvl not in ("error", "warning"):
            continue
        spans = [s for s in msg.get("spans", []) if s.get("is_primary")] or msg.get("spans", [])
        if not spans:
            continue
        n += 1
        code = (msg.get("code") or {}).get("code", "") or ""
        out.add("clippy", rel(project, spans[0]["file_name"]), spans[0]["line_start"], code, msg.get("message"),
                "error" if lvl == "error" else "warn")
    out.status("clippy", f"ok {n} hits" if n or rc == 0 else f"failed: {se[-200:]}")


# ---------------------------------------------------------------- security

def semgrep(project, out):
    if not have("semgrep"):
        return out.status("semgrep", "missing: uv tool install semgrep")
    cmd = ["semgrep", "scan", "--config", "p/security-audit", "--json", "--metrics=off", "--quiet",
           "--timeout", "60", "."]
    for d in SKIP:
        cmd += ["--exclude", d]
    rc, so, se = run(cmd, project)
    try:
        data = json.loads(so)
    except ValueError:
        return out.status("semgrep", f"failed (needs internet for rules): {se[-160:]}")
    n = 0
    for r in data.get("results", []):
        n += 1
        out.add("semgrep", rel(project, r["path"]), r["start"]["line"], r.get("check_id", "").split(".")[-1],
                r.get("extra", {}).get("message"), "security")
    out.status("semgrep", f"ok {n} hits")


def gitleaks(project, out):
    if not have("gitleaks"):
        return out.status("gitleaks", "missing: go install github.com/zricethezav/gitleaks/v8@latest")
    rep = os.path.join(project, ".audit", "gitleaks.json")
    rc, so, se = run(["gitleaks", "dir", ".", "--no-banner", "-f", "json", "-r", rep, "--exit-code", "3"], project)
    try:
        with open(rep, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        data = []
    n = 0
    for r in data or []:
        if any(part in SKIP for part in r.get("File", "").split("/")):
            continue
        n += 1
        out.add("gitleaks", rel(project, r["File"]), r.get("StartLine"), r.get("RuleID"),
                f"possible secret: {r.get('Description')}", "security")
    if os.path.exists(rep):
        os.remove(rep)
    out.status("gitleaks", f"ok {n} hits" if rc in (0, 3) else f"failed: {se[-200:]}")


# ---------------------------------------------------------------- main

def main(argv):
    if not argv:
        print(__doc__)
        sys.exit(2)
    project = os.path.abspath(argv[0])
    if not os.path.isdir(project):
        print(f"FATAL: not a folder: {project}", file=sys.stderr)
        sys.exit(1)
    os.environ["PATH"] = os.pathsep.join(PATH_EXTRA + [os.environ.get("PATH", "")])
    os.makedirs(os.path.join(project, ".audit"), exist_ok=True)
    found = langs(project)
    print(f"languages: {', '.join(sorted(found)) or 'none'}")
    out = Out()
    if "py" in found:
        ruff(project, out)
        pyright(project, out)
    if "js" in found or "ts" in found:
        eslint(project, out)
    if "ts" in found:
        tsc(project, out)
    if "go" in found:
        govet(project, out)
    if "rs" in found:
        clippy(project, out)
    semgrep(project, out)
    gitleaks(project, out)
    out.findings.sort(key=lambda f: ({"error": 0, "security": 1, "warn": 2}[f["severity"]], f["file"], f["line"]))
    with open(os.path.join(project, ".audit", "checkers.json"), "w", encoding="utf-8") as f:
        json.dump({"tools": out.tools, "findings": out.findings}, f, separators=(",", ":"))
    by = {}
    for f in out.findings:
        by[f["severity"]] = by.get(f["severity"], 0) + 1
    print(f"findings: {len(out.findings)}  " + "  ".join(f"{k} {v}" for k, v in by.items()))


if __name__ == "__main__":
    main(sys.argv[1:])
