from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Form, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel
from sqlalchemy import or_, func
from sqlalchemy.orm import Session
import os
import subprocess
import tempfile
import secrets
import re

from .database import engine, Base, get_db
from .models import (
    Comment, Playlist, PlaylistVideo, Report, Role, Subscription, User, Video, VideoLike,
    VideoPermission, Visibility, VideoStatus,
)
from .auth import create_stream_ticket, create_token, get_current_user, get_optional_user, hash_password, verify_password, verify_stream_ticket
from .storage import delete_object, get_object, object_size, put_object

Base.metadata.create_all(bind=engine)

app = FastAPI(title="MineTube", version="1.0.0", docs_url="/docs")
class RegisterRequest(BaseModel):
    username: str
    email: str
    password: str
    display_name: str | None = None


class LoginRequest(BaseModel):
    email: str
    password: str


class CommentRequest(BaseModel):
    text: str


class ReportRequest(BaseModel):
    reason: str


class PermissionRequest(BaseModel):
    username: str


class PlaylistRequest(BaseModel):
    title: str
    description: str = ""
    visibility: str = "public"


class PlaylistItemRequest(BaseModel):
    video_id: int


def playlist_json(playlist: Playlist, db: Session, user: User | None):
    items = [
        serialize_video(item.video, db, user)
        for item in playlist.items
        if can_view(item.video, user, db)
    ]
    return {
        "id": playlist.id,
        "title": playlist.title,
        "description": playlist.description,
        "visibility": playlist.visibility.value,
        "owner": {"username": playlist.owner.username, "display_name": playlist.owner.display_name},
        "videos": items,
        "video_count": len(items),
    }


def can_view(video: Video, user: User | None, db: Session) -> bool:
    if video.status == VideoStatus.hidden:
        return bool(user and (user.role in (Role.admin, Role.moderator) or user.id == video.owner_id))
    if video.visibility == Visibility.public:
        return True
    if not user:
        return False
    if user.id == video.owner_id or user.role in (Role.admin, Role.moderator):
        return True
    return db.query(VideoPermission).filter_by(video_id=video.id, user_id=user.id).first() is not None


def serialize_video(video: Video, db: Session, user: User | None = None):
    likes = db.query(func.count(VideoLike.id)).filter(VideoLike.video_id == video.id).scalar()
    comments = db.query(func.count(Comment.id)).filter(Comment.video_id == video.id).scalar()
    return {
        "id": video.id,
        "title": video.title,
        "description": video.description,
        "owner": {
            "id": video.owner.id,
            "username": video.owner.username,
            "display_name": video.owner.display_name,
        },
        "visibility": video.visibility.value,
        "status": video.status.value,
        "views": video.views,
        "duration_seconds": video.duration_seconds,
        "likes": likes,
        "comments": comments,
        "created_at": video.created_at.isoformat(),
        "thumbnail_url": f"/api/videos/{video.id}/thumbnail?ticket={create_stream_ticket(video.id, user.id if user else None)}" if video.thumbnail_key else None,
        "video_url": f"/api/videos/{video.id}/stream?ticket={create_stream_ticket(video.id, user.id if user else None)}",
        "liked": bool(user and db.query(VideoLike).filter_by(video_id=video.id, user_id=user.id).first()),
    }


@app.post("/api/auth/register")
def register(payload: RegisterRequest, db: Session = Depends(get_db)):
    username = payload.username.strip()
    if len(username) < 3:
        raise HTTPException(400, "Username must be at least 3 characters")
    if len(payload.password) < 8:
        raise HTTPException(400, "Password must be at least 8 characters")
    email = payload.email.strip().lower()
    if len(email) > 255 or not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        raise HTTPException(400, "A valid email is required")
    if db.query(User).filter(or_(User.username == username, User.email == email)).first():
        raise HTTPException(409, "User already exists")
    user = User(
        username=username,
        email=email,
        password_hash=hash_password(payload.password),
        display_name=(payload.display_name or username).strip(),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return {"token": create_token(user.id), "user": {"id": user.id, "username": user.username, "display_name": user.display_name, "role": user.role.value}}


@app.post("/api/auth/login")
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == payload.email.strip().lower()).first()
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(401, "Incorrect email or password")
    return {"token": create_token(user.id), "user": {"id": user.id, "username": user.username, "display_name": user.display_name, "role": user.role.value}}


