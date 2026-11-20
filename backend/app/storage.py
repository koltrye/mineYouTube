import boto3
from botocore.exceptions import ClientError
from botocore.config import Config
from typing import BinaryIO

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
    except ClientError as error:
        code = error.response.get("Error", {}).get("Code")
        if code not in ("404", "NoSuchBucket", "NotFound"):
            raise
        client.create_bucket(Bucket=settings.s3_bucket)


def put_object(key: str, data: bytes | BinaryIO, content_type: str):
    ensure_bucket()
    client.put_object(Bucket=settings.s3_bucket, Key=key, Body=data, ContentType=content_type)


def get_object(key: str, range_header: str | None = None):
    params = {"Bucket": settings.s3_bucket, "Key": key}
    if range_header:
        params["Range"] = range_header
    return client.get_object(**params)


def object_size(key: str) -> int:
    return client.head_object(Bucket=settings.s3_bucket, Key=key)["ContentLength"]


def delete_object(key: str):
    client.delete_object(Bucket=settings.s3_bucket, Key=key)
