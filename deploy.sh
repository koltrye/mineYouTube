#!/usr/bin/env bash
set -euo pipefail
if [ ! -f .env ]; then
  umask 077
  printf 'JWT_SECRET=%s\nDB_PASSWORD=%s\nMINIO_ACCESS_KEY=%s\nMINIO_SECRET_KEY=%s\n' \
    "$(openssl rand -hex 32)" "$(openssl rand -hex 24)" \
    "$(openssl rand -hex 16)" "$(openssl rand -hex 32)" > .env
fi
docker compose up --build -d
docker compose run --rm seed
echo "MineTube is running at http://localhost:8000"
