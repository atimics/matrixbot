#!/bin/sh
set -eu

if [ "$(id -u)" = "0" ]; then
    if [ -d /data ]; then
        chown chatbot:chatbot /data
    fi
    exec gosu chatbot "$@"
fi

exec "$@"
