import calendar
import re
from datetime import date, datetime, timezone
from enum import StrEnum
from typing import Literal, Protocol

from pydantic import BaseModel, Field, field_validator, model_validator


class AdapterError(Exception):
    """A source failed; preserve the last successful catalogue state."""


class TransientAdapterError(AdapterError):
    """An outage or rate limit can be retried without changing catalogue data."""


class Precision(StrEnum):
    INSTANT = "instant"
    DAY = "day"
    MONTH = "month"
    SEASON = "season"
    YEAR = "year"
    UNKNOWN = "unknown"


class ReleaseTime(BaseModel):
    precision: Precision = Precision.UNKNOWN
    start: date | None = None
    end: date | None = None
    timestamp: datetime | None = None
    label: str = Field(default="", max_length=200)
    timezone: str = Field(default="", max_length=50)

    @model_validator(mode="after")
    def validate_precision(self):
        if self.precision == Precision.UNKNOWN:
            if self.start or self.end or self.timestamp:
                raise ValueError("An unknown date cannot contain an invented date or time")
            return self
        if self.precision == Precision.INSTANT:
            if not self.timestamp or self.timestamp.tzinfo is None:
                raise ValueError("Exact release times must include a timezone")
            self.start = self.end = self.timestamp.date()
        else:
            if self.timestamp:
                raise ValueError("Date windows must not contain an invented exact time")
            if not self.start or not self.end or self.end < self.start:
                raise ValueError("A valid, ordered release window is required")
            if self.precision == Precision.DAY and self.start != self.end:
                raise ValueError("A day must have equal window bounds")
            if self.precision == Precision.MONTH:
                expected_end = date(self.start.year, self.start.month, calendar.monthrange(self.start.year, self.start.month)[1])
                if self.start.day != 1 or self.end != expected_end:
                    raise ValueError("A month must span the entire named month")
            if self.precision == Precision.YEAR:
                if self.start != date(self.start.year, 1, 1) or self.end != date(self.start.year, 12, 31):
                    raise ValueError("A year must span the entire named year")
        return self


def parse_release_time(value: str | None) -> ReleaseTime:
    """Only parse explicit dates. Never infer a year from the current clock."""
    if not value:
        return ReleaseTime()
    value = value.strip()
    if value in {'0000', '0000-00', '0000-00-00'}:
        return ReleaseTime()
    if re.fullmatch(r"\d{4}", value):
        year = int(value)
        return ReleaseTime(precision="year", start=date(year, 1, 1), end=date(year, 12, 31), label=value)
    if re.fullmatch(r"\d{4}-\d{2}", value):
        year, month = map(int, value.split("-"))
        return ReleaseTime(precision="month", start=date(year, month, 1), end=date(year, month, calendar.monthrange(year, month)[1]), label=value)
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        day = date.fromisoformat(value)
        return ReleaseTime(precision="day", start=day, end=day, label=value)
    if re.match(r"\d{4}-\d{2}-\d{2}T", value):
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return ReleaseTime(precision="instant", timestamp=stamp, label=value)
    return ReleaseTime(label=value)


class Identity(BaseModel):
    provider: str
    namespace: str
    external_id: str = Field(min_length=1, max_length=200)


class Candidate(Identity):
    title: str = Field(min_length=1, max_length=1000)
    kind: str
    creators: list[str] = Field(default_factory=list)
    year: str = ""
    url: str = ""
    existing_work_id: str | None = None


class Metadata(Candidate):
    original_title: str = Field(default="", max_length=1000)
    aliases: list[str] = Field(default_factory=list)
    summary: str = ""
    language: str = ""
    status: str = ""
    image_url: str = ""
    extra: dict = Field(default_factory=dict)


class SourceUnit(BaseModel):
    external_id: str = Field(min_length=1, max_length=200)
    kind: str
    title: str = Field(min_length=1, max_length=1000)
    label: str = Field(default="", max_length=200)
    ordinal: int = 0
    url: str = ""
    release: ReleaseTime = Field(default_factory=ReleaseTime)
    published_at: datetime | None = None
    modified_at: datetime | None = None

    @field_validator("published_at", "modified_at")
    @classmethod
    def aware_timestamps(cls, value):
        if value is not None and value.tzinfo is None:
            raise ValueError("Unit timestamps must include a timezone")
        return value


class SourceEdition(BaseModel):
    product_id: str
    isbn: str = ""
    title: str
    volume_label: str = ""
    publisher: str = ""
    imprint: str = ""
    format: str = "print"
    language: str = "ja"
    release: ReleaseTime = Field(default_factory=ReleaseTime)
    url: str = ""


