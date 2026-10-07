#!/usr/bin/env python3
"""Graph side of /audit. Stdlib only.

  audit.py graph <project>              build graphify graph, trim it, write .audit/graph.json + structure.md
  audit.py next  <project> [--n 3]      rank modules, print the next unfinished ones
  audit.py pack  <project> <module> [--budget 12000] [--page N]
                                        what a reader sub-agent needs for one module, nothing more
                                        big modules come in pages, the output says when there is a next one
  audit.py body  <project> <file> <name>  one function body with line numbers
  audit.py report <project> <module>...   render .audit/verify.json into .audit/findings.md
  audit.py done  <project> <module>     mark a module finished
  audit.py reset <project>              forget progress, start the audit over

Never prints graphify-out/graph.json. That file is bigger than the source.
"""
import json
import os
import re
import shutil
import subprocess
import sys
from collections import defaultdict, Counter

SKIP_DIRS = {"node_modules", ".git", "venv", ".venv", "env", "dist", "build", "target",
             "graphify-out", ".audit", "__pycache__", "vendor", ".next", ".cache",
             "coverage", ".tox", ".mypy_cache", ".ruff_cache", "site-packages"}
CODE_EXT = {".py", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".go", ".rs", ".java",
            ".c", ".h", ".cpp", ".hpp", ".cc", ".rb", ".php", ".kt", ".swift", ".cs"}
ENTRY_NAMES = {"main", "index", "app", "server", "cli", "run", "manage", "wsgi", "asgi", "__main__"}
TEST_HINT = re.compile(r"(^|/)(tests?|__tests__|spec)(/|$)|(_test|\.test|\.spec|test_)")
KEEP_REL = {"calls", "imports", "imports_from", "inherits", "extends", "references",
            "uses", "method", "indirect_call", "re_exports", "defines"}
SMALL_FILE = 150
TINY_MODULE = 6


def die(msg):
    print(f"FATAL: {msg}", file=sys.stderr)
    sys.exit(1)


def audit_dir(project):
    d = os.path.join(project, ".audit")
    os.makedirs(d, exist_ok=True)
    return d


def load(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def save(path, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, separators=(",", ":"))


def source_files(project):
    out = []
    for root, dirs, files in os.walk(project):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".")]
        for fn in files:
            if os.path.splitext(fn)[1] in CODE_EXT:
                out.append(os.path.relpath(os.path.join(root, fn), project))
    return sorted(out)


def line_count(path):
    try:
        with open(path, "rb") as f:
            return sum(1 for _ in f)
    except OSError:
        return 0


# ---------------------------------------------------------------- graph

def run_graphify(project):
    if not shutil.which("graphify"):
        die("graphify not installed. Run: uv tool install graphifyy")
    r = subprocess.run(["graphify", "update", project], capture_output=True, text=True)
    if r.returncode != 0 or not os.path.exists(os.path.join(project, "graphify-out", "graph.json")):
        print(r.stdout[-800:], r.stderr[-800:], file=sys.stderr)
        die("graphify update failed")
    html = os.path.join(project, "graphify-out", "graph.html")
    if os.path.exists(html) and os.path.getsize(html) > 20_000_000:
        os.remove(html)  # useless above ~5k nodes, and huge


def run_ctags(project):
    """(file, name, start) -> end line. Empty if ctags is missing."""
    ends = {}
    if not shutil.which("ctags"):
        print("note: ctags missing, end lines are guessed from the next symbol", file=sys.stderr)
        return ends
    cmd = ["ctags", "--output-format=json", "--fields=+ne", "-R", "--extras=-F"]
    for d in SKIP_DIRS:
        cmd.append(f"--exclude={d}")
    cmd.append(".")
    r = subprocess.run(cmd, cwd=project, capture_output=True, text=True)
    for line in r.stdout.splitlines():
        try:
            t = json.loads(line)
        except ValueError:
            continue
        if "end" in t and "line" in t:
            ends[(t["path"].lstrip("./"), t["name"], t["line"])] = t["end"]
    return ends


def parse_loc(s):
    m = re.match(r"L(\d+)", str(s or ""))
    return int(m.group(1)) if m else None


