from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .ingestion.contracts import Candidate, Identity, SourceEvent


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


class UserOut(BaseModel):
    id: int
    username: str
    is_staff: bool


class LoginIn(Input):
    username: str = Field(min_length=1, max_length=150)
    password: str = Field(min_length=1, max_length=500)


class LoginOut(BaseModel):
    token: str
    user: UserOut


class IdentityOut(Identity):
    id: UUID


class FranchiseOut(BaseModel):
    id: UUID
    title: str


class WorkOut(BaseModel):
    id: UUID
    title: str
    original_title: str
    aliases: list[str]
    kind: str
    creators: list[str]
    summary: str
    language: str
    status: str
    canonical_url: str
    image_url: str
    franchise_id: UUID | None
    franchise_title: str | None
    identities: list[IdentityOut]
    unit_count: int
    metadata: dict


class SearchOut(BaseModel):
    candidates: list[Candidate]
    errors: list[str]


class ImportIn(Input):
    provider: str = Field(max_length=50)
    namespace: str = Field(max_length=50)
    external_id: str = Field(min_length=1, max_length=200)
    include_related: bool = False


class RunOut(BaseModel):
    id: UUID
    work_id: UUID | None
    provider: str
    status: str
    message: str
    created_at: datetime
    finished_at: datetime | None


class UnitOut(BaseModel):
    id: UUID
    provider: str
    external_id: str
    kind: str
    title: str
    label: str
    ordinal: int
    canonical_url: str
    active: bool


class EditionOut(BaseModel):
    id: UUID
    title: str
    isbn: str
    volume_label: str
    publisher: str
    imprint: str
    format: str
    language: str
    release_date: date | None
    canonical_url: str


class RelationshipOut(BaseModel):
    id: UUID
    kind: str
    from_work_id: UUID
    to_work_id: UUID
    from_title: str
    to_title: str
    verification: str


class WorkDetailOut(BaseModel):
    work: WorkOut
    units: list[UnitOut]
    editions: list[EditionOut]
    relationships: list[RelationshipOut]


class FollowIn(Input):
    work_id: UUID | None = None
    franchise_id: UUID | None = None
    include_related: bool = False

    @model_validator(mode="after")
    def one_target(self):
        if bool(self.work_id) == bool(self.franchise_id):
            raise ValueError("Choose exactly one work or franchise")
        return self


class ProgressIn(Input):
    status: Literal["planned", "in_progress", "completed", "paused", "dropped"]
    progress: int = Field(ge=0, le=1000000)
    include_related: bool
    progress_kind: Literal["episode", "chapter", "volume"]


class FollowOut(BaseModel):
    id: UUID
    work: WorkOut | None
    franchise_id: UUID | None
    franchise_title: str | None
    include_related: bool
    status: str
    progress: int
    progress_kind: str


class EventOut(BaseModel):
    id: UUID
    work_id: UUID
    work_title: str
    work_kind: str
    franchise_id: UUID | None
    kind: str
    title: str
    summary: str
    verification: str
    lifecycle: str
    precision: str
    date_label: str
    scheduled_at: datetime | None
    window_start: date | None
    window_end: date | None
    source_timezone: str
    region: str
    platform: str
    language: str
    published_at: datetime | None
    observed_at: datetime
    provider: str
    evidence_count: int
    personal: bool


class TimelineOut(BaseModel):
    events: list[EventOut]
    total: int
    tba_count: int
    offset: int
    limit: int


class EvidenceOut(BaseModel):
    id: UUID
    url: str
    provider: str
    title: str
    locator: str
    original_text: str
    published_at: datetime | None
    observed_at: datetime


class RevisionOut(BaseModel):
    id: UUID
    before: dict
    after: dict
    reason: str
    created_at: datetime


class EventDetailOut(BaseModel):
    event: EventOut
    evidence: list[EvidenceOut]
    revisions: list[RevisionOut]


class StatsOut(BaseModel):
    followed: int
    upcoming: int
    needs_review: int
    stale_sources: int


class SourceOut(BaseModel):
    provider: str
    status: str
    policy: str


class SourceStateOut(BaseModel):
    id: UUID
    work_id: UUID
    work_title: str
    provider: str
    last_checked_at: datetime | None
    last_success_at: datetime | None
    last_error: str
    diagnostics: list[str]


class SourcesOut(BaseModel):
    adapters: list[SourceOut]
    states: list[SourceStateOut]


class FilterIn(Input):
    name: str = Field(min_length=1, max_length=100)
    filters: dict


class FilterOut(FilterIn):
    id: UUID


class ArticleIn(Input):
    work_id: UUID
    url: str = Field(max_length=2000)
    use_model: bool = False


class ModelIn(Input):
    provider: Literal["openai-compatible", "openai", "anthropic", "google", "ollama"]
    endpoint: str = Field(min_length=1, max_length=2000)
    model: str = Field(min_length=1, max_length=200)
    credential: str | None = Field(default=None, max_length=10000)
    max_input_chars: int = Field(default=12000, ge=1000, le=30000)
    max_output_tokens: int = Field(default=2000, ge=100, le=8000)
    daily_requests: int = Field(default=20, ge=1, le=1000)


class ModelOut(BaseModel):
    provider: str
    endpoint: str
    model: str
    has_credential: bool
    max_input_chars: int
    max_output_tokens: int
    daily_requests: int


class ReviewOut(BaseModel):
    id: UUID
    work_id: UUID
    work_title: str
    source_url: str
    excerpt: str
    payload: SourceEvent
    model: str
    status: str
    message: str
    created_at: datetime


class ReviewIn(Input):
    action: Literal["approve", "reject"]
    payload: SourceEvent | None = None


class FeedIn(Input):
    work_id: UUID
    url: str = Field(max_length=2000)
    source_kind: Literal["rss", "youtube", "apple", "netflix", "disney"] = "rss"


class FeedOut(FeedIn):
    id: UUID
    last_checked_at: datetime | None
    last_error: str


class StatusOut(BaseModel):
    ok: bool
    message: str = ""


class WorkCorrectionIn(Input):
    title: str = Field(min_length=1, max_length=1000)
    aliases: list[str] = Field(max_length=100)
    franchise_id: UUID | None = None


CONTRACT_MODELS = [UserOut, LoginIn, LoginOut, FranchiseOut, WorkOut, WorkDetailOut, SearchOut, ImportIn, RunOut, FollowIn, ProgressIn, FollowOut, EventOut, TimelineOut, EventDetailOut, StatsOut, SourcesOut, FilterIn, FilterOut, ArticleIn, ModelIn, ModelOut, ReviewOut, ReviewIn, FeedIn, FeedOut, StatusOut, WorkCorrectionIn]