EventKind = Literal["announcement", "release", "episode_release", "chapter_release", "volume_release", "availability", "pv", "rumour", "sequel", "adaptation", "delay", "cancellation", "metadata_change"]
Verification = Literal["confirmed", "reported", "unverified", "contradicted", "retracted"]
Lifecycle = Literal["announced", "scheduled", "released", "delayed", "cancelled"]


class SourceEvent(BaseModel):
    external_key: str = Field(min_length=1, max_length=500)
    kind: EventKind
    title: str = Field(min_length=1, max_length=1000)
    summary: str = Field(default="", max_length=10000)
    release: ReleaseTime = Field(default_factory=ReleaseTime)
    verification: Verification = "reported"
    lifecycle: Lifecycle = "scheduled"
    region: str = Field(default="", max_length=10)
    platform: str = Field(default="", max_length=100)
    language: str = Field(default="", max_length=20)
    url: str
    locator: str = Field(default="", max_length=1000)
    original_text: str = Field(default="", max_length=12000)
    published_at: datetime | None = None
    unit_id: str | None = None
    product_id: str | None = None

    @field_validator("published_at")
    @classmethod
    def aware_publication(cls, value):
        if value is not None and value.tzinfo is None:
            raise ValueError("Publication timestamps must include a timezone")
        return value


class SourceRelationship(BaseModel):
    target: Identity
    kind: Literal["sequel_to", "adaptation_of", "spinoff_of", "part_of"]
    reverse: bool = False


class Snapshot(BaseModel):
    metadata: Metadata
    units: list[SourceUnit] = Field(default_factory=list)
    editions: list[SourceEdition] = Field(default_factory=list)
    relationships: list[SourceRelationship] = Field(default_factory=list)
    events: list[SourceEvent] = Field(default_factory=list)
    complete: bool = True
    diagnostics: list[str] = Field(default_factory=list)
    observed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("observed_at")
    @classmethod
    def aware_observation(cls, value):
        if value.tzinfo is None:
            raise ValueError("Observation timestamps must include a timezone")
        return value


class Change(BaseModel):
    kind: Literal["added", "edited", "reordered", "removed"]
    unit: SourceUnit


class DiffResult(BaseModel):
    changes: list[Change] = Field(default_factory=list)
    missing_counts: dict[str, int] = Field(default_factory=dict)
    baseline: Snapshot


def diff_snapshots(previous: Snapshot | None, current: Snapshot, missing_counts: dict[str, int] | None = None) -> DiffResult:
    if not current.complete:
        raise AdapterError("Incomplete chapter index: last good snapshot was retained")
    if previous and previous.metadata.model_dump(include={"provider", "namespace", "external_id"}) != current.metadata.model_dump(include={"provider", "namespace", "external_id"}):
        raise AdapterError("Snapshot identity changed")
    old = {u.external_id: u for u in previous.units} if previous else {}
    new = {u.external_id: u for u in current.units}
    if len(new) != len(current.units):
        raise AdapterError("Duplicate unit identifiers in chapter index")
    counts = dict(missing_counts or {})
    changes = []
    retained = []
    for key, unit in new.items():
        counts.pop(key, None)
        if key not in old:
            changes.append(Change(kind="added", unit=unit))
        else:
            before, after = old[key], unit
            if before.model_dump(exclude={"ordinal"}) != after.model_dump(exclude={"ordinal"}):
                changes.append(Change(kind="edited", unit=unit))
            if before.ordinal != after.ordinal:
                changes.append(Change(kind="reordered", unit=unit))
    for key, unit in old.items():
        if key in new:
            continue
        counts[key] = counts.get(key, 0) + 1
        if counts[key] >= 2:
            changes.append(Change(kind="removed", unit=unit))
            counts.pop(key, None)
        else:
            retained.append(unit)
    baseline = current.model_copy(update={"units": current.units + retained})
    return DiffResult(changes=changes, missing_counts=counts, baseline=baseline)


class Adapter(Protocol):
    name: str

    def resolve(self, value: str) -> Identity | None: ...
    def search(self, query: str, author: str = "") -> list[Candidate]: ...
    def fetch_snapshot(self, identity: Identity) -> Snapshot: ...
    def diff(self, previous: Snapshot | None, current: Snapshot, missing_counts: dict[str, int] | None = None) -> DiffResult: ...
