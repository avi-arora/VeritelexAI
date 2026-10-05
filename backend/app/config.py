"""Runtime configuration, loaded from environment variables (prefix ``VTX_``).

No secrets live here: every Google Cloud call authenticates with
Application Default Credentials (your gcloud login locally, the service
account attached to Cloud Run in production).
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import BaseModel, Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class CouncilMember(BaseModel):
    """One model on the council. Every member is served from Google Cloud (Agent Platform),
    authenticated with Application Default Credentials; there are no third-party API keys."""

    id: str = Field(pattern=r"^[a-z][a-z0-9]{1,15}$")
    name: str
    vendor: str
    provider: Literal["gemini", "anthropic", "openai"]
    """gemini = google-genai SDK; anthropic = Claude rawPredict; openai = OpenAI-compatible chat completions."""
    models: list[str] = Field(min_length=1)
    """Fallback chain, preferred model first."""
    location: str = "global"
    host: str = "Google Cloud · Agent Platform (global)"
    mono: str
    color: str = Field(pattern=r"^#[0-9A-Fa-f]{6}$")
    max_input_chars: int = 1_200_000
    """Prompt budget per call. Must keep a single call under the member's input-token quota."""
    max_output_tokens: int = 16_384
    concurrency: int = 3
    rpm: int = 0
    """Client-side rate limits (0 = unlimited) mirroring the project's quota, so the council never
    triggers its own 429s when pre-analysis and asks run at the same time."""
    input_tpm: int = 0
    output_tpm: int = 0
    json_mode: bool = True
    """OpenAI-compatible members: request ``response_format: json_object`` (dropped automatically if refused)."""
    console_url: str = ""
    """Model Garden page where the model is enabled (``{project}`` is substituted)."""
    enabled: bool = True


def _default_council() -> list[CouncilMember]:
    garden = "https://console.cloud.google.com/agent-platform/publishers/{pub}/model-garden/{model}?project={{project}}"
    return [
        CouncilMember(
            id="gemini", name="Gemini 3.1 Pro", vendor="Google", provider="gemini",
            models=["gemini-3.1-pro-preview", "gemini-3.8-flash", "gemini-2.5-pro"],
            mono="Ge", color="#3B5BA5", max_input_chars=1_200_000, max_output_tokens=32_768, concurrency=3,
            console_url=garden.format(pub="google", model="gemini-3.1-pro-preview"),
        ),
        CouncilMember(
            id="claude", name="Claude Opus 5.5", vendor="Anthropic", provider="anthropic",
            models=["claude-opus-5-5", "claude-sonnet-5-5"],
            mono="C", color="#B4613E", max_input_chars=1_200_000, max_output_tokens=32_000, concurrency=3,
            console_url=garden.format(pub="anthropic", model="claude-opus-5-5"),
        ),
        CouncilMember(
            id="grok", name="Grok 4.7", vendor="xAI", provider="openai",
            models=["xai/grok-4.7", "xai/grok-4.6"],
            # Default quota is 13 QPM, 188k input TPM, 16k output TPM: one full-record read per minute.
            mono="Gr", color="#4F5A66", max_input_chars=360_000, max_output_tokens=12_000, concurrency=2,
            rpm=10, input_tpm=150_000, output_tpm=14_000,
            console_url=garden.format(pub="xai", model="grok-4.7"),
        ),
    ]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="VTX_", env_file=".env", extra="ignore")

    env: Literal["local", "prod"] = "local"
    role: Literal["all", "api", "worker"] = "all"
    """Which routers this process serves. ``all`` is used for local development."""

    project_id: str
    region: str = "us-central1"
    vertex_location: str = "global"
    """Gemini endpoint location. Gemini 3 models are served from the global endpoint."""

    firestore_database: str = "(default)"
    case_bucket: str = ""
    artifact_bucket: str = ""

    # ---- Orchestration -------------------------------------------------
    dispatcher: Literal["local", "cloud_tasks"] = "local"
    tasks_queue: str = "agent-steps"
    worker_url: str = ""
    """Base URL of the worker service (Cloud Tasks target + OIDC audience)."""
    tasks_invoker_sa: str = ""
    """Service account whose OIDC token Cloud Tasks attaches to each request."""
    local_concurrency: int = 8
    """Max steps executed concurrently by the in-process dispatcher."""
    lease_seconds: int = 120
    stale_run_seconds: int = 600
    """A run with no step activity for this long is reconciled (stuck steps re-dispatched)."""

    # ---- Models --------------------------------------------------------
    model_pro: list[str] = Field(default_factory=lambda: ["gemini-3.1-pro-preview", "gemini-2.5-pro"])
    model_flash: list[str] = Field(default_factory=lambda: ["gemini-3.8-flash", "gemini-3.7-flash", "gemini-2.5-flash"])
    llm_concurrency: int = 6
    llm_call_timeout_s: int = 300
    llm_call_attempts: int = 3
    breaker_failures: int = 4
    breaker_cooldown_s: int = 60

    # ---- Ingestion budgets --------------------------------------------
    ocr_pages_per_call: int = 15
    ocr_max_inflight_batches: int = 4
    """Per document: OCR page batches built and in flight at once (bounds memory on large scans)."""
    min_text_chars_per_page: int = 40
    """Pages with less extractable text than this are sent to Gemini for OCR."""
    parse_workers: int = 2
    """Threads reserved for CPU-bound parsing (PDF/DOCX/XLSX), kept apart from the I/O thread pool."""
    scratch_dir: str = ""
    """Where source files are streamed for parsing (empty = system temp dir). Cloud Run's filesystem is
    in-memory, so worker memory must cover the largest files being ingested concurrently."""
    doc_chunk_chars: int = 400_000
    corpus_budget_chars: int = 1_200_000

    # ---- API / uploads -------------------------------------------------
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])
    signing_sa_email: str = ""
    """Service account used to sign V4 upload URLs (via IAM signBlob, no keys)."""
    max_upload_bytes: int = 500 * 1024 * 1024
    max_files_per_upload: int = 50
    upload_url_ttl_s: int = 900
    rate_limit_per_minute: int = 240

    # ---- Grounding -----------------------------------------------------
    url_check_timeout_s: float = 8.0

    # ---- Model council -------------------------------------------------
    council_enabled: bool = True
    council_members: list[CouncilMember] = Field(default_factory=_default_council)
    council_chair: list[str] = Field(default_factory=lambda: ["gemini", "claude", "grok"])
    """Who synthesises (compares) the members' work, in order of preference."""
    council_status_ttl_s: int = 900
    """How long a member's probed availability is cached for the settings screen."""
    council_unavailable_ttl_s: int = 600
    """A model that answered 404/403 (not enabled) is skipped for this long, then tried again."""
    ask_corpus_chars: int = 800_000
    """Upper bound on the record sent with each question (members with smaller budgets use theirs)."""
    ask_max_running_per_case: int = 3

    @computed_field  # type: ignore[prop-decorator]
    @property
    def serves_api(self) -> bool:
        return self.role in ("all", "api")

    @computed_field  # type: ignore[prop-decorator]
    @property
    def serves_worker(self) -> bool:
        return self.role in ("all", "worker")


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
