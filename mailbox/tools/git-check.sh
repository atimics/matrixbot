#!/bin/bash
# Git awareness — check status across all key repos.
# Run from the mailbox directory. Output goes to stdout for Mirquo to read.

REPOS=(
  "/Users/ratimics/develop/ratichat-local"
  "/Users/ratimics/develop/app-moonbridge"
  "/Users/ratimics/develop/app-sector-one-local"
  "/Users/ratimics/develop/signal"
)

echo "=== GIT STATUS $(date +%H:%M) ==="
for repo in "${REPOS[@]}"; do
  name=$(basename "$repo")
  if [ -d "$repo/.git" ]; then
    cd "$repo" || continue
    branch=$(git branch --show-current 2>/dev/null)
    ahead=$(git rev-list --count origin/"$branch"..HEAD 2>/dev/null || echo "?")
    dirty=$(git status --porcelain 2>/dev/null | wc -l | tr -d ' ')
    echo ""
    echo "--- $name ($branch) ---"
    if [ "$ahead" != "0" ] && [ "$ahead" != "?" ]; then
      echo "  UNPUSHED: $ahead commits ahead of origin"
    fi
    if [ "$dirty" != "0" ]; then
      echo "  DIRTY: $dirty uncommitted files"
    fi
    echo "  Recent commits:"
    git log --oneline -3 2>/dev/null | sed 's/^/    /'
  else
    echo ""
    echo "--- $name ---"
    echo "  (no git repo)"
  fi
done
echo ""
echo "=== END ==="
