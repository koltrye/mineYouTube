#!/usr/bin/env bash
set -euo pipefail
docker compose up --build -d
docker compose run --rm seed
echo "MineTube is running at http://localhost:8000"
