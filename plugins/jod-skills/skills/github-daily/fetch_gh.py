#!/usr/bin/env python3
"""Fetch GitHub trending repos for the github-daily skill.

No API key needed (the trending page is public HTML; READMEs come from the
public GitHub API at 60 req/hr unauthenticated). Set GITHUB_TOKEN in the
environment to lift the rate limit to 5000/hr.

Modes:
  list mode (default):
      python3 fetch_gh.py [--since daily|weekly|monthly] [--language python]
      -> JSON of the trending repos with an `is_new` flag (new since the last
         run). Also records what was shown so the next run can tell new from
         old. No READMEs here (fast).
  readme mode:
      python3 fetch_gh.py --readmes google-research/timesfm,n0-computer/iroh
      -> JSON with each repo's README text (truncated unless --full).
  tree mode (deep dive):
      python3 fetch_gh.py --tree owner/repo
      -> JSON file tree (blob paths + sizes) and the default branch.
  file mode (deep dive):
      python3 fetch_gh.py --file owner/repo:path/to/file [--full]
      -> JSON with that file's raw text (truncated unless --full).

Nothing is hardcoded: the repo list and current trends are fetched fresh.
"""
import urllib.request, urllib.error, urllib.parse, json, re, html, sys, os, argparse
from concurrent.futures import ThreadPoolExecutor

TRENDING = "https://github.com/trending"
API = "https://api.github.com"
def _state_path():
    """Where the seen-names file lives. Outside the skill folder on purpose:
    a plugin update replaces the skill folder, and history should survive it."""
    env = os.environ.get("GH_DAILY_STATE")
    if env:
        return os.path.expanduser(env)
    base = os.environ.get("XDG_STATE_HOME") or os.path.expanduser("~/.local/state")
    return os.path.join(base, "jod-skills", "github-daily", "seen.json")


DEFAULT_STATE = _state_path()
SEEN_CAP = 600          # keep at most this many recent repo names in seen.json
README_TRUNC = 3000     # chars per README in digest mode (enough for a summary)
FILE_TRUNC = 8000       # chars per file in file mode
TREE_CAP = 400          # max blob paths returned in tree mode


# A token bumps the rate limit to 5000/hr, but an invalid one 401s every call.
# Use it if present, and drop it for the rest of the run on the first 401 so we
# fall back to the (ample) 60/hr unauthenticated limit instead of failing.
_USE_TOKEN = [True]


def _headers(accept="application/vnd.github+json", use_token=True):
    h = {"User-Agent": "github-daily", "Accept": accept}
    tok = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if tok and use_token and _USE_TOKEN[0]:
        h["Authorization"] = f"Bearer {tok}"
    return h


def _get(url, accept, use_token, timeout):
    req = urllib.request.Request(url, headers=_headers(accept, use_token))
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def fetch_text(url, accept="text/html", timeout=25):
    try:
        return _get(url, accept, True, timeout)
    except urllib.error.HTTPError as e:
        # An invalid env token 401s every call. Retry once unauthenticated and
        # disable the token for later calls (60/hr unauth is plenty here).
        if e.code == 401:
            _USE_TOKEN[0] = False
            return _get(url, accept, False, timeout)
        raise


def fetch_json(url, timeout=25):
    return json.loads(fetch_text(url, "application/vnd.github+json", timeout))


def strip_html(t):
    t = re.sub(r"<[^>]+>", " ", t or "")
    return re.sub(r"\s+", " ", html.unescape(t)).strip()


def first_int(text):
    m = re.search(r"[\d,]+", text or "")
    return int(m.group(0).replace(",", "")) if m else 0


# ---------- list mode (scrape the trending page) ----------

def parse_trending(htmltext):
    repos = []
    blocks = re.split(r'<article class="Box-row">', htmltext)[1:]
    for b in blocks:
        m = re.search(r'href="/([^"]+?)/stargazers"', b)
        if not m:
            continue
        full = m.group(1)
        desc_m = re.search(r'<p[^>]*class="[^"]*col-9[^"]*"[^>]*>(.*?)</p>', b, re.S)
        lang_m = re.search(r'<span itemprop="programmingLanguage">([^<]+)</span>', b)
        stars_m = re.search(r'href="/%s/stargazers"[^>]*>(.*?)</a>' % re.escape(full), b, re.S)
        forks_m = re.search(r'href="/%s/forks"[^>]*>(.*?)</a>' % re.escape(full), b, re.S)
        period_m = re.search(r'<span[^>]*class="[^"]*float-sm-right[^"]*"[^>]*>(.*?)</span>', b, re.S)
        period_txt = strip_html(period_m.group(1)) if period_m else ""
        plabel = "today"
        if "this week" in period_txt:
            plabel = "this week"
        elif "this month" in period_txt:
            plabel = "this month"
        owner, _, name = full.partition("/")
        repos.append({
            "full_name": full,
            "owner": owner,
            "name": name,
            "url": f"https://github.com/{full}",
            "description": strip_html(desc_m.group(1)) if desc_m else "",
            "language": lang_m.group(1).strip() if lang_m else None,
            "stars": first_int(strip_html(stars_m.group(1))) if stars_m else 0,
            "forks": first_int(strip_html(forks_m.group(1))) if forks_m else 0,
            "stars_period": first_int(period_txt),
            "period": plabel,
        })
    return repos


