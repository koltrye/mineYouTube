from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql://youtube:youtube@db:5432/youtube"
    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 60 * 24
    s3_endpoint: str = "http://minio:9000"
    s3_public_endpoint: str = "http://localhost:9000"
    s3_access_key: str = "minioadmin"
    s3_secret_key: str = "minioadmin"
    s3_bucket: str = "youtube-videos"
    s3_region: str = "us-east-1"

    class Config:
        env_file = ".env"


settings = Settings()

