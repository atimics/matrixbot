#!/bin/bash
# Check status of all dispatched workers.
# Outputs JSON array of worker statuses.

echo "["
first=true
for dir in mailbox/workers/*/; do
  [ -d "$dir" ] || continue
  task_id=$(basename "$dir")
  task_file="$dir/task.json"
  result_file="$dir/result.json"
  
  [ "$first" = true ] || echo ","
  first=false
  
  if [ -f "$result_file" ]; then
    # Worker completed
    echo -n "{\"task_id\": \"$task_id\", \"status\": \"done\", "
    cat "$result_file" | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'\"summary\": \"{d.get(\"summary\",\"\")}\"')" 2>/dev/null || echo '"summary": ""'
    echo -n "}"
  elif [ -f "$task_file" ]; then
    # Worker running
    started=$(python3 -c "import json; print(json.load(open('$task_file')).get('started',''))" 2>/dev/null)
    echo -n "{\"task_id\": \"$task_id\", \"status\": \"running\", \"started\": \"$started\"}"
  fi
done
echo ""
echo "]"
