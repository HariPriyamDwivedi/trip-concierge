"""Where memory files live: S3 when a bucket is configured, else a local folder.

Keys look like `<prefix>/users/<user_id>/<media_id>/<original|thumb>`, so one
user's files never share a path with another's. Downloads from S3 use short-lived
presigned URLs (the bucket stays private); local files are served by the API
after an ownership check.
"""

import os
import shutil
from pathlib import Path
from typing import BinaryIO, Optional

URL_TTL = 3600  # seconds a presigned link stays valid


class LocalStorage:
    kind = "local"

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)

    def _path(self, key: str) -> Path:
        path = (self.root / key).resolve()
        if not path.is_relative_to(self.root.resolve()):
            raise ValueError("bad storage key")
        return path

    def put(self, key: str, fileobj: BinaryIO, content_type: str) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("wb") as out:
            shutil.copyfileobj(fileobj, out)

    def open(self, key: str) -> Path:
        return self._path(key)

    def url(self, key: str, media_id: str, variant: str, filename: str, content_type: str) -> str:
        return f"/api/media/{media_id}/{variant}"  # served by the API after an ownership check

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)


class S3Storage:
    kind = "s3"

    def __init__(self, bucket: str, prefix: str, region: Optional[str] = None) -> None:
        import boto3

        self.bucket, self.prefix = bucket, prefix.strip("/")
        self.client = boto3.client("s3", region_name=region)

    def _key(self, key: str) -> str:
        return f"{self.prefix}/{key}"

    def put(self, key: str, fileobj: BinaryIO, content_type: str) -> None:
        # upload_fileobj streams large videos in multipart chunks
        self.client.upload_fileobj(
            fileobj, self.bucket, self._key(key),
            ExtraArgs={"ContentType": content_type, "ServerSideEncryption": "AES256"},
        )

    def url(self, key: str, media_id: str, variant: str, filename: str, content_type: str) -> str:
        safe = filename.replace('"', "")
        return self.client.generate_presigned_url(
            "get_object",
            Params={
                "Bucket": self.bucket,
                "Key": self._key(key),
                "ResponseContentType": content_type,
                "ResponseContentDisposition": f'inline; filename="{safe}"',
            },
            ExpiresIn=URL_TTL,
        )

    def delete(self, key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=self._key(key))


def make_storage():
    bucket = os.getenv("MEDIA_BUCKET") or os.getenv("S3_ATTACHMENTS_BUCKET")
    if bucket:
        return S3Storage(bucket, os.getenv("MEDIA_PREFIX", "trip-concierge"), os.getenv("AWS_REGION"))
    return LocalStorage(os.getenv("MEDIA_DIR") or Path(__file__).resolve().parent.parent / "media")
