#!/bin/bash
set -e

echo "Generating secrets..."

generate_secret() {
    python3 -c "import secrets; print(secrets.token_hex(32))"
}

echo "POSTGRES_PASSWORD=$(generate_secret)"
echo "INFLUXDB_PASSWORD=$(generate_secret)"
echo "VAULT_ROOT_TOKEN=$(generate_secret)"
echo "MESSAGE_SIGNING_KEY=$(generate_secret)"
echo "GRAFANA_PASSWORD=$(generate_secret)"

echo "Done. Copy the above values into your .env file."
