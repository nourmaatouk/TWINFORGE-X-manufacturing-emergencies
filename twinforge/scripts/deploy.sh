#!/bin/bash
set -e

echo "Deploying TWINFORGE..."
docker-compose build
docker-compose up -d
echo "Deployment complete."