@app.get("/api/me")
def me(user: User = Depends(get_current_user)):
    return {"id": user.id, "username": user.username, "display_name": user.display_name, "role": user.role.value}


@app.get("/api/videos")
def feed(db: Session = Depends(get_db), user: User | None = Depends(get_optional_user), q: str = ""):
    query = db.query(Video).filter(Video.status == VideoStatus.ready)
    if q:
        query = query.filter(Video.title.ilike(f"%{q}%"))
    videos = query.order_by(Video.created_at.desc()).all()
    visible = [video for video in videos if can_view(video, user, db)]
    return [serialize_video(video, db, user) for video in visible]


@app.get("/api/videos/{video_id}")
def get_video(video_id: int, db: Session = Depends(get_db), user: User | None = Depends(get_optional_user)):
    video = db.get(Video, video_id)
    if not video or not can_view(video, user, db):
        raise HTTPException(404, "Video not found")
    video.views += 1
    db.commit()
    return serialize_video(video, db, user)


def authorized_stream_video(video_id: int, ticket: str, db: Session):
    video = db.get(Video, video_id)
    user_id = verify_stream_ticket(ticket, video_id)
    user = db.get(User, user_id) if user_id is not None else None
    if not video or (user_id is not None and not user) or not can_view(video, user, db):
        raise HTTPException(404, "Video not found")
    return video


@app.get("/api/videos/{video_id}/stream")
def stream_video(video_id: int, request: Request, ticket: str, db: Session = Depends(get_db)):
    video = authorized_stream_video(video_id, ticket, db)
    range_header = request.headers.get("range")
    range_start = range_end = None
    if range_header:
        try:
            unit, value = range_header.split("=", 1)
            if unit != "bytes" or "," in value:
                raise ValueError
            start_text, end_text = value.split("-", 1)
            total = object_size(video.object_key)
            if not start_text:
                suffix_length = int(end_text)
                if suffix_length <= 0:
                    raise ValueError
                range_start = max(0, total - suffix_length)
                range_end = total - 1
            else:
                range_start = int(start_text)
                range_end = min(int(end_text), total - 1) if end_text else total - 1
            if range_start < 0 or range_start >= total or range_end < range_start:
                raise ValueError
        except (ValueError, IndexError):
            total = object_size(video.object_key)
            return Response(status_code=416, headers={"Content-Range": f"bytes */{total}"})
        range_header = f"bytes={range_start}-{range_end}"

    stored = get_object(video.object_key, range_header)
    body = stored["Body"]

    def chunks():
        try:
            yield from body.iter_chunks(chunk_size=1024 * 1024)
        finally:
            body.close()

    headers = {
        "Accept-Ranges": "bytes",
        "Content-Length": str(stored["ContentLength"]),
        "Content-Type": stored.get("ContentType", "video/mp4"),
    }
    if range_start is not None:
        headers["Content-Range"] = f"bytes {range_start}-{range_end}/{total}"
    return StreamingResponse(
        chunks(),
        status_code=206 if range_start is not None else 200,
        headers=headers,
        media_type=stored.get("ContentType", "video/mp4"),
    )


@app.get("/api/videos/{video_id}/thumbnail")
def video_thumbnail(video_id: int, ticket: str, db: Session = Depends(get_db)):
    video = authorized_stream_video(video_id, ticket, db)
    if not video.thumbnail_key:
        raise HTTPException(404, "Thumbnail not found")
    stored = get_object(video.thumbnail_key)
    body = stored["Body"]
    try:
        content = body.read()
    finally:
        body.close()
    return Response(content=content, media_type=stored.get("ContentType", "image/jpeg"))


