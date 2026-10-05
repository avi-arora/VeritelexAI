"""Upload allow-list and content sniffing (magic bytes), independent of the
client-declared name or Content-Type."""

from __future__ import annotations

import io
import os
import zipfile
from dataclasses import dataclass
from typing import BinaryIO


@dataclass(frozen=True)
class FileKind:
    ext: str
    label: str  # shown in the UI ("PDF", "DOC", ...)
    mime: str


KINDS: dict[str, FileKind] = {
    "pdf": FileKind("pdf", "PDF", "application/pdf"),
    "docx": FileKind("docx", "DOC", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
    "xlsx": FileKind("xlsx", "XLS", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
    "png": FileKind("png", "IMG", "image/png"),
    "jpg": FileKind("jpg", "IMG", "image/jpeg"),
    "jpeg": FileKind("jpg", "IMG", "image/jpeg"),
    "tif": FileKind("tif", "IMG", "image/tiff"),
    "tiff": FileKind("tif", "IMG", "image/tiff"),
    "txt": FileKind("txt", "TXT", "text/plain"),
}


def kind_for_name(name: str) -> FileKind | None:
    ext = os.path.splitext(os.path.basename(name))[1].lower().lstrip(".")
    return KINDS.get(ext)


def sniff(head: bytes) -> str | None:
    """Return the canonical extension implied by the leading bytes, or None."""
    if head.startswith(b"%PDF-"):
        return "pdf"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if head.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if head.startswith((b"II*\x00", b"MM\x00*")):
        return "tif"
    if head.startswith(b"PK\x03\x04"):
        return "zip"  # OOXML container; refined by ooxml_kind() from the zip directory
    if head and _looks_like_text(head):
        return "txt"
    return None


def _looks_like_text(head: bytes) -> bool:
    try:
        head.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return b"\x00" not in head


MIN_OOXML_BYTES = 128
"""Smallest zip that can hold ``word/document.xml`` or ``xl/workbook.xml`` (local header + central
directory entry + end record). Anything shorter is rejected before its central directory is read."""


def ooxml_kind(src: bytes | BinaryIO | str | os.PathLike[str]) -> str | None:
    """Identify DOCX/XLSX by their mandatory parts; rejects zip bombs and path traversal entries.

    Only the zip central directory is read, so passing a seekable file object (or path) avoids
    loading the whole file.
    """
    try:
        with zipfile.ZipFile(io.BytesIO(src) if isinstance(src, bytes) else src) as zf:
            infos = zf.infolist()
            if len(infos) > 5000:
                return None
            total = sum(i.file_size for i in infos)
            if total > 1024 * 1024 * 1024 or any(i.file_size > 50 * max(1, i.compress_size) and i.file_size > 50_000_000 for i in infos):
                return None  # decompression bomb heuristics
            names = {i.filename for i in infos}
            if any(n.startswith("/") or ".." in n.split("/") for n in names):
                return None
            if "word/document.xml" in names:
                return "docx"
            if "xl/workbook.xml" in names:
                return "xlsx"
    except (zipfile.BadZipFile, ValueError):
        # ValueError: malformed directory entries (e.g. UnicodeDecodeError on a bad UTF-8 name).
        # OSError is deliberately NOT caught: network errors from a ranged reader subclass it, and a
        # transient failure must surface as a retryable error, never reject a valid upload.
        return None
    return None


def matches(expected_ext: str, head: bytes) -> bool:
    sniffed = sniff(head)
    if expected_ext in ("docx", "xlsx"):
        return sniffed == "zip"
    return sniffed == expected_ext
