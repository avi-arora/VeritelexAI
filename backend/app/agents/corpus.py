"""Builds the citable text views of the case record that agents read.

Every segment is tagged ``⟦<Doc label>, <ref>⟧`` and agents are instructed to
cite exactly those tags, so the verifier can check every citation against
the corpus deterministically.
"""

from __future__ import annotations

import re
from typing import Any, Iterable

PRIORITY = [
    "Claim Form", "Particulars of Claim", "Defence", "Defence and Counterclaim", "Reply", "Order", "Judgment",
    "Skeleton Argument", "Application", "Contract", "Expert Report", "Witness Statement", "Minutes",
    "Correspondence", "Invoice", "Other",
]
PLEADINGS = {"Claim Form", "Particulars of Claim", "Defence", "Defence and Counterclaim", "Reply", "Skeleton Argument", "Application"}
COURT = {"Order", "Judgment"}


def labelled(ingests: dict[str, dict[str, Any]], order: Iterable[str] | None = None) -> list[dict[str, Any]]:
    """Ingest outputs in a stable order with unique display labels."""
    keys = [k for k in (order or sorted(ingests)) if k in ingests]
    seen: dict[str, int] = {}
    docs: list[dict[str, Any]] = []
    for k in keys:
        d = dict(ingests[k])
        base = (d.get("label") or d.get("doc_type") or d.get("name") or "Document").strip()
        seen[base] = seen.get(base, 0) + 1
        d["cite_label"] = base if seen[base] == 1 else f"{base} ({seen[base]})"
        docs.append(d)
    return docs


def by_priority(docs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rank = {t: i for i, t in enumerate(PRIORITY)}
    return sorted(docs, key=lambda d: rank.get(d.get("doc_type", "Other"), len(PRIORITY)))


def render_doc(doc: dict[str, Any], budget: int | None = None) -> str:
    head = (
        f"=== DOCUMENT: {doc['cite_label']} | type: {doc.get('doc_type')} | filed by: {doc.get('filed_by')}"
        f" | date: {doc.get('doc_date') or 'n/a'} | file: {doc.get('name')} ===\n"
    )
    parts = [head]
    used = len(head)
    for seg in doc.get("segments", []):
        line = f"⟦{doc['cite_label']}, {seg['ref']}⟧ {seg['text']}\n"
        if budget is not None and used + len(line) > budget:
            parts.append(f"[… remainder of {doc['cite_label']} omitted for length …]\n")
            break
        parts.append(line)
        used += len(line)
    return "".join(parts)


def render_corpus(docs: list[dict[str, Any]], budget: int, include: set[str] | None = None) -> str:
    """Render documents in priority order until the character budget is spent.
    Documents that do not fit are listed with their summary so agents know they exist."""
    out: list[str] = []
    remaining = budget
    skipped: list[dict[str, Any]] = []
    for d in by_priority(docs):
        if include is not None and d.get("doc_type") not in include:
            skipped.append(d)
            continue
        if remaining <= 2000:
            skipped.append(d)
            continue
        text = render_doc(d, budget=remaining)
        out.append(text)
        remaining -= len(text)
    if skipped:
        out.append("=== OTHER DOCUMENTS ON FILE (summaries only) ===\n")
        out += [f"- {d['cite_label']} ({d.get('doc_type')}, {d.get('pages')} pp): {d.get('summary', '')}\n" for d in skipped]
    return "".join(out)


def citation_index(docs: list[dict[str, Any]]) -> dict[str, dict[str, str]]:
    """{normalised doc label: {normalised ref: text}} for verification."""
    idx: dict[str, dict[str, str]] = {}
    for d in docs:
        refs = {norm_ref(s["ref"]): s["text"] for s in d.get("segments", [])}
        idx[norm_label(d["cite_label"])] = refs
    return idx


_WS = re.compile(r"\s+")


def norm_label(s: str) -> str:
    return _WS.sub(" ", s.strip().lower())


def norm_ref(s: str) -> str:
    s = s.strip().lower().replace("para", "¶").replace("pp.", "p.").replace("page", "p.")
    return _WS.sub("", s)


_CITE = re.compile(r"^(?P<label>.+?),\s*(?P<ref>(?:p\.|pp\.|¶|para|page|table|sheet)\s*.+)$", re.IGNORECASE)


def resolve(citation: str, idx: dict[str, dict[str, str]]) -> str | None:
    """Return the cited segment text if ``citation`` ('Label, p. 12' / 'Label, p. 12-14') exists."""
    m = _CITE.match(citation.strip())
    if not m:
        return None
    label = norm_label(m.group("label"))
    refs = idx.get(label)
    if refs is None:
        # tolerate shortened labels ("Particulars" for "Particulars of Claim")
        cands = [k for k in idx if k.startswith(label) or label.startswith(k)]
        if len(cands) != 1:
            return None
        refs = idx[cands[0]]
    ref = norm_ref(m.group("ref"))
    if ref in refs:
        return refs[ref]
    rng = re.match(r"^(p\.|¶)(\d+)[-–](\d+)$", ref)
    if rng:
        kind, a, b = rng.group(1), int(rng.group(2)), int(rng.group(3))
        texts = [refs.get(f"{kind}{i}") for i in range(a, min(b, a + 10) + 1)]
        joined = "\n".join(t for t in texts if t)
        return joined or None
    return None
