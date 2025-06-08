#!/bin/bash

# Exit immediately if a command exits with a non-zero status.
set -e

# Define the wallet file path, ensuring it matches the path in your Python app.
# Using an environment variable is best practice.
WALLET_FILE=${ARWEAVE_WALLET_FILE_PATH:-"/data/arweave_wallet.json"}

echo "🚀 Starting Arweave Uploader Service..."
echo "📂 Wallet file path: $WALLET_FILE"

# Check if the wallet file does NOT exist.
if [ ! -f "$WALLET_FILE" ]; then
  echo "🔐 Wallet file not found at $WALLET_FILE. Generating new wallet..."
  
  # Ensure the directory exists
  mkdir -p $(dirname "$WALLET_FILE")
  
  # Check if ardrive-cli is available
  if ! command -v ardrive-cli > /dev/null; then
    echo "❌ ERROR: ardrive-cli not found. Cannot generate wallet."
    exit 1
  fi
  
  # Use ardrive-cli to generate the wallet and save it to the specified path.
  # The path is a direct argument to the `wallet-create` command.
  echo "🔧 Generating wallet using ardrive-cli..."
  if ardrive-cli wallet-create "$WALLET_FILE"; then
    echo "✅ New Arweave wallet successfully created at $WALLET_FILE"
    
    # Verify the wallet file was created and is valid JSON
    if [ -f "$WALLET_FILE" ] && [ -s "$WALLET_FILE" ]; then
      # Quick JSON validation
      if ! python3 -m json.tool "$WALLET_FILE" > /dev/null 2>&1; then
        echo "❌ ERROR: Generated wallet file is not valid JSON"
        exit 1
      fi
      echo "✅ Wallet file validation passed"
      
      # Extract and display the wallet address for easy access
      # This requires arweave-python, but we'll make it optional
      echo "🔑 New wallet created! Please back up this file securely."
      echo "💰 Remember to fund the wallet address to enable uploads."
    else
      echo "❌ ERROR: Wallet file was not created properly"
      exit 1
    fi
  else
    echo "❌ ERROR: Failed to generate wallet using ardrive-cli"
    exit 1
  fi
else
  echo "✅ Existing Arweave wallet found at $WALLET_FILE"
  
  # Verify existing wallet file is valid
  if ! python3 -m json.tool "$WALLET_FILE" > /dev/null 2>&1; then
    echo "❌ ERROR: Existing wallet file is corrupted (invalid JSON)"
    exit 1
  fi
  echo "✅ Existing wallet file validation passed"
fi

# Set proper permissions on the wallet file (readable only by owner)
chmod 600 "$WALLET_FILE"

echo "🎯 Wallet setup complete. Starting Python application..."

# Execute the command passed to this script (i.e., the CMD from the Dockerfile)
# This will start the uvicorn server.
exec "$@"
