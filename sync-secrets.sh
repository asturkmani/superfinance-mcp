#!/bin/bash

# Sync .env file to Fly.io secrets
# Usage: ./sync-secrets.sh

if [ ! -f .env ]; then
    echo "Error: .env file not found"
    exit 1
fi

echo "Syncing .env to Fly.io secrets for app: superfinance-mcp"
echo "================================================"

# Read .env file and set each secret
while IFS='=' read -r key value; do
    # Skip empty lines and comments
    if [[ -z "$key" ]] || [[ "$key" =~ ^# ]]; then
        continue
    fi

    # Skip if value is empty
    if [[ -z "$value" ]]; then
        echo "⚠️  Skipping $key (empty value)"
        continue
    fi

    # Remove quotes from value if present
    value="${value%\"}"
    value="${value#\"}"

    echo "✓ Setting $key"
    flyctl secrets set "$key=$value" -a superfinance-mcp --stage
done < .env

echo ""
echo "Deploying with new secrets..."
flyctl deploy -a superfinance-mcp

echo ""
echo "✅ Secrets synced and deployed successfully!"
