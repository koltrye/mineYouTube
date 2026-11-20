# mineYouTube

A YouTube-style video platform built with FastAPI, PostgreSQL, MinIO object storage, and a vanilla JavaScript frontend.

## Deploy on Ubuntu

Requirements: Docker Engine and Docker Compose.

```bash
bash deploy.sh
```

Open `http://localhost:8000`. Swagger is at `http://localhost:8000/docs`.

## Demo accounts

| Account | Email | Password | Role |
|---|---|---|---|
| Demo Creator | demo@minetube.local | demo123 | user |
| Alice Travels | alice@minetube.local | demo123 | user |
| Moderator | moderator@minetube.local | demo123 | moderator |
| Administrator | admin@minetube.local | demo123 | admin |

The seed process creates demo videos, comments, users, and a private-capable MinIO bucket.

## Run tests

```bash
docker compose run --rm app pytest -q /app/tests
```

## Services

- App and frontend: port 8000
- PostgreSQL: internal port 5432
- MinIO API: port 9000
- MinIO console: port 9001

Set `JWT_SECRET` to a strong random value in `docker-compose.yml` or environment configuration for production.
