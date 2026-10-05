"""API-facing models. Field names deliberately mirror ``src/lib/data.ts`` so the
existing React components can render API data without reshaping it."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field, field_validator

Tone = Literal["green", "blue", "amber", "red", "grey"]
CaseStatus = Literal["queued", "ingesting", "ai", "ready", "action"]
Coverage = Literal["full", "partial", "none"]


class CaseField(BaseModel):
    k: str
    v: str
    src: str = ""
    full: bool = False


class CaseSummary(BaseModel):
    id: str
    no: str
    title: str
    type: str
    division: str
    docs: str
    pages: str
    status: CaseStatus
    pct: int | None = None
    at: int | None = None
    note: str
    updated: str
    updatedAt: str
    past: bool = False
    isNew: bool = False


class CaseDetail(CaseSummary):
    subtitle: str = ""
    reportReadyAt: str | None = None
    fields: list[CaseField] = Field(default_factory=list)
    latestRunId: str | None = None


class DocumentOut(BaseModel):
    id: str
    n: str
    t: str
    p: str
    ext: str
    by: str
    s: str
    tone: Tone
    status: str
    sizeBytes: int | None = None


# ---- Report sections -----------------------------------------------------


class KeyFact(BaseModel):
    k: str
    v: str


class BackgroundSection(BaseModel):
    paragraphs: list[str]
    keyFacts: list[KeyFact]
    fields: list[CaseField]
    counts: dict[str, int] = Field(default_factory=dict)


class ChronoEntry(BaseModel):
    d: str
    t: str
    b: str
    st: str
    tone: Tone
    iss: list[int] = Field(default_factory=list)
    cv: str = ""
    cRef: str = ""
    dv: str = ""
    dRef: str = ""
    ground: list[str] = Field(default_factory=list)
    side: Literal["both", "c", "d"] = "both"
    i: int = -1
    mapped: int = 0
    verified: bool = True


class MatrixSection(BaseModel):
    entries: list[ChronoEntry]


class Decision(BaseModel):
    name: str
    cite: str
    court: str
    date: str
    rel: str
    tone: Tone
    how: str
    via: str
    href: str


class MappingGroup(BaseModel):
    facts: list[int]
    d: str
    t: str
    iss: str
    decisions: list[Decision]


class MappingSection(BaseModel):
    groups: list[MappingGroup]
    totalDecisions: int
    excluded: int = 0


class IssueOut(BaseModel):
    n: int
    topic: str
    q: str
    law: str
    st: str
    tone: Tone
    facts: str = ""


class IssuesSection(BaseModel):
    issues: list[IssueOut]


class GroundSource(BaseModel):
    short: str
    type: str
    meta: str
    sum: str
    auth: list[str]
    cov: list[tuple[Coverage, str]]


class GroundingSection(BaseModel):
    sources: dict[str, GroundSource]
    verification: dict[str, int] = Field(default_factory=dict)


# ---- Requests ------------------------------------------------------------


class CreateCaseRequest(BaseModel):
    title: str | None = Field(default=None, max_length=300)


class UploadFileSpec(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    size: int = Field(gt=0)
    contentType: str = Field(min_length=1, max_length=120)


class UploadRequest(BaseModel):
    files: list[UploadFileSpec] = Field(min_length=1)


class UploadTarget(BaseModel):
    documentId: str
    name: str
    uploadUrl: str
    method: Literal["PUT"] = "PUT"
    headers: dict[str, str]


class UploadResponse(BaseModel):
    caseId: str
    targets: list[UploadTarget]


class UpdateCaseRequest(BaseModel):
    fields: list[CaseField] | None = None
    confirmed: bool | None = None


class StepView(BaseModel):
    id: str
    agent: str
    status: str
    attempts: int
    error: str | None = None
    startedAt: str | None = None
    finishedAt: str | None = None
    outcome: str | None = None
    """Set on succeeded steps whose agent reported ``unavailable`` (council member not enabled) or ``skipped``."""
    reused: bool = False
    """Council re-runs: the step's result was reused from the source version."""


class RunView(BaseModel):
    id: str
    status: str
    stage: str
    pct: int
    createdAt: str
    updatedAt: str
    steps: list[StepView]
    mode: str = "full"
    sourceRunId: str | None = None


# ---- Model council and report versions ----------------------------------------

