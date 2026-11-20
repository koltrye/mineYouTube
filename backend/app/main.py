from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Form, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy import or_, func
from sqlalchemy.orm import Session
import os

from .database import engine, Base, get_db
from .models import (
    Comment, Report, Role, Subscription, User, Video, VideoLike,
    VideoPermission, Visibility, VideoStatus,
)
from .auth import create_token, get_current_user, get_optional_user, hash_password, verify_password
from .config import settings
from .storage import presigned_url, put_object

Base.metadata.create_all(bind=engine)

app = FastAPI(title="MineTube", version="1.0.0", docs_url="/docs")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


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


def public_url(key: str) -> str:
    url = presigned_url(key)
    return url.replace(settings.s3_endpoint, settings.s3_public_endpoint)


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
        "likes": likes,
        "comments": comments,
        "created_at": video.created_at.isoformat(),
        "thumbnail_url": public_url(video.thumbnail_key) if video.thumbnail_key else None,
        "video_url": public_url(video.object_key),
        "liked": bool(user and db.query(VideoLike).filter_by(video_id=video.id, user_id=user.id).first()),
    }


@app.post("/api/auth/register")
def register(payload: RegisterRequest, db: Session = Depends(get_db)):
    username = payload.username.strip()
    if len(username) < 3:
        raise HTTPException(400, "Username must be at least 3 characters")
    if db.query(User).filter(or_(User.username == username, User.email == payload.email.strip().lower())).first():
        raise HTTPException(409, "User already exists")
    user = User(
        username=username,
        email=payload.email.strip().lower(),
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
    query = db.query(Video).filter(Video.status != VideoStatus.hidden)
    if q:
        query = query.filter(or_(Video.title.ilike(f"%{q}%"), Video.description.ilike(f"%{q}%")))
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


@app.post("/api/videos/{video_id}/view")
def count_view(video_id: int, db: Session = Depends(get_db)):
    video = db.get(Video, video_id)
    if not video:
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
def comments(video_id: int, db: Session = Depends(get_db)):
    rows = db.query(Comment).filter(Comment.video_id == video_id).order_by(Comment.created_at.desc()).all()
    return [{"id": r.id, "text": r.text, "created_at": r.created_at.isoformat(), "user": {"id": r.user.id, "username": r.user.username, "display_name": r.user.display_name}} for r in rows]


@app.post("/api/videos/{video_id}/comments")
def add_comment(video_id: int, payload: CommentRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if not payload.text.strip():
        raise HTTPException(400, "Comment cannot be empty")
    video = db.get(Video, video_id)
    if not video or not can_view(video, user, db):
        raise HTTPException(404, "Video not found")
    comment = Comment(video_id=video_id, user_id=user.id, text=payload.text.strip())
    db.add(comment)
    db.commit()
    db.refresh(comment)
    return {"id": comment.id, "text": comment.text, "created_at": comment.created_at.isoformat(), "user": {"id": user.id, "username": user.username, "display_name": user.display_name}}


@app.post("/api/videos/upload")
async def upload(
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
    data = await file.read()
    if len(data) > 1024 * 1024 * 500:
        raise HTTPException(413, "Video exceeds 500 MB")
    ext = os.path.splitext(file.filename)[1].lower() or ".mp4"
    key = f"videos/{user.id}/{title.strip().lower().replace(' ', '-')}-{os.urandom(4).hex()}{ext}"
    put_object(key, data, file.content_type)
    video = Video(owner_id=user.id, title=title.strip(), description=description.strip(), object_key=key, visibility=vis, status=VideoStatus.ready)
    db.add(video)
    db.commit()
    db.refresh(video)
    return serialize_video(video, db, user)


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
    videos = db.query(Video).filter(Video.owner_id == channel_owner.id, Video.status != VideoStatus.hidden).order_by(Video.created_at.desc()).all()
    visible = [v for v in videos if can_view(v, user, db)]
    subscribed = bool(user and db.query(Subscription).filter_by(subscriber_id=user.id, channel_id=channel_owner.id).first())
    return {
        "channel": {"id": channel_owner.id, "username": channel_owner.username, "display_name": channel_owner.display_name},
        "subscribed": subscribed,
        "subscriber_count": db.query(func.count(Subscription.id)).filter(Subscription.channel_id == channel_owner.id).scalar(),
        "videos": [serialize_video(v, db, user) for v in visible],
    }


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


@app.post("/api/videos/{video_id}/report")
def report_video(video_id: int, payload: ReportRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    video = db.get(Video, video_id)
    if not video:
        raise HTTPException(404, "Video not found")
    db.add(Report(video_id=video_id, reporter_id=user.id, reason=payload.reason.strip()))
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
