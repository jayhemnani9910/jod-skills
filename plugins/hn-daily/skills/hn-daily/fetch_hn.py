#!/usr/bin/env python3
"""Fetch the Hacker News front page for the hn-daily skill.

Two modes (no API key needed; free HN APIs):
  list mode (default):
      python3 fetch_hn.py
      -> JSON of the top 30 front-page stories with an `is_new` flag
         (new since the last run). Also records what was shown so the
         next run can tell new from old. No comments here (fast).
  comment mode:
      python3 fetch_hn.py --comments 48497609,48500012
      -> JSON with the top comments for just those story IDs.

Primary source: Algolia HN Search API. Fallback: official Firebase API.
Nothing is hardcoded: stories and the current date are fetched fresh.
"""
import urllib.request, json, re, html, sys, os, argparse
from concurrent.futures import ThreadPoolExecutor

UA = {"User-Agent": "hn-daily"}
ALGOLIA = "https://hn.algolia.com/api/v1"
FIREBASE = "https://hacker-news.firebaseio.com/v0"
def _state_path():
    """Where the seen-IDs file lives. Outside the skill folder on purpose:
    a plugin update replaces the skill folder, and history should survive it."""
    env = os.environ.get("HN_DAILY_STATE")
    if env:
        return os.path.expanduser(env)
    base = os.environ.get("XDG_STATE_HOME") or os.path.expanduser("~/.local/state")
    return os.path.join(base, "jod-skills", "hn-daily", "seen.json")


DEFAULT_STATE = _state_path()
SEEN_CAP = 600  # keep at most this many recent story IDs in the seen file

# Interest topics -> tag. Whole-word match against the title
# (so "ai" does not match "main", "git" does not match "github").
# Point HN_DAILY_INTERESTS at a JSON file of {"Tag": ["keyword", ...]} to
# replace these with your own.
INTERESTS = {
    "AI": ["ai", "a.i.", "llm", "llms", "gpt", "claude", "gemini", "openai",
           "anthropic", "machine learning", "ml", "neural", "model", "models",
           "agent", "agents", "chatbot", "deep learning", "diffusion",
           "transformer", "inference"],
    "Startup": ["startup", "startups", "y combinator", "yc", "funding", "raise",
                "raises", "seed round", "series a", "series b", "venture", "vc",
                "founder", "founders", "launch hn", "show hn", "acquire",
                "acquired", "acquisition", "ipo"],
    "Dev": ["rust", "python", "javascript", "typescript", "golang", "framework",
            "open source", "open-source", "database", "postgres", "linux",
            "kernel", "compiler", "api", "programming", "developer", "developers",
            "self-hosted", "docker", "kubernetes", "git", "terminal", "npm"],
}

_custom = os.environ.get("HN_DAILY_INTERESTS")
if _custom:
    try:
        with open(os.path.expanduser(_custom)) as f:
            INTERESTS = json.load(f)
    except Exception as e:
        sys.stderr.write(f"could not read HN_DAILY_INTERESTS: {e}, using defaults\n")


def fetch(url, timeout=20):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def strip_html(t):
    t = re.sub(r"<[^>]+>", " ", t or "")
    return re.sub(r"\s+", " ", html.unescape(t)).strip()


def tag_interests(title):
    t = (title or "").lower()
    tags = []
    for tag, kws in INTERESTS.items():
        for k in kws:
            if re.search(r"(?<![a-z0-9])" + re.escape(k) + r"(?![a-z0-9])", t):
                tags.append(tag)
                break
    return tags


def get_front_page(n):
    # Primary: Algolia front_page (one call, metadata for all n stories).
    try:
        data = fetch(f"{ALGOLIA}/search?tags=front_page&hitsPerPage={n}")
        stories = []
        for h in data.get("hits", []):
            oid = h["objectID"]
            stories.append({
                "objectID": oid,
                "title": h.get("title"),
                "url": h.get("url") or f"https://news.ycombinator.com/item?id={oid}",
                "points": h.get("points") or 0,
                "num_comments": h.get("num_comments") or 0,
                "author": h.get("author"),
            })
        if stories:
            return stories, "algolia"
    except Exception as e:
        sys.stderr.write(f"Algolia front_page failed, using fallback: {e}\n")

    # Fallback: official Firebase topstories + per-item fetch (concurrent).
    ids = fetch(f"{FIREBASE}/topstories.json")[:n]

    def one(i):
        it = fetch(f"{FIREBASE}/item/{i}.json")
        return {
            "objectID": str(i),
            "title": it.get("title"),
            "url": it.get("url") or f"https://news.ycombinator.com/item?id={i}",
            "points": it.get("score") or 0,
            "num_comments": it.get("descendants") or 0,
            "author": it.get("by"),
        }

    with ThreadPoolExecutor(max_workers=10) as ex:
        return list(ex.map(one, ids)), "firebase"


def get_comments(oid, limit=8, maxlen=600):
    """Top-level comments for one story, text stripped and truncated."""
    try:
        item = fetch(f"{ALGOLIA}/items/{oid}")
    except Exception:
        return []
    out = []
    for c in item.get("children", []) or []:
        tx = strip_html(c.get("text"))
        if tx:
            out.append({"author": c.get("author"), "text": tx[:maxlen]})
        if len(out) >= limit:
            break
    return out


def load_seen(path):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return []


def save_seen(path, ids):
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            json.dump(ids[:SEEN_CAP], f)
    except Exception as e:
        sys.stderr.write(f"could not write seen file: {e}\n")


def comment_mode(ids):
    with ThreadPoolExecutor(max_workers=8) as ex:
        results = list(ex.map(lambda i: (i, get_comments(i)), ids))
    print(json.dumps({"comments": {i: c for i, c in results}}, ensure_ascii=False))


def list_mode(args):
    stories, source = get_front_page(args.stories)
    stories.sort(key=lambda s: s["points"], reverse=True)

    seen = load_seen(args.state)
    seen_set = set(seen)
    for rank, s in enumerate(stories, 1):
        s["rank"] = rank
        s["hn_url"] = f"https://news.ycombinator.com/item?id={s['objectID']}"
        s["interests"] = tag_interests(s["title"])
        s["is_new"] = s["objectID"] not in seen_set

    if not args.no_update:
        current = [s["objectID"] for s in stories]
        merged = current + [x for x in seen if x not in set(current)]
        save_seen(args.state, merged)

    print(json.dumps({
        "source": source,
        "count": len(stories),
        "new_count": sum(1 for s in stories if s["is_new"]),
        "stories": stories,
    }, ensure_ascii=False))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stories", type=int, default=30, help="how many front-page stories")
    ap.add_argument("--comments", help="comma-separated story IDs to fetch comments for")
    ap.add_argument("--state", default=DEFAULT_STATE, help="path to the seen-IDs file")
    ap.add_argument("--no-update", action="store_true", help="do not update the seen file")
    args = ap.parse_args()

    if args.comments:
        ids = [x.strip() for x in args.comments.split(",") if x.strip()]
        comment_mode(ids)
    else:
        list_mode(args)


if __name__ == "__main__":
    main()
