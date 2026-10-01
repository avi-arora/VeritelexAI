// Demo data for the VeriteLex AI prototype. Every report screen renders the
// CFI-114/2026 matter; replace with API calls once a backend exists.

export type Tone = "green" | "blue" | "amber" | "red" | "grey";

export const TONE: Record<Tone, { fg: string; bg: string }> = {
  green: { fg: "#2E6B4F", bg: "#e7f0ea" },
  blue: { fg: "#245C86", bg: "#e8f0f7" },
  amber: { fg: "#8F6A1E", bg: "#f7f0e0" },
  red: { fg: "#9B3E35", bg: "#f8eae8" },
  grey: { fg: "#5c646d", bg: "#f0eeea" },
};

const DIFC_URL = "https://www.difccourts.ae/rules-decisions/judgments-orders";

export const REPORT_CASE_ID = "cfi-114-2026";

/* ───────────── Cases ───────────── */

export type CaseStatus = "queued" | "ingesting" | "ai" | "ready" | "action";

export type CaseSummary = {
  no: string;
  title: string;
  type: string;
  division: string;
  docs: string;
  pages: string;
  status: CaseStatus;
  pct?: number;
  /** For "action" cases: which pipeline step needs attention (1–4). */
  at?: number;
  note: string;
  updated: string;
  past?: boolean;
  isNew?: boolean;
};

export const BASE_CASES: CaseSummary[] = [
  { no: "CFI-114/2026", title: "Meridian Gulf Contracting LLC v Aurora Vertex Developments Ltd", type: "Construction · delay, variations, liquidated damages", division: "Technology & Construction", docs: "46 documents", pages: "1,842 pages", status: "ready", note: "Report generated 29 Sep 2026 · 12 dated facts · 6 issues", updated: "2 days ago" },
  { no: "CFI-089/2026", title: "Nadir Al Owais v Helvetic Private Bank (DIFC Branch)", type: "Banking · mis-selling of structured notes", division: "Court of First Instance", docs: "31 documents", pages: "612 pages", status: "ai", pct: 62, note: "Mapping facts to decided cases · about 6 min left", updated: "Just now" },
  { no: "CFI-097/2026", title: "In the matter of Solstice Holdings Ltd (in liquidation)", type: "Insolvency · liquidator directions", division: "Court of First Instance", docs: "88 documents", pages: "2,905 pages", status: "ingesting", pct: 41, note: "Reading documents · 1,190 of 2,905 pages", updated: "4 min ago" },
  { no: "CFI-121/2026", title: "Sabine Kessler v Orbital Freight FZ-LLC", type: "Employment · end-of-service and Art. 19 penalty", division: "Court of First Instance", docs: "12 documents", pages: "147 pages", status: "action", at: 2, note: "Confirm party name — two spellings found in the pleadings", updated: "1 hour ago" },
  { no: "CFI-076/2026", title: "Bright Harbour Logistics LLC v Delta Meridian Insurance PJSC", type: "Jurisdiction challenge · RDC Part 12", division: "Court of First Instance", docs: "9 documents", pages: "96 pages", status: "action", at: 1, note: "14 scanned pages unreadable — re-upload a clearer copy", updated: "Yesterday" },
  { no: "ARB-014/2026", title: "Zenith Petrochem DMCC v Larkspur Trading Ltd", type: "Arbitration · application to set aside an award", division: "Arbitration", docs: "22 documents", pages: "388 pages", status: "ready", note: "Report generated 18 Sep 2026", updated: "13 days ago" },
  { no: "DEC-006/2026", title: "Kalix Labs FZ-LLC v Northgate Data Services Ltd", type: "Digital economy · SaaS outage and data loss", division: "Digital Economy Court", docs: "27 documents", pages: "431 pages", status: "ready", note: "Report generated 02 Sep 2026", updated: "4 weeks ago" },
  { no: "CFI-052/2025", title: "Harbourline Marine LLC v Vantage Estates Ltd (enforcement)", type: "Construction · liquidated damages", division: "Technology & Construction", docs: "38 documents", pages: "1,120 pages", status: "ready", past: true, note: "Judgment delivered 14 Mar 2026", updated: "Mar 2026" },
  { no: "CFI-018/2025", title: "Corniche Assets Ltd v Pelican Bay Holdings", type: "Shareholder dispute · unfair prejudice", division: "Court of First Instance", docs: "41 documents", pages: "905 pages", status: "ready", past: true, note: "Judgment delivered 09 Dec 2025", updated: "Dec 2025" },
];

export const STATUS: Record<CaseStatus, { label: string; fg: string; step: number }> = {
  queued: { label: "Uploaded · waiting to start", fg: "#5c646d", step: 1 },
  ingesting: { label: "Reading documents", fg: "#245C86", step: 2 },
  ai: { label: "AI analysis running", fg: "#245C86", step: 3 },
  ready: { label: "Report ready", fg: "#2E6B4F", step: 4 },
  action: { label: "Action required", fg: "#8F6A1E", step: 0 },
};

/** The case created by the upload flow; its status is simulated client-side. */
export const NEW_CASE = {
  no: "CFI-142/2026",
  title: "Halcyon Marine Services LLC v Qasr Al Bahr Properties Ltd",
  type: "Commercial contract · unpaid invoices and set-off",
  division: "Court of First Instance",
  docs: "5 documents",
  pages: "312 pages",
  totalPages: 312,
};

/* ───────────── Upload ───────────── */

export const NEW_FILES = [
  { n: "Claim Form — Halcyon v Qasr Al Bahr.pdf", t: "Claim Form", p: "14 pp", ext: "PDF" },
  { n: "Particulars of Claim.docx", t: "Particulars of Claim", p: "38 pp", ext: "DOC" },
  { n: "Defence and Counterclaim.pdf", t: "Defence", p: "41 pp", ext: "PDF" },
  { n: "Marine services agreement 2024.pdf", t: "Contract", p: "86 pp", ext: "PDF" },
  { n: "Invoices and correspondence (scanned).pdf", t: "Correspondence", p: "133 pp", ext: "PDF" },
];

export const CASE_FIELDS = [
  { k: "Claim number", v: "CFI-142/2026", src: "From Claim Form, page 1", full: false },
  { k: "Division", v: "Court of First Instance", src: "From Claim Form, page 1", full: false },
  { k: "Case title", v: "Halcyon Marine Services LLC v Qasr Al Bahr Properties Ltd", src: "From Claim Form, page 1", full: true },
  { k: "Claimant", v: "Halcyon Marine Services LLC", src: "From Particulars of Claim ¶1", full: false },
  { k: "Defendant", v: "Qasr Al Bahr Properties Ltd", src: "From Particulars of Claim ¶2", full: false },
  { k: "Case type", v: "Commercial contract · unpaid invoices and set-off", src: "Suggested from the pleadings", full: false },
  { k: "Amount claimed", v: "AED 9,420,000", src: "From Claim Form, box 4", full: false },
];

export const PIPELINE = [
  { t: "Uploaded", b: "Files are stored in the UAE and checked for completeness.", c: "#b8b4ad" },
  { t: "Reading documents", b: "Text is extracted, scans are OCR’d, and dates, parties and clauses are identified.", c: "#7fa5c4" },
  { t: "AI analysis running", b: "Chronology, issues and submissions are built and mapped to decided cases.", c: "#245C86" },
  { t: "Report ready", b: "Shown with a green tick. Open it from the Cases list.", c: "#2E6B4F" },
  { t: "Action required", b: "Shown if we need you — for example an unreadable scan or a party name to confirm.", c: "#C8922E" },
];

/* ───────────── Report: CFI-114/2026 ───────────── */

