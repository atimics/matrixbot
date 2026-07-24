#!/bin/bash
# Git awareness — check status across all key repos.
# Run from the mailbox directory. Output goes to stdout for Mirquo to read.

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
RATICHAT_REPO="$(cd -- "$SCRIPT_DIR/../.." && pwd)"
WORKSPACE_ROOT="${RATICHAT_WORKSPACE_ROOT:-$(dirname -- "$RATICHAT_REPO")}"
REPOS=(
  "$RATICHAT_REPO"
  "$WORKSPACE_ROOT/app-moonbridge"
  "$WORKSPACE_ROOT/app-sector-one-local"
  "$WORKSPACE_ROOT/signal"
)

echo "=== GIT STATUS $(date +%H:%M) ==="
for repo in "${REPOS[@]}"; do
  name=$(basename "$repo")
  if [ -d "$repo/.git" ]; then
    branch=$(git -C "$repo" branch --show-current 2>/dev/null)
    ahead=$(git -C "$repo" rev-list --count origin/"$branch"..HEAD 2>/dev/null || echo "?")
    dirty=$(git -C "$repo" status --porcelain 2>/dev/null | wc -l | tr -d ' ')
    echo ""
    echo "--- $name ($branch) ---"
    if [ "$ahead" != "0" ] && [ "$ahead" != "?" ]; then
      echo "  UNPUSHED: $ahead commits ahead of origin"
    fi
    if [ "$dirty" != "0" ]; then
      echo "  DIRTY: $dirty uncommitted files"
    fi
    echo "  Recent commits:"
    git -C "$repo" log --oneline -3 2>/dev/null | sed 's/^/    /'
  else
    echo ""
    echo "--- $name ---"
    echo "  (no git repo)"
  fi
done
echo ""
echo "=== END ==="