MemberId = Annotated[str, Field(pattern=r"^[a-z][a-z0-9]{1,15}$")]
RunIdStr = Annotated[str, Field(pattern=r"^r[0-9a-f]{12}$")]


class CouncilMemberOut(BaseModel):
    id: str
    name: str
    vendor: str
    host: str
    m: str
    c: str
    models: list[str]
    status: Literal["ready", "fallback", "unavailable", "error", "unknown"]
    activeModel: str | None = None
    detail: str = ""
    consoleUrl: str = ""
    checkedAt: str | None = None


class CouncilModelsOut(BaseModel):
    chair: list[str]
    members: list[CouncilMemberOut]


class CouncilRunMember(BaseModel):
    id: str
    status: str
    model: str | None = None
    error: str | None = None


class RunCounts(BaseModel):
    facts: int = 0
    issues: int = 0
    decisions: int = 0


class RunSummary(BaseModel):
    id: str
    version: int
    status: str
    mode: Literal["full", "council"] = "full"
    trigger: str
    sourceRunId: str | None = None
    sourceVersion: int | None = None
    createdAt: str
    finishedAt: str | None = None
    stage: str = ""
    pct: int = 0
    hasReport: bool
    published: bool
    docCount: int = 0
    counts: RunCounts | None = None
    council: list[CouncilRunMember] = Field(default_factory=list)


class StartRunRequest(BaseModel):
    mode: Literal["full", "council"] = "full"
    sourceRunId: RunIdStr | None = None


AskMode = Literal["independent", "debate", "steelman"]


class AskScopeIn(BaseModel):
    kind: Literal["record", "issue"] = "record"
    issue: int | None = Field(default=None, ge=1, le=1000)


class AskRequest(BaseModel):
    question: str = Field(min_length=5, max_length=2000)
    mode: AskMode = "independent"
    scope: AskScopeIn = Field(default_factory=AskScopeIn)
    members: list[MemberId] | None = Field(default=None, min_length=1, max_length=8)
    runId: RunIdStr | None = None

    @field_validator("question")
    @classmethod
    def _clean_question(cls, v: str) -> str:
        v = "".join(ch for ch in v if ch in "\n\t" or ord(ch) >= 32).strip()
        if len(v) < 5:
            raise ValueError("The question must be at least 5 characters")
        return v


class AskScope(BaseModel):
    kind: Literal["record", "issue"]
    issue: int | None = None
    label: str


class AskSummary(BaseModel):
    id: str
    question: str
    mode: AskMode
    scope: AskScope
    status: Literal["running", "succeeded", "partial", "failed"]
    runId: str
    version: int | None = None
    createdAt: str
    finishedAt: str | None = None


class CiteOut(BaseModel):
    kind: Literal["record", "authority"]
    text: str
    status: Literal["verified", "warn", "bad"]
    note: str = ""


class SteelPointOut(BaseModel):
    point: str
    cites: list[CiteOut] = Field(default_factory=list)
    by: list[str] = Field(default_factory=list)


class AskAnswerOut(BaseModel):
    member: str
    status: str
    model: str | None = None
    error: str | None = None
    paragraphs: list[str] = Field(default_factory=list)
    turnsOnDisputedFact: bool = False
    cites: list[CiteOut] = Field(default_factory=list)
    claimant: list[SteelPointOut] = Field(default_factory=list)
    defendant: list[SteelPointOut] = Field(default_factory=list)


class ReviewNoteOut(BaseModel):
    about: str
    point: str


class AskReviewOut(BaseModel):
    member: str
    status: str
    error: str | None = None
    notes: list[ReviewNoteOut] = Field(default_factory=list)
    revised: str = ""


class SynthesisOut(BaseModel):
    status: str
    chair: str | None = None
    model: str | None = None
    error: str | None = None
    summary: str = ""
    agree: list[str] = Field(default_factory=list)
    differ: list[str] = Field(default_factory=list)
    leftOut: list[str] = Field(default_factory=list)


class SteelmanOut(BaseModel):
    claimant: list[SteelPointOut] = Field(default_factory=list)
    defendant: list[SteelPointOut] = Field(default_factory=list)


class AskView(AskSummary):
    members: list[str]
    answers: list[AskAnswerOut]
    reviews: list[AskReviewOut] = Field(default_factory=list)
    synthesis: SynthesisOut | None = None
    steelman: SteelmanOut | None = None
