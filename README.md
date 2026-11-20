# mineYouTube

A YouTube-style video platform built with FastAPI, PostgreSQL, MinIO object storage, and a vanilla JavaScript frontend.

## Deploy on Ubuntu

Requirements: Docker Engine and Docker Compose.

```bash
bash deploy.sh
```

The deploy script creates a local `.env` with random database, JWT, and object-storage credentials, starts the services, then loads demo data. Open `http://localhost:8000`; Swagger is at `http://localhost:8000/docs`.

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
bash deploy.sh
docker compose run --rm app pytest -q /app/tests
```

## Services

- App and frontend: port 8000
- PostgreSQL and MinIO are private to the Compose network; video playback is streamed through the app.

The demo credentials are for local evaluation only. Do not expose them as production accounts.