def clean_name(label):
    return re.sub(r"\(\)$", "", label or "").lstrip(".")


def trim(project, raw, ends):
    nodes = {}
    for n in raw.get("nodes", []):
        f = n.get("source_file") or ""
        if n.get("file_type") != "code" or os.path.splitext(f)[1] not in CODE_EXT:
            continue
        start = parse_loc(n.get("source_location"))
        label = n.get("label") or ""
        name = clean_name(label)
        is_file = start == 1 and name == os.path.basename(f)
        # python/js nodes carry _callable; go/rust nodes only say "name()" in the label
        callable_ = bool(n.get("_callable")) or label.endswith("()")
        is_type = bool(n.get("_callable_class")) or (
            not label.endswith("()") and name[:1].isupper() and not is_file and f.endswith((".go", ".rs", ".java", ".kt", ".cs")))
        nodes[n["id"]] = {
            "id": n["id"], "file": f, "name": name, "start": start, "end": None,
            "kind": "file" if is_file else ("func" if (callable_ or is_type) else "var"),
            "cls": is_type,
            "community": n.get("community", -1),
            "cname": n.get("community_name") or "",
        }
    # end lines: ctags match by file+name+line, else next symbol in file, else EOF
    by_file = defaultdict(list)
    for nd in nodes.values():
        if nd["kind"] != "file" and nd["start"]:
            by_file[nd["file"]].append(nd)
    lens = {}
    for f, lst in by_file.items():
        lst.sort(key=lambda x: x["start"])
        lens[f] = line_count(os.path.join(project, f))
        for i, nd in enumerate(lst):
            e = ends.get((f, nd["name"], nd["start"]))
            if e is None:
                e = ends.get((f, nd["name"].split(".")[-1], nd["start"]))
            if e is None:
                nxt = next((x["start"] for x in lst[i + 1:] if x["start"] > nd["start"]), None)
                e = (nxt - 1) if nxt else lens[f]
                nd["guessed_end"] = True
            nd["end"] = e
    for nd in nodes.values():
        if nd["kind"] == "file":
            nd["start"], nd["end"] = 1, lens.get(nd["file"]) or line_count(os.path.join(project, nd["file"]))
    # a decorated, exported or module-level-registered function is called by a framework,
    # not by our code. The graph cannot see that, so mark it and never call it dead.
    cache = {}
    for nd in nodes.values():
        if nd["kind"] != "func" or not nd["start"]:
            continue
        if nd["file"] not in cache:
            try:
                with open(os.path.join(project, nd["file"]), encoding="utf-8", errors="replace") as fh:
                    cache[nd["file"]] = fh.readlines()
            except OSError:
                cache[nd["file"]] = []
        lines = cache[nd["file"]]
        own = lines[nd["start"] - 1] if nd["start"] - 1 < len(lines) else ""
        above = [l.strip() for l in lines[max(0, nd["start"] - 4):nd["start"] - 1]]
        if own.lstrip().startswith(("export ", "module.exports", "pub fn", "pub async fn")):
            nd["hook"] = "export"
        elif any(l.startswith("@") for l in above) or any(l.startswith("#[") for l in above):
            nd["hook"] = "decorated"
        elif own.strip()[:1].isupper() and nd["file"].endswith((".jsx", ".tsx")):
            nd["hook"] = "component"
    edges = []
    seen = set()
    for e in raw.get("links", []):
        rel = e.get("relation")
        if rel not in KEEP_REL:
            continue
        key = (e["source"], rel, e["target"])
        if key in seen:
            continue
        seen.add(key)
        edges.append({"src": e["source"], "rel": rel, "dst": e["target"],
                      "sure": e.get("confidence") == "EXTRACTED"})
    return nodes, edges


def is_entry(nd):
    base = os.path.splitext(os.path.basename(nd["file"]))[0]
    return nd["kind"] == "file" and base in ENTRY_NAMES or nd["name"] in ("main", "__main__")