export const BACKGROUND = [
  "In March 2023 Aurora Vertex Developments Ltd engaged Meridian Gulf Contracting LLC to design and build the Aurora Vertex Tower on Plot D-12 in the DIFC, for a lump sum of USD 214 million under an amended FIDIC Yellow Book. Clause 20.6 opts in to the jurisdiction of the DIFC Courts.",
  "The works ran late. The Contractor says the delay came from changes the Employer instructed to the façade and from late access, and that it was wrongly refused an extension of time. The Employer says the changes were never validly instructed, notice was given late, and it was entitled to deduct liquidated damages of USD 42,000 a day — USD 6.4 million in all — before terminating for convenience in September 2025.",
  "The Contractor claims USD 48.2 million for variations, prolongation, repayment of liquidated damages and wrongful termination. A challenge to jurisdiction was dismissed in April 2026. Liability is listed for trial from 19 October 2026; quantum is stayed. Judgment on the liquidated-damages application is reserved.",
];

export const KEY_FACTS = [
  { k: "Claimant", v: "Meridian Gulf Contracting LLC (Contractor)" },
  { k: "Defendant", v: "Aurora Vertex Developments Ltd (Employer)" },
  { k: "Contract", v: "FIDIC Yellow Book 1999, amended · 14 Mar 2023 · USD 214.0m" },
  { k: "Amount claimed", v: "USD 48.2m" },
  { k: "Stage", v: "Liability trial listed 19–26 Oct 2026 · quantum stayed" },
  { k: "Presiding", v: "H.E. Justice Amina R. Farouk" },
];

export type MatrixFact = { d: string; t: string; b: string; src: string; st: string; tone: Tone; iss: number[] };

export const MATRIX: MatrixFact[] = [
  { d: "14 Mar 2023", t: "Contract signed", b: "Design-build contract for the Aurora Vertex Tower, USD 214.0m. Clause 20.6 opts in to the DIFC Courts.", src: "Contract, Bundle A/12", st: "Agreed", tone: "green", iss: [1] },
  { d: "02 Apr 2023", t: "Works begin", b: "The Engineer certifies the commencement date. Time for completion: 865 days.", src: "Bundle A/61", st: "Agreed", tone: "green", iss: [] },
  { d: "11 Sep 2023", t: "Façade change communicated", b: "The Employer emails a revised curtain-wall specification. The Claimant treats it as an instruction (VO-07); the Defendant says it was only a design comment.", src: "Bundle B/104", st: "Disputed", tone: "red", iss: [2, 3] },
  { d: "20 Oct 2023", t: "Delay notice served", b: "The Contractor claims 39 days under cl. 20.1. Whether it was served within 28 days is disputed.", src: "Bundle B/211", st: "Disputed", tone: "red", iss: [3] },
  { d: "07 Jan 2024", t: "Extension of time refused", b: "The Engineer's determination ENG-DET-014 refuses any extension. The programme analysis it relies on is not in the bundle.", src: "Bundle C/44", st: "Agreed", tone: "green", iss: [3, 4] },
  { d: "22 Feb 2024", t: "Further variations said to be instructed orally", b: "VO-08 to VO-11 at site meeting no. 41. The minutes were never counter-signed.", src: "Bundle B/338", st: "Disputed", tone: "red", iss: [2] },
  { d: "15 Aug 2024", t: "Time for completion expires", b: "No extension of time has been granted.", src: "Agreed chronology ¶11", st: "Agreed", tone: "green", iss: [4, 5] },
  { d: "30 Sep 2024", t: "Employer begins deducting liquidated damages", b: "USD 42,000 a day under cl. 8.7, reaching USD 6.40m in total.", src: "Bundle C/118", st: "Agreed", tone: "green", iss: [5] },
  { d: "18 Feb 2025", t: "Global prolongation claim served", b: "USD 11.60m, not divided between its causes.", src: "Bundle B/604", st: "Agreed", tone: "green", iss: [6] },
  { d: "09 Sep 2025", t: "Contract terminated for convenience", b: "The Employer serves notice under cl. 15.5.", src: "Bundle C/301", st: "Agreed", tone: "green", iss: [] },
  { d: "27 Apr 2026", t: "Jurisdiction challenge dismissed", b: "Order 3: the cl. 20.6 opt-in was not displaced by Addendum No. 2.", src: "Order 3", st: "Decided", tone: "blue", iss: [1] },
  { d: "05 Aug 2026", t: "Liquidated-damages application heard", b: "Order 7: judgment reserved; a short note on the anchor-tenant agreements directed.", src: "Order 7", st: "Reserved", tone: "amber", iss: [5] },
];

/** Each party's pleaded version of the MATRIX entry at the same index. */
export const PARTY_VIEWS: { cv: string; cRef: string; dv: string; dRef: string; ground: string[]; b2?: string }[] = [
  { cv: "Contract signed; cl. 20.6 gives the DIFC Courts exclusive jurisdiction.", cRef: "Particulars ¶4", dv: "Admitted. Says cl. 20.6 was later replaced by Addendum No. 2 (12 Jan 2024).", dRef: "Defence ¶3", ground: ["Contract, Bundle A/12", "Admitted in Defence ¶3"] },
  { cv: "Works began on 02 Apr 2023.", cRef: "Particulars ¶6", dv: "Admitted.", dRef: "Defence ¶4", ground: ["Engineer's certificate, Bundle A/61"] },
  { cv: "The Employer instructed a revised curtain-wall system — variation VO-07, worth USD 3.9m.", cRef: "Particulars ¶19", dv: "A design comment only. No instruction was given under cl. 13.", dRef: "Defence ¶21", ground: ["Email of 11 Sep 2023, Bundle B/104"], b2: "The email was sent. Whether it was an instruction is disputed." },
  { cv: "Notice served within 28 days of becoming aware of the delay on 04 Oct 2023.", cRef: "Particulars ¶61", dv: "Notice received, but late — the Contractor was aware on 11 Sep 2023.", dRef: "Defence ¶55", ground: ["Notice letter, Bundle B/211", "Receipt admitted, Defence ¶55"] },
  { cv: "Refused without a proper programme analysis.", cRef: "Particulars ¶66", dv: "Properly refused by the Engineer under cl. 3.5.", dRef: "Defence ¶60", ground: ["ENG-DET-014, Bundle C/44"] },
  { cv: "VO-08 to VO-11 were instructed orally at site meeting no. 41.", cRef: "Particulars ¶44", dv: "No instruction was given; the minutes were never agreed.", dRef: "Defence ¶36", ground: ["Unsigned minutes, Bundle B/338"] },
  { cv: "", cRef: "", dv: "Time for completion expired on 15 Aug 2024 with no extension granted.", dRef: "Defence ¶64", ground: ["Agreed chronology ¶11"], b2: "Time for completion expired. The Claimant says time was at large (Particulars ¶80)." },
  { cv: "The deductions of USD 6.40m were unlawful and must be repaid.", cRef: "Particulars ¶112", dv: "Liquidated damages deducted at USD 42,000 a day from 30 Sep 2024.", dRef: "Defence ¶67", ground: ["Payment records, Bundle C/118"] },
  { cv: "Prolongation claim of USD 11.60m served.", cRef: "Particulars ¶95", dv: "Received, but not properly particularised.", dRef: "Defence ¶91", ground: ["Claim document, Bundle B/604"] },
  { cv: "Termination was a device to avoid paying for the variations.", cRef: "Particulars ¶111", dv: "A valid termination for convenience on 28 days' notice.", dRef: "Defence ¶107", ground: ["Notice of termination, Bundle C/301"] },
  { cv: "Order 3 dismissed the jurisdiction challenge.", cRef: "Reply ¶2", dv: "Permission to appeal sought (CA-021/2026).", dRef: "Appeal notice", ground: ["Order 3", "Court file"] },
  { cv: "Judgment reserved.", cRef: "Skeleton ¶1", dv: "Judgment reserved; note on anchor-tenant agreements due.", dRef: "Response ¶2", ground: ["Order 7", "Court file"] },
];

export type ChronoEntry = {
  d: string; t: string; b: string; st: string; tone: Tone; iss: number[];
  cv: string; cRef: string; dv: string; dRef: string; ground: string[];
  side: "both" | "c" | "d";
  /** Index into MATRIX, or -1 for facts only one party pleads. */
  i: number;
};

