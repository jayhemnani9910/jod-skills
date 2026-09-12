---
name: hn-daily
description: Build a daily Hacker News digest (some people call it "Y Combinator news"). Pull the front page, curate it down to the stories worth the user's time, mark what is new since last time, read the comments on the picks, and write it all in plain simple English, then save it to a dated file. Use when the user runs /hn-daily, or asks for "today's Hacker News", "HN digest", "YC news", "what's popular on Hacker News today", or a daily tech-news catch-up.
---

# Hacker News Daily Digest (hn-daily)

Makes a daily digest of the Hacker News front page and saves it. No API key needed. Uses the free Hacker News APIs through the bundled script. It curates the front page down to what is worth the user's time, and marks what is new since the last digest.

Scripts live next to this file. `{SKILL}` below is the absolute path of the folder this SKILL.md is in.

## Steps when this skill runs

1. Get today's date:
   ```
   date +%F
   ```
   (gives something like `2026-06-13`, use this for the file name and the header.)
   Uses the machine's timezone. `TZ=<zone> date +%F` if the user wants another one.

2. Pull the front page list (fast, no comments):
   ```
   python3 {SKILL}/fetch_hn.py
   ```
   Prints JSON: `count`, `new_count`, and `stories` (top 30, sorted by points). Each story has `rank`, `title`, `url`, `points`, `num_comments`, `hn_url`, `interests` (tags), and `is_new` (true if it was not in the last digest).
   - This call also records what was shown, so the next run can tell new from old. Do not pass `--no-update` on a real run (that flag is only for testing).
   - `--stories N` changes how many to pull. If the whole command fails, say the news site was unreachable and stop. Do not invent stories.

3. Curate the list down to what is worth the user's time (aim for about 8 to 12 picks):
   - Lean toward stories tagged AI, Startup, or Dev (these are `interests`) and the highest-point stories.
   - Also include any big or genuinely interesting story even if it has no tag (major science, security, world news, a notable launch).
   - Skip niche, low-signal, or repetitive items, even if they carry a tag.

4. Get comments for the picks that have real discussion:
   - Take the picked stories with the most comments (up to about 8 of them) and fetch their comments in one call:
     ```
     python3 {SKILL}/fetch_hn.py --comments <id1>,<id2>,<id3>
     ```
   - Use those comments to write 1 to 2 short plain bullets per story (the main thing people agree on or argue about). Picks with few or no comments do not need a comment section.

5. Write the digest in SIMPLE ENGLISH (see style rules below) using the layout below.
   - Mark new stories with 🆕.
   - Show interest tags next to a story.
   - List the stories you did NOT pick as quick one-liners at the bottom, so nothing is hidden.

6. Show the digest in chat AND save it:
   - Write the same digest to: `$HN_DAILY_OUT/<date>.md`, where `HN_DAILY_OUT`
     defaults to `~/claude-digests/news` if it is not set. Create the folder if it is missing.
   - If a file for today already exists, overwrite it.

## Style rules (follow these)

- Use simple, everyday English. Write like you are explaining the news to a smart friend who is not a tech person.
- Minimal words. Short sentences. Common words. If a technical word is needed, add a few plain words to explain it.
- No buzzwords, no hype, no fancy vocabulary.
- No em-dashes. Use commas, periods, or parentheses instead.
- One short line per summary. One short sentence per comment bullet. No extra info: no background, no speculation, no "this could mean" - just the fact and why it's worth knowing, then move on.

## Digest layout (follow this format)

```
# 📰 Hacker News Daily · <date>

⭐ For you: #1 [AI] · #3 [Dev] · #5 [Startup]
🆕 = new since your last digest  ·  (X new on the front page today)

## ✅ Worth your time today

**1. <title>** 🆕 `[AI]`
🔗 <short link> · 💯 <points> pts · 💬 <num_comments> · [discussion](<hn_url>)
<one short plain line: what it is and why it matters>
💬 What people say:
- <one short plain sentence>
- <one short plain sentence>

**2. <title>** `[Dev]`
...continue through the picks...

## 📋 The rest (quick skim)

- <title> 🆕 `[tag]` · 💯 <pts> · 💬 <comments> · [link](<url>)
- <title> · 💯 <pts> · 💬 <comments> · [link](<url>)
...one line for every story you did not pick...
```

## Notes
- "Popular" = sorted by points, highest first.
- Keep it skimmable. This gets read in the morning.
- This is a manual skill: the user runs it when they want it.
- To change which topics get tagged, point `HN_DAILY_INTERESTS` at a JSON file
  of `{"Tag": ["keyword", ...]}`. It replaces the built-in list.
- New/seen tracking is stored in `~/.local/state/jod-skills/hn-daily/seen.json`
  (`HN_DAILY_STATE` moves it).

## Settings

| Env var | Default | What it does |
|---|---|---|
| `HN_DAILY_OUT` | `~/claude-digests/news` | where the digest file is saved |
| `HN_DAILY_STATE` | `~/.local/state/jod-skills/hn-daily/seen.json` | the new/seen file |
| `HN_DAILY_INTERESTS` | built-in AI / Startup / Dev lists | JSON file of your own tags |
| `TZ` | the machine's timezone | which day "today" means |