def structure(project, nodes, edges, files, raw_ids):
    incoming = Counter()
    outgoing = Counter()
    callers = defaultdict(set)
    for e in edges:
        if e["rel"] in ("calls", "indirect_call", "references", "uses", "method"):
            incoming[e["dst"]] += 1
            callers[e["dst"]].add(e["src"])
        outgoing[e["src"]] += 1
    dead = []
    for nd in nodes.values():
        if nd["kind"] != "func" or nd["cls"]:
            continue
        if TEST_HINT.search(nd["file"]) or nd["name"].startswith("test") or is_entry(nd):
            continue
        if nd["name"].startswith("_") and nd["name"].endswith("_"):
            continue  # dunder, called by the runtime
        if nd.get("hook"):
            continue  # decorated route, export, component: the framework calls it
        if incoming[nd["id"]] == 0:
            dead.append(nd)
    # import cycles, file level
    fimp = defaultdict(set)
    for e in edges:
        if e["rel"] in ("imports", "imports_from") and e["src"] in nodes and e["dst"] in nodes:
            a, b = nodes[e["src"]]["file"], nodes[e["dst"]]["file"]
            if a != b:
                fimp[a].add(b)
    cycles = set()
    for a in fimp:
        for b in fimp[a]:
            if a in fimp.get(b, ()):
                cycles.add(tuple(sorted((a, b))))
    unknown = [e for e in edges if e["dst"] not in raw_ids and e["rel"] in ("calls", "imports", "imports_from")]
    deg = Counter()
    for e in edges:
        deg[e["src"]] += 1
        deg[e["dst"]] += 1
    hubs = [nodes[i] for i, _ in deg.most_common(40) if i in nodes and nodes[i]["kind"] != "file"][:10]
    entries = [nd for nd in nodes.values() if is_entry(nd)]
    parsed = {nd["file"] for nd in nodes.values()}
    unparsed = [f for f in files if f not in parsed]
    lines = [f"# Structure: {os.path.basename(os.path.abspath(project))}", ""]
    lines.append(f"files {len(files)}, parsed {len(parsed)}, functions {sum(1 for n in nodes.values() if n['kind']=='func')}, edges {len(edges)}")
    lines.append("")
    lines.append(f"## Entry points ({len(entries)})")
    lines += [f"- {n['file']}:{n['start']} {n['name']}" for n in entries[:15]] or ["- none found by name, say so"]
    lines.append("")
    lines.append(f"## Hubs, most connected ({len(hubs)})")
    lines += [f"- {n['file']}:{n['start']} {n['name']} ({deg[n['id']]} edges)" for n in hubs]
    lines.append("")
    lines.append(f"## Never called ({len(dead)}), graph says. Exports and framework hooks can be false alarms")
    lines += [f"- {n['file']}:{n['start']}-{n['end']} {n['name']}" for n in sorted(dead, key=lambda x: (x['file'], x['start']))[:60]]
    if len(dead) > 60:
        lines.append(f"- and {len(dead) - 60} more, see graph.json")
    lines.append("")
    lines.append(f"## Import cycles ({len(cycles)})")
    lines += [f"- {a} <-> {b}" for a, b in sorted(cycles)]
    lines.append("")
    lines.append(f"## Edges to nothing ({len(unknown)}), call or import of something the graph never saw")
    lines += [f"- {nodes[e['src']]['file']} -> {e['dst']}" for e in unknown[:30] if e["src"] in nodes]
    lines.append("")
    lines.append(f"## Files graphify could not parse ({len(unparsed)}), these get read whole or skipped")
    lines += [f"- {f} ({line_count(os.path.join(project, f))} lines)" for f in unparsed[:40]]
    return "\n".join(lines) + "\n", {"dead": [n["id"] for n in dead], "hubs": [n["id"] for n in hubs],
                                     "entries": [n["id"] for n in entries], "unparsed": unparsed}


