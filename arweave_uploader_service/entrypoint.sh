#!/bin/sh

# Exit immediately if a command exits with a non-zero status.
set -e

# Define the wallet file path, ensuring it matches the path in your Python app.
# Using an environment variable is best practice.
WALLET_FILE=${ARWEAVE_WALLET_FILE_PATH:-"/data/arweave_wallet.json"}

# Check if the wallet file does NOT exist.
if [ ! -f "$WALLET_FILE" ]; then
  echo "Wallet file not found at $WALLET_FILE. Generating new wallet..."
  
  # Ensure the directory exists
  mkdir -p $(dirname "$WALLET_FILE")
  
  # Use ardrive-cli to generate the wallet and save it to the specified path.
  # The --key-file flag tells it where to save the JWK.
  ardrive-cli create-wallet --wallet-file "$WALLET_FILE"
  
  echo "✅ New Arweave wallet successfully created at $WALLET_FILE"
  echo "🔑 Please back up this file securely and fund the new wallet address."
else
  echo "✅ Existing Arweave wallet found at $WALLET_FILE"
fi

# Execute the command passed to this script (i.e., the CMD from the Dockerfile)
# This will start the uvicorn server.
exec "$@"
