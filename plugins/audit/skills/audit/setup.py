#!/usr/bin/env python3
"""Setup side of /audit. Stdlib only.

  setup.py <project>

- says which tools are installed and which are missing
- works out languages, how to run the project, how to test it
- writes .audit/project.json
- adds graphify-out/ and .audit/ to .gitignore

Every run/test command carries a "sure" or "guess" tag. A guess must be shown
to the user before anyone runs it.
"""
import json
import os
import re
import shutil
import sys

TOOLS = {
    "graphify": "uv tool install graphifyy",
    "ctags": "download universal-ctags nightly to ~/.local/bin",
    "ruff": "uv tool install ruff",
    "pyright": "uv tool install pyright",
    "eslint": "npm i -g eslint",
    "tsc": "npm i -g typescript",
    "go": "apt install golang",
    "cargo": "rustup",
    "semgrep": "uv tool install semgrep",
    "gitleaks": "go install github.com/zricethezav/gitleaks/v8@latest",
}
SKIP = {"node_modules", ".git", "venv", ".venv", "env", "dist", "build", "target",
        "graphify-out", ".audit", "__pycache__", "vendor", ".next", "coverage"}
CMD_HINT = re.compile(r"^\s*\$?\s*((npm|pnpm|yarn|bun|python3?|uv|uvicorn|flask|fastapi|gunicorn|streamlit|node|go|cargo|make|docker(-compose)?|pytest|django-admin)\b[^`]*)$")


def read(p, limit=200_000):
    try:
        with open(p, encoding="utf-8", errors="replace") as f:
            return f.read(limit)
    except OSError:
        return ""


def langs(project):
    c = {}
    for _root, dirs, files in os.walk(project):
        dirs[:] = [d for d in dirs if d not in SKIP and not d.startswith(".")]
        for fn in files:
            ext = os.path.splitext(fn)[1]
            if ext in (".py", ".js", ".jsx", ".ts", ".tsx", ".go", ".rs", ".java", ".c", ".cpp", ".rb", ".php"):
                c[ext] = c.get(ext, 0) + 1
    return dict(sorted(c.items(), key=lambda kv: -kv[1]))


def detect(project):
    run, test, notes = [], [], []

    def add(lst, cmd, how, cwd="."):
        lst.append({"cmd": cmd, "sure": how == "sure", "cwd": cwd})

    # look at root and one level down (frontend/, backend/, server/ ...)
    roots = ["."] + sorted(d for d in os.listdir(project)
                           if os.path.isdir(os.path.join(project, d)) and d not in SKIP and not d.startswith("."))
    for sub in roots:
        base = os.path.join(project, sub)
        pj = os.path.join(base, "package.json")
        if os.path.exists(pj):
            try:
                data = json.loads(read(pj))
            except ValueError:
                data = {}
            scripts = data.get("scripts", {}) or {}
            for key in ("dev", "start", "serve"):
                if key in scripts:
                    add(run, f"npm run {key}", "sure", sub)
                    break
            if "test" in scripts and "no test specified" not in scripts["test"]:
                add(test, "npm test", "sure", sub)
            if not os.path.isdir(os.path.join(base, "node_modules")):
                notes.append(f"{sub}: node_modules missing, npm install first")
        if os.path.exists(os.path.join(base, "Makefile")):
            mk = read(os.path.join(base, "Makefile"))
            for tgt in ("run", "dev", "start", "serve"):
                if re.search(rf"^{tgt}:", mk, re.M):
                    add(run, f"make {tgt}", "sure", sub)
                    break
            if re.search(r"^test:", mk, re.M):
                add(test, "make test", "sure", sub)
        if os.path.exists(os.path.join(base, "go.mod")):
            add(test, "go build ./... && go test ./...", "sure", sub)
            if os.path.exists(os.path.join(base, "main.go")):
                add(run, "go run .", "sure", sub)
            else:
                cmds = os.path.join(base, "cmd")
                if os.path.isdir(cmds):
                    for d in sorted(os.listdir(cmds))[:3]:
                        add(run, f"go run ./cmd/{d}", "guess", sub)
        if os.path.exists(os.path.join(base, "Cargo.toml")):
            add(test, "cargo build && cargo test", "sure", sub)
            add(run, "cargo run", "guess", sub)
        py = os.path.join(base, "pyproject.toml")
        if os.path.exists(py):
            t = read(py)
            if "pytest" in t or os.path.isdir(os.path.join(base, "tests")):
                add(test, "pytest -q", "guess", sub)
            m = re.search(r"\[project\.scripts\]\s*\n\s*([\w-]+)\s*=", t)
            if m:
                add(run, m.group(1), "guess", sub)
        for cand, cmd in (("manage.py", "python manage.py runserver"), ("app.py", "python app.py"),
                          ("main.py", "python main.py"), ("server.py", "python server.py"),
                          ("run.py", "python run.py")):
            if os.path.exists(os.path.join(base, cand)):
                txt = read(os.path.join(base, cand))
                if "FastAPI(" in txt:
                    cmd = f"uvicorn {cand[:-3]}:app --reload"
                elif "Flask(" in txt or "create_app" in txt:
                    cmd = f"flask --app {cand[:-3]} run"
                add(run, cmd, "guess", sub)
                break
        if os.path.isdir(os.path.join(base, "tests")) and not any(x["cwd"] == sub for x in test):
            if any(f.endswith(".py") for f in os.listdir(os.path.join(base, "tests"))):
                add(test, "pytest -q", "guess", sub)
        for env in (".env.example", ".env.sample", "env.example"):
            if os.path.exists(os.path.join(base, env)):
                keys = re.findall(r"^([A-Z][A-Z0-9_]+)=", read(os.path.join(base, env)), re.M)
                notes.append(f"{sub}: needs env keys {', '.join(keys[:12])}")
        if any(os.path.exists(os.path.join(base, f)) for f in ("docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml")):
            notes.append(f"{sub}: has docker compose, `docker compose up` may be the real run command")
        if os.path.exists(os.path.join(base, "requirements.txt")) and not os.path.isdir(os.path.join(base, ".venv")) and not os.path.isdir(os.path.join(base, "venv")):
            notes.append(f"{sub}: requirements.txt but no venv, pip install -r requirements.txt first")
    # a static site: html at the root, browse.js can serve and click it
    htmls = sorted(f for f in os.listdir(project) if f.endswith(".html"))
    if htmls:
        entry = "index.html" if "index.html" in htmls else htmls[0]
        browse = os.path.join(os.path.dirname(os.path.abspath(__file__)), "browse.js")
        add(run, f"node {browse} . (opens {entry})", "sure")
        notes.append(f"static site, entry {entry}. Put click steps in .audit/browse.json to test more than button clicks")
    # README hints, only lines that look like commands inside code fences
    hints = []
    for rd in ("README.md", "readme.md", "README.rst", "README"):
        p = os.path.join(project, rd)
        if os.path.exists(p):
            infence = False
            for line in read(p, 60_000).splitlines():
                if line.strip().startswith("```"):
                    infence = not infence
                    continue
                if infence:
                    m = CMD_HINT.match(line)
                    if m and len(hints) < 12:
                        hints.append(m.group(1).strip())
            break
    return run, test, notes, hints