def cmd_graph(project):
    run_graphify(project)
    raw = load(os.path.join(project, "graphify-out", "graph.json"), None)
    if raw is None:
        die("graphify-out/graph.json missing or unreadable")
    ends = run_ctags(project)
    nodes, edges = trim(project, raw, ends)
    files = source_files(project)
    raw_ids = {n["id"] for n in raw.get("nodes", [])}
    text, meta = structure(project, nodes, edges, files, raw_ids)
    d = audit_dir(project)
    save(os.path.join(d, "graph.json"), {"nodes": list(nodes.values()), "edges": edges, "meta": meta})
    with open(os.path.join(d, "structure.md"), "w", encoding="utf-8") as f:
        f.write(text)
    if os.path.exists(os.path.join(d, "modules.json")):
        os.remove(os.path.join(d, "modules.json"))  # graph changed, rank again
    src_bytes = sum(os.path.getsize(os.path.join(project, f)) for f in files) or 1
    print(f"graph: {len(nodes)} nodes, {len(edges)} edges, {len(files)} source files, "
          f"{len(meta['unparsed'])} unparsed, trimmed graph is {os.path.getsize(os.path.join(d, 'graph.json')) * 100 // src_bytes}% of source")
    print(text)


# ---------------------------------------------------------------- modules

def checker_hits(project):
    hits = load(os.path.join(project, ".audit", "checkers.json"), {"findings": []})
    per_file = Counter()
    per_line = defaultdict(list)
    for h in hits.get("findings", []):
        per_file[h.get("file")] += 1
        per_line[h.get("file")].append(h)
    return per_file, per_line


def build_modules(project, g):
    nodes = {n["id"]: n for n in g["nodes"]}
    meta = g["meta"]
    per_file, _ = checker_hits(project)
    files = sorted({n["file"] for n in nodes.values()})
    groups = defaultdict(set)
    for n in nodes.values():
        groups[n["community"]].add(n["file"])
    # a file lands in the community holding most of its symbols
    file_comm = {}
    for f in files:
        c = Counter(n["community"] for n in nodes.values() if n["file"] == f)
        file_comm[f] = c.most_common(1)[0][0]
    comm_files = defaultdict(list)
    for f, c in file_comm.items():
        comm_files[c].append(f)
    mods = []
    unparsed = sorted(meta["unparsed"])  # no symbols, so the pack reads them whole if small
    if len(files) < 40:
        mods.append({"id": "all", "files": files + unparsed})
    else:
        rest = list(unparsed)
        for c, fl in comm_files.items():
            if len(fl) < 3 and sum(1 for n in nodes.values() if n["file"] in fl) < TINY_MODULE:
                rest += fl
            else:
                mods.append({"id": f"c{c}", "files": sorted(fl)})
        if rest:
            mods.append({"id": "rest", "files": sorted(rest)})
    for m in mods:
        fs = set(m["files"])
        ids = [n["id"] for n in nodes.values() if n["file"] in fs]
        names = Counter(nodes[i]["cname"] for i in ids if nodes[i]["cname"])
        m["name"] = names.most_common(1)[0][0] if names else ""
        m["hits"] = sum(per_file[f] for f in fs)
        m["entry"] = sum(1 for i in ids if i in meta["entries"])
        m["hub"] = sum(1 for i in ids if i in meta["hubs"])
        m["funcs"] = sum(1 for i in ids if nodes[i]["kind"] == "func")
        m["lines"] = sum(line_count(os.path.join(project, f)) for f in fs)
        m["risk"] = m["hits"] * 3 + m["hub"] * 2 + m["entry"] * 2 + m["funcs"] // 10
    mods.sort(key=lambda m: -m["risk"])
    for i, m in enumerate(mods):
        m["rank"] = i + 1
    return mods


def cmd_next(project, n):
    d = audit_dir(project)
    g = load(os.path.join(d, "graph.json"), None)
    if g is None:
        die("no .audit/graph.json, run: audit.py graph <project>")
    mp = os.path.join(d, "modules.json")
    mods = load(mp, None)
    if mods is None:
        mods = build_modules(project, g)
        save(mp, mods)
    prog = load(os.path.join(d, "progress.json"), {"done": []})
    # module ids change when graph re-clusters, the files read do not
    read = set(prog.get("files", []))
    todo = [m for m in mods if not set(m["files"]) <= read]
    print(f"modules {len(mods)}, done {len(mods) - len(todo)}, left {len(todo)}")
    for m in todo[:n]:
        print(f"NEXT {m['id']}  {m.get('name', '')}  rank {m['rank']}  risk {m['risk']}  files {len(m['files'])}  funcs {m['funcs']}  lines {m['lines']}  checker hits {m['hits']}")
        for f in m["files"][:12]:
            print(f"   {f}")
        if len(m["files"]) > 12:
            print(f"   and {len(m['files']) - 12} more")
    if not todo:
        print("ALL DONE, nothing left. audit.py reset <project> to start over")


