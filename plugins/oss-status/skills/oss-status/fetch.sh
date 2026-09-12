#!/usr/bin/env bash
# What is waiting on you across your open GitHub work.
# Covers PRs and issues you opened, plus PRs where you were asked to review.
# Reads inline review threads, not just the conversation tab.
# Marks NEW / CHANGED / SAME against the last run, and flags stale items.
#
# Usage: fetch.sh [SINCE_YYYY-MM-DD]     (default: 14 days ago)
# Env:   OSS_ACCOUNT, OSS_STALE_DAYS, OSS_STATE

set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# The account defaults to whoever gh is logged in as. Set OSS_ACCOUNT to pin
# one when you have more than one account.
ACCOUNT="${OSS_ACCOUNT:-$(env -u GITHUB_TOKEN -u GH_TOKEN gh api user --jq .login 2>/dev/null)}"
SINCE="${1:-$(date -d '14 days ago' +%F 2>/dev/null || date -v-14d +%F)}"
TODAY="$(date +%F)"
STALE_DAYS="${OSS_STALE_DAYS:-14}"
# State lives outside the skill folder: a plugin update replaces that folder.
STATE_DIR="${XDG_STATE_HOME:-$HOME/.local/state}/jod-skills/oss-status"
STATE="${OSS_STATE:-$STATE_DIR/state.json}"
mkdir -p "$(dirname "$STATE")"

gh_() { env -u GITHUB_TOKEN -u GH_TOKEN gh "$@"; }

# An expired token in the environment and the wrong active account both fail
# in a way that looks like "no contributions". Rule them out before anything.
if [ -z "$ACCOUNT" ]; then
  echo "FATAL: gh is not logged in, so there is no account to check."
  echo "FIX: gh auth login       (or set OSS_ACCOUNT=<your-login>)"
  exit 1
fi

who="$(gh_ api user --jq .login 2>/dev/null)"
if [ "$who" != "$ACCOUNT" ]; then
  gh_ auth switch --user "$ACCOUNT" >/dev/null 2>&1
  who="$(gh_ api user --jq .login 2>/dev/null)"
fi
if [ "$who" != "$ACCOUNT" ]; then
  echo "FATAL: gh is not authenticated as $ACCOUNT (got: '${who:-nothing}')."
  echo "FIX: env -u GITHUB_TOKEN -u GH_TOKEN gh auth switch --user $ACCOUNT"
  exit 1
fi

echo "account: $ACCOUNT"
echo "window: $SINCE to $TODAY   stale after: ${STALE_DAYS}d"
[ -f "$STATE" ] || echo "note: no previous state, everything reads NEW"
echo

# Logins are matched lower-cased. "Copilot" and "Copilot[bot]" are the same bot
# wearing two names, and a bot counted as a person is the one failure this
# whole skill exists to prevent.
BOTS='["greptile-apps","copilot","copilot-pull-request-reviewer","github-actions","claassistant","codecov","codecov-commenter","coderabbitai","dependabot","sonarcloud","vercel","netlify","changeset-bot","socket-security","gitguardian","renovate","mergify","allcontributors","sweep-ai","codiumai-pr-agent"]'
JQ_BOT="def isbot: (ascii_downcase) as \$l | (\$l|test(\"\\\\[bot\\\\]\$\")) or ($BOTS | index(\$l) != null);"

NEWSTATE="$(mktemp)"
trap 'rm -f "$NEWSTATE"' EXIT

age_days() {
  local t n
  t=$(date -d "$1" +%s 2>/dev/null) || { echo "?"; return; }
  n=$(date +%s)
  echo $(( (n - t) / 86400 ))
}

old_fp() { jq -r --arg k "$1" '.[$k] // ""' "$STATE" 2>/dev/null; }

emit_change() { # $1=key $2=fingerprint
  local o; o="$(old_fp "$1")"
  printf '%s\t%s\n' "$1" "$2" >> "$NEWSTATE"
  if   [ -z "$o"        ]; then echo "change: NEW"
  elif [ "$o" != "$2"   ]; then echo "change: CHANGED"
  else                          echo "change: SAME"
  fi
}

search_urls() { # $1=prs|issues  $2..=extra args
  local kind="$1"; shift
  gh_ search "$kind" "$@" --json url --limit 100 2>/dev/null | jq -r '.[].url'
}

