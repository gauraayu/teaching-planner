"""Object storage abstraction for lecture notes, assignment files and attachments.

V1 runs in URL mode: professors paste a link (Drive, OneDrive, LMS) and only the
link is stored. Setting STORAGE_BUCKET switches to an S3-compatible backend
(AWS S3, Cloudflare R2, MinIO, Supabase Storage) where the browser uploads
directly with a presigned URL, and the database keeps only metadata
(lecture_materials.storage_key / file_url). Binary data never goes into the database.
"""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from typing import Protocol

from app.core.config import get_settings
from app.core.errors import AppError

ALLOWED_CONTENT_TYPES = {
    "application/pdf", "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation", "image/png", "image/jpeg",
}
MAX_UPLOAD_MB = 25


@dataclass
class UploadTicket:
    storage_key: str
    upload_url: str
    file_url: str
    expires_in: int


class StorageBackend(Protocol):
    enabled: bool

    def create_upload(self, *, owner_id: uuid.UUID, file_name: str, content_type: str, size_bytes: int) -> UploadTicket: ...


class UrlOnlyStorage:
    enabled = False

    def create_upload(self, **_) -> UploadTicket:
        raise AppError("File upload is not enabled yet. Add a link to the document instead.", code="UPLOAD_NOT_ENABLED", status_code=501)


class S3Storage:
    """Presigned PUT uploads. Requires `boto3` (optional dependency)."""

    enabled = True

    def __init__(self, bucket: str, endpoint_url: str | None, public_base_url: str | None):
        import boto3  # imported lazily so URL mode has no extra dependency

        self.bucket = bucket
        self.public_base_url = public_base_url
        self.client = boto3.client("s3", endpoint_url=endpoint_url or None)

    def create_upload(self, *, owner_id, file_name, content_type, size_bytes) -> UploadTicket:
        if content_type not in ALLOWED_CONTENT_TYPES:
            raise AppError("Upload a PDF, Word, PowerPoint or image file.", code="UNSUPPORTED_FILE")
        if size_bytes > MAX_UPLOAD_MB * 1024 * 1024:
            raise AppError(f"Files must be smaller than {MAX_UPLOAD_MB} MB.", code="FILE_TOO_LARGE")
        safe = re.sub(r"[^A-Za-z0-9._-]+", "-", file_name)[-120:]
        key = f"lecture-materials/{owner_id}/{uuid.uuid4().hex}/{safe}"
        url = self.client.generate_presigned_url("put_object", Params={"Bucket": self.bucket, "Key": key, "ContentType": content_type},
                                                 ExpiresIn=900)
        public = f"{self.public_base_url.rstrip('/')}/{key}" if self.public_base_url else f"s3://{self.bucket}/{key}"
        return UploadTicket(storage_key=key, upload_url=url, file_url=public, expires_in=900)


def get_storage() -> StorageBackend:
    s = get_settings()
    if s.storage_bucket:
        return S3Storage(s.storage_bucket, s.storage_endpoint_url, s.storage_public_base_url)
    return UrlOnlyStorage()


# ---------------------------------------------------------------------------
# Class photos (optional evidence a professor attaches to a lecture).
# Uploaded through the API, validated server-side, stored outside the database.
# ---------------------------------------------------------------------------

IMAGE_SIGNATURES: tuple[tuple[bytes, str, str], ...] = (
    (b"\xff\xd8\xff", "image/jpeg", "jpg"),
    (b"\x89PNG\r\n\x1a\n", "image/png", "png"),
)


def sniff_image(data: bytes) -> tuple[str, str]:
    """Return (content_type, extension) from the file's own bytes - the browser's claim is not trusted."""
    for magic, ctype, ext in IMAGE_SIGNATURES:
        if data.startswith(magic):
            return ctype, ext
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp", "webp"
    raise AppError("Upload a JPG, PNG or WebP image.", code="UNSUPPORTED_FILE")


@dataclass
class StoredFile:
    storage_key: str
    file_url: str
    content_type: str
    size_bytes: int


class LocalImageStore:
    """Development / single-server storage: files under LOCAL_UPLOAD_DIR, served at /api/uploads/<key>."""

    def __init__(self, root: str):
        from pathlib import Path
        self.root = Path(root).resolve()

    def save(self, data: bytes, *, folder: str, ext: str, content_type: str) -> StoredFile:
        key = f"{folder}/{uuid.uuid4().hex}.{ext}"  # server-generated; the original file name never becomes a path
        path = self.root / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return StoredFile(storage_key=key, file_url=f"/api/uploads/{key}", content_type=content_type, size_bytes=len(data))

    def delete(self, key: str) -> None:
        path = (self.root / key).resolve()
        if self.root in path.parents and path.is_file():
            path.unlink()


class S3ImageStore:
    def __init__(self, s3: S3Storage):
        self.s3 = s3

    def save(self, data: bytes, *, folder: str, ext: str, content_type: str) -> StoredFile:
        key = f"{folder}/{uuid.uuid4().hex}.{ext}"
        self.s3.client.put_object(Bucket=self.s3.bucket, Key=key, Body=data, ContentType=content_type)
        base = self.s3.public_base_url
        return StoredFile(storage_key=key, file_url=f"{base.rstrip('/')}/{key}" if base else f"s3://{self.s3.bucket}/{key}",
                          content_type=content_type, size_bytes=len(data))

    def delete(self, key: str) -> None:
        self.s3.client.delete_object(Bucket=self.s3.bucket, Key=key)


def get_image_store():
    s = get_settings()
    if s.storage_bucket:
        return S3ImageStore(S3Storage(s.storage_bucket, s.storage_endpoint_url, s.storage_public_base_url))
    return LocalImageStore(s.local_upload_dir)