# ---------------------------------------------------------------- pack / body

def read_lines(project, f, a, b):
    try:
        with open(os.path.join(project, f), encoding="utf-8", errors="replace") as fh:
            lines = fh.readlines()
    except OSError:
        return f"[could not read {f}]\n"
    a = max(1, a or 1)
    b = min(len(lines), b or len(lines))
    return "".join(f"{i:5d}| {lines[i - 1]}" for i in range(a, b + 1))


def cmd_pack(project, mod_id, budget, page):
    d = audit_dir(project)
    g = load(os.path.join(d, "graph.json"), None)
    mods = load(os.path.join(d, "modules.json"), None)
    if g is None or mods is None:
        die("run audit.py graph then audit.py next first")
    m = next((x for x in mods if x["id"] == mod_id), None)
    if m is None:
        die(f"no module {mod_id}, run audit.py next")
    nodes = {n["id"]: n for n in g["nodes"]}
    meta = g["meta"]
    fs = set(m["files"])
    _, per_line = checker_hits(project)
    out = []
    out.append(f"# MODULE {mod_id}  ({len(fs)} files, {m['lines']} lines, {m['funcs']} functions)")
    out.append("")
    out.append("## Files")
    for f in sorted(fs):
        n_lines = line_count(os.path.join(project, f))
        out.append(f"- {f} ({n_lines} lines, {len(per_line.get(f, []))} checker hits)")
    out.append("")
    inc = Counter()
    outc = Counter()
    for e in g["edges"]:
        if e["rel"] in ("calls", "indirect_call", "method", "references", "uses"):
            inc[e["dst"]] += 1
            outc[e["src"]] += 1
    syms = [n for n in nodes.values() if n["file"] in fs and n["kind"] != "file"]
    syms.sort(key=lambda n: (n["file"], n["start"] or 0))
    cut = len(out)
    out.append("## Symbols  file:start-end name [in=callers out=callees] flags")
    for n in syms:
        flags = []
        if n["id"] in meta["dead"]:
            flags.append("NEVER-CALLED")
        if n["id"] in meta["hubs"]:
            flags.append("HUB")
        if n["id"] in meta["entries"]:
            flags.append("ENTRY")
        if n.get("hook"):
            flags.append(n["hook"].upper())
        out.append(f"- {n['file']}:{n['start']}-{n['end']} {n['name']} [in={inc[n['id']]} out={outc[n['id']]}] {' '.join(flags)}".rstrip())
    out.append("")
    out.append("## Edges leaving the module (what it depends on, what depends on it)")
    cross = 0
    for e in g["edges"]:
        s, t = nodes.get(e["src"]), nodes.get(e["dst"])
        if not s or not t:
            continue
        if (s["file"] in fs) != (t["file"] in fs):
            cross += 1
            if cross <= 40:
                out.append(f"- {s['file']}:{s['name']} {e['rel']} {t['file']}:{t['name']}")
    if cross > 40:
        out.append(f"- and {cross - 40} more")
    out.append("")
    out.append("## Checker hits in this module")
    any_hit = False
    for f in sorted(fs):
        for h in per_line.get(f, [])[:30]:
            any_hit = True
            out.append(f"- {f}:{h.get('line')} [{h.get('tool')} {h.get('code', '')}] {h.get('msg', '')[:160]}")
    if not any_hit:
        out.append("- none")
    out.append("")
    # bodies, riskiest first. One ordered list of chunks, cut into pages by budget.
    # The cut always uses the page 1 header cost, so every page agrees on where pages start.
    head_tokens = sum(len(x) for x in out) // 4
    if page > 1:
        out[cut:] = ["## Symbols, edges and checker hits are on page 1", ""]
    out.append(f"## Code, riskiest first, page {page}. Line numbers are real. Anything not shown was not read.")

    def risk(n):
        hits = sum(1 for h in per_line.get(n["file"], []) if n["start"] and n["end"] and n["start"] <= (h.get("line") or 0) <= n["end"])
        return hits * 5 + (3 if n["id"] in meta["hubs"] else 0) + (2 if n["id"] in meta["entries"] else 0) + inc[n["id"]] + outc[n["id"]]

    chunks = []  # (title, text)
    small = [f for f in sorted(fs) if line_count(os.path.join(project, f)) <= SMALL_FILE]
    for f in small:
        chunks.append((f"### {f}  (whole file)", read_lines(project, f, 1, None)))
    funcs = [n for n in syms if n["kind"] == "func" and not n["cls"] and n["file"] not in small
             and n["start"] and n["end"] and n["end"] >= n["start"]]
    # a nested function sits inside its parent's range, print the parent once
    by_f = defaultdict(list)
    for n in funcs:
        by_f[n["file"]].append(n)
    top = []
    for lst in by_f.values():
        for n in lst:
            if not any(o is not n and o["start"] <= n["start"] and n["end"] <= o["end"]
                       and (o["end"] - o["start"]) > (n["end"] - n["start"]) for o in lst):
                top.append(n)
    top.sort(key=lambda n: -risk(n))
    for n in top:
        chunks.append((f"### {n['file']}:{n['start']}-{n['end']} {n['name']}  risk {risk(n)}",
                       read_lines(project, n["file"], n["start"], n["end"])))
    pages = [[]]
    page_tokens = [head_tokens]
    tail_tokens = 30  # the "page 1 has symbols" note on later pages
    for c in chunks:
        cost = (len(c[0]) + len(c[1])) // 4
        if pages[-1] and page_tokens[-1] + cost > budget:
            pages.append([])
            page_tokens.append(tail_tokens)
        pages[-1].append(c)
        page_tokens[-1] += cost
    used = page_tokens[page - 1] if page <= len(pages) else 0
    if page > len(pages):
        die(f"module {mod_id} has only {len(pages)} pages")
    for title, text in pages[page - 1]:
        out.append("\n" + title)
        out.append(text)
    unparsed_here = [f for f in sorted(fs) if f in meta["unparsed"]]
    out.append("")
    if unparsed_here:
        out.append(f"## Files graphify could not parse, read them yourself if they matter ({len(unparsed_here)})")
        out += [f"- {f}" for f in unparsed_here]
    if page < len(pages):
        later = sum(len(p) for p in pages[page:])
        out.append(f"## Not on this page ({later} chunks). Run: audit.py pack <project> {mod_id} --page {page + 1}")
        out += [f"- {t[4:]}" for t, _ in pages[page][:40]]
    else:
        out.append("## Last page. Everything the graph knows about this module has been shown")
    out.append(f"\n(page {page} of {len(pages)}, approx {used} tokens of {budget})")
    print("\n".join(out))