split_url() {
  echo "$1" | sed -E 's#https://github.com/([^/]+/[^/]+)/(pull|issues)/([0-9]+)#\1 \3#'
}

PR_URLS="$(search_urls prs --author "$ACCOUNT" --created ">=$SINCE")" \
  || PR_URLS="$(sleep 3; search_urls prs --author "$ACCOUNT" --created ">=$SINCE")" \
  || { echo "ERROR: could not search pull requests (gh search failed twice)."; PR_URLS=""; }

ISSUE_URLS="$(search_urls issues --author "$ACCOUNT" --created ">=$SINCE")" \
  || ISSUE_URLS="$(sleep 3; search_urls issues --author "$ACCOUNT" --created ">=$SINCE")" \
  || { echo "ERROR: could not search issues (gh search failed twice)."; ISSUE_URLS=""; }

# Review requests ignore the window. An old one still sits on him.
REVIEW_URLS="$(search_urls prs --review-requested "$ACCOUNT" --state open)" \
  || { echo "ERROR: could not search review requests."; REVIEW_URLS=""; }

pr_block() { # $1=repo $2=num $3=url $4=kind
  local repo="$1" num="$2" url="$3" kind="$4" d threads
  d=$(gh_ pr view "$num" -R "$repo" --json \
      title,state,isDraft,mergeable,mergeStateStatus,reviewDecision,labels,createdAt,updatedAt,additions,deletions,comments,reviews,statusCheckRollup \
      2>/dev/null) || { echo "== $kind $repo#$num =="; echo "ERROR: could not read this pull request"; echo; return; }

  # Inline review comments. gh pr view does not return these, and this is
  # exactly where a maintainer question goes unseen.
  threads=$(gh_ api "repos/$repo/pulls/$num/comments" --paginate 2>/dev/null) || threads='[]'
  [ -n "$threads" ] || threads='[]'

  echo "== $kind $repo#$num =="
  echo "url: $url"
  echo "kind: $kind"
  echo "$d" | jq -r "$JQ_BOT
    \"title: \(.title)\",
    \"state: \(.state)\(if .isDraft then \" (DRAFT)\" else \"\" end)  size: +\(.additions)/-\(.deletions)\",
    \"merge: \(.mergeable) / \(.mergeStateStatus)  reviewDecision: \(if .reviewDecision == \"\" then \"none\" else .reviewDecision end)\",
    \"labels: \(if (.labels|length)==0 then \"-\" else ([.labels[].name]|join(\", \")) end)\",
    \"checks: \(if (.statusCheckRollup|length)==0 then \"none\" else ([.statusCheckRollup[]|\"\(.name)=\(.conclusion // .status)\"]|join(\" \")) end)\",
    \"reviews_human: \(([.reviews[]|select((.author.login|isbot)|not)|\"\(.author.login):\(.state)\"]|unique|join(\" \")) as \$h | if \$h==\"\" then \"NONE\" else \$h end)\",
    \"reviews_bot: \(([.reviews[]|select(.author.login|isbot)|\"\(.author.login):\(.state)\"]|unique|join(\" \")) as \$b | if \$b==\"\" then \"none\" else \$b end)\",
    \"commenters_human: \(([.comments[]|select((.author.login|isbot)|not)|.author.login]|unique|join(\" \")) as \$c | if \$c==\"\" then \"NONE\" else \$c end)\",
    \"last_comment: \(if (.comments|length)==0 then \"none\" else \"\(.comments[-1].author.login) on \(.comments[-1].createdAt[0:10])\" end)\",
    \"created: \(.createdAt[0:10])  updated: \(.updatedAt[0:10])\"
  " 2>/dev/null

  echo "$threads" | jq -r "$JQ_BOT
    (map(select((.user.login|isbot)|not))) as \$h
    | \"thread_count: \(length)  by_humans: \(\$h|length)\",
      \"thread_humans: \((\$h|map(.user.login)|unique|join(\" \")) as \$n | if \$n==\"\" then \"NONE\" else \$n end)\",
      \"last_thread: \(if (\$h|length)==0 then \"none\" else (\$h|sort_by(.created_at)|last) as \$l | \"\(\$l.user.login) on \(\$l.created_at[0:10]) in \(\$l.path // \"?\"): \(\$l.body|gsub(\"\\\\s+\";\" \")|.[0:160])\" end)\"
  " 2>/dev/null

  local created updated idle
  created=$(echo "$d" | jq -r .createdAt); updated=$(echo "$d" | jq -r .updatedAt)
  idle=$(age_days "$updated")
  echo "age_days: $(age_days "$created")  idle_days: $idle"
  if [ "$idle" != "?" ] && [ "$idle" -ge "$STALE_DAYS" ] 2>/dev/null; then
    echo "stale: yes"
  else
    echo "stale: no"
  fi

  emit_change "$kind:$repo#$num" \
    "$updated|$(echo "$d" | jq -r '.reviewDecision')|$(echo "$d" | jq -r '[.statusCheckRollup[]?|(.conclusion // .status)]|join(",")')|$(echo "$d" | jq -r '.comments|length')|$(echo "$threads" | jq -r 'length')"
  echo
}

