import os
import subprocess
import tempfile
import time

from sqlalchemy.exc import OperationalError

from app.database import engine, SessionLocal, Base
from app.models import User, Video, Comment, Role, VideoStatus, Visibility
from app.auth import hash_password
from app.storage import ensure_bucket, put_object


for attempt in range(30):
    try:
        Base.metadata.create_all(bind=engine)
        break
    except OperationalError:
        time.sleep(2)
else:
    raise RuntimeError("PostgreSQL did not become ready")

ensure_bucket()
db = SessionLocal()

user_defaults = [
    ("demo", "demo@minetube.local", "Demo Creator", Role.user),
    ("alice", "alice@minetube.local", "Alice Travels", Role.user),
    ("moderator", "moderator@minetube.local", "Site Moderator", Role.moderator),
    ("admin", "admin@minetube.local", "Administrator", Role.admin),
]
for username, email, display_name, role in user_defaults:
    if not db.query(User).filter_by(username=username).first():
        db.add(User(
            username=username,
            email=email,
            password_hash=hash_password("demo123"),
            display_name=display_name,
            role=role,
        ))
db.commit()
users = db.query(User).order_by(User.id).all()

colors = [("demo", "0x1c5d99"), ("alice", "0x7b2cbf"), ("alice", "0x2d6a4f")]
titles = [
    ("A beautiful test video", "Public demo content from MineTube."),
    ("Mountain adventure", "A cinematic trip through the mountains."),
    ("Quiet moments in nature", "Relaxing scenery and color."),
]

for index, ((owner_name, color), (title, description)) in enumerate(zip(colors, titles)):
    owner = next(u for u in users if u.username == owner_name)
    if db.query(Video).filter_by(owner_id=owner.id, title=title).first():
        continue
    key = f"videos/{owner.id}/demo-{index + 1}.mp4"
    with tempfile.TemporaryDirectory() as temp:
        video_path = os.path.join(temp, "video.mp4")
        thumbnail_path = os.path.join(temp, "thumbnail.jpg")
        subprocess.run([
            "ffmpeg", "-y", "-f", "lavfi", "-i", f"color=c={color}:s=1280x720:d=3",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=3",
            "-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", video_path
        ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        with open(video_path, "rb") as f:
            put_object(key, f.read(), "video/mp4")
        subprocess.run(["ffmpeg", "-y", "-i", video_path, "-frames:v", "1", thumbnail_path], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        thumb_key = f"thumbnails/{owner.id}/demo-{index + 1}.jpg"
        with open(thumbnail_path, "rb") as f:
            put_object(thumb_key, f.read(), "image/jpeg")
    video = Video(owner_id=owner.id, title=title, description=description, object_key=key, thumbnail_key=thumb_key, duration_seconds=3, visibility=Visibility.public, status=VideoStatus.ready, views=(index + 1) * 120)
    db.add(video)
    db.commit()
    db.refresh(video)
    db.add(Comment(video_id=video.id, user_id=users[index % 2 + 1].id, text="Amazing video!"))
db.commit()
db.close()
print("Seeded demo users and videos")
