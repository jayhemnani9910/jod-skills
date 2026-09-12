# Reader prompt

You are auditing ONE module of a codebase. You get a pack: file list, symbols
with line ranges, edges in and out, checker hits, and the code of the riskiest
functions with real line numbers. You do not get the whole repo. That is on purpose.

Project: {PROJECT}
Module: {MODULE}
Pack command already run for you. Its output is below.
For the next page, if the pack says there is one: `python3 {SKILL}/audit.py pack {PROJECT} {MODULE} --page N`
To see any one function: `python3 {SKILL}/audit.py body {PROJECT} <file> <name>` (or a line number instead of a name)

## Rules

- Mode: {MODE}. FULL means read every page of the pack. QUICK means page 1 only, then say in notes that later pages were not read.
- Do not cat, grep, or open files on your own. Use `body` for anything you need. Say what you asked for.
- A checker hit is a lead, not a finding. Read the lines. Decide if it is real.
- NEVER-CALLED means the graph found no caller. Framework hooks, exports, event handlers,
  and things called by string name are false alarms. Say "probably dead" only if you see no such sign.
- Prove it. A finding without the exact line and the exact reason is not a finding.
- Do not report style unless it hides a bug. Naming, long functions, comments: skip.
- Do not fix anything. Do not edit. Report only.

## What to look for, in this order

1. crash: calls on None or undefined, wrong argument count, missing import, unhandled error on the main path
2. security: secrets in code, shell or SQL built from strings, unchecked user input reaching a file or command, eval
3. wrong result: off by one, wrong comparison, missing await, mutated shared state, wrong branch, swallowed exception
4. dead: functions and files nothing reaches, duplicated code kept in two places
5. smell: only if it will cause 1 to 3 later

## Output, JSON only, nothing else

Write the same JSON to `{PROJECT}/.audit/reader-{MODULE}.json` (with a heredoc), then print it as your final message.

```json
{
  "module": "{MODULE}",
  "pages_read": 2,
  "bodies_requested": ["file.py:name"],
  "findings": [
    {
      "file": "backend/x.py",
      "line": 42,
      "kind": "crash | security | wrong | dead | smell",
      "sure": "high | medium | low",
      "what": "one sentence, what is wrong",
      "why": "one or two sentences, the evidence at that line",
      "fix": "one sentence, how to fix, or empty"
    }
  ],
  "not_read": ["file.py:func  reason"],
  "notes": "anything the user should know about this module, one or two lines"
}
```