const PARTY_ONLY: ChronoEntry[] = [
  { d: "04 Mar 2024", t: "MEP subcontractor falls behind", side: "d", dv: "The MEP subcontractor was 31 days behind programme — the real cause of the delay.", dRef: "Defence ¶74", cv: "", cRef: "", b: "Asserted by the Defendant only. The MEP programme rev. 9 shows 22 days of float in this window, which partly supports it.", ground: ["MEP programme rev. 9, Bundle C/212 (partial)"], st: "One side only", tone: "grey", iss: [4], i: -1 },
  { d: "06 Nov 2024", t: "Substantial completion said to be achieved", side: "c", cv: "Levels 1–24 were substantially complete; liquidated damages should stop from this date.", cRef: "Particulars ¶88", dv: "", dRef: "", b: "Asserted by the Claimant only. No completion certificate is in the bundle; Taking-Over was certified on 12 Dec 2024.", ground: ["Taking-Over Certificate, Bundle B/511 (contradicts)"], st: "One side only", tone: "grey", iss: [5], i: -1 },
];

/** Agreed matrix, party pleadings and one-sided facts merged into one date-ordered chronology. */
export const CHRONOLOGY: ChronoEntry[] = MATRIX.map((m, i): ChronoEntry => {
  const pv = PARTY_VIEWS[i];
  return { d: m.d, t: m.t, st: m.st, tone: m.tone, iss: m.iss, cv: pv.cv, cRef: pv.cRef, dv: pv.dv, dRef: pv.dRef, ground: pv.ground, b: pv.b2 || m.b, i, side: "both" };
})
  .concat(PARTY_ONLY)
  .sort((a, b) => Date.parse(a.d) - Date.parse(b.d));

export type Decision = { name: string; cite: string; court: string; date: string; rel: string; tone: Tone; how: string; via: string; href: string };

const D = (name: string, cite: string, court: string, date: string, rel: string, tone: Tone, how: string, via: string, href: string): Decision =>
  ({ name, cite, court, date, rel, tone, how, via, href });

export const MAPPING: { facts: number[]; d: string; t: string; iss: string; decisions: Decision[] }[] = [
  { facts: [0, 10], d: "14 Mar 2023 · 27 Apr 2026", t: "Jurisdiction opt-in and its challenge", iss: "Issue 1", decisions: [
    D("Order 3 — Jurisdiction", "CFI-114/2026", "DIFC CFI (this case)", "27 Apr 2026", "This case", "blue", "Held that the cl. 20.6 opt-in survives Addendum No. 2. Costs to the Claimant.", "Case record", "#"),
    D("Corniche Assets Ltd v Delta Ridge Ltd", "[2021] DIFC CA 004", "DIFC Court of Appeal", "18 May 2021", "Binding", "blue", "An express opt-in survives a later, general choice-of-court clause. Followed in Order 3.", "DIFC Courts Judgments", DIFC_URL),
  ] },
  { facts: [2, 5], d: "11 Sep 2023 · 22 Feb 2024", t: "Variations without written confirmation", iss: "Issue 2", decisions: [
    D("Al Rafi Contracting LLC v Pearl Crescent Development Ltd", "[2023] DIFC CFI 041", "DIFC Court of First Instance", "09 Oct 2023", "Applied", "green", "An oral instruction cannot be valued as a variation without the written confirmation the contract requires.", "DIFC Courts Judgments · Harvey", DIFC_URL),
  ] },
  { facts: [3, 4], d: "20 Oct 2023 · 07 Jan 2024", t: "Notice of delay and refused extension", iss: "Issue 3", decisions: [
    D("Emirates Structural Works LLC v Sunridge FZE", "[2024] DIFC CA 007", "DIFC Court of Appeal", "21 Mar 2024", "Binding", "blue", "Notice clauses framed as 'entitled … only if' are conditions precedent.", "DIFC Courts Judgments", DIFC_URL),
    D("Obrascon Huarte Lain SA v HM Attorney General for Gibraltar", "[2014] EWHC 1028 (TCC)", "High Court of England & Wales (TCC)", "16 Apr 2014", "Persuasive", "grey", "FIDIC cl. 20.1 is a condition precedent; time runs from when the contractor should have been aware of the delay.", "Harvey · BAILII", "https://www.bailii.org/ew/cases/EWHC/TCC/2014/1028.html"),
    D("Ridgeway Tower Ltd v Kestrel Facades LLC", "[2020] DIFC CFI 026", "DIFC Court of First Instance", "02 Jun 2020", "Doubted", "red", "Held notice waived by the Engineer's conduct. Reasoning doubted in Emirates Structural Works ¶52.", "Citation graph", DIFC_URL),
  ] },
  { facts: [4, 6], d: "07 Jan 2024 · 15 Aug 2024", t: "Prevention and time at large", iss: "Issue 4", decisions: [
    D("Multiplex Constructions (UK) Ltd v Honeywell Control Systems Ltd", "[2007] EWHC 447 (TCC)", "High Court of England & Wales (TCC)", "06 Mar 2007", "Persuasive", "grey", "When acts of prevention set time at large, and how an extension-of-time clause avoids that.", "Harvey · BAILII", "https://www.bailii.org/ew/cases/EWHC/TCC/2007/447.html"),
  ] },
  { facts: [7, 11], d: "30 Sep 2024 · 05 Aug 2026", t: "Liquidated damages at USD 42,000 a day", iss: "Issue 5", decisions: [
    D("Cavendish Square Holding BV v Makdessi", "[2015] UKSC 67", "UK Supreme Court", "04 Nov 2015", "Followed in DIFC", "green", "The penalty test: is the clause out of all proportion to a legitimate interest in performance?", "Harvey · BAILII", "https://www.bailii.org/uk/cases/UKSC/2015/67.html"),
    D("Harbourline Marine LLC v Vantage Estates Ltd", "[2022] DIFC CFI 018", "DIFC Court of First Instance", "14 Jul 2022", "Applied", "green", "A daily rate tied to the employer's financing exposure was upheld. That contract had a cap; this one does not.", "DIFC Courts Judgments", DIFC_URL),
    D("Kailash Nath Associates v Delhi Development Authority", "(2015) 4 SCC 136", "Supreme Court of India", "09 Jan 2015", "Persuasive · non-DIFC", "grey", "Under s. 74 of the Indian Contract Act, recovery is limited to reasonable compensation. Different statutory basis.", "SCC Online", "#"),
    D("Order 7 — Liquidated damages", "CFI-114/2026", "DIFC CFI (this case)", "05 Aug 2026", "Reserved", "amber", "Argument heard; judgment reserved. Note on anchor-tenant agreements directed.", "Case record", "#"),
  ] },
  { facts: [8], d: "18 Feb 2025", t: "Global prolongation claim", iss: "Issue 6", decisions: [
    D("Walter Lilly & Co Ltd v Mackay", "[2012] EWHC 1773 (TCC)", "High Court of England & Wales (TCC)", "11 Jul 2012", "Persuasive", "grey", "A global claim may succeed where the records make apportionment impossible.", "Harvey · BAILII", "https://www.bailii.org/ew/cases/EWHC/TCC/2012/1773.html"),
    D("Northcape Engineering LLC v Silver Sands JV", "[2025] DIFC CFI 052", "DIFC Court of First Instance", "03 Jun 2025", "Applied", "green", "Global claim struck out where a court-ordered Scott Schedule was not complied with. Qualifies Walter Lilly.", "DIFC Courts Judgments", DIFC_URL),
    D("Order 5 — Case management", "CFI-114/2026", "DIFC CFI (this case)", "19 Jun 2026", "This case", "blue", "Split trial ordered; Scott Schedule for VO-07 to VO-11 directed.", "Case record", "#"),
  ] },
];

/** Number of decisions mapped to the MATRIX fact at index i. */
export const mapCount = (i: number) =>
  MAPPING.filter((g) => g.facts.includes(i)).reduce((a, g) => a + g.decisions.length, 0);

export const TOTAL_DECISIONS = MAPPING.reduce((a, g) => a + g.decisions.length, 0);

export type Issue = { n: number; topic: string; q: string; law: string; st: string; tone: Tone };