@app.post("/api/videos/{video_id}/view")
def count_view(video_id: int, db: Session = Depends(get_db), user: User | None = Depends(get_optional_user)):
    video = db.get(Video, video_id)
    if not video or not can_view(video, user, db):
        raise HTTPException(404, "Video not found")
    video.views += 1
    db.commit()
    return {"views": video.views}


@app.post("/api/videos/{video_id}/like")
def toggle_like(video_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    video = db.get(Video, video_id)
    if not video or not can_view(video, user, db):
        raise HTTPException(404, "Video not found")
    like = db.query(VideoLike).filter_by(video_id=video_id, user_id=user.id).first()
    if like:
        db.delete(like)
        liked = False
    else:
        db.add(VideoLike(video_id=video_id, user_id=user.id))
        liked = True
    db.commit()
    likes = db.query(func.count(VideoLike.id)).filter(VideoLike.video_id == video_id).scalar()
    return {"liked": liked, "likes": likes}


@app.get("/api/videos/{video_id}/comments")
def comments(video_id: int, db: Session = Depends(get_db), user: User | None = Depends(get_optional_user)):
    video = db.get(Video, video_id)
    if not video or not can_view(video, user, db):
        raise HTTPException(404, "Video not found")
    rows = db.query(Comment).filter(Comment.video_id == video_id).order_by(Comment.created_at.desc()).all()
    return [{"id": r.id, "text": r.text, "created_at": r.created_at.isoformat(), "user": {"id": r.user.id, "username": r.user.username, "display_name": r.user.display_name}} for r in rows]


@app.post("/api/videos/{video_id}/comments")
def add_comment(video_id: int, payload: CommentRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if not payload.text.strip() or len(payload.text) > 5000:
        raise HTTPException(400, "Comment must be between 1 and 5000 characters")
    video = db.get(Video, video_id)
    if not video or not can_view(video, user, db):
        raise HTTPException(404, "Video not found")
    comment = Comment(video_id=video_id, user_id=user.id, text=payload.text.strip())
    db.add(comment)
    db.commit()
    db.refresh(comment)
    return {"id": comment.id, "text": comment.text, "created_at": comment.created_at.isoformat(), "user": {"id": user.id, "username": user.username, "display_name": user.display_name}}


@app.post("/api/videos/upload")
def upload(
    file: UploadFile = File(...),
    title: str = Form(...),
    description: str = Form(""),
    visibility: str = Form("public"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not file.filename:
        raise HTTPException(400, "No file selected")
    if not file.content_type or not file.content_type.startswith("video/"):
        raise HTTPException(400, "Only video files are accepted")
    try:
        vis = Visibility(visibility)
    except ValueError:
        raise HTTPException(400, "Invalid visibility")
    clean_title = title.strip()
    if not clean_title or len(clean_title) > 200:
        raise HTTPException(400, "Title must be between 1 and 200 characters")

    video_key = f"videos/{user.id}/{secrets.token_hex(16)}.mp4"
    thumbnail_key = f"thumbnails/{user.id}/{secrets.token_hex(16)}.jpg"
    path = None
    processed_path = None
    thumbnail_path = None
    uploaded_keys = []
    try:
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as temp_video:
            path = temp_video.name
            size = 0
            while chunk := file.file.read(1024 * 1024):
                size += len(chunk)
                if size > 500 * 1024 * 1024:
                    raise HTTPException(413, "Video exceeds 500 MB")
                temp_video.write(chunk)
        if size == 0:
            raise HTTPException(400, "Video file is empty")
        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", path],
            check=True, capture_output=True, text=True, timeout=30,
        )
        duration = max(0, int(float(probe.stdout.strip())))
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as processed_video:
            processed_path = processed_video.name
        subprocess.run(
            [
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", path, "-map", "0:v:0", "-map", "0:a?",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
                "-pix_fmt", "yuv420p", "-c:a", "aac", "-movflags", "+faststart",
                processed_path,
            ],
            check=True, capture_output=True, timeout=3600,
        )
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as temp_thumbnail:
            thumbnail_path = temp_thumbnail.name
        subprocess.run(
            ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", "0", "-i", processed_path, "-frames:v", "1", "-vf", "scale=640:-2", thumbnail_path],
            check=True, capture_output=True, timeout=60,
        )
        uploaded_keys.append(video_key)
        with open(processed_path, "rb") as source:
            put_object(video_key, source, "video/mp4")
        uploaded_keys.append(thumbnail_key)
        with open(thumbnail_path, "rb") as source:
            put_object(thumbnail_key, source.read(), "image/jpeg")
        video = Video(
            owner_id=user.id, title=clean_title, description=description.strip(),
            object_key=video_key, thumbnail_key=thumbnail_key, duration_seconds=duration,
            visibility=vis, status=VideoStatus.ready,
        )
        db.add(video)
        db.commit()
        db.refresh(video)
        uploaded_keys.clear()
        return serialize_video(video, db, user)
    except HTTPException:
        raise
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, ValueError) as error:
        raise HTTPException(400, "Could not process this video file") from error
    finally:
        for key in uploaded_keys:
            delete_object(key)
        for temp_path in (path, processed_path, thumbnail_path):
            if temp_path and os.path.exists(temp_path):
                os.unlink(temp_path)


@app.post("/api/videos/{video_id}/permissions")
def add_permission(video_id: int, payload: PermissionRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    video = db.get(Video, video_id)
    if not video or video.owner_id != user.id:
        raise HTTPException(403, "Only the owner can change permissions")
    allowed = db.query(User).filter(User.username == payload.username).first()
    if not allowed:
        raise HTTPException(404, "User not found")
    if not db.query(VideoPermission).filter_by(video_id=video_id, user_id=allowed.id).first():
        db.add(VideoPermission(video_id=video_id, user_id=allowed.id))
        db.commit()
    return {"ok": True}


@app.get("/api/channels/{username}")
def channel(username: str, db: Session = Depends(get_db), user: User | None = Depends(get_optional_user)):
    channel_owner = db.query(User).filter(User.username == username).first()
    if not channel_owner:
        raise HTTPException(404, "Channel not found")
    videos = db.query(Video).filter(Video.owner_id == channel_owner.id, Video.status == VideoStatus.ready).order_by(Video.created_at.desc()).all()
    visible = [v for v in videos if can_view(v, user, db)]
    subscribed = bool(user and db.query(Subscription).filter_by(subscriber_id=user.id, channel_id=channel_owner.id).first())
    playlists_query = db.query(Playlist).filter(
        Playlist.owner_id == channel_owner.id,
        Playlist.visibility == Visibility.public,
    )
    if user and user.id == channel_owner.id:
        playlists_query = db.query(Playlist).filter(Playlist.owner_id == channel_owner.id)
    playlists = playlists_query.order_by(Playlist.created_at.desc()).all()
    return {
        "channel": {"id": channel_owner.id, "username": channel_owner.username, "display_name": channel_owner.display_name},
        "subscribed": subscribed,
        "subscriber_count": db.query(func.count(Subscription.id)).filter(Subscription.channel_id == channel_owner.id).scalar(),
        "videos": [serialize_video(v, db, user) for v in visible],
        "playlists": [{
            "id": p.id,
            "title": p.title,
            "description": p.description,
            "video_count": sum(1 for item in p.items if can_view(item.video, user, db)),
        } for p in playlists],
    }


@app.get("/api/playlists/{playlist_id}")
def get_playlist(
    playlist_id: int,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_optional_user),
):
    playlist = db.get(Playlist, playlist_id)
    if not playlist or (playlist.visibility == Visibility.private and (not user or user.id != playlist.owner_id)):
        raise HTTPException(404, "Playlist not found")
    return playlist_json(playlist, db, user)


@app.post("/api/playlists")
def create_playlist(
    payload: PlaylistRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    title = payload.title.strip()
    if not title or len(title) > 150:
        raise HTTPException(400, "Playlist title must be between 1 and 150 characters")
    try:
        visibility = Visibility(payload.visibility)
    except ValueError:
        raise HTTPException(400, "Invalid visibility")
    playlist = Playlist(
        owner_id=user.id,
        title=title,
        description=payload.description.strip(),
        visibility=visibility,
    )
    db.add(playlist)
    db.commit()
    db.refresh(playlist)
    return playlist_json(playlist, db, user)


@app.post("/api/playlists/{playlist_id}/videos")
def add_playlist_video(
    playlist_id: int,
    payload: PlaylistItemRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    playlist = db.get(Playlist, playlist_id)
    if not playlist or playlist.owner_id != user.id:
        raise HTTPException(404, "Playlist not found")
    video = db.get(Video, payload.video_id)
    if not video or not can_view(video, user, db):
        raise HTTPException(404, "Video not found")
    if db.query(PlaylistVideo).filter_by(playlist_id=playlist.id, video_id=video.id).first():
        raise HTTPException(409, "Video is already in this playlist")
    position = db.query(func.max(PlaylistVideo.position)).filter_by(playlist_id=playlist.id).scalar()
    db.add(PlaylistVideo(playlist_id=playlist.id, video_id=video.id, position=(position or 0) + 1))
    db.commit()
    db.refresh(playlist)
    return playlist_json(playlist, db, user)


@app.post("/api/channels/{username}/subscribe")
def subscribe(username: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    channel_owner = db.query(User).filter(User.username == username).first()
    if not channel_owner:
        raise HTTPException(404, "Channel not found")
    if channel_owner.id == user.id:
        raise HTTPException(400, "Cannot subscribe to yourself")
    row = db.query(Subscription).filter_by(subscriber_id=user.id, channel_id=channel_owner.id).first()
    if row:
        db.delete(row)
        subscribed = False
    else:
        db.add(Subscription(subscriber_id=user.id, channel_id=channel_owner.id))
        subscribed = True
    db.commit()
    count = db.query(func.count(Subscription.id)).filter(Subscription.channel_id == channel_owner.id).scalar()
    return {"subscribed": subscribed, "subscriber_count": count}


@app.get("/api/subscriptions")
def subscription_feed(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    channel_ids = db.query(Subscription.channel_id).filter(Subscription.subscriber_id == user.id).subquery()
    videos = db.query(Video).filter(
        Video.owner_id.in_(channel_ids),
        Video.status == VideoStatus.ready,
    ).order_by(Video.created_at.desc()).all()
    return [serialize_video(video, db, user) for video in videos if can_view(video, user, db)]


@app.post("/api/videos/{video_id}/report")
def report_video(video_id: int, payload: ReportRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    video = db.get(Video, video_id)
    if not video:
        raise HTTPException(404, "Video not found")
    reason = payload.reason.strip()
    if not reason or len(reason) > 500:
        raise HTTPException(400, "Report reason must be between 1 and 500 characters")
    db.add(Report(video_id=video_id, reporter_id=user.id, reason=reason))
    db.commit()
    return {"ok": True}


@app.get("/api/moderation/reports")
def reports(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if user.role not in (Role.moderator, Role.admin):
        raise HTTPException(403, "Moderator access required")
    rows = db.query(Report).filter(Report.resolved == False).order_by(Report.created_at.desc()).all()
    return [{"id": r.id, "reason": r.reason, "created_at": r.created_at.isoformat(), "video": {"id": r.video_id, "title": db.get(Video, r.video_id).title}} for r in rows]


@app.post("/api/moderation/videos/{video_id}/hide")
def hide_video(video_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if user.role not in (Role.moderator, Role.admin):
        raise HTTPException(403, "Moderator access required")
    video = db.get(Video, video_id)
    if not video:
        raise HTTPException(404, "Video not found")
    video.status = VideoStatus.hidden
    db.query(Report).filter(Report.video_id == video_id).update({"resolved": True})
    db.commit()
    return {"ok": True}


frontend_dir = os.environ.get("FRONTEND_DIR") or "/app/frontend"
if not os.path.isdir(frontend_dir):
    frontend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "frontend"))
if os.path.isdir(frontend_dir):
    app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")
