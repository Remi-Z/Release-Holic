import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q


class Record(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Franchise(Record):
    title = models.CharField(max_length=500)

    def __str__(self):
        return self.title


class Creator(Record):
    name = models.CharField(max_length=300)
    aliases = models.JSONField(default=list)

    def __str__(self):
        return self.name


class Work(Record):
    class Kind(models.TextChoices):
        SHOW = "show", "TV series"
        MOVIE = "movie", "Movie"
        ANIME = "anime", "Anime"
        WEB_NOVEL = "web_novel", "Web novel"
        LIGHT_NOVEL = "light_novel", "Light novel"

    franchise = models.ForeignKey(Franchise, null=True, blank=True, on_delete=models.SET_NULL, related_name="works")
    title = models.CharField(max_length=1000)
    original_title = models.CharField(max_length=1000, blank=True)
    aliases = models.JSONField(default=list)
    creators = models.ManyToManyField(Creator, blank=True, related_name="works")
    kind = models.CharField(max_length=20, choices=Kind.choices)
    summary = models.TextField(blank=True)
    language = models.CharField(max_length=20, blank=True)
    status = models.CharField(max_length=50, blank=True)
    canonical_url = models.URLField(max_length=2000, blank=True)
    image_url = models.URLField(max_length=2000, blank=True)
    metadata = models.JSONField(default=dict)
    curated_fields = models.JSONField(default=dict, blank=True)

    def __str__(self):
        return self.title


class ExternalIdentity(Record):
    work = models.ForeignKey(Work, on_delete=models.CASCADE, related_name="identities")
    provider = models.CharField(max_length=50)
    namespace = models.CharField(max_length=50)
    external_id = models.CharField(max_length=200)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["provider", "namespace", "external_id"], name="unique_external_identity")]

    def __str__(self):
        return f"{self.provider}:{self.namespace}:{self.external_id}"


class Unit(Record):
    work = models.ForeignKey(Work, on_delete=models.CASCADE, related_name="units")
    provider = models.CharField(max_length=50)
    external_id = models.CharField(max_length=200)
    kind = models.CharField(max_length=20)
    title = models.CharField(max_length=1000)
    label = models.CharField(max_length=200, blank=True)
    ordinal = models.IntegerField(default=0)
    canonical_url = models.URLField(max_length=2000, blank=True)
    published_at = models.DateTimeField(null=True, blank=True)
    modified_at = models.DateTimeField(null=True, blank=True)
    active = models.BooleanField(default=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["work", "provider", "external_id"], name="unique_source_unit")]
        ordering = ["ordinal", "id"]


class Edition(Record):
    work = models.ForeignKey(Work, on_delete=models.CASCADE, related_name="editions")
    unit = models.ForeignKey(Unit, null=True, blank=True, on_delete=models.SET_NULL)
    provider = models.CharField(max_length=50)
    product_id = models.CharField(max_length=200)
    isbn = models.CharField(max_length=13, blank=True)
    title = models.CharField(max_length=1000)
    volume_label = models.CharField(max_length=200, blank=True)
    publisher = models.CharField(max_length=300, blank=True)
    imprint = models.CharField(max_length=300, blank=True)
    format = models.CharField(max_length=50, default="print")
    language = models.CharField(max_length=20, default="ja")
    release_date = models.DateField(null=True, blank=True)
    canonical_url = models.URLField(max_length=2000, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["provider", "product_id", "format", "language"], name="unique_source_edition")]


class SourceDocument(Record):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.CASCADE)
    scope_key = models.CharField(max_length=100, default="shared")
    provider = models.CharField(max_length=50)
    url = models.URLField(max_length=2000)
    title = models.CharField(max_length=1000, blank=True)
    content_hash = models.CharField(max_length=64)
    excerpt = models.TextField(blank=True)
    published_at = models.DateTimeField(null=True, blank=True)
    observed_at = models.DateTimeField()
    metadata = models.JSONField(default=dict)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["scope_key", "url", "content_hash"], name="unique_document_version")]


class Relationship(Record):
    from_work = models.ForeignKey(Work, on_delete=models.CASCADE, related_name="outgoing_relationships")
    to_work = models.ForeignKey(Work, on_delete=models.CASCADE, related_name="incoming_relationships")
    kind = models.CharField(max_length=30)
    source = models.ForeignKey(SourceDocument, null=True, blank=True, on_delete=models.PROTECT)
    verification = models.CharField(max_length=30, default="reported")

    class Meta:
        constraints = [models.UniqueConstraint(fields=["from_work", "to_work", "kind"], name="unique_work_relationship")]