for url in $PR_URLS;     do read -r r n <<<"$(split_url "$url")"; pr_block "$r" "$n" "$url" "PR"; done
for url in $REVIEW_URLS; do
  case " $PR_URLS " in *" $url "*) continue;; esac   # already shown as his own PR
  read -r r n <<<"$(split_url "$url")"; pr_block "$r" "$n" "$url" "REVIEW-REQUEST"
done

for url in $ISSUE_URLS; do
  case "$url" in *"/pull/"*) continue;; esac
  read -r repo num <<<"$(split_url "$url")"
  d=$(gh_ issue view "$num" -R "$repo" --json \
      title,state,stateReason,labels,assignees,createdAt,updatedAt,comments \
      2>/dev/null) || { echo "== ISSUE $repo#$num =="; echo "ERROR: could not read this issue"; echo; continue; }

  echo "== ISSUE $repo#$num =="
  echo "url: $url"
  echo "kind: ISSUE"
  echo "$d" | jq -r "$JQ_BOT
    \"title: \(.title)\",
    \"state: \(.state)\(if (.stateReason // \"\") == \"\" then \"\" else \" (\(.stateReason))\" end)\",
    \"labels: \(if (.labels|length)==0 then \"-\" else ([.labels[].name]|join(\", \")) end)\",
    \"assignees: \(if (.assignees|length)==0 then \"none\" else ([.assignees[].login]|join(\" \")) end)\",
    \"commenters_human: \(([.comments[]|select((.author.login|isbot)|not)|.author.login]|unique|join(\" \")) as \$c | if \$c==\"\" then \"NONE\" else \$c end)\",
    \"last_comment: \(if (.comments|length)==0 then \"none\" else \"\(.comments[-1].author.login) on \(.comments[-1].createdAt[0:10])\" end)\",
    \"claim_signals: \(([.comments[]|select(.body|test(\"(?i)(i.?(ll| will|.?d like to) (work|take|implement)|working on (this|it)|going ahead with|picking (this|it) up|i.?m on it|taking (this|it)|i have (the|a) fix|fix ready|will (open|send|submit|link)( a| the)? pr|assign (this )?to me)\"))|.author.login]|unique|join(\" \")) as \$k | if \$k==\"\" then \"none\" else \$k end)\",
    \"created: \(.createdAt[0:10])  updated: \(.updatedAt[0:10])\"
  " 2>/dev/null

  updated=$(echo "$d" | jq -r .updatedAt)
  idle=$(age_days "$updated")
  echo "age_days: $(age_days "$(echo "$d" | jq -r .createdAt)")  idle_days: $idle"
  if [ "$idle" != "?" ] && [ "$idle" -ge "$STALE_DAYS" ] 2>/dev/null; then
    echo "stale: yes"
  else
    echo "stale: no"
  fi
  emit_change "ISSUE:$repo#$num" \
    "$updated|$(echo "$d" | jq -r .state)|$(echo "$d" | jq -r '.comments|length')"
  echo
done

npr=$(echo "$PR_URLS"     | grep -c . || true)
nis=$(echo "$ISSUE_URLS"  | grep -c . || true)
nrr=$(echo "$REVIEW_URLS" | grep -c . || true)
echo "totals: $npr pull requests, $nis issues, $nrr review requests"

jq -Rn '[inputs | split("\t") | {(.[0]): .[1]}] | add // {}' < "$NEWSTATE" > "$STATE.tmp" \
  && mv "$STATE.tmp" "$STATE"
