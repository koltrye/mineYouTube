import boto3
from botocore.config import Config

from .config import settings


client = boto3.client(
    "s3",
    endpoint_url=settings.s3_endpoint,
    aws_access_key_id=settings.s3_access_key,
    aws_secret_access_key=settings.s3_secret_key,
    region_name=settings.s3_region,
    config=Config(signature_version="s3v4"),
)


def ensure_bucket():
    try:
        client.head_bucket(Bucket=settings.s3_bucket)
    except Exception:
        client.create_bucket(Bucket=settings.s3_bucket)


def put_object(key: str, data: bytes, content_type: str):
    ensure_bucket()
    client.put_object(Bucket=settings.s3_bucket, Key=key, Body=data, ContentType=content_type)


def presigned_url(key: str, expires: int = 3600) -> str:
    return client.generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.s3_bucket, "Key": key},
        ExpiresIn=expires,
    )