export const ISSUES: Issue[] = [
  { n: 1, topic: "Jurisdiction", q: "Do the DIFC Courts have jurisdiction, given the opt-in at cl. 20.6 and the later Addendum No. 2?", law: "JAL Art. 5(A)(1)(a) · RDC Part 12", st: "Decided · Order 3", tone: "blue" },
  { n: 2, topic: "Variations", q: "Were VO-08 to VO-11 valid variations without the written confirmation required by cl. 13.3.1?", law: "Contract cl. 13.3, 13.3.1", st: "For trial", tone: "grey" },
  { n: 3, topic: "Notice of delay", q: "Is the cl. 20.1 notice a condition precedent to an extension of time, and was it given in time?", law: "Contract cl. 20.1, 8.4", st: "For trial", tone: "grey" },
  { n: 4, topic: "Prevention", q: "Did the Employer's own acts prevent completion, so that time was set at large?", law: "Prevention principle", st: "For trial", tone: "grey" },
  { n: 5, topic: "Liquidated damages", q: "Is USD 42,000 a day a penalty — out of all proportion to the Employer's legitimate interest?", law: "Contract cl. 8.7 · penalty rule", st: "Reserved · Order 7", tone: "amber" },
  { n: 6, topic: "Global claim", q: "Can the prolongation claim go forward without dividing the loss between its causes?", law: "RDC Part 17 · Order 5", st: "For trial", tone: "grey" },
];

export const SUBS: Record<number, { c: string[]; cRef: string; d: string[]; dRef: string; pos: string }> = {
  1: { c: ["Clause 20.6 is an express, written opt-in to the DIFC Courts.", "Addendum No. 2 dealt only with scope and price; it says nothing about jurisdiction."], cRef: "Reply ¶12–19", d: ["Addendum No. 2 restated the whole contract, and its Dubai Courts clause replaced cl. 20.6.", "Alternatively, the Joint Judicial Committee should decide which court is competent."], dRef: "Application ¶8–24", pos: "Decided for the Claimant — Order 3, 27 Apr 2026." },
  2: { c: ["Written confirmation under cl. 13.3.1 is a formality, not a condition of payment.", "The Employer knew the work was being done and paid part of it under PC-13."], cRef: "Particulars of Claim ¶41–58", d: ["No written confirmation exists, so the variations cannot be valued.", "The part payment was made under protest and reversed in PC-14."], dRef: "Defence ¶33–52", pos: "Not yet decided. For the liability trial." },
  3: { c: ["Notice was given within 28 days of the Contractor becoming aware of the delay.", "On its wording, cl. 20.1 is not a condition precedent."], cRef: "Particulars of Claim ¶61–74", d: ["The Contractor was aware on 11 Sep 2023, so notice was 11 days late.", "Clause 20.1 says the Contractor is entitled 'only if' notice is given — a condition precedent."], dRef: "Defence ¶55–70", pos: "Not yet decided. For the liability trial." },
  4: { c: ["The façade redesign, late access to Zone 3 and the refused extension together prevented completion.", "Time is therefore at large and liquidated damages cannot be levied."], cRef: "Particulars of Claim ¶77–92", d: ["Each event ran alongside the Contractor's own delay on the MEP works.", "Concurrent delay does not engage the prevention principle."], dRef: "Defence ¶73–88", pos: "Not yet decided. For the liability trial." },
  5: { c: ["USD 42,000 a day was never calculated by reference to any likely loss.", "It is out of all proportion to any legitimate interest and is a penalty."], cRef: "Skeleton argument ¶6–29", d: ["The rate reflects financing, marketing and anchor-tenant exposure.", "Proportionality is judged at the date of the contract, not with hindsight."], dRef: "Response ¶9–34", pos: "Reserved — Order 7, 05 Aug 2026." },
  6: { c: ["The causes cannot be separated because of the Employer's own poor records.", "A global claim is therefore permissible."], cRef: "Particulars of Claim ¶95–108", d: ["Causation is not pleaded and the claim should be struck out.", "The Scott Schedule ordered by Order 5 is still incomplete."], dRef: "Defence ¶91–104", pos: "Not yet decided. For the liability trial." },
};

export type Coverage = "full" | "partial" | "none";

export const GROUND: Record<string, { short: string; type: string; meta: string; sum: string; auth: string[]; cov: [Coverage, string][] }> = {
  difc: { short: "DIFC Courts", type: "Court judgments", meta: "Queried 29 Sep 2026 · 38 results · 12 relevant", sum: "The primary source for this case. Returns the binding Court of Appeal authority on notice and the DIFC first-instance line on variations, liquidated damages and global claims.", auth: ["Emirates Structural Works LLC v Sunridge FZE [2024] DIFC CA 007", "Harbourline Marine LLC v Vantage Estates Ltd [2022] DIFC CFI 018", "Northcape Engineering LLC v Silver Sands JV [2025] DIFC CFI 052"], cov: [["full", "Corniche Assets and the opt-in jurisdiction line."], ["full", "Al Rafi Contracting [2023] DIFC CFI 041 on written confirmation."], ["full", "Emirates Structural Works [2024] DIFC CA 007 — binding."], ["partial", "No DIFC decision squarely on prevention; English TCC authority applied in practice."], ["full", "Harbourline Marine [2022] DIFC CFI 018 applies Cavendish."], ["full", "Northcape Engineering [2025] DIFC CFI 052 qualifies Walter Lilly."]] },
  google: { short: "Google", type: "Web search", meta: "Grounded search · 24 pages read · 4 cited", sum: "Useful for procedural material the Court publishes: practice directions, RDC amendments and jurisdiction guidance. Commentary is shown but never relied on as authority.", auth: ["difccourts.ae — RDC Part 31 amendments, effective 1 Jan 2026", "difccourts.ae — Jurisdiction of the DIFC Courts"], cov: [["partial", "DIFC Courts jurisdiction guidance; no case law."], ["none", "Law-firm commentary only."], ["none", "Commentary on Obrascon; not authority."], ["partial", "RDC Part 31 amendments on expert evidence."], ["none", "Summaries of Cavendish; not authority."], ["none", "Nothing authoritative."]] },
  bing: { short: "Bing", type: "Web search", meta: "Grounded search · 19 pages read · 2 cited", sum: "Largely overlaps with Google Search. Returned the same Court guidance pages and one further DIFC Courts release on the 2026 rule changes.", auth: ["difccourts.ae — Release on the 2026 RDC amendments"], cov: [["partial", "Same jurisdiction guidance as Google Search."], ["none", "Nothing authoritative."], ["none", "Nothing authoritative."], ["partial", "Release on the RDC Part 31 amendments."], ["none", "Commentary only."], ["none", "Nothing returned."]] },
  harvey: { short: "Harvey AI", type: "Legal AI", meta: "Research memo · 6 pages · 9 authorities", sum: "Covers variations, prevention and liquidated damages in full; notice and global claims in part. Relies mainly on English TCC authority and two DIFC first-instance decisions.", auth: ["Cavendish Square Holding BV v Makdessi [2015] UKSC 67", "Obrascon Huarte Lain SA v HM AG for Gibraltar [2014] EWHC 1028 (TCC)"], cov: [["partial", "Discusses opt-in clauses in general; does not cite Corniche Assets."], ["full", "Memo §3 applies Al Rafi and English authority on written confirmation."], ["partial", "Cites Obrascon. Misses the binding Court of Appeal decision in Emirates Structural Works."], ["full", "Memo §5 on prevention and concurrent delay, citing Multiplex."], ["full", "Memo §6 applies Cavendish and cites Harbourline."], ["partial", "Cites Walter Lilly, but not Northcape (2025), which qualifies it."]] },
  scc: { short: "SCC Online", type: "Case law database", meta: "Queried 29 Sep 2026 · 14 results · 2 relevant", sum: "Coverage is limited to liquidated damages, through the Indian Contract Act s. 74 line of authority. Persuasive only; the statutory basis differs from DIFC law.", auth: ["Kailash Nath Associates v DDA (2015) 4 SCC 136", "ONGC Ltd v Saw Pipes Ltd (2003) 5 SCC 705"], cov: [["none", "No DIFC jurisdiction material returned."], ["none", "Results concern Indian public-works contracts; not relevant."], ["none", "Nothing returned."], ["none", "Nothing returned."], ["partial", "Indian s. 74 line (Kailash Nath; ONGC v Saw Pipes). Persuasive only."], ["none", "Nothing returned."]] },
  bailii: { short: "BAILII", type: "Case law database", meta: "Queried 29 Sep 2026 · 41 results · 6 relevant", sum: "Strong on the English authorities the DIFC Courts routinely follow. No DIFC material.", auth: ["Multiplex Constructions (UK) Ltd v Honeywell [2007] EWHC 447 (TCC)", "Walter Lilly & Co Ltd v Mackay [2012] EWHC 1773 (TCC)"], cov: [["none", "No DIFC material."], ["partial", "English authority on written variation instructions."], ["partial", "Obrascon [2014] EWHC 1028 (TCC). Persuasive only."], ["full", "Multiplex v Honeywell [2007] EWHC 447 (TCC)."], ["full", "Cavendish v Makdessi [2015] UKSC 67."], ["partial", "Walter Lilly v Mackay; no later DIFC treatment."]] },
  westlaw: { short: "Westlaw", type: "Case law database", meta: "Queried 29 Sep 2026 · 57 results · 9 relevant", sum: "English case law with Practical Law notes and subsequent treatment. Good on prevention and penalties; misses DIFC appellate authority on notice.", auth: ["Cavendish Square Holding BV v Makdessi [2015] UKSC 67", "Obrascon Huarte Lain SA v HM AG for Gibraltar [2014] EWHC 1028 (TCC)"], cov: [["partial", "Practical Law note on DIFC opt-in; no case law."], ["full", "English authority and commentary on written confirmation."], ["partial", "Obrascon with treatment; misses Emirates Structural Works."], ["full", "Multiplex with subsequent treatment."], ["full", "Cavendish and later English applications."], ["partial", "Walter Lilly; not Northcape."]] },
  lexis: { short: "Lexis+", type: "Case law database", meta: "Queried 29 Sep 2026 · 48 results · 7 relevant", sum: "Similar ground to Westlaw, with UAE commentary. Includes two DIFC first-instance decisions but not the Court of Appeal.", auth: ["Al Rafi Contracting LLC v Pearl Crescent Development Ltd [2023] DIFC CFI 041", "Walter Lilly & Co Ltd v Mackay [2012] EWHC 1773 (TCC)"], cov: [["partial", "General commentary on DIFC jurisdiction."], ["full", "Al Rafi Contracting [2023] DIFC CFI 041."], ["partial", "Obrascon; no Court of Appeal decision."], ["full", "Multiplex and textbook commentary."], ["full", "Cavendish; Harbourline noted."], ["partial", "Walter Lilly; not Northcape."]] },
  vlex: { short: "vLex", type: "Case law database", meta: "Queried 29 Sep 2026 · 33 results · 5 relevant", sum: "Broad common-law coverage including some Gulf judgments. Coverage here mirrors BAILII.", auth: ["Walter Lilly & Co Ltd v Mackay [2012] EWHC 1773 (TCC)"], cov: [["partial", "Some DIFC jurisdiction decisions indexed."], ["partial", "English authority only."], ["partial", "Obrascon only."], ["full", "Multiplex v Honeywell."], ["full", "Cavendish v Makdessi."], ["partial", "Walter Lilly only."]] },
  manupatra: { short: "Manupatra", type: "Case law database", meta: "Queried 29 Sep 2026 · 11 results · 1 relevant", sum: "Indian case law. Only the s. 74 line on liquidated damages is relevant, and only as persuasive authority.", auth: ["Kailash Nath Associates v DDA (2015) 4 SCC 136"], cov: [["none", "Nothing returned."], ["none", "Not relevant."], ["none", "Nothing returned."], ["none", "Nothing returned."], ["partial", "Kailash Nath; persuasive only."], ["none", "Nothing returned."]] },
};

