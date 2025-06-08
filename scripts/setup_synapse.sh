#!/bin/sh
set -e

# This script automates the initial setup for a Synapse Matrix server.

# Path to the Synapse data directory within the container
SYNAPSE_DATA_DIR="/data"
CONFIG_FILE="$SYNAPSE_DATA_DIR/homeserver.yaml"

# Check if the config file already exists
if [ -f "$CONFIG_FILE" ]; then
    echo "Configuration file already exists. Skipping generation."
    exit 0
fi

# Generate a new configuration file
# Note: These environment variables must be set in the docker-compose file
/start.py generate

# Modify the generated configuration to use PostgreSQL
# We use yq, a command-line YAML processor, for safe and reliable YAML editing.
# First, install yq
apk add --no-cache yq

# Now, modify the config
yq -i '.database.name = "psycopg2"' "$CONFIG_FILE"
yq -i '.database.args.user = "synapse"' "$CONFIG_FILE"
yq -i '.database.args.password = "${SYNAPSE_DB_PASSWORD}"' "$CONFIG_FILE"
yq -i '.database.args.database = "synapse"' "$CONFIG_FILE"
yq -i '.database.args.host = "postgres"' "$CONFIG_FILE"
yq -i '.database.args.cp_min = 5' "$CONFIG_FILE"
yq -i '.database.args.cp_max = 10' "$CONFIG_FILE"

# Disable TLS for local communication
yq -i '.listeners[0].tls = false' "$CONFIG_FILE"

# Enable registration without a captcha
yq -i '.enable_registration = true' "$CONFIG_FILE"
yq -i 'del(.registrations_require_3pid)' "$CONFIG_FILE"

echo "Synapse configuration complete."
