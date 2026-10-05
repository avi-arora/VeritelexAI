"""Structured-output schemas for each agent.

These are the contracts between agents. They are passed to Gemini as the
response schema and validated with Pydantic on the way back. They are kept
deliberately flat (strings, ints, enums, lists of objects) so every Gemini
model can honour them.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

DocType = Literal[
    "Claim Form", "Particulars of Claim", "Defence", "Defence and Counterclaim", "Reply",
    "Contract", "Correspondence", "Witness Statement", "Expert Report", "Order", "Judgment",
    "Skeleton Argument", "Application", "Invoice", "Minutes", "Other",
]
FiledBy = Literal["Claimant", "Defendant", "Court", "Registry", "Third party", "Unknown"]


# ---------------------------------------------------------------- ingest


class OcrPage(BaseModel):
    page: int = Field(description="1-based page number within the document")
    text: str = Field(description="Verbatim transcription of the page. Empty if unreadable.")
    readable: bool = Field(description="False if the page is blank, illegible or corrupted")


class OcrResult(BaseModel):
    pages: list[OcrPage]


class DocProfile(BaseModel):
    doc_type: DocType
    label: str = Field(description="Short human label, e.g. 'Particulars of Claim' or 'Order 3'")
    filed_by: FiledBy
    doc_date: str = Field(description="Date on the document as written, or empty")
    summary: str = Field(description="Two or three sentence neutral summary")


class Segment(BaseModel):
    ref: str  # "p. 12" | "¶ 4" | "Sheet Invoices"
    text: str


class IngestOutput(BaseModel):
    doc_id: str
    name: str
    label: str
    doc_type: str
    filed_by: str
    doc_date: str = ""
    summary: str = ""
    pages: int
    segments: list[Segment]
    unreadable: list[str] = Field(default_factory=list)
    ocr_pages: int = 0


# ---------------------------------------------------------------- background


class SourcedValue(BaseModel):
    value: str
    source: str = Field(description="Where it was found, e.g. 'Claim Form, p. 1' or 'Suggested from the pleadings'")


class CaseProfile(BaseModel):
    claim_number: SourcedValue
    division: SourcedValue
    title: SourcedValue
    claimant: SourcedValue
    defendant: SourcedValue
    case_type: SourcedValue = Field(description="'Area · specific subject', e.g. 'Construction · delay, variations'")
    amount_claimed: SourcedValue


class BackgroundOutput(BaseModel):
    profile: CaseProfile
    paragraphs: list[str] = Field(description="2-4 plain-English paragraphs: the deal, the dispute, where it stands")
    key_facts: list[KeyFactOut] = Field(description="Claimant, Defendant, Contract, Amount claimed, Stage, Presiding")
    subtitle: str = Field(description="Division · subject · amount, one line for the case header")


class KeyFactOut(BaseModel):
    label: str
    value: str


BackgroundOutput.model_rebuild()


# ---------------------------------------------------------------- facts


class ExtractedFact(BaseModel):
    date_iso: str = Field(description="YYYY-MM-DD (use 01 for unknown day/month)")
    date_text: str = Field(description="Date as a judge would write it, e.g. '14 Mar 2023'")
    title: str = Field(description="Short headline, max 8 words")
    description: str = Field(description="What happened, one or two sentences, neutral")
    asserted_by: Literal["Claimant", "Defendant", "Court", "Document"]
    position: str = Field(description="The asserting party's version in their words, or empty for neutral documents")
    ref: str = Field(description="Pinpoint within THIS document exactly as given in the segment tags, e.g. 'p. 12' or '¶ 19'")


class FactsOutput(BaseModel):
    doc_id: str = ""
    label: str = ""
    facts: list[ExtractedFact]


# ---------------------------------------------------------------- chronology


class ChronologyEntry(BaseModel):
    date_iso: str
    date_text: str
    title: str
    common: str = Field(description="What the documents show, neutral. If disputed, state only what is not in dispute and what is.")
    status: Literal["Agreed", "Disputed", "One side only", "Decided", "Reserved"]
    side: Literal["both", "c", "d"]
    claimant_view: str = ""
    claimant_ref: str = Field(default="", description="e.g. 'Particulars ¶19'")
    defendant_view: str = ""
    defendant_ref: str = ""
    ground: list[str] = Field(description="Document citations that ground the common entry, e.g. 'Contract, p. 12'")


class ChronologyOutput(BaseModel):
    entries: list[ChronologyEntry]


# ---------------------------------------------------------------- issues


class IssueDraft(BaseModel):
    n: int
    topic: str = Field(description="One or two words, e.g. 'Notice of delay'")
    question: str = Field(description="The question the Court must answer, one sentence")
    law: str = Field(description="Provisions / rules / doctrines engaged, e.g. 'Contract cl. 20.1 · RDC Part 12'")
    status_kind: Literal["decided", "reserved", "for_trial"]
    status_text: str = Field(description="e.g. 'Decided · Order 3', 'Reserved · Order 7', 'For trial'")
    fact_indices: list[int] = Field(description="Indices into the chronology list of the facts this issue turns on")


class IssuesOutput(BaseModel):
    issues: list[IssueDraft]


# ---------------------------------------------------------------- mapping


class DecisionDraft(BaseModel):
    name: str = Field(description="Case name or 'Order N — subject' for orders in this case")
    cite: str = Field(description="Neutral citation, or the claim number for this case's orders")
    court: str
    date: str = Field(description="Date of decision, e.g. '21 Mar 2024'")
    relation: Literal["This case", "Binding", "Applied", "Followed in DIFC", "Persuasive", "Persuasive · non-DIFC", "Doubted", "Reserved"]
    how: str = Field(description="How it relates to these facts, one or two sentences")
    url: str = Field(description="Full https URL of the judgment text from the search results, or empty for this case's orders")
    from_case_record: bool = Field(description="True only for orders/judgments that are documents in this case's record")


class MappingOutput(BaseModel):
    issue: int = 0
    title: str = Field(description="Short title for this group of facts")
    decisions: list[DecisionDraft]
    search_queries: list[str] = Field(default_factory=list)
    sources: list[SourceRef] = Field(default_factory=list)


class SourceRef(BaseModel):
    uri: str
    title: str = ""
    domain: str = ""


MappingOutput.model_rebuild()


# ---------------------------------------------------------------- grounding


class CoverageDraft(BaseModel):
    coverage: Literal["full", "partial", "none"]
    note: str = Field(description="One sentence on what the sources returned for this issue")
    authorities: list[str] = Field(description="Most relevant authorities found, as 'Name [citation]'")


class CoverageOutput(BaseModel):
    issue: int = 0
    coverage: str = "none"
    note: str = ""
    authorities: list[str] = Field(default_factory=list)
    search_queries: list[str] = Field(default_factory=list)
    sources: list[SourceRef] = Field(default_factory=list)


class SupportCheck(BaseModel):
    index: int
    verdict: Literal["supported", "partial", "unsupported"]


class SupportBatch(BaseModel):
    checks: list[SupportCheck]


class VerifyOutput(BaseModel):
    chronology_verified: list[bool]
    ground_kept: list[list[str]]
    decisions_kept: dict[str, list[int]] = Field(default_factory=dict)
    decision_hrefs: dict[str, list[str]] = Field(default_factory=dict)
    stats: dict[str, int] = Field(default_factory=dict)


# ---------------------------------------------------------------- model council


class CouncilCiteDraft(BaseModel):
    kind: Literal["record", "authority"] = Field(
        description="record = a passage of the case record; authority = a decision from the VERIFIED AUTHORITIES list"
    )
    text: str = Field(
        description="record: the tag content exactly, e.g. 'Contract, p. 12'. authority: 'Name [citation]' exactly as listed."
    )


class IssueReadingDraft(BaseModel):
    issue: int = Field(description="Issue number")
    reading: str = Field(description="One or two neutral sentences on how the issue is structured and what it turns on")
    turns_on: str = Field(description="The decisive point (fact, date, document or legal test), one sentence")
    confidence: Literal["high", "medium", "low"]
    cites: list[CouncilCiteDraft]


class FlaggedFactDraft(BaseModel):
    text: str = Field(description="A decisive fact or a gap in the record, one sentence")
    ref: str = Field(description="Record citation 'Document label, ref'")


class CounselQuestionDraft(BaseModel):
    to: Literal["Claimant", "Defendant", "Both"]
    question: str
    why: str = Field(description="Why the answer matters, one sentence")
    issue: int
    ref: str = Field(description="Record citation that raises the question ('Document label, ref'), or empty")


class CouncilReadingOutput(BaseModel):
    readings: list[IssueReadingDraft]
    flagged: list[FlaggedFactDraft] = Field(description="The 2-5 facts or gaps most likely to decide the case")
    questions: list[CounselQuestionDraft] = Field(description="3-8 questions the judge could put to counsel")


class PositionDraft(BaseModel):
    text: str = Field(description="Neutral statement of this reading, one or two sentences, using only what members said")
    members: list[str] = Field(description="Ids of the members holding this reading")


class IssueConsensusDraft(BaseModel):
    issue: int
    positions: list[PositionDraft] = Field(
        description="One position if the readings agree in substance, otherwise the two main competing readings"
    )


class MergedFlagDraft(BaseModel):
    text: str
    ref: str
    members: list[str]


class MergedQuestionDraft(BaseModel):
    to: Literal["Claimant", "Defendant", "Both"]
    question: str
    why: str
    issue: int
    ref: str
    members: list[str]


class ConsensusDraft(BaseModel):
    issues: list[IssueConsensusDraft]
    flagged: list[MergedFlagDraft]
    questions: list[MergedQuestionDraft]


# ---------------------------------------------------------------- ask the council


class AskAnswerDraft(BaseModel):
    paragraphs: list[str] = Field(description="One to four short paragraphs answering the question")
    turns_on_disputed_fact: bool = Field(description="True if the answer depends on a fact the parties dispute")
    cites: list[CouncilCiteDraft]


class SteelPointDraft(BaseModel):
    point: str = Field(description="One argument, one or two sentences")
    cites: list[CouncilCiteDraft]


class SteelmanDraft(BaseModel):
    claimant: list[SteelPointDraft] = Field(description="The strongest points for the Claimant, 2-5")
    defendant: list[SteelPointDraft] = Field(description="The strongest points for the Defendant, 2-5")


class ReviewNoteDraft(BaseModel):
    answer: int = Field(description="Number of the answer this note is about")
    point: str = Field(description="One specific weakness, error, omission or unsupported citation, one sentence")


class ReviewDraft(BaseModel):
    notes: list[ReviewNoteDraft]
    revised: str = Field(description="Your revised position, two or three sentences, after reading the other answers")


class SynthesisDraft(BaseModel):
    summary: str = Field(description="Two or three neutral sentences on where the answers land together")
    agree: list[str] = Field(description="Points every answer shares")
    differ: list[str] = Field(description="Points where the answers differ, saying which answer says what")


class MergedPointDraft(BaseModel):
    point: str
    members: list[str] = Field(description="Ids of the members who made this point")
    cites: list[CouncilCiteDraft]


class SteelmanMergeDraft(BaseModel):
    claimant: list[MergedPointDraft]
    defendant: list[MergedPointDraft]
