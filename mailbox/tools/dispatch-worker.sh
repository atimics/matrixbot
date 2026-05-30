#!/bin/bash
# Dispatch a coding worker to a repo.
# Usage: dispatch-worker.sh <task-id> <repo> "<prompt>"
# Workers write results to mailbox/workers/<task-id>/result.json

TASK_ID="$1"
REPO_NAME="$2"
PROMPT="$3"

if [ -z "$TASK_ID" ] || [ -z "$REPO_NAME" ] || [ -z "$PROMPT" ]; then
  echo '{"error": "usage: dispatch-worker.sh <task-id> <repo> \"<prompt>\""}'
  exit 1
fi

WORKER_DIR="mailbox/workers/$TASK_ID"
mkdir -p "$WORKER_DIR"

# Map repo name to path
case "$REPO_NAME" in
  ratichat)    REPO_PATH="/Users/ratimics/develop/ratichat-local" ;;
  moonbridge)  REPO_PATH="/Users/ratimics/develop/app-moonbridge" ;;
  sector-one)  REPO_PATH="/Users/ratimics/develop/app-sector-one-local" ;;
  signal)      REPO_PATH="/Users/ratimics/develop/signal" ;;
  *)           REPO_PATH="/Users/ratimics/develop/$REPO_NAME" ;;
esac

# Write task manifest
cat > "$WORKER_DIR/task.json" << EOF
{"task_id": "$TASK_ID", "repo": "$REPO_NAME", "prompt": "$PROMPT", "started": "$(date -u +%Y-%m-%dT%H:%M:%SZ)", "status": "dispatched"}
EOF

# Spawn the worker (background, detached)
nohup codex exec \
  --dangerously-bypass-approvals-and-sandbox \
  -C "$REPO_PATH" \
  "You are a coding worker dispatched by Mirquo. Task: $PROMPT
   When done, write your result to $PWD/$WORKER_DIR/result.json
   as {\"status\": \"done\", \"summary\": \"<what you did>\", \"files_changed\": [...]}
   Then commit your changes." \
  > "$WORKER_DIR/worker.log" 2>&1 &

echo "{\"task_id\": \"$TASK_ID\", \"status\": \"dispatched\", \"repo\": \"$REPO_NAME\", \"worker_dir\": \"$WORKER_DIR\"}"