/** [long label, short label, tone] */
export const COV: Record<Coverage, [string, string, Tone]> = {
  full: ["Covered", "Covered", "green"],
  partial: ["Partly covered", "Partial", "amber"],
  none: ["Not covered", "—", "grey"],
};

export const GAPS: { kind: string; tone: Tone; t: string; b: string; via: string; ref: string }[] = [
  { kind: "Binding authority missed", tone: "red", t: "Emirates Structural Works LLC v Sunridge FZE [2024] DIFC CA 007", b: "A Court of Appeal decision on condition-precedent notices, binding on Issue 3. Westlaw, Lexis+ and Harvey AI did not return it.", via: "DIFC Courts Judgments", ref: "Issue 3" },
  { kind: "Doubted authority relied on", tone: "red", t: "Ridgeway Tower Ltd v Kestrel Facades LLC [2020] DIFC CFI 026", b: "The Claimant relies on it at Reply ¶68 for waiver of notice. Its reasoning was doubted in Emirates Structural Works ¶52.", via: "Citation graph", ref: "Issue 3" },
  { kind: "Later authority", tone: "amber", t: "Northcape Engineering LLC v Silver Sands JV [2025] DIFC CFI 052", b: "Qualifies Walter Lilly on global claims where a Scott Schedule was ordered. Westlaw, Lexis+ and Harvey AI cite Walter Lilly without it.", via: "DIFC Courts Judgments", ref: "Issue 6" },
  { kind: "Missing document", tone: "amber", t: "The programme analysis behind the refused extension", b: "ENG-DET-014 refers to a programme analysis at ¶6. It is not in the bundle and neither delay expert deals with it.", via: "Case record", ref: "Issues 3 and 4" },
  { kind: "Contradiction in the record", tone: "amber", t: "Two different dates for the façade instruction", b: "The Reply dates it 11 Sep 2023; the Claimant's own delay expert uses 04 Oct 2023. The 28-day notice point turns on which is right.", via: "Case record", ref: "Issue 3" },
  { kind: "Procedural update", tone: "blue", t: "Amendments to the RDC on expert evidence", b: "The DIFC Courts published amendments to RDC Part 31 (experts) effective 1 Jan 2026 — relevant to the delay experts' joint statement.", via: "Google Search · difccourts.ae", ref: "Issue 4" },
];

export const DOCS: { n: string; p: string; by: string; s: string; tone: Tone }[] = [
  { n: "Contract documents (Bundle A)", p: "214 pages", by: "Registry", s: "Read", tone: "green" },
  { n: "Claimant correspondence and variations (Bundle B)", p: "1,104 pages", by: "Claimant", s: "Read", tone: "green" },
  { n: "Defendant documents (Bundle C)", p: "388 pages", by: "Defendant", s: "Read", tone: "green" },
  { n: "Applications and orders (Bundle D)", p: "96 pages", by: "Registry", s: "Read", tone: "green" },
  { n: "Delay expert report — Claimant", p: "112 pages", by: "Claimant", s: "Read", tone: "green" },
  { n: "Delay expert report — Defendant", p: "98 pages", by: "Defendant", s: "Read", tone: "green" },
  { n: "Scott Schedule (VO-07 to VO-11)", p: "—", by: "Claimant", s: "Not yet filed", tone: "red" },
  { n: "Note on anchor-tenant agreements", p: "—", by: "Defendant", s: "Awaited", tone: "amber" },
];

/* ───────────── Report sections ───────────── */