def gitignore(project):
    p = os.path.join(project, ".gitignore")
    want = ["graphify-out/", ".audit/"]
    cur = read(p) if os.path.exists(p) else ""
    missing = [w for w in want if w not in cur.splitlines() and w.rstrip("/") not in cur.splitlines()]
    if not missing:
        return "already ignored"
    with open(p, "a", encoding="utf-8") as f:
        if cur and not cur.endswith("\n"):
            f.write("\n")
        f.write("\n# /audit outputs\n" + "\n".join(missing) + "\n")
    return f"added {', '.join(missing)}"


def main(argv):
    if not argv:
        print(__doc__)
        sys.exit(2)
    project = os.path.abspath(argv[0])
    if not os.path.isdir(project):
        print(f"FATAL: not a folder: {project}", file=sys.stderr)
        sys.exit(1)
    os.environ["PATH"] = os.pathsep.join([os.path.expanduser("~/.local/bin"), os.path.expanduser("~/go/bin"),
                                          os.path.expanduser("~/.cargo/bin"), os.environ.get("PATH", "")])
    os.makedirs(os.path.join(project, ".audit"), exist_ok=True)
    tools = {t: ("ok" if shutil.which(t) else f"missing: {how}") for t, how in TOOLS.items()}
    lg = langs(project)
    run, test, notes, hints = detect(project)
    info = {"project": project, "languages": lg, "run": run, "test": test, "notes": notes,
            "readme_hints": hints, "tools": tools, "git": os.path.isdir(os.path.join(project, ".git"))}
    with open(os.path.join(project, ".audit", "project.json"), "w", encoding="utf-8") as f:
        json.dump(info, f, indent=1)
    print(f"project: {project}")
    print(f"git repo: {'yes' if info['git'] else 'no'}")
    print("languages: " + ", ".join(f"{k} {v}" for k, v in lg.items()))
    print("tools: " + ", ".join(f"{t} {'ok' if s == 'ok' else 'MISSING'}" for t, s in tools.items()))
    for t, s in tools.items():
        if s != "ok":
            print(f"  install {t}: {s[9:]}")

    def show(label, lst):
        print(f"{label}:")
        if not lst:
            print("  UNKNOWN, ask the user")
        for x in lst:
            where = "" if x["cwd"] == "." else f" (in {x['cwd']})"
            print(f"  {x['cmd']}{where}  [{'sure' if x['sure'] else 'GUESS, confirm with the user'}]")

    show("run", run)
    show("test", test)
    if notes:
        print("notes:")
        for n in notes:
            print(f"  {n}")
    if hints:
        print("readme says:")
        for h in hints:
            print(f"  {h}")
    print(f"gitignore: {gitignore(project)}")


if __name__ == "__main__":
    main(sys.argv[1:])