def cmd_body(project, f, name):
    g = load(os.path.join(project, ".audit", "graph.json"), None)
    if g is None:
        die("no .audit/graph.json")
    cands = [n for n in g["nodes"] if n["file"] == f and (n["name"] == name or n["name"].endswith("." + name))]
    if not cands:
        if name.isdigit():
            ln = int(name)
            print(read_lines(project, f, max(1, ln - 20), ln + 20))
            return
        die(f"no symbol {name} in {f}. Pass a line number to see 40 lines around it")
    for n in cands:
        print(f"### {n['file']}:{n['start']}-{n['end']} {n['name']}")
        print(read_lines(project, n["file"], n["start"], n["end"]))


KIND_ORDER = {"crash": 0, "security": 1, "wrong": 2, "dead": 3, "smell": 4}
SURE_ORDER = {"high": 0, "medium": 1, "low": 2}


def cmd_report(project, modules):
    d = audit_dir(project)
    v = load(os.path.join(d, "verify.json"), None)
    if v is None:
        die("no .audit/verify.json, the verifier has not run")
    kept = sorted(v.get("kept", []), key=lambda f: (KIND_ORDER.get(f.get("kind"), 9), SURE_ORDER.get(f.get("sure"), 9), f.get("file", ""), f.get("line", 0)))
    unv = v.get("unverified", [])
    dropped = v.get("dropped", [])
    proj = load(os.path.join(d, "project.json"), {})
    chk = load(os.path.join(d, "checkers.json"), {"tools": {}, "findings": []})
    g = load(os.path.join(d, "graph.json"), {"meta": {"unparsed": []}})
    mods = load(os.path.join(d, "modules.json"), [])
    prog = load(os.path.join(d, "progress.json"), {"done": []})
    read = set(prog.get("files", [])) | {f for m in mods if m["id"] in modules for f in m["files"]}
    left = sum(1 for m in mods if not set(m["files"]) <= read)
    lines = [f"# Audit: {os.path.basename(project)}", ""]
    lines.append(f"modules read this run: {', '.join(modules) or 'none'}   left after this run: {left}")
    lines.append(f"checker hits: {len(chk['findings'])}   findings kept: {len(kept)}   dropped by verify: {len(dropped)}   unverified: {len(unv)}")
    lines.append("")
    lines.append("## Findings, ranked. This list is ranked, not complete.")
    for i, f in enumerate(kept, 1):
        lines.append(f"{i}. {f.get('file')}:{f.get('line')}  [{f.get('kind')}, {f.get('sure')}]  {f.get('what')}")
        if f.get("why"):
            lines.append(f"   why: {f['why']}")
        if f.get("fix"):
            lines.append(f"   fix: {f['fix']}")
    if not kept:
        lines.append("nothing found in what was read")
    if unv:
        lines.append("")
        lines.append("## Unverified, could not prove either way")
        lines += [f"- {f.get('file')}:{f.get('line')}  {f.get('what')}" for f in unv]
    if dropped:
        lines.append("")
        lines.append("## Dropped by verify")
        lines += [f"- {f.get('file')}:{f.get('line')}  {f.get('what')}  ({f.get('reason')})" for f in dropped]
    lines.append("")
    lines.append("## Coverage")
    missing = [t for t, s in proj.get("tools", {}).items() if s != "ok"]
    skipped = [f"{t}: {s}" for t, s in chk.get("tools", {}).items() if not s.startswith("ok")]
    lines.append(f"- tools missing: {', '.join(missing) or 'none'}")
    lines.append(f"- checkers not run: {'; '.join(skipped) or 'none'}")
    unp = g.get("meta", {}).get("unparsed", [])
    lines.append(f"- files graphify could not parse: {len(unp)}" + (f" ({', '.join(unp[:8])})" if unp else ""))
    text = "\n".join(lines) + "\n"
    with open(os.path.join(d, "findings.md"), "w", encoding="utf-8") as f:
        f.write(text)
    print(text)


