# Architecture

## Components

- Browser SPA: feed, search, channel, watch, auth, upload, comments, likes, subscriptions, and moderation UI.
- FastAPI: REST API and Swagger documentation.
- PostgreSQL: users, roles, video metadata, comments, likes, subscriptions, permissions, and reports.
- MinIO: S3-compatible object storage for original video files.
- Docker Compose: single-command deployment of every service.

## Video flow

1. An authenticated browser uploads multipart video data.
2. FastAPI validates size and media type and writes the object to the `youtube-videos` bucket.
3. PostgreSQL stores metadata and ownership.
4. Playback requests receive a short-lived presigned URL.
5. Private videos require ownership, moderator/admin access, or an explicit `video_permissions` record.

## Database design

The schema uses foreign keys for ownership and relationships, uniqueness constraints for subscriptions and likes, and enum fields for roles, visibility, and video status. Reports can be resolved when an authorized moderator hides a video.

## Security

- Passwords use bcrypt.
- API authentication uses signed JWT bearer tokens.
- Private objects are checked by application authorization before a presigned URL is generated.
- Moderator and admin endpoints enforce role checks.
- Upload size and video MIME type are validated.
- Secrets are environment-configurable and must be replaced outside local development.