class Event(Record):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.CASCADE)
    scope_key = models.CharField(max_length=100, default="shared")
    work = models.ForeignKey(Work, on_delete=models.CASCADE, related_name="events")
    unit = models.ForeignKey(Unit, null=True, blank=True, on_delete=models.SET_NULL)
    edition = models.ForeignKey(Edition, null=True, blank=True, on_delete=models.SET_NULL)
    provider = models.CharField(max_length=50)
    external_key = models.CharField(max_length=500)
    kind = models.CharField(max_length=40)
    title = models.CharField(max_length=1000)
    summary = models.TextField(blank=True)
    verification = models.CharField(max_length=30, default="reported")
    lifecycle = models.CharField(max_length=30, default="scheduled")
    precision = models.CharField(max_length=20, default="unknown")
    date_label = models.CharField(max_length=200, blank=True)
    scheduled_at = models.DateTimeField(null=True, blank=True)
    window_start = models.DateField(null=True, blank=True)
    window_end = models.DateField(null=True, blank=True)
    source_timezone = models.CharField(max_length=50, blank=True)
    region = models.CharField(max_length=10, blank=True)
    platform = models.CharField(max_length=100, blank=True)
    language = models.CharField(max_length=20, blank=True)
    published_at = models.DateTimeField(null=True, blank=True)
    observed_at = models.DateTimeField()
    curated_fields = models.JSONField(default=dict, blank=True)

    def clean(self):
        from django.core.exceptions import ValidationError
        from pydantic import ValidationError as ContractError
        from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
        from .ingestion.contracts import ReleaseTime, SourceEvent

        try:
            stamp = self.scheduled_at
            if stamp and self.source_timezone:
                try:
                    stamp = stamp.astimezone(ZoneInfo(self.source_timezone))
                except ZoneInfoNotFoundError:
                    pass
            release = ReleaseTime(precision=self.precision, start=self.window_start, end=self.window_end, timestamp=stamp, label=self.date_label, timezone=self.source_timezone)
            SourceEvent(external_key=self.external_key, kind=self.kind, title=self.title, verification=self.verification, lifecycle=self.lifecycle, release=release, url='https://example.com/')
            self.window_start, self.window_end = release.start, release.end
        except ContractError as exc:
            raise ValidationError('Check event type, verification, lifecycle, and release precision/window.') from exc

    class Meta:
        constraints = [models.UniqueConstraint(fields=["scope_key", "work", "provider", "external_key"], name="unique_source_event")]
        indexes = [models.Index(fields=["window_start", "kind"], name="tracker_event_date_kind_idx")]


class Claim(Record):
    source = models.ForeignKey(SourceDocument, on_delete=models.PROTECT, related_name="claims")
    event = models.ForeignKey(Event, null=True, blank=True, on_delete=models.CASCADE, related_name="claims")
    work = models.ForeignKey(Work, null=True, blank=True, on_delete=models.CASCADE)
    payload = models.JSONField(default=dict)
    locator = models.CharField(max_length=1000, blank=True)
    original_text = models.TextField(blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["source", "event"], name="unique_event_evidence")]


class EventRevision(Record):
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="revisions")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    source = models.ForeignKey(SourceDocument, null=True, on_delete=models.PROTECT)
    before = models.JSONField(default=dict)
    after = models.JSONField(default=dict)
    reason = models.CharField(max_length=500)


class Follow(Record):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="follows")
    work = models.ForeignKey(Work, null=True, blank=True, on_delete=models.CASCADE)
    franchise = models.ForeignKey(Franchise, null=True, blank=True, on_delete=models.CASCADE)
    include_related = models.BooleanField(default=False)
    status = models.CharField(max_length=20, default="planned")
    progress = models.PositiveIntegerField(default=0)
    progress_kind = models.CharField(max_length=20, default="episode")

    class Meta:
        constraints = [
            models.CheckConstraint(condition=(Q(work__isnull=False, franchise__isnull=True) | Q(work__isnull=True, franchise__isnull=False)), name="follow_one_target"),
            models.UniqueConstraint(fields=["owner", "work"], name="unique_user_work_follow"),
            models.UniqueConstraint(fields=["owner", "franchise"], name="unique_user_franchise_follow"),
        ]


class SavedFilter(Record):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    filters = models.JSONField(default=dict)


class AdapterState(Record):
    identity = models.OneToOneField(ExternalIdentity, on_delete=models.CASCADE, related_name="adapter_state")
    last_good_snapshot = models.JSONField(default=dict)
    missing_counts = models.JSONField(default=dict)
    last_checked_at = models.DateTimeField(null=True, blank=True)
    last_success_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True)
    diagnostics = models.JSONField(default=list)
    lease_until = models.DateTimeField(null=True, blank=True)


class IngestionRun(Record):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.CASCADE)
    identity = models.ForeignKey(ExternalIdentity, null=True, blank=True, on_delete=models.CASCADE)
    work = models.ForeignKey(Work, null=True, blank=True, on_delete=models.CASCADE)
    provider = models.CharField(max_length=50)
    input = models.JSONField(default=dict)
    status = models.CharField(max_length=20, default="queued")
    message = models.CharField(max_length=1000, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)


class ModelConfig(Record):
    owner = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    provider = models.CharField(max_length=30, default="openai-compatible")
    endpoint = models.URLField(max_length=2000)
    model = models.CharField(max_length=200)
    credential_ciphertext = models.TextField(blank=True)
    max_input_chars = models.PositiveIntegerField(default=12000)
    max_output_tokens = models.PositiveIntegerField(default=2000)
    daily_requests = models.PositiveIntegerField(default=20)


class ExtractionUsage(models.Model):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    date = models.DateField()
    requests = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["owner", "date"], name="unique_daily_model_usage")]


class ReviewProposal(Record):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    work = models.ForeignKey(Work, on_delete=models.CASCADE)
    source = models.ForeignKey(SourceDocument, on_delete=models.PROTECT)
    external_key = models.CharField(max_length=500)
    payload = models.JSONField(default=dict)
    status = models.CharField(max_length=20, default="pending")
    model = models.CharField(max_length=200, blank=True)
    message = models.TextField(blank=True)
    event = models.ForeignKey(Event, null=True, blank=True, on_delete=models.SET_NULL)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["owner", "work", "source", "external_key"], name="unique_review_claim")]


class FeedSubscription(Record):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    work = models.ForeignKey(Work, on_delete=models.CASCADE)
    url = models.URLField(max_length=2000)
    source_kind = models.CharField(max_length=30, default="rss")
    last_checked_at = models.DateTimeField(null=True, blank=True)
    last_error = models.CharField(max_length=1000, blank=True)
    seen_ids = models.JSONField(default=list)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["owner", "work", "url"], name="unique_user_feed")]


class APIToken(Record):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    digest = models.CharField(max_length=64, unique=True)
    expires_at = models.DateTimeField()