def cmd_done(project, mod_id):
    p = os.path.join(audit_dir(project), "progress.json")
    prog = load(p, {"done": []})
    if mod_id not in prog["done"]:
        prog["done"].append(mod_id)
    mods = load(os.path.join(audit_dir(project), "modules.json"), [])
    files = next((m["files"] for m in mods if m["id"] == mod_id), [])
    prog["files"] = sorted(set(prog.get("files", [])) | set(files))
    save(p, prog)
    print(f"done: {', '.join(prog['done'])}")


def cmd_reset(project):
    p = os.path.join(audit_dir(project), "progress.json")
    if os.path.exists(p):
        os.remove(p)
    print("progress cleared")


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        sys.exit(2)
    cmd, project = argv[0], os.path.abspath(argv[1])
    if not os.path.isdir(project):
        die(f"not a folder: {project}")
    rest = argv[2:]

    def opt(flag, default):
        if flag in rest:
            i = rest.index(flag)
            v = rest[i + 1]
            del rest[i:i + 2]
            return int(v)
        return default

    if cmd == "graph":
        cmd_graph(project)
    elif cmd == "next":
        cmd_next(project, opt("--n", 3))
    elif cmd == "pack":
        b = opt("--budget", 12000)
        pg = opt("--page", 1)
        cmd_pack(project, rest[0], b, pg)
    elif cmd == "body":
        cmd_body(project, rest[0], rest[1])
    elif cmd == "report":
        cmd_report(project, rest)
    elif cmd == "done":
        cmd_done(project, rest[0])
    elif cmd == "reset":
        cmd_reset(project)
    else:
        die(f"unknown command {cmd}")


if __name__ == "__main__":
    main(sys.argv[1:])
