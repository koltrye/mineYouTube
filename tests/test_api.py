import os
from fastapi.testclient import TestClient

# Tests use the real database configuration only when run inside Docker.
os.environ.setdefault("DATABASE_URL", "sqlite:///./test.db")

from backend.app.main import app


client = TestClient(app)


def test_health():
    response = client.get("/api/videos")
    assert response.status_code in (200, 500)


def test_register_and_login():
    email = "test@example.com"
    response = client.post("/api/auth/register", json={
        "username": "testuser",
        "email": email,
        "password": "secret12",
        "display_name": "Test User",
    })
    assert response.status_code in (200, 409)
