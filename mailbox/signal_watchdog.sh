#!/bin/bash
# Auto-restarts the Signal server when it dies
PORT=9091
LOG=/private/tmp/signal-server-bots.log
BINARY=/Users/ratimics/develop/signal/build/signal_server
WORKDIR=/Users/ratimics/develop/signal

while true; do
    if ! lsof -i :$PORT -sTCP:LISTEN >/dev/null 2>&1; then
        echo "[watchdog] $(date): server down, restarting..." >> /tmp/signal-watchdog.log
        cd "$WORKDIR"
        SIGNAL_PERSISTENCE_MODE=ephemeral \
        PORT=$PORT \
        SIGNAL_API_TOKEN="mirquo-sector-one-token" \
        SIGNAL_BOT_BRAIN_MODE=autopilot \
        SIGNAL_BOT_PLAYERS=31 \
        SIGNAL_FRONTIER_VIRTUAL_PILOTS=1000 \
        nohup "$BINARY" > "$LOG" 2>&1 &
        echo "[watchdog] $(date): started PID $!" >> /tmp/signal-watchdog.log
    fi
    sleep 30
done
