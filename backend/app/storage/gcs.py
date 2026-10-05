"""Cloud Storage helpers.

* Original uploads live in the private *case-files* bucket under random
  object names (``cases/{caseId}/{docId}/{uuid}.{ext}``); the original file
  name is stored only in Firestore.
* Agent outputs and the extracted corpus live in the *artifacts* bucket.
* Upload URLs are V4 signed URLs minted through IAM ``signBlob`` — no service
  account keys exist anywhere.
"""

from __future__ import annotations

import asyncio
import json
import threading
from collections.abc import Callable
from datetime import timedelta
from pathlib import Path
from typing import Any, BinaryIO, TypeVar

import google.auth
from google.auth.transport.requests import Request
from google.cloud import storage

from app.config import Settings

R = TypeVar("R")


class Gcs:
    def __init__(self, settings: Settings):
        self._s = settings
        self._client = storage.Client(project=settings.project_id)
        self._creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
        self._creds_lock = threading.Lock()
        # The storage client's HTTP pool holds 10 connections; more concurrent calls just churn sockets.
        self._io_sem = asyncio.Semaphore(10)
        # Whole-file downloads can run for minutes: they may hold at most 4 of those 10 slots, so
        # artifact reads/writes never queue behind a batch of multi-hundred-MB transfers.
        self._bulk_sem = asyncio.Semaphore(4)

    async def _io(self, fn: Callable[..., R], *args: Any) -> R:
        async with self._io_sem:
            return await asyncio.to_thread(fn, *args)

    # ------------------------------------------------------------ uploads
    def _access_token(self) -> str:
        # Upload links are signed in parallel worker threads; refresh the shared credentials once.
        with self._creds_lock:
            if not self._creds.valid:
                self._creds.refresh(Request())
            return self._creds.token

    def _signed_put_url(self, object_name: str, content_type: str, max_bytes: int) -> tuple[str, dict[str, str]]:
        if not self._s.signing_sa_email:
            raise RuntimeError("VTX_SIGNING_SA_EMAIL is not configured")
        token = self._access_token()
        blob = self._client.bucket(self._s.case_bucket).blob(object_name)
        headers = {
            "Content-Type": content_type,
            # Enforced by GCS: the PUT is rejected if the body is outside this range.
            # Browsers send it as a custom header, so the bucket's CORS policy must list it
            # (infra/setup.sh and infra/deploy.sh do), or every browser upload fails preflight.
            "x-goog-content-length-range": f"1,{max_bytes}",
        }
        url = blob.generate_signed_url(
            version="v4",
            method="PUT",
            expiration=timedelta(seconds=self._s.upload_url_ttl_s),
            content_type=content_type,
            headers={"x-goog-content-length-range": headers["x-goog-content-length-range"]},
            service_account_email=self._s.signing_sa_email,
            access_token=token,
        )
        return url, headers

    async def signed_put_url(self, object_name: str, content_type: str, max_bytes: int) -> tuple[str, dict[str, str]]:
        return await self._io(self._signed_put_url, object_name, content_type, max_bytes)

    async def stat(self, bucket: str, object_name: str) -> dict[str, Any] | None:
        def _stat() -> dict[str, Any] | None:
            blob = self._client.bucket(bucket).get_blob(object_name)
            if blob is None:
                return None
            return {"size": blob.size, "generation": blob.generation, "crc32c": blob.crc32c, "content_type": blob.content_type}

        return await self._io(_stat)

    async def read_head(self, bucket: str, object_name: str, n: int = 8192) -> bytes:
        return await self._io(
            lambda: self._client.bucket(bucket).blob(object_name).download_as_bytes(start=0, end=n - 1)
        )

    async def download_to_file(self, bucket: str, object_name: str, path: Path, generation: int | None = None) -> int:
        """Stream an object to ``path`` in chunks (never held whole in memory), verified with CRC32C.

        ``generation`` pins the exact object version that was validated at upload time.
        Returns the size in bytes; raises ``google.api_core.exceptions.NotFound`` if it is gone.
        """
        def _download() -> int:
            blob = self._client.bucket(bucket).blob(object_name, generation=generation)
            blob.download_to_filename(str(path), checksum="crc32c")
            return path.stat().st_size

        async with self._bulk_sem:
            return await self._io(_download)

    async def inspect(
        self, bucket: str, object_name: str, fn: Callable[[BinaryIO], R], generation: int | None = None,
    ) -> R:
        """Run ``fn`` on a seekable reader that fetches byte ranges on demand — nothing is
        downloaded up front. Reading a zip's central directory this way costs a few small
        requests instead of a full download."""
        def _run() -> R:
            blob = self._client.bucket(bucket).blob(object_name, generation=generation)
            with blob.open("rb", chunk_size=1024 * 1024) as fh:
                return fn(fh)

        return await self._io(_run)

    async def delete(self, bucket: str, object_name: str) -> None:
        def _del() -> None:
            blob = self._client.bucket(bucket).blob(object_name)
            if blob.exists():
                blob.delete()

        await self._io(_del)

    # ------------------------------------------------------------ artifacts
    async def write_json(self, object_name: str, data: Any) -> str:
        payload = json.dumps(data, ensure_ascii=False, default=str).encode()

        def _write() -> None:
            blob = self._client.bucket(self._s.artifact_bucket).blob(object_name)
            blob.upload_from_string(payload, content_type="application/json")

        await self._io(_write)
        return f"gs://{self._s.artifact_bucket}/{object_name}"

    async def read_json(self, uri: str) -> Any:
        bucket, _, name = uri.removeprefix("gs://").partition("/")
        raw = await self._io(lambda: self._client.bucket(bucket).blob(name).download_as_bytes())
        return json.loads(raw)

    async def exists(self, uri: str) -> bool:
        bucket, _, name = uri.removeprefix("gs://").partition("/")
        return await self._io(lambda: self._client.bucket(bucket).blob(name).exists())