export const SECTIONS = [
  { k: "background", g: "Core analysis", label: "Background", title: "Brief background of the matter", desc: "What the dispute is about, in plain terms, and where it stands.", src: ["Case record"] },
  { k: "matrix", g: "Core analysis", label: "Dates and facts", star: true, title: "Summarised factual matrix", desc: "The key facts in date order, as each party pleads them and as the documents show them. The common chronology is grounded in the record and cites every source.", src: ["Particulars of Claim", "Defence", "Case record · 46 documents"] },
  { k: "mapping", g: "Core analysis", label: "Mapped to decisions", star: true, title: "Facts mapped to decisions and orders", desc: "For each group of facts: the judgments and orders that deal with them, with the date of decision and a link to the text.", src: ["DIFC Courts Judgments", "Harvey", "SCC Online", "BAILII", "Case record"] },
  { k: "issues", g: "Core analysis", label: "Legal issues", star: true, title: "Legal issues involved", desc: "The questions the Court must answer, drawn from the statements of case and reconciled with orders already made.", src: ["Case record"] },
  { k: "subs", g: "Core analysis", label: "Parties’ submissions", title: "Parties’ submissions on each issue", desc: "Each side’s position on one issue at a time, summarised from the pleading or skeleton cited.", src: ["Case record"] },
  { k: "tools", g: "Grounding", label: "Grounding sources", star: true, title: "Grounding", desc: "How each legal issue is covered by the sources the analysis was grounded in: court judgments, case-law databases, legal AI and web search.", src: ["Connected sources"] },
  { k: "gaps", g: "Grounding", label: "Beyond the sources", title: "What the research tools missed", desc: "Authorities, documents and inconsistencies the external research tools did not surface, found by VeriteLex in DIFC judgments, its citation graph and the case record.", src: ["DIFC Courts Judgments", "Citation graph", "Case record"] },
  { k: "council", g: "Model council", label: "Council pre-analysis", star: true, title: "Council pre-analysis", desc: "When the report was generated, each model read the whole record independently. This shows where they agree and where they divide, issue by issue.", src: ["Case record", "DIFC Courts Judgments", "Harvey", "BAILII"] },
  { k: "ask", g: "Model council", label: "Ask the council", star: true, title: "Ask the council", desc: "Put your own question about this case. Each model answers independently; you can also have them review each other, or set out the strongest case for each side.", src: ["Case record", "DIFC Courts Judgments", "Harvey", "BAILII", "Google Search"] },
  { k: "questions", g: "Model council", label: "Questions for counsel", title: "Questions for counsel", desc: "Questions the council suggests putting to each party, each tied to the document that raises it and showing how many models raised it.", src: ["Case record"] },
  { k: "docs", g: "Record", label: "Documents", title: "Documents on file", desc: "Everything the analysis has read, and what is still outstanding under the Court’s orders.", src: ["Case record"] },
] as const;

export type SectionKey = (typeof SECTIONS)[number]["k"];

/* ───────────── Models and council ───────────── */

export type ModelId = "claude" | "gpt" | "gemini" | "llama" | "mistral" | "jais";

export const MODELS: { id: ModelId; name: string; vendor: string; host: string; m: string; c: string; lat: string }[] = [
  { id: "claude", name: "Claude Opus", vendor: "Anthropic", host: "Cloud · UAE region", m: "C", c: "#B4613E", lat: "avg 9 s" },
  { id: "gpt", name: "GPT-5", vendor: "OpenAI", host: "Azure · UAE North", m: "G", c: "#2F6F5E", lat: "avg 11 s" },
  { id: "gemini", name: "Gemini 2.5 Pro", vendor: "Google", host: "Google Cloud · Doha", m: "Ge", c: "#3B5BA5", lat: "avg 8 s" },
  { id: "llama", name: "Llama 4 Maverick", vendor: "Meta · self-hosted", host: "On-premises · DIFC data centre", m: "L", c: "#4F5A66", lat: "avg 14 s" },
  { id: "mistral", name: "Mistral Large", vendor: "Mistral AI", host: "Cloud · EU", m: "M", c: "#C26B1E", lat: "avg 10 s" },
  { id: "jais", name: "Jais", vendor: "Inception · G42", host: "On-premises · UAE", m: "J", c: "#6B4F8A", lat: "avg 12 s" },
];

export type CiteStatus = "ok" | "warn" | "bad";
export type Cite = { t: string; note: string; st: CiteStatus };
export type Answer = { time: string; fact?: boolean; paras: string[]; cites: Cite[] };

const ok = (t: string, note: string): Cite => ({ t, note, st: "ok" });
const warn = (t: string, note: string): Cite => ({ t, note, st: "warn" });
const bad = (t: string, note: string): Cite => ({ t, note, st: "bad" });

export const CITE_ST: Record<CiteStatus, { icon: string; bg: string; noteFg: string }> = {
  ok: { icon: "✓", bg: "#2E6B4F", noteFg: "#80878f" },
  warn: { icon: "!", bg: "#B07A18", noteFg: "#8F6A1E" },
  bad: { icon: "×", bg: "#9B3E35", noteFg: "#9B3E35" },
};

const ANSWERS: Record<ModelId, Answer> = {
  claude: { time: "8.4 s", fact: true, paras: ["Yes, on authority binding this Court. Emirates Structural Works [2024] DIFC CA 007 holds that notice clauses framed as 'entitled … only if' are conditions precedent, and cl. 20.1 uses that wording.", "The decisive question is factual: when the Contractor became aware of the delay. The Defence says 11 Sep 2023; the Claimant's expert uses 04 Oct 2023. On the first date the notice is late; on the second it is in time."], cites: [ok("Emirates Structural Works [2024] DIFC CA 007", "Verified · DIFC Courts Judgments"), ok("Defence ¶55", "Verified · case record"), ok("Delay expert report ¶2.14", "Verified · case record")] },
  gpt: { time: "11.2 s", fact: false, paras: ["Clause 20.1 is likely a condition precedent. Obrascon v Gibraltar [2014] EWHC 1028 (TCC) treats the FIDIC wording that way, and Emirates Structural Works [2024] DIFC CA 007 takes the same approach in the DIFC.", "The Claimant may argue that notice was waived by the Engineer's conduct, relying on Ridgeway Tower [2020] DIFC CFI 026."], cites: [ok("Obrascon v Gibraltar [2014] EWHC 1028 (TCC)", "Verified · Harvey, BAILII"), ok("Emirates Structural Works [2024] DIFC CA 007", "Verified · DIFC Courts Judgments"), warn("Ridgeway Tower [2020] DIFC CFI 026", "Doubted in Emirates Structural Works ¶52")] },
  gemini: { time: "7.9 s", fact: false, paras: ["Emirates Structural Works [2024] DIFC CA 007 governs and treats the clause as a condition precedent.", "Time runs from when the Contractor ought reasonably to have been aware of the delay, consistent with Gulf Span Contracting v Al Noor Developments [2019] DIFC CFI 011."], cites: [ok("Emirates Structural Works [2024] DIFC CA 007", "Verified · DIFC Courts Judgments"), bad("Gulf Span Contracting v Al Noor [2019] DIFC CFI 011", "Not found in any connector")] },
  llama: { time: "13.6 s", fact: true, paras: ["The clause is a condition precedent under Emirates Structural Works [2024] DIFC CA 007.", "The record gives two dates on which the Contractor may have become aware (11 Sep and 04 Oct 2023). The Court will need to decide which applies."], cites: [ok("Emirates Structural Works [2024] DIFC CA 007", "Verified · DIFC Courts Judgments"), ok("Reply ¶34", "Verified · case record")] },
  mistral: { time: "9.8 s", fact: false, paras: ["Obrascon and Emirates Structural Works both support reading cl. 20.1 as a condition precedent.", "Nothing in the record supports reading the clause as directory only."], cites: [ok("Obrascon v Gibraltar [2014] EWHC 1028 (TCC)", "Verified · Harvey, BAILII"), ok("Emirates Structural Works [2024] DIFC CA 007", "Verified · DIFC Courts Judgments")] },
  jais: { time: "12.1 s", fact: true, paras: ["The notice clause is a condition precedent: Emirates Structural Works [2024] DIFC CA 007.", "The date of awareness is disputed between the pleadings and the expert evidence."], cites: [ok("Emirates Structural Works [2024] DIFC CA 007", "Verified · DIFC Courts Judgments"), ok("Delay expert report ¶2.14", "Verified · case record")] },
};

