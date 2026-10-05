"""Generate a small, entirely fictional DIFC case bundle for local smoke tests.

    uv run python scripts/make_sample_case.py  # writes ./sample_case/
"""

from __future__ import annotations

import pathlib

from docx import Document

OUT = pathlib.Path(__file__).resolve().parent.parent / "sample_case"

CLAIM_FORM = [
    "IN THE COURTS OF THE DUBAI INTERNATIONAL FINANCIAL CENTRE",
    "COURT OF FIRST INSTANCE",
    "Claim No. CFI-201/2026",
    "CLAIM FORM (RDC Part 7)",
    "Claimant: Falcon Reach Marine Services LLC",
    "Defendant: Opal Crescent Hospitality Ltd",
    "Date of issue: 12 March 2026",
    "Brief details of claim: The Claimant claims AED 4,850,000 being unpaid invoices under a",
    "Marine Maintenance Services Agreement dated 3 February 2024, together with interest and costs.",
    "Value: AED 4,850,000",
]

PARTICULARS = [
    "PARTICULARS OF CLAIM",
    "1. The Claimant is a marine services company registered in Dubai. The Defendant operates the "
    "Opal Crescent marina and hotel in the DIFC.",
    "2. By a Marine Maintenance Services Agreement dated 3 February 2024 (the Agreement) the Claimant agreed "
    "to maintain the Defendant's marina pontoons and fuel berth for 24 months at a monthly fee of AED 310,000.",
    "3. Clause 9.2 of the Agreement requires payment within 30 days of invoice. Clause 14 provides that the "
    "Agreement is governed by DIFC law and that the DIFC Courts have exclusive jurisdiction.",
    "4. Between 1 June 2025 and 31 December 2025 the Claimant issued invoices INV-2025-061 to INV-2025-075 "
    "totalling AED 4,850,000. None has been paid.",
    "5. On 15 January 2026 the Claimant served a notice of default. On 2 February 2026 the Defendant replied "
    "alleging defective work on the fuel berth and asserting a right of set-off.",
    "6. The Claimant denies any defective work. Clause 11.4 excludes set-off unless a defect notice was served "
    "within 14 days of the work. No defect notice was served.",
    "7. The Claimant claims AED 4,850,000, interest under Article 17 of the DIFC Law of Damages and Remedies, and costs.",
]

DEFENCE = [
    "DEFENCE",
    "1. Paragraphs 1 to 3 of the Particulars of Claim are admitted.",
    "2. Paragraph 4 is admitted save that the Defendant says invoices INV-2025-070 to INV-2025-075 "
    "(AED 1,860,000) relate to works on the fuel berth that were defective.",
    "3. On 20 August 2025 a fuel leak occurred at the fuel berth, closing it for 41 days. The Defendant's "
    "surveyor attributed the leak to the Claimant's faulty replacement of hose couplings in July 2025.",
    "4. The Defendant notified the Claimant of the leak by email on 21 August 2025, which was a defect notice "
    "for the purposes of clause 11.4.",
    "5. The Defendant is entitled to set off its losses of AED 2,300,000 (lost berth revenue and remediation) "
    "against any sums due. Alternatively the Defendant counterclaims that sum.",
    "6. It is denied that the Claimant is entitled to the sum claimed or to interest.",
]

ORDER = [
    "IN THE COURTS OF THE DUBAI INTERNATIONAL FINANCIAL CENTRE",
    "Claim No. CFI-201/2026",
    "ORDER OF JUDICIAL OFFICER MARIAM HADDAD",
    "Dated 28 April 2026",
    "UPON the Case Management Conference held on 27 April 2026",
    "IT IS HEREBY ORDERED THAT:",
    "1. The Claimant's application for immediate judgment on invoices INV-2025-061 to INV-2025-069",
    "   (AED 2,990,000) is reserved to the trial judge.",
    "2. The parties shall exchange witness statements by 30 June 2026.",
    "3. Each party may rely on one expert in marine engineering; reports by 31 July 2026.",
    "4. The trial is listed for 5 days commencing 12 October 2026.",
    "5. Costs in the case.",
]


def _docx(path: pathlib.Path, paras: list[str]) -> None:
    doc = Document()
    for p in paras:
        doc.add_paragraph(p)
    doc.save(path)


def _pdf(path: pathlib.Path, lines: list[str]) -> None:
    """Minimal single-page text PDF (no third-party dependency)."""
    def esc(s: str) -> str:
        return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

    text = "BT /F1 11 Tf 50 790 Td 15 TL " + " ".join(f"({esc(l)}) '" for l in lines) + " ET"
    objs = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        f"<< /Length {len(text)} >>\nstream\n{text}\nendstream",
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, o in enumerate(objs, 1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n{o}\nendobj\n".encode("latin-1")
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    out += "".join(f"{off:010d} 00000 n \n" for off in offsets).encode()
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    path.write_bytes(bytes(out))


def main() -> None:
    OUT.mkdir(exist_ok=True)
    _pdf(OUT / "Claim Form - Falcon Reach v Opal Crescent.pdf", CLAIM_FORM)
    _docx(OUT / "Particulars of Claim.docx", PARTICULARS)
    _docx(OUT / "Defence and Counterclaim.docx", DEFENCE)
    _pdf(OUT / "Order of 28 April 2026.pdf", ORDER)
    print(f"wrote sample case to {OUT}")


if __name__ == "__main__":
    main()
