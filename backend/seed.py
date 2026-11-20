import os
import subprocess
import tempfile
import time

from sqlalchemy.exc import OperationalError

from app.database import engine, SessionLocal, Base
from app.models import User, Video, Comment, VideoStatus, Visibility
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

if db.query(User).filter_by(username="demo").first():
    print("Database already seeded")
    db.close()
    raise SystemExit

users = [
    User(username="demo", email="demo@minetube.local", password_hash=hash_password("demo123"), display_name="Demo Creator"),
    User(username="alice", email="alice@minetube.local", password_hash=hash_password("demo123"), display_name="Alice Travels"),
    User(username="moderator", email="moderator@minetube.local", password_hash=hash_password("demo123"), display_name="Site Moderator", role="moderator"),
    User(username="admin", email="admin@minetube.local", password_hash=hash_password("demo123"), display_name="Administrator", role="admin"),
]
db.add_all(users)
db.commit()
for u in users:
    db.refresh(u)

colors = [("demo", "0x1c5d99"), ("alice", "0x7b2cbf"), ("alice", "0x2d6a4f")]
titles = [
    ("A beautiful test video", "Public demo content from MineTube."),
    ("Mountain adventure", "A cinematic trip through the mountains."),
    ("Quiet moments in nature", "Relaxing scenery and color."),
]

for index, ((owner_name, color), (title, description)) in enumerate(zip(colors, titles)):
    owner = next(u for u in users if u.username == owner_name)
    key = f"videos/{owner.id}/demo-{index + 1}.mp4"
    with tempfile.TemporaryDirectory() as temp:
        video_path = os.path.join(temp, "video.mp4")
        subprocess.run([
            "ffmpeg", "-y", "-f", "lavfi", "-i", f"color=c={color}:s=1280x720:d=3",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=3",
            "-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", video_path
        ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        with open(video_path, "rb") as f:
            put_object(key, f.read(), "video/mp4")
    video = Video(owner_id=owner.id, title=title, description=description, object_key=key, visibility=Visibility.public, status=VideoStatus.ready, views=(index + 1) * 120)
    db.add(video)
    db.commit()
    db.refresh(video)
    db.add(Comment(video_id=video.id, user_id=users[index % 2 + 1].id, text="Amazing video!"))
db.commit()
db.close()
print("Seeded demo users and videos")
