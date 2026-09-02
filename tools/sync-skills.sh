#!/usr/bin/env bash
# sync-skills.sh -- copy the shareable skill set into this repo, and refuse to do it
# if anything in them names something that must not leave.
#
#   tools/sync-skills.sh          # check + sync
#   tools/sync-skills.sh --check  # check only, no writes  (use this in CI)
#
# WHY A GATE RATHER THAN A RULE
#   "Remember not to publish the engine internals" is not a control; it is a hope that
#   holds until the day someone is tired. These skills are edited in ~/.claude/skills
#   where nothing is watching, and copied here where everything is public. The copy is
#   the moment to check, so the check lives in the copy.
set -uo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
SRC="${SKILLS_SRC:-$HOME/.claude/skills}"
DEST="$REPO/skills"
CHECK_ONLY=0
[ "${1:-}" = "--check" ] && CHECK_ONLY=1

# The shareable set: platform knowledge, measurement method, and workflow.
# Everything here is about how to work on the hardware -- none of it is the engine.
SKILLS=(
  rt-budget-proof
  audio-gain-staging
  elk-midi-routing
  elk-stomp-io
  elk-serial-console
  midi-controller-profile
)

# Things that must never appear in a public copy. Each line: <regex>@@<why>
# NOTE the '@@' delimiter -- '|' cannot be used here because the patterns themselves
# contain alternations, and splitting on '|' silently truncated them to invalid regex.
# Engine internals are the differentiator; the voicing doctrine IS the product.
#
# WHY THE LIST IS NOT IN THIS FILE
#   The patterns name the exact symbols and phrases worth protecting. A list like that,
#   sitting in a public repo next to the gate, is a map to everything the gate exists to
#   keep back -- it leaks by being read, without a single skill ever being wrong. So the
#   list lives outside the repo and the mechanism stays in it. See deny-patterns.example.
DENY_FILE="${DENY_FILE:-$HOME/.thiri/skills-deny.txt}"

# Fail CLOSED. A gate whose rules are missing must refuse, not wave everything through --
# the same reason an unrunnable pattern below is an error rather than a skipped line.
if [ ! -r "$DENY_FILE" ]; then
  echo "!! no deny list at $DENY_FILE (set DENY_FILE=... to point elsewhere)"
  echo "   REFUSING TO SYNC -- a gate with no rules is not a gate."
  echo "   See deny-patterns.example for the format."
  exit 1
fi

DENY=()
while IFS= read -r line; do
  case "$line" in ''|'#'*) continue ;; esac   # skip blanks and comments
  DENY+=("$line")
done < "$DENY_FILE"

if [ "${#DENY[@]}" -eq 0 ]; then
  echo "!! deny list $DENY_FILE has no patterns -- REFUSING TO SYNC."
  exit 1
fi

fail=0
scan() {                                  # scan <dir-or-file>
  local target="$1" rule pat why hits
  for rule in "${DENY[@]}"; do
    pat="${rule%%@@*}"; why="${rule#*@@}"
    hits=$(grep -rIinE -- "$pat" "$target" 2>/dev/null); rc=$?
    if [ "$rc" -gt 1 ]; then
      echo "!! BAD PATTERN (grep error $rc): /$pat/ -- a rule that cannot run is not a rule"
      fail=$((fail+1)); continue
    fi
    if [ -n "$hits" ]; then
      echo "!! BLOCKED ($why): /$pat/"
      echo "$hits" | sed 's/^/     /'
      fail=$((fail+1))
    fi
  done
}

echo "== checking shareable skills in $SRC"
echo "== ${#DENY[@]} deny patterns loaded from $DENY_FILE"
for s in "${SKILLS[@]}"; do
  if [ ! -d "$SRC/$s" ]; then echo "!! missing skill: $s"; fail=$((fail+1)); continue; fi
  before=$fail
  scan "$SRC/$s"
  [ "$fail" -eq "$before" ] && echo "   ok  $s" || echo "   FAIL $s"
done

if [ "$fail" -ne 0 ]; then
  echo
  echo "REFUSING TO SYNC. Remove the flagged text, or if it is a false positive,"
  echo "narrow the pattern in tools/sync-skills.sh -- do not delete the rule."
  exit 1
fi

if [ "$CHECK_ONLY" -eq 1 ]; then echo "== check only, nothing written"; exit 0; fi

mkdir -p "$DEST"
for s in "${SKILLS[@]}"; do
  rm -rf "${DEST:?}/$s"
  cp -R "$SRC/$s" "$DEST/$s"
done
echo "== synced ${#SKILLS[@]} skills -> $DEST"