const ANSWERS2: Record<ModelId, Answer> = {
  claude: { time: "9.1 s", paras: ["Three documents bear directly on it: the design-team minutes for September 2023, the Contractor’s programme updates for weeks 36–40, and the Engineer’s programme analysis referred to in ENG-DET-014 ¶6.", "Only the first is in the bundle (Bundle B/97–103). The other two have not been disclosed."], cites: [ok("Bundle B/97–103", "Verified · case record"), ok("ENG-DET-014 ¶6", "Verified · case record")] },
  gpt: { time: "10.4 s", paras: ["The Contractor’s own programme updates would show when the delay was first recorded. They have not been disclosed despite the deadline in Order 5.", "The 04 Oct 2023 date used by the Claimant’s expert appears to come from an email that is not in the bundle."], cites: [ok("Order 5 ¶2", "Verified · case record"), warn("Delay expert report ¶2.14", "Source email not in the bundle")] },
  gemini: { time: "7.6 s", paras: ["The Engineer’s programme analysis is the most important missing document; it would show the Engineer’s own view of when the delay arose.", "Site diaries for September and October 2023 would also help."], cites: [ok("ENG-DET-014 ¶6", "Verified · case record"), ok("Bundle B index", "Verified · case record")] },
  llama: { time: "12.9 s", paras: ["The Contractor’s programme updates and the site diaries for September and October 2023."], cites: [ok("Bundle B index", "Verified · case record")] },
  mistral: { time: "9.2 s", paras: ["The September 2023 design-team minutes and the Contractor’s programme updates for weeks 36–40."], cites: [ok("Bundle B/97–103", "Verified · case record")] },
  jais: { time: "11.5 s", paras: ["The Engineer’s programme analysis, and the 04 Oct 2023 email relied on by the Claimant’s expert."], cites: [warn("Delay expert report ¶2.14", "Source email not in the bundle")] },
};

const ANSWERS3: Record<ModelId, Answer> = {
  claude: { time: "8.7 s", paras: ["Harbourline treated the 10% cap as one indicator of proportionality, not as decisive (¶44). Its absence here is relevant but does not by itself make the clause a penalty.", "Cavendish asks whether the clause is out of all proportion to a legitimate interest; the cap is evidence on that question, not a separate test."], cites: [ok("Harbourline [2022] DIFC CFI 018 ¶44", "Verified · DIFC Courts Judgments"), ok("Cavendish [2015] UKSC 67 ¶32", "Verified · BAILII")] },
  gpt: { time: "11.0 s", paras: ["Yes, materially. Without a cap the total exposure is unbounded, which weighs towards a penalty under Cavendish.", "The Employer’s anchor-tenant evidence, not yet filed, would be needed to justify the rate."], cites: [ok("Cavendish [2015] UKSC 67 ¶32", "Verified · BAILII"), ok("Order 7 ¶3", "Verified · case record")] },
  gemini: { time: "7.4 s", paras: ["It distinguishes Harbourline on the facts but not in principle; the test is still Cavendish."], cites: [ok("Harbourline [2022] DIFC CFI 018 ¶44", "Verified · DIFC Courts Judgments")] },
  llama: { time: "13.2 s", paras: ["The cap mattered in Harbourline; its absence helps the Claimant but is not conclusive."], cites: [ok("Harbourline [2022] DIFC CFI 018 ¶44", "Verified · DIFC Courts Judgments")] },
  mistral: { time: "9.9 s", paras: ["Indian law (Kailash Nath) would treat an uncapped rate differently, but that line does not apply in the DIFC."], cites: [warn("Kailash Nath (2015) 4 SCC 136", "Persuasive only · non-DIFC")] },
  jais: { time: "11.8 s", paras: ["The absence of a cap is relevant to proportionality; the anchor-tenant evidence is the key missing material."], cites: [ok("Order 7 ¶3", "Verified · case record")] },
};

type Synth = { agree: string[]; differ: string[]; out: string[] };

export type Preset = {
  label: string;
  q: string;
  answers: Record<ModelId, Answer>;
  when: string;
  mode: string;
  steel: { c: string[]; d: string[] };
  review: { from: ModelId; to: ModelId; self?: boolean; t: string }[];
  outcome: string;
  synth: (ids: ModelId[], nm: (id: ModelId) => string) => Synth;
};

export const PRESETS: Preset[] = [
  {
    label: "Notice as a condition precedent",
    q: "Is the cl. 20.1 notice a condition precedent to an extension of time, and which authorities govern? (Issue 3)",
    answers: ANSWERS, when: "Today, 10:12", mode: "Independent",
    steel: {
      c: ["Awareness ran from 04 Oct 2023, the date the Claimant’s own expert uses; on that date the notice is in time.", "The 11 Sep 2023 email was a design comment, so it could not have made the Contractor aware of an instruction."],
      d: ["Emirates Structural Works makes cl. 20.1 a condition precedent, and the Contractor knew of the change on 11 Sep 2023.", "The only authority for waiver, Ridgeway Tower, has been doubted by the Court of Appeal."],
    },
    review: [
      { from: "claude", to: "gpt", t: "Ridgeway Tower was doubted in Emirates Structural Works ¶52; the waiver point needs other support." },
      { from: "gpt", to: "gpt", self: true, t: "Accepts. Puts waiver as arguable only, with no authority." },
      { from: "llama", to: "gemini", t: "Gulf Span Contracting cannot be found in any connected source." },
      { from: "gemini", to: "gemini", self: true, t: "Withdraws the Gulf Span citation." },
    ],
    outcome: "After review, every model relies only on verified authority. The remaining difference is whether waiver is arguable at all.",
    synth: (ids, nm) => {
      const n = ids.length;
      const f = ids.filter((id) => ANSWERS[id].fact).length;
      const differ: string[] = [];
      const out: string[] = [];
      if (ids.includes("gpt")) differ.push(nm("gpt") + " relies on Ridgeway Tower for waiver of notice — doubted in Emirates Structural Works ¶52.");
      if (ids.includes("mistral")) differ.push(nm("mistral") + " does not address the disputed date of awareness.");
      if (ids.includes("gemini")) out.push(nm("gemini") + " cites Gulf Span Contracting v Al Noor [2019] DIFC CFI 011, which was not found in any connected source.");
      return { agree: [`${n} of ${n} identify Emirates Structural Works [2024] DIFC CA 007 as the governing authority.`, `${f} of ${n} identify the date of awareness as the deciding factual dispute.`], differ, out };
    },
  },
  {
    label: "Documents on the awareness date",
    q: "Which documents would resolve when the Contractor became aware of the delay to the façade works?",
    answers: ANSWERS2, when: "Yesterday, 16:40", mode: "Independent",
    steel: {
      c: ["The missing programme analysis is the Engineer’s document; the gap counts against the Employer’s reliance on the refusal."],
      d: ["The Contractor holds its own programme updates and has not disclosed them, despite Order 5."],
    },
    review: [
      { from: "gpt", to: "claude", t: "Bundle B/97–103 are draft minutes; their status should be confirmed." },
      { from: "claude", to: "claude", self: true, t: "Agrees, and marks them as unsigned drafts." },
    ],
    outcome: "After review, all models treat the September 2023 minutes as drafts and the two undisclosed documents as decisive.",
    synth: (ids, nm) => {
      const n = ids.length;
      const w = ids.filter((id) => id === "gpt" || id === "jais").map(nm);
      return {
        agree: [`${n} of ${n} point to the Engineer’s programme analysis or the Contractor’s programme updates as decisive.`, "None of those documents has been disclosed; only the September 2023 design-team minutes are in the bundle."],
        differ: w.length ? [w.join(" and ") + " note that the 04 Oct 2023 email used by the Claimant’s expert is not in the bundle; the others do not address it."] : [],
        out: [],
      };
    },
  },
  {
    label: "No cap on liquidated damages",
    q: "Does the absence of a cap on liquidated damages distinguish Harbourline Marine v Vantage Estates? (Issue 5)",
    answers: ANSWERS3, when: "29 Sep, 14:31", mode: "Debate",
    steel: {
      c: ["An uncapped USD 42,000 a day, set without any calculation, is the kind of clause Cavendish treats as out of all proportion."],
      d: ["Harbourline upheld a comparable rate tied to financing exposure; the cap there was one factor among several."],
    },
    review: [
      { from: "claude", to: "mistral", t: "Kailash Nath applies s. 74 of the Indian Contract Act and has no bearing on DIFC law." },
      { from: "mistral", to: "mistral", self: true, t: "Accepts, and keeps it only as a comparison." },
    ],
    outcome: "After review, all models apply Cavendish; they differ only on how much weight the missing cap carries.",
    synth: (ids, nm) => {
      const n = ids.length;
      const differ: string[] = [];
      const out: string[] = [];
      if (ids.includes("gpt")) differ.push(nm("gpt") + " treats the missing cap as weighing materially towards a penalty; the others treat it as relevant but not conclusive.");
      if (ids.includes("mistral")) out.push(nm("mistral") + " relies on Kailash Nath (Indian law) — flagged as persuasive only.");
      return { agree: [`${n} of ${n} treat Cavendish as the governing test.`], differ, out };
    },
  },
];

