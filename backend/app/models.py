from datetime import datetime, timezone
from enum import Enum as PyEnum
from sqlalchemy import Boolean, Column, DateTime, Enum, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship

from .database import Base


class Role(str, PyEnum):
    user = "user"
    moderator = "moderator"
    admin = "admin"


class Visibility(str, PyEnum):
    public = "public"
    private = "private"


class VideoStatus(str, PyEnum):
    processing = "processing"
    ready = "ready"
    hidden = "hidden"


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    display_name = Column(String(100), nullable=False)
    avatar_url = Column(String(500), nullable=True)
    role = Column(Enum(Role), default=Role.user, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    videos = relationship("Video", back_populates="owner")


class Video(Base):
    __tablename__ = "videos"
    id = Column(Integer, primary_key=True)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    title = Column(String(200), nullable=False)
    description = Column(Text, default="")
    object_key = Column(String(500), nullable=False)
    thumbnail_key = Column(String(500), nullable=True)
    duration_seconds = Column(Integer, default=0)
    visibility = Column(Enum(Visibility), default=Visibility.public, nullable=False)
    status = Column(Enum(VideoStatus), default=VideoStatus.processing, nullable=False)
    views = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    owner = relationship("User", back_populates="videos")
    comments = relationship("Comment", back_populates="video", cascade="all, delete-orphan")


class VideoLike(Base):
    __tablename__ = "video_likes"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    video_id = Column(Integer, ForeignKey("videos.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    __table_args__ = (UniqueConstraint("user_id", "video_id", name="uq_like_user_video"),)


class Comment(Base):
    __tablename__ = "comments"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    video_id = Column(Integer, ForeignKey("videos.id"), nullable=False, index=True)
    text = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    video = relationship("Video", back_populates="comments")
    user = relationship("User")


class Subscription(Base):
    __tablename__ = "subscriptions"
    id = Column(Integer, primary_key=True)
    subscriber_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    channel_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    __table_args__ = (UniqueConstraint("subscriber_id", "channel_id", name="uq_subscription"),)


class VideoPermission(Base):
    __tablename__ = "video_permissions"
    id = Column(Integer, primary_key=True)
    video_id = Column(Integer, ForeignKey("videos.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    __table_args__ = (UniqueConstraint("video_id", "user_id", name="uq_video_permission"),)


class Playlist(Base):
    __tablename__ = "playlists"
    id = Column(Integer, primary_key=True)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    title = Column(String(150), nullable=False)
    description = Column(Text, default="")
    visibility = Column(Enum(Visibility), default=Visibility.public, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    owner = relationship("User")
    items = relationship("PlaylistVideo", back_populates="playlist", cascade="all, delete-orphan", order_by="PlaylistVideo.position")


class PlaylistVideo(Base):
    __tablename__ = "playlist_videos"
    id = Column(Integer, primary_key=True)
    playlist_id = Column(Integer, ForeignKey("playlists.id"), nullable=False)
    video_id = Column(Integer, ForeignKey("videos.id"), nullable=False)
    position = Column(Integer, nullable=False, default=0)
    added_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    playlist = relationship("Playlist", back_populates="items")
    video = relationship("Video")
    __table_args__ = (
        UniqueConstraint("playlist_id", "video_id", name="uq_playlist_video"),
        UniqueConstraint("playlist_id", "position", name="uq_playlist_position"),
    )


class Report(Base):
    __tablename__ = "reports"
    id = Column(Integer, primary_key=True)
    video_id = Column(Integer, ForeignKey("videos.id"), nullable=False)
    reporter_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    reason = Column(String(500), nullable=False)
    resolved = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

