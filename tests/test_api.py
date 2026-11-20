import os
import sys
import tempfile
import uuid
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

os.environ["DATABASE_URL"] = f"sqlite:///{os.path.join(tempfile.gettempdir(), 'minetube-' + uuid.uuid4().hex + '.db')}"
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend")))

from app import main
from app.auth import create_stream_ticket, create_token, hash_password
from app.database import Base, SessionLocal, engine
from app.models import Comment, User, Video, VideoPermission, VideoStatus, Visibility


@pytest.fixture
def client():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with TestClient(main.app) as test_client:
        yield test_client
    Base.metadata.drop_all(bind=engine)


def test_frontend_and_swagger_are_served(client):
    homepage = client.get("/")
    assert homepage.status_code == 200
    assert "MineTube" in homepage.text
    assert client.get("/docs").status_code == 200


def create_user(username):
    db = SessionLocal()
    user = User(
        username=username,
        email=f"{username}@example.com",
        password_hash=hash_password("strongpass123"),
        display_name=username.title(),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    db.close()
    return user.id


def create_video(owner_id, visibility=Visibility.public):
    db = SessionLocal()
    video = Video(
        owner_id=owner_id,
        title="Test video",
        description="A test",
        object_key="videos/test.mp4",
        status=VideoStatus.ready,
        visibility=visibility,
    )
    db.add(video)
    db.commit()
    db.refresh(video)
    video_id = video.id
    db.close()
    return video_id


def test_registration_rejects_weak_password_and_creates_account(client):
    weak = client.post("/api/auth/register", json={
        "username": "newuser",
        "email": "new@example.com",
        "password": "short",
    })
    assert weak.status_code == 400

    created = client.post("/api/auth/register", json={
        "username": "newuser",
        "email": "new@example.com",
        "password": "strongpass123",
    })
    assert created.status_code == 200
    assert created.json()["user"]["username"] == "newuser"

    login = client.post("/api/auth/login", json={
        "email": "new@example.com",
        "password": "strongpass123",
    })
    assert login.status_code == 200
    assert login.json()["token"]


def test_private_video_and_comments_require_owner_permission(client, monkeypatch):
    owner_id = create_user("owner")
    viewer_id = create_user("viewer")
    video_id = create_video(owner_id, Visibility.private)
    db = SessionLocal()
    db.add(Comment(video_id=video_id, user_id=owner_id, text="Private comment"))
    db.commit()
    db.close()

    assert client.get(f"/api/videos/{video_id}").status_code == 404
    assert client.get(f"/api/videos/{video_id}/comments").status_code == 404
    assert client.post(f"/api/videos/{video_id}/view").status_code == 404
    ticket = create_stream_ticket(video_id, None)
    assert client.get(f"/api/videos/{video_id}/stream?ticket={ticket}").status_code == 404
    viewer_token = create_token(viewer_id)
    assert client.get(
        f"/api/videos/{video_id}",
        headers={"Authorization": f"Bearer {viewer_token}"},
    ).status_code == 404

    db = SessionLocal()
    db.add(VideoPermission(video_id=video_id, user_id=viewer_id))
    db.commit()
    db.close()
    authorized = client.get(
        f"/api/videos/{video_id}",
        headers={"Authorization": f"Bearer {viewer_token}"},
    )
    assert authorized.status_code == 200
    comments = client.get(
        f"/api/videos/{video_id}/comments",
        headers={"Authorization": f"Bearer {viewer_token}"},
    )
    assert comments.status_code == 200
    assert comments.json()[0]["text"] == "Private comment"

    class FakeBody:
        def iter_chunks(self, chunk_size):
            yield b"cdef"

        def close(self):
            pass

    monkeypatch.setattr(main, "object_size", lambda key: 10)
    monkeypatch.setattr(main, "get_object", lambda key, range_header: {
        "Body": FakeBody(),
        "ContentLength": 4,
        "ContentType": "video/mp4",
    })
    stream_url = authorized.json()["video_url"]
    streamed = client.get(stream_url, headers={"Range": "bytes=2-5"})
    assert streamed.status_code == 206
    assert streamed.headers["content-range"] == "bytes 2-5/10"
    assert streamed.content == b"cdef"


def test_playlists_can_be_created_and_prevent_duplicate_videos(client):
    owner_id = create_user("creator")
    video_id = create_video(owner_id)
    token = create_token(owner_id)
    headers = {"Authorization": f"Bearer {token}"}

    created = client.post(
        "/api/playlists",
        headers=headers,
        json={"title": "Favorites", "description": "Good videos"},
    )
    assert created.status_code == 200
    playlist_id = created.json()["id"]

    added = client.post(
        f"/api/playlists/{playlist_id}/videos",
        headers=headers,
        json={"video_id": video_id},
    )
    assert added.status_code == 200
    assert added.json()["video_count"] == 1
    duplicate = client.post(
        f"/api/playlists/{playlist_id}/videos",
        headers=headers,
        json={"video_id": video_id},
    )
    assert duplicate.status_code == 409

    public_playlist = client.get(f"/api/playlists/{playlist_id}")
    assert public_playlist.status_code == 200
    assert public_playlist.json()["videos"][0]["id"] == video_id


def test_registration_upload_playback_like_and_comment(client, monkeypatch):
    registration = client.post("/api/auth/register", json={
        "username": "uploader",
        "email": "uploader@example.com",
        "password": "strongpass123",
    })
    assert registration.status_code == 200
    headers = {"Authorization": f"Bearer {registration.json()['token']}"}
    stored_objects = {}

    def fake_subprocess(args, **kwargs):
        if args[0] == "ffprobe":
            return SimpleNamespace(stdout="3.5")
        with open(args[-1], "wb") as output:
            output.write(b"processed-video")
        return SimpleNamespace(stdout="", stderr="")

    monkeypatch.setattr(main.subprocess, "run", fake_subprocess)
    def fake_put_object(key, data, content_type):
        stored_objects[key] = (data.read() if hasattr(data, "read") else data, content_type)

    monkeypatch.setattr(main, "put_object", fake_put_object)
    uploaded = client.post(
        "/api/videos/upload",
        headers=headers,
        data={"title": "First upload", "description": "Smoke test", "visibility": "public"},
        files={"file": ("sample.mp4", b"source-video", "video/mp4")},
    )
    assert uploaded.status_code == 200
    video = uploaded.json()
    assert video["title"] == "First upload"
    assert video["duration_seconds"] == 3
    assert len(stored_objects) == 2
    video_id = video["id"]

    fetched = client.get(f"/api/videos/{video_id}", headers=headers)
    assert fetched.status_code == 200
    assert fetched.json()["views"] == 1
    assert "ticket=" in fetched.json()["video_url"]

    liked = client.post(f"/api/videos/{video_id}/like", headers=headers)
    assert liked.json() == {"liked": True, "likes": 1}
    comment = client.post(
        f"/api/videos/{video_id}/comments",
        headers=headers,
        json={"text": "Looks good"},
    )
    assert comment.status_code == 200
    assert comment.json()["text"] == "Looks good"
    assert client.get(f"/api/videos/{video_id}/comments").json()[0]["text"] == "Looks good"
