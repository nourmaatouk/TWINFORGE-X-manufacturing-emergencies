#!/bin/bash
set -e

echo "Setting up TWINFORGE..."

if [ ! -f .env ]; then
    cp .env.example .env
    echo "Created .env from .env.example - please update with real values"
fi

echo "Setup complete."