export const PRE: { n: number; topic: string; a: string; b: string; votes: Record<ModelId, "A" | "B"> }[] = [
  { n: 1, topic: "Jurisdiction", a: "Already decided by Order 3; jurisdiction is established.", b: "", votes: { claude: "A", gpt: "A", gemini: "A", llama: "A", mistral: "A", jais: "A" } },
  { n: 2, topic: "Variations", a: "Written confirmation is a precondition to valuation (Al Rafi).", b: "Waiver by the Employer’s conduct is arguable on the PC-13 payment.", votes: { claude: "A", gpt: "A", gemini: "B", llama: "A", mistral: "A", jais: "B" } },
  { n: 3, topic: "Notice of delay", a: "Clause 20.1 is a condition precedent; the issue turns on the date of awareness.", b: "", votes: { claude: "A", gpt: "A", gemini: "A", llama: "A", mistral: "A", jais: "A" } },
  { n: 4, topic: "Prevention", a: "Cannot be resolved on the documents; it depends on the delay experts.", b: "The façade redesign is an arguable act of prevention on the documents alone.", votes: { claude: "A", gpt: "B", gemini: "A", llama: "A", mistral: "B", jais: "A" } },
  { n: 5, topic: "Liquidated damages", a: "Turns on the anchor-tenant evidence, which has not yet been filed.", b: "The absence of a cap is the main point distinguishing Harbourline.", votes: { claude: "A", gpt: "A", gemini: "B", llama: "A", mistral: "A", jais: "A" } },
  { n: 6, topic: "Global claim", a: "Northcape applies; the outstanding Scott Schedule is central.", b: "The Walter Lilly approach remains open on these records.", votes: { claude: "A", gpt: "A", gemini: "A", llama: "B", mistral: "A", jais: "A" } },
];

export const FLAGGED = [
  { t: "The two dates for the façade instruction (11 Sep and 04 Oct 2023) decide the notice point.", ref: "Reply ¶34 · expert report ¶2.14" },
  { t: "The programme analysis behind the refused extension has not been disclosed.", ref: "ENG-DET-014 ¶6" },
];

export const COUNSEL_QS: { to: "Claimant" | "Defendant"; q: string; why: string; iss: number; ref: string; by: ModelId[] }[] = [
  { to: "Claimant", q: "On what document do you say the oral instructions of 22 Feb 2024 were confirmed in writing under cl. 13.3.1?", why: "No counter-signed minutes or written confirmation is in Bundle B.", iss: 2, ref: "Bundle B/338", by: ["claude", "gpt", "gemini", "llama", "mistral", "jais"] },
  { to: "Claimant", q: "What is the source of the 04 Oct 2023 awareness date used by your delay expert?", why: "The Reply uses 11 Sep 2023; the email the expert relies on is not in the bundle.", iss: 3, ref: "Expert report ¶2.14", by: ["claude", "gpt", "jais", "llama"] },
  { to: "Claimant", q: "How is the USD 11.60m prolongation claim divided between VO-07 and the alleged prevention?", why: "Order 5 required a Scott Schedule by 14 Aug 2026; it is still outstanding.", iss: 6, ref: "Order 5 ¶4", by: ["claude", "gemini", "mistral"] },
  { to: "Defendant", q: "What evidence from the date of the contract supports USD 42,000 a day as tied to a legitimate interest?", why: "The anchor-tenant agreements are referred to but have not been filed.", iss: 5, ref: "Order 7 ¶3", by: ["claude", "gpt", "gemini", "jais", "mistral"] },
  { to: "Defendant", q: "Why was the programme analysis referred to in ENG-DET-014 not disclosed?", why: "The refusal of an extension relies on it at ¶6.", iss: 3, ref: "ENG-DET-014 ¶6", by: ["gpt", "gemini", "llama", "jais"] },
  { to: "Defendant", q: "On what basis are liquidated damages claimed for the period after termination on 09 Sep 2025?", why: "The deduction schedule runs to 30 Nov 2025 without explanation.", iss: 5, ref: "Bundle C/118", by: ["claude", "llama"] },
];

/* ───────────── Settings ───────────── */

export type ConnectorId = "difc" | "google" | "bing" | "harvey" | "scc" | "bailii" | "westlaw" | "lexis" | "vlex" | "manupatra";

export const CONNECTORS: { id: ConnectorId; name: string; by: string; m: string; mono: string; desc: string; builtin?: boolean }[] = [
  { id: "difc", name: "DIFC Courts Judgments", by: "DIFC Courts", m: "DC", mono: "#10202e", desc: "Every published CFI, Court of Appeal, TCD, Arbitration, DEC and SCT judgment and order.", builtin: true },
  { id: "google", name: "Google Search", by: "Google", m: "G", mono: "#3B5BA5", desc: "Web grounding for court notices, practice directions and public filings." },
  { id: "bing", name: "Bing Search", by: "Microsoft", m: "Bi", mono: "#2C7A7B", desc: "Web grounding that cross-checks Google results for court notices and public filings." },
  { id: "harvey", name: "Harvey", by: "Harvey AI", m: "H", mono: "#1a1d21", desc: "Legal research memos across common-law jurisdictions." },
  { id: "scc", name: "SCC Online", by: "Eastern Book Company", m: "SCC", mono: "#8A2B2B", desc: "Indian and international case law, statutes and commentary." },
  { id: "bailii", name: "BAILII", by: "British and Irish Legal Information Institute", m: "B", mono: "#4F5A66", desc: "Free access to UK and Irish judgments." },
  { id: "westlaw", name: "Westlaw", by: "Thomson Reuters", m: "W", mono: "#C26B1E", desc: "UK and US case law, Practical Law and CoCounsel." },
  { id: "lexis", name: "Lexis+ AI", by: "LexisNexis", m: "LN", mono: "#B4313A", desc: "UK, Commonwealth and Middle East case law and commentary." },
  { id: "vlex", name: "vLex Vincent AI", by: "vLex", m: "V", mono: "#2F6F5E", desc: "Case law across 100+ jurisdictions, with AI research." },
  { id: "manupatra", name: "Manupatra", by: "Manupatra", m: "Mp", mono: "#6B4F8A", desc: "Indian case law and tribunal decisions." },
];

export const POLICIES: [string, string][] = [
  ["Every statement must cite a source", "Sentences without a citation to the record or a connected source are removed from the report."],
  ["Leave out unverified citations", "A citation not found in any connected source is flagged and excluded from comparisons."],
  ["Limit Google Search to court and government sites", "For example difccourts.ae, dfsa.ae, difc.ae, gov.ae."],
  ["Use on-premises models only for sealed documents", "Documents marked sealed or confidential are never sent to cloud models."],
  ["Show model names in the council", "If off, answers are labelled Model A, B, C to reduce anchoring."],
];

export const SETTINGS_TABS = [
  { k: "connectors", label: "Connectors" },
  { k: "council", label: "Model council" },
  { k: "policy", label: "Grounding policy" },
] as const;

export type SettingsTab = (typeof SETTINGS_TABS)[number]["k"];

export const EXPORT_SECTIONS: [string, number][] = [
  ["Background and key facts", 2],
  ["Factual matrix (dates and facts)", 4],
  ["Facts mapped to decisions and orders", 6],
  ["Legal issues", 2],
  ["Parties’ submissions by issue", 7],
  ["SCC Online, Harvey and further information", 5],
  ["Model council answers", 6],
];
