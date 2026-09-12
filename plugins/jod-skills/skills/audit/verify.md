# Verify prompt

You get a list of findings from reader agents. Your only job is to throw out
the ones that are not real and keep the ones that are. You are the last gate
before the user sees the list. A false alarm wastes their time. A dropped real bug is worse.

Project: {PROJECT}
To see a function: `python3 {SKILL}/audit.py body {PROJECT} <file> <name>` (or a line number)
To check a name is used or declared somewhere: `grep -rn "<name>" {PROJECT} --include=*.py --include=*.js --include=*.ts --include=*.go --include=*.rs --include=*.html -l` and then `body` on the hit. Do not cat whole files. Never open graphify-out/graph.json.

## Rules

- Re-read the exact lines for every finding marked high or medium. Low ones too if quick.
- Keep only what you can prove from the code you saw. If the proof needs a file you cannot see, mark it "unverified", do not drop it.
- Two findings about the same lines merge into one.
- A "dead" finding stays only if you also checked for decorators, exports, string-name calls, and test usage.
- You may lower "sure". You may not raise it.
- Do not add new findings unless you tripped over one while checking. Then mark it "found while verifying".
- Do not fix anything.

## Output, JSON only

Write the same JSON to `{PROJECT}/.audit/verify.json` (with a heredoc), then print it as your final message.

```json
{
  "kept": [ ...same shape as input, with "sure" possibly lowered... ],
  "dropped": [ {"file": "", "line": 0, "what": "", "reason": "why it is not real"} ],
  "unverified": [ ...findings you could not prove either way... ]
}
```
