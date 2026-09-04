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

# This foundation supports Farcaster observation. A later reviewed change can
# enable outbound actions by removing this guard and adding a signer secret.
unset FARCASTER_BOT_SIGNER_UUID

exec python -m chatbot.main_with_ui
