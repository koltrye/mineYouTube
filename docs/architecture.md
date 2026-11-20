# Architecture

## Components

- Browser SPA: feed, search, channel, watch, auth, upload, comments, likes, subscriptions, playlists, and moderation UI.
- FastAPI: REST API and Swagger documentation.
- PostgreSQL: users, roles, video metadata, comments, likes, subscriptions, permissions, and reports.
- MinIO: S3-compatible object storage for original video files.
- Docker Compose: single-command deployment of every service.

## Video flow

1. An authenticated browser uploads multipart video data.
2. FastAPI validates size and media type and writes the object to the `youtube-videos` bucket.
3. PostgreSQL stores metadata and ownership.
4. Playback uses a short-lived, video-scoped signed ticket and a byte-range streaming endpoint, so video files do not need public object-store access.
5. Private videos require ownership, moderator/admin access, or an explicit `video_permissions` record; the stream endpoint checks access again when a ticket is used.

## Database design

The schema uses foreign keys for ownership and relationships, uniqueness constraints for subscriptions, likes, and playlist items, and enum fields for roles, visibility, and video status. Reports can be resolved when an authorized moderator hides a video.

## Security

- Passwords use bcrypt.
- API authentication uses signed JWT bearer tokens.
- Private objects are never made public; short-lived stream tickets are scoped to one video and authorization is rechecked for private playback.
- Moderator and admin endpoints enforce role checks.
- Uploads are size-limited, spooled to disk, and probed by FFmpeg before thumbnails and playback metadata are stored.
- The deploy script creates random local secrets. Demo credentials and the generated local secret file are for evaluation only.
