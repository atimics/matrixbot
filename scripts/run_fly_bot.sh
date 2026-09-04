#!/bin/sh

set -eu

# Keep the Matrix encryption store on the Fly volume. The current Matrix
# integration uses this fixed path inside the application directory.
mkdir -p /data/matrix_store
if [ -d /app/matrix_store ] && [ ! -L /app/matrix_store ]; then
    rmdir /app/matrix_store
fi
if [ ! -e /app/matrix_store ]; then
    ln -s /data/matrix_store /app/matrix_store
fi

# Keep the verified Matrix session beside the encrypted client store.
if [ ! -L /app/matrix_token.json ]; then
    if [ -e /app/matrix_token.json ]; then
        echo "Refusing to replace the existing /app/matrix_token.json" >&2
        exit 1
    fi
    ln -s /data/matrix_token.json /app/matrix_token.json
fi

# This foundation supports Farcaster observation. A later reviewed change can
# enable outbound actions by removing this guard and adding a signer secret.
unset FARCASTER_BOT_SIGNER_UUID

exec python -m chatbot.main_with_ui