def load_seen(path):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return []


def save_seen(path, names):
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            json.dump(names[:SEEN_CAP], f)
    except Exception as e:
        sys.stderr.write(f"could not write seen file: {e}\n")


def list_mode(args):
    url = TRENDING + (f"/{args.language}" if args.language else "")
    url += f"?since={args.since}"
    try:
        repos = parse_trending(fetch_text(url))
    except Exception as e:
        sys.stderr.write(f"could not reach GitHub trending: {e}\n")
        sys.exit(2)
    if not repos:
        sys.stderr.write("trending page returned no repos (layout may have changed)\n")
        sys.exit(3)

    seen = load_seen(args.state)
    seen_set = set(seen)
    for rank, r in enumerate(repos, 1):
        r["rank"] = rank
        r["is_new"] = r["full_name"] not in seen_set

    if not args.no_update:
        current = [r["full_name"] for r in repos]
        merged = current + [x for x in seen if x not in set(current)]
        save_seen(args.state, merged)

    print(json.dumps({
        "since": args.since,
        "language": args.language,
        "count": len(repos),
        "new_count": sum(1 for r in repos if r["is_new"]),
        "repos": repos,
    }, ensure_ascii=False))


# ---------- readme mode ----------

def get_readme(slug, full):
    try:
        txt = fetch_text(f"{API}/repos/{slug}/readme", "application/vnd.github.raw")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return {"found": False, "text": "", "note": "no README found"}
        return {"found": False, "text": "", "note": f"HTTP {e.code}"}
    except Exception as e:
        return {"found": False, "text": "", "note": str(e)}
    truncated = not full and len(txt) > README_TRUNC
    if truncated:
        txt = txt[:README_TRUNC] + "\n\n[...README truncated...]"
    return {"found": True, "text": txt, "truncated": truncated}


def readme_mode(slugs, full):
    with ThreadPoolExecutor(max_workers=8) as ex:
        results = list(ex.map(lambda s: (s, get_readme(s, full)), slugs))
    print(json.dumps({"readmes": {s: r for s, r in results}}, ensure_ascii=False))


# ---------- tree mode (deep dive) ----------

def tree_mode(slug):
    try:
        meta = fetch_json(f"{API}/repos/{slug}")
        branch = meta.get("default_branch", "main")
        data = fetch_json(f"{API}/repos/{slug}/git/trees/{branch}?recursive=1")
    except Exception as e:
        print(json.dumps({"error": str(e)}))
        sys.exit(4)
    blobs = [{"path": t["path"], "size": t.get("size", 0)}
             for t in data.get("tree", []) if t.get("type") == "blob"]
    print(json.dumps({
        "full_name": slug,
        "default_branch": branch,
        "stars": meta.get("stargazers_count"),
        "homepage": meta.get("homepage"),
        "topics": meta.get("topics", []),
        "truncated": data.get("truncated", False) or len(blobs) > TREE_CAP,
        "file_count": len(blobs),
        "files": blobs[:TREE_CAP],
    }, ensure_ascii=False))


# ---------- file mode (deep dive) ----------

def file_mode(spec, full):
    slug, _, path = spec.partition(":")
    if not path:
        print(json.dumps({"error": "use --file owner/repo:path/to/file"}))
        sys.exit(5)
    try:
        txt = fetch_text(f"{API}/repos/{slug}/contents/{urllib.parse.quote(path)}", "application/vnd.github.raw")
    except Exception as e:
        print(json.dumps({"error": str(e), "path": path}))
        sys.exit(6)
    truncated = not full and len(txt) > FILE_TRUNC
    if truncated:
        txt = txt[:FILE_TRUNC] + "\n\n[...file truncated...]"
    print(json.dumps({"full_name": slug, "path": path,
                      "truncated": truncated, "text": txt}, ensure_ascii=False))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", choices=["daily", "weekly", "monthly"], default="daily")
    ap.add_argument("--language", help="filter by language, e.g. python (trending path segment)")
    ap.add_argument("--readmes", help="comma-separated owner/repo slugs to fetch READMEs for")
    ap.add_argument("--tree", help="owner/repo: list the repo file tree (deep dive)")
    ap.add_argument("--file", help="owner/repo:path/to/file: fetch one file's raw text (deep dive)")
    ap.add_argument("--full", action="store_true", help="do not truncate README/file output")
    ap.add_argument("--state", default=DEFAULT_STATE, help="path to the seen-names file")
    ap.add_argument("--no-update", action="store_true", help="do not update the seen file")
    args = ap.parse_args()

    if args.readmes:
        readme_mode([s.strip() for s in args.readmes.split(",") if s.strip()], args.full)
    elif args.tree:
        tree_mode(args.tree.strip())
    elif args.file:
        file_mode(args.file.strip(), args.full)
    else:
        list_mode(args)


if __name__ == "__main__":
    main()
