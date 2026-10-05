"""Tiny dependency-free PDF builder for tests and benchmarks.

``make_pdf([["line", ...], None, ...])`` creates one page per item: a list of text lines gives a
page with a real text layer; ``None`` gives a page with no text (what a scan looks like to the text
extractor, so it is routed to OCR). With ``image_bytes`` set, each such page also carries an image
XObject of that many (random, incompressible) bytes, like a scanned page.
"""

from __future__ import annotations

import os


def _esc(s: str) -> str:
    return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _stream(header: str, data: bytes) -> bytes:
    return f"<< {header} /Length {len(data)} >>\nstream\n".encode() + data + b"\nendstream"


def make_pdf(pages: list[list[str] | None], image_bytes: int = 0) -> bytes:
    objs: dict[int, bytes] = {
        1: b"<< /Type /Catalog /Pages 2 0 R >>",
        3: b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    }
    kids: list[int] = []
    next_id = 4
    for lines in pages:
        pid, cid = next_id, next_id + 1
        next_id += 2
        kids.append(pid)
        resources = "/Font << /F1 3 0 R >>"
        if lines:
            ops = ["BT", "/F1 10 Tf", "12 TL", "50 790 Td", *(f"({_esc(ln)}) Tj T*" for ln in lines), "ET"]
        elif image_bytes:
            iid = next_id
            next_id += 1
            # Random bytes labelled as JPEG: never decoded by text extraction or page copying.
            objs[iid] = _stream("/Type /XObject /Subtype /Image /Width 1 /Height 1 /ColorSpace /DeviceGray "
                                "/BitsPerComponent 8 /Filter /DCTDecode", os.urandom(image_bytes))
            resources += f" /XObject << /Im0 {iid} 0 R >>"
            ops = ["q", "595 0 0 842 0 0 cm", "/Im0 Do", "Q"]
        else:
            ops = []
        objs[cid] = _stream("", "\n".join(ops).encode("latin-1"))
        objs[pid] = (
            "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
            f"/Resources << {resources} >> /Contents {cid} 0 R >>"
        ).encode()
    objs[2] = f"<< /Type /Pages /Kids [{' '.join(f'{k} 0 R' for k in kids)}] /Count {len(kids)} >>".encode()

    out = bytearray(b"%PDF-1.4\n")
    offsets: dict[int, int] = {}
    for i in range(1, next_id):
        offsets[i] = len(out)
        out += f"{i} 0 obj\n".encode() + objs[i] + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {next_id}\n0000000000 65535 f \n".encode()
    out += b"".join(f"{offsets[i]:010d} 00000 n \n".encode() for i in range(1, next_id))
    out += f"trailer\n<< /Size {next_id} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)


def text_page(i: int, lines: int = 45) -> list[str]:
    """A dense page (~3,000 characters), similar to a typed pleading."""
    return [
        f"Page {i} line {j}: The Claimant contends that the Defendant failed to pay invoice INV-{i:04d}-{j:02d} when due."
        for j in range(1, lines + 1)
    ]
