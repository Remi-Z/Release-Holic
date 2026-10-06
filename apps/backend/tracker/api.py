import hashlib
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, time
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.contrib.auth import authenticate
from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.db.models import Case, DateField, Q, When
from django.db.models.functions import Coalesce, TruncDate
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from ninja import NinjaAPI
from ninja.errors import HttpError
from ninja.security import HttpBearer

from . import schemas as s
from .ingestion.byom import encrypt_credential
from .ingestion.contracts import AdapterError, Candidate, SourceEvent
from .ingestion.http import safe_url
from .ingestion.registry import ADAPTERS, adapter_for, capabilities, resolve
from .models import APIToken, AdapterState, Event, FeedSubscription, Follow, Franchise, IngestionRun, ModelConfig, ReviewProposal, SavedFilter, Work, ExternalIdentity
from .services import issue_token, library_work_ids, upsert_event
from .tasks import dispatch, import_article, poll_feed, refresh_work


class TokenAuth(HttpBearer):
    def authenticate(self, request, token):
        digest = hashlib.sha256(token.encode()).hexdigest()
        record = APIToken.objects.select_related("owner").filter(digest=digest, expires_at__gt=timezone.now(), owner__is_active=True).first()
        return record.owner if record else None


api = NinjaAPI(title="Release-Holic API", version="0.1.0", auth=TokenAuth())


@api.exception_handler(AdapterError)
def adapter_error(request, exc):
    return JsonResponse({"detail": str(exc)}, status=422)


def visible_events(user):
    return Event.objects.filter(Q(owner__isnull=True) | Q(owner=user)).select_related("work", "work__franchise").prefetch_related("claims__source")


def display_zone(name):
    try:
        if len(name) > 100:
            raise ValueError
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise HttpError(422, 'Choose a valid display timezone') from exc


def release_from(day, zone):
    return Q(precision='instant', scheduled_at__gte=datetime.combine(day, time.min, tzinfo=zone)) | (~Q(precision='instant') & Q(window_end__gte=day))


def release_through(day, zone):
    return Q(precision='instant', scheduled_at__lte=datetime.combine(day, time.max, tzinfo=zone)) | (~Q(precision='instant') & Q(window_start__lte=day))


def work_out(work):
    return s.WorkOut(id=work.id, title=work.title, original_title=work.original_title, aliases=work.aliases, kind=work.kind, creators=[c.name for c in work.creators.all()], summary=work.summary, language=work.language, status=work.status, canonical_url=work.canonical_url, image_url=work.image_url, franchise_id=work.franchise_id, franchise_title=work.franchise.title if work.franchise else None, identities=[s.IdentityOut(id=i.id, provider=i.provider, namespace=i.namespace, external_id=i.external_id) for i in work.identities.all()], unit_count=work.units.filter(active=True).count(), metadata=work.metadata)


def event_out(event):
    return s.EventOut(**{name: getattr(event, name) for name in ["id", "work_id", "kind", "title", "summary", "verification", "lifecycle", "precision", "date_label", "scheduled_at", "window_start", "window_end", "source_timezone", "region", "platform", "language", "published_at", "observed_at", "provider"]}, work_title=event.work.title, work_kind=event.work.kind, franchise_id=event.work.franchise_id, evidence_count=len({claim.source.url for claim in event.claims.all()}), personal=event.owner_id is not None)


def run_out(run):
    return s.RunOut(**{key: getattr(run, key) for key in s.RunOut.model_fields})


def follow_out(follow):
    return s.FollowOut(id=follow.id, work=work_out(follow.work) if follow.work else None, franchise_id=follow.franchise_id, franchise_title=follow.franchise.title if follow.franchise else None, include_related=follow.include_related, status=follow.status, progress=follow.progress, progress_kind=follow.progress_kind)


@api.get("/health", auth=None, response=s.StatusOut, tags=["System"])
def health(request):
    return {"ok": True, "message": "Release-Holic API"}


@api.post("/auth/login", auth=None, response=s.LoginOut, tags=["Account"])
def login(request, payload: s.LoginIn):
    ip = request.META.get("REMOTE_ADDR", "unknown")
    key = "login:" + hashlib.sha256((ip + payload.username).encode()).hexdigest()
    attempts = cache.get(key, 0)
    if attempts >= 8:
        raise HttpError(429, "Too many login attempts. Try again in a minute.")
    user = authenticate(username=payload.username, password=payload.password)
    if not user or not user.is_active:
        cache.set(key, attempts + 1, 60)
        raise HttpError(401, "Username or password is incorrect")
    cache.delete(key)
    return {"token": issue_token(user), "user": {"id": user.pk, "username": user.username, "is_staff": user.is_staff}}


@api.get("/auth/me", response=s.UserOut, tags=["Account"])
def me(request):
    return {"id": request.auth.pk, "username": request.auth.username, "is_staff": request.auth.is_staff}


@api.post("/auth/logout", response=s.StatusOut, tags=["Account"])
def logout(request):
    raw = request.headers.get("Authorization", "").removeprefix("Bearer ")
    APIToken.objects.filter(owner=request.auth, digest=hashlib.sha256(raw.encode()).hexdigest()).delete()
    return {"ok": True}


@api.get("/search", response=s.SearchOut, tags=["Catalogue"])
def search(request, query: str = "", author: str = "", provider: str = "all", value: str = ""):
    if max(len(query), len(author), len(value)) > 1000:
        raise HttpError(422, "Search input is too long")
    if value:
        identity = resolve(value)
        existing = ExternalIdentity.objects.filter(**identity.model_dump()).select_related("work").first()
        kind = {"tmdb": "movie" if identity.namespace == "movie" else "show", "tvmaze": "show", "bangumi": "anime", "kakuyomu": "web_novel"}.get(identity.provider, "light_novel")
        return {"candidates": [Candidate(**identity.model_dump(), title=existing.work.title if existing else value, kind=kind, existing_work_id=str(existing.work_id) if existing else None)], "errors": []}
    if not query.strip() and not author.strip():
        return {"candidates": [], "errors": []}
    normalize = lambda value: unicodedata.normalize("NFKC", value).casefold().strip()
    q, a = normalize(query), normalize(author)
    local = []
    for work in Work.objects.prefetch_related("creators", "identities").all()[:5000]:
        titles = [work.title, work.original_title, *work.aliases]
        authors = [c.name for c in work.creators.all()]
        author_names = [name for creator in work.creators.all() for name in [creator.name, *creator.aliases]]
        if q and not any(q in normalize(title) for title in titles):
            continue
        if a and not any(a in normalize(name) for name in author_names):
            continue
        first = work.identities.first()
        if first:
            local.append(Candidate(provider=first.provider, namespace=first.namespace, external_id=first.external_id, title=work.title, kind=work.kind, creators=authors, url=work.canonical_url, existing_work_id=str(work.id)))
    selected = ["tvmaze", "bangumi", "ndl"] if provider == "all" else [provider]
    if provider == "all":
        from django.conf import settings

        if settings.TMDB_TOKEN:
            selected.append("tmdb")
    errors, candidates = [], list(local)

    def remote(name):
        try:
            return adapter_for(name).search(query, author), None
        except Exception as exc:
            return [], f"{name}: {str(exc) if isinstance(exc, AdapterError) else 'Search failed; try a direct URL or identifier'}"

    with ThreadPoolExecutor(max_workers=4) as executor:
        for found, error in executor.map(remote, selected):
            candidates.extend(found)
            if error:
                errors.append(error)
    keyed = {(c.provider, c.namespace, c.external_id): c for c in candidates}
    # Existing identities win over remote candidates and never merge fuzzy matches.
    for candidate in local:
        keyed[(candidate.provider, candidate.namespace, candidate.external_id)] = candidate
    return {"candidates": list(keyed.values())[:80], "errors": errors}


@api.post("/catalogue/import", response=s.RunOut, tags=["Catalogue"])
def import_work(request, payload: s.ImportIn):
    value = f"{payload.provider}:{payload.namespace}:{payload.external_id}"
    if payload.provider == "ndl" and payload.namespace == "isbn":
        value = f"isbn:{payload.external_id}"
    identity = resolve(value)
    with transaction.atomic():
        external = ExternalIdentity.objects.filter(**identity.model_dump()).first()
        if not external:
            kind = {"tmdb": "movie" if identity.namespace == "movie" else "show", "tvmaze": "show", "bangumi": "anime", "kakuyomu": "web_novel"}.get(identity.provider, "light_novel")
            work = Work.objects.create(title=f"{identity.provider} · {identity.external_id}", kind=kind, status="awaiting_metadata")
            try:
                with transaction.atomic():
                    external = ExternalIdentity.objects.create(work=work, **identity.model_dump())
            except IntegrityError:
                # Two clients may import the same exact provider identity concurrently.
                work.delete()
                external = ExternalIdentity.objects.get(**identity.model_dump())
        Follow.objects.get_or_create(owner=request.auth, work=external.work, defaults={"include_related": payload.include_related, "progress_kind": "chapter" if external.work.kind == "web_novel" else "volume" if external.work.kind == "light_novel" else "episode"})
        run = IngestionRun.objects.create(owner=request.auth, identity=external, work=external.work, provider=external.provider)
    dispatch(refresh_work, run)
    run.refresh_from_db()
    return run_out(run)


@api.get("/runs/{run_id}", response=s.RunOut, tags=["Sources"])
def run_status(request, run_id: UUID):
    return run_out(get_object_or_404(IngestionRun, pk=run_id, owner=request.auth))


@api.get("/runs", response=list[s.RunOut], tags=["Sources"])
def run_history(request):
    return [run_out(run) for run in IngestionRun.objects.filter(owner=request.auth).order_by("-created_at")[:50]]


@api.get("/works", response=list[s.WorkOut], tags=["Catalogue"])
def works(request):
    return [work_out(work) for work in Work.objects.select_related("franchise").prefetch_related("creators", "identities").order_by("title")[:500]]


@api.get("/franchises", response=list[s.FranchiseOut], tags=["Catalogue"])
def franchises(request):
    return [{"id": row.id, "title": row.title} for row in Franchise.objects.order_by('title')[:500]]


@api.get("/works/{work_id}", response=s.WorkDetailOut, tags=["Catalogue"])
def work_detail(request, work_id: UUID):
    work = get_object_or_404(Work, pk=work_id)
    from .models import Relationship

    relationships = Relationship.objects.filter(Q(from_work=work) | Q(to_work=work)).select_related("from_work", "to_work")
    return {"work": work_out(work), "units": [s.UnitOut(**{name: getattr(unit, name) for name in s.UnitOut.model_fields}) for unit in work.units.all()[:2000]], "editions": [s.EditionOut(**{name: getattr(edition, name) for name in s.EditionOut.model_fields}) for edition in work.editions.all()], "relationships": [{"id": r.id, "kind": r.kind, "from_work_id": r.from_work_id, "to_work_id": r.to_work_id, "from_title": r.from_work.title, "to_title": r.to_work.title, "verification": r.verification} for r in relationships]}


@api.patch("/works/{work_id}", response=s.WorkOut, tags=["Catalogue"])
def correct_work(request, work_id: UUID, payload: s.WorkCorrectionIn):
    if not request.auth.is_staff:
        raise HttpError(403, "Catalogue corrections require a curator account")
    work = get_object_or_404(Work, pk=work_id)
    if payload.franchise_id:
        get_object_or_404(Franchise, pk=payload.franchise_id)
    work.title, work.aliases, work.franchise_id = payload.title, payload.aliases, payload.franchise_id
    work.curated_fields.update(payload.model_dump(mode="json"))
    work.save()
    return work_out(work)


@api.post("/works/{work_id}/refresh", response=list[s.RunOut], tags=["Sources"])
def refresh(request, work_id: UUID):
    work = get_object_or_404(Work, pk=work_id)
    runs = []
    for identity in work.identities.filter(provider__in=ADAPTERS):
        run = IngestionRun.objects.create(owner=request.auth, identity=identity, work=work, provider=identity.provider)
        dispatch(refresh_work, run)
        run.refresh_from_db()
        runs.append(run_out(run))
    return runs


@api.get("/library", response=list[s.FollowOut], tags=["Library"])
def library(request):
    return [follow_out(follow) for follow in Follow.objects.filter(owner=request.auth).select_related("work__franchise", "franchise").order_by("-created_at")]


@api.post("/library", response=s.FollowOut, tags=["Library"])
def follow(request, payload: s.FollowIn):
    work = get_object_or_404(Work, pk=payload.work_id) if payload.work_id else None
    franchise = get_object_or_404(Franchise, pk=payload.franchise_id) if payload.franchise_id else None
    row, _ = Follow.objects.get_or_create(owner=request.auth, work=work, franchise=franchise, defaults={"include_related": payload.include_related, "progress_kind": "chapter" if work and work.kind == "web_novel" else "volume" if work and work.kind == "light_novel" else "episode"})
    return follow_out(row)


@api.patch("/library/{follow_id}", response=s.FollowOut, tags=["Library"])
def update_progress(request, follow_id: UUID, payload: s.ProgressIn):
    row = get_object_or_404(Follow, pk=follow_id, owner=request.auth)
    for key, value in payload.model_dump().items():
        setattr(row, key, value)
    row.save()
    return follow_out(row)


@api.delete("/library/{follow_id}", response=s.StatusOut, tags=["Library"])
def unfollow(request, follow_id: UUID):
    get_object_or_404(Follow, pk=follow_id, owner=request.auth).delete()
    return {"ok": True}


@api.get("/timeline", response=s.TimelineOut, tags=["Timeline"])
def timeline(request, medium: str = "", kind: str = "", platform: str = "", region: str = "", verification: str = "", lifecycle: str = "", franchise_id: UUID | None = None, work_id: UUID | None = None, status: str = "", library_only: bool = True, date_from: date | None = None, date_to: date | None = None, include_tba: bool = True, tba_only: bool = False, basis: str = "release", display_timezone: str = "UTC", offset: int = 0, limit: int = 80):
    if not 0 <= offset <= 100000 or not 1 <= limit <= 200 or basis not in {"release", "announcement"}:
        raise HttpError(422, "Invalid pagination or date basis")
    zone = display_zone(display_timezone)
    events = visible_events(request.auth)
    if library_only or status:
        events = events.filter(work_id__in=library_work_ids(request.auth, status or None))
    if kind == "releases":
        events = events.filter(kind__in=["release", "episode_release", "chapter_release", "volume_release"])
        kind = ""
    for field, value in [("work__kind", medium), ("kind", kind), ("platform__iexact", platform), ("verification", verification), ("lifecycle", lifecycle), ("work__franchise_id", franchise_id), ("work_id", work_id)]:
        if value:
            events = events.filter(**{field: value})
    if region:
        events = events.filter(Q(region__iexact=region) | Q(region=""))
    tba_count = events.filter(window_start__isnull=True).count()
    if basis == "announcement":
        events = events.annotate(display_time=Coalesce("published_at", "observed_at"))
        if date_from:
            events = events.filter(display_time__gte=datetime.combine(date_from, time.min, tzinfo=zone))
        if date_to:
            events = events.filter(display_time__lte=datetime.combine(date_to, time.max, tzinfo=zone))
        events = events.order_by("display_time", "id")
    else:
        if tba_only:
            events = events.filter(window_start__isnull=True)
        elif not include_tba:
            events = events.filter(window_start__isnull=False)
        if date_from:
            events = events.filter(release_from(date_from, zone) | (Q(window_start__isnull=True) if include_tba else Q(pk__in=[])))
        if date_to:
            events = events.filter(release_through(date_to, zone) | (Q(window_start__isnull=True) if include_tba else Q(pk__in=[])))
        events = events.annotate(display_day=Case(When(precision='instant', then=TruncDate('scheduled_at', tzinfo=zone)), default='window_start', output_field=DateField())).order_by("display_day", "scheduled_at", "id")
    return {"events": [event_out(event) for event in events[offset:offset+limit]], "total": events.count(), "tba_count": tba_count, "offset": offset, "limit": limit}


@api.get("/events/{event_id}", response=s.EventDetailOut, tags=["Timeline"])
def event_detail(request, event_id: UUID):
    event = get_object_or_404(visible_events(request.auth), pk=event_id)
    claims = event.claims.filter(Q(source__owner__isnull=True) | Q(source__owner=request.auth)).select_related("source")
    return {"event": event_out(event), "evidence": [{"id": claim.id, "url": claim.source.url, "provider": claim.source.provider, "title": claim.source.title, "locator": claim.locator, "original_text": claim.original_text, "published_at": claim.source.published_at, "observed_at": claim.source.observed_at} for claim in claims], "revisions": [s.RevisionOut(**{name: getattr(revision, name) for name in s.RevisionOut.model_fields}) for revision in event.revisions.order_by("-created_at")[:100]]}


@api.get("/stats", response=s.StatsOut, tags=["Timeline"])
def stats(request, display_timezone: str = 'UTC'):
    ids = library_work_ids(request.auth)
    zone = display_zone(display_timezone)
    return {"followed": Follow.objects.filter(owner=request.auth).count(), "upcoming": visible_events(request.auth).filter(release_from(timezone.now().astimezone(zone).date(), zone), work_id__in=ids).exclude(lifecycle="cancelled").count(), "needs_review": ReviewProposal.objects.filter(owner=request.auth, status="pending").count(), "stale_sources": AdapterState.objects.filter(identity__work_id__in=ids).exclude(last_error="").count()}


@api.get("/sources", response=s.SourcesOut, tags=["Sources"])
def sources(request):
    states = AdapterState.objects.filter(identity__work_id__in=library_work_ids(request.auth)).select_related("identity__work")
    return {"adapters": capabilities(), "states": [{"id": state.id, "work_id": state.identity.work_id, "work_title": state.identity.work.title, "provider": state.identity.provider, "last_checked_at": state.last_checked_at, "last_success_at": state.last_success_at, "last_error": state.last_error, "diagnostics": state.diagnostics} for state in states]}


@api.get("/filters", response=list[s.FilterOut], tags=["Timeline"])
def filters(request):
    return [{"id": row.id, "name": row.name, "filters": row.filters} for row in SavedFilter.objects.filter(owner=request.auth)]


@api.post("/filters", response=s.FilterOut, tags=["Timeline"])
def save_filter(request, payload: s.FilterIn):
    allowed = {"medium", "kind", "platform", "region", "verification", "lifecycle", "franchise_id", "work_id", "status", "library_only", "date_from", "date_to", "include_tba", "tba_only", "basis"}
    if set(payload.filters) - allowed or len(str(payload.filters)) > 4000:
        raise HttpError(422, "Invalid saved filter")
    row = SavedFilter.objects.create(owner=request.auth, **payload.model_dump())
    return {"id": row.id, "name": row.name, "filters": row.filters}


@api.delete("/filters/{filter_id}", response=s.StatusOut, tags=["Timeline"])
def delete_filter(request, filter_id: UUID):
    get_object_or_404(SavedFilter, owner=request.auth, pk=filter_id).delete()
    return {"ok": True}


@api.post("/articles", response=s.RunOut, tags=["Review"])
def submit_article(request, payload: s.ArticleIn):
    safe_url(payload.url)
    work = get_object_or_404(Work, pk=payload.work_id)
    run = IngestionRun.objects.create(owner=request.auth, work=work, provider="article", input=payload.model_dump(mode="json"))
    dispatch(import_article, run)
    run.refresh_from_db()
    return run_out(run)


@api.get("/model", response=s.ModelOut | None, tags=["Model"])
def model_config(request):
    config = ModelConfig.objects.filter(owner=request.auth).first()
    if not config:
        return None
    return {**{name: getattr(config, name) for name in s.ModelOut.model_fields if name != "has_credential"}, "has_credential": bool(config.credential_ciphertext)}


@api.put("/model", response=s.ModelOut, tags=["Model"])
def set_model(request, payload: s.ModelIn):
    safe_url(payload.endpoint, model=True)
    if payload.provider == "google" and payload.endpoint.rstrip("/") != "https://generativelanguage.googleapis.com":
        raise HttpError(422, "The Google provider uses https://generativelanguage.googleapis.com")
    data = payload.model_dump(exclude={"credential"})
    if payload.credential is not None:
        data['credential_ciphertext'] = encrypt_credential(payload.credential)
    ModelConfig.objects.update_or_create(owner=request.auth, defaults=data)
    return model_config(request)


@api.delete("/model", response=s.StatusOut, tags=["Model"])
def delete_model(request):
    ModelConfig.objects.filter(owner=request.auth).delete()
    return {"ok": True}


@api.get("/review", response=list[s.ReviewOut], tags=["Review"])
def review(request, status: str = "pending"):
    rows = ReviewProposal.objects.filter(owner=request.auth, status=status).select_related("work", "source").order_by("-created_at")[:200]
    return [{"id": row.id, "work_id": row.work_id, "work_title": row.work.title, "source_url": row.source.url, "excerpt": row.source.excerpt, "payload": SourceEvent.model_validate(row.payload), "model": row.model, "status": row.status, "message": row.message, "created_at": row.created_at} for row in rows]


@api.post("/review/{proposal_id}", response=s.StatusOut, tags=["Review"])
@transaction.atomic
def decide_review(request, proposal_id: UUID, payload: s.ReviewIn):
    row = get_object_or_404(ReviewProposal.objects.select_for_update(), pk=proposal_id, owner=request.auth)
    if row.status != "pending":
        raise HttpError(409, "This proposal has already been reviewed")
    if payload.action == "reject":
        row.status = "rejected"
    else:
        incoming = payload.payload or SourceEvent.model_validate(row.payload)
        incoming.external_key = row.external_key
        if incoming.original_text.strip() and incoming.original_text.strip() not in row.source.excerpt:
            raise HttpError(422, "The supporting quotation must occur in the collected source text")
        incoming.url = row.source.url
        row.event = upsert_event(row.work, "review", incoming, row.source, owner=request.auth, actor=request.auth, reason="User reviewed a source claim")
        row.payload = incoming.model_dump(mode="json")
        row.status = "approved"
    row.save()
    return {"ok": True, "message": "Claim added to your timeline" if row.status == "approved" else "Claim rejected"}


@api.get("/feeds", response=list[s.FeedOut], tags=["Sources"])
def feeds(request):
    return [s.FeedOut(**{name: getattr(row, name) for name in s.FeedOut.model_fields}) for row in FeedSubscription.objects.filter(owner=request.auth)]


@api.post("/feeds", response=s.FeedOut, tags=["Sources"])
def add_feed(request, payload: s.FeedIn):
    from .ingestion.news import PRESS_PAGES

    url = PRESS_PAGES.get(payload.source_kind) or safe_url(payload.url)
    work = get_object_or_404(Work, pk=payload.work_id)
    row, _ = FeedSubscription.objects.get_or_create(owner=request.auth, work=work, url=url, defaults={"source_kind": payload.source_kind})
    try:
        poll_feed.delay(str(row.id))
    except Exception:
        row.last_error = "Ingestion queue unavailable. Start the worker to monitor this source."
        row.save()
    return s.FeedOut(**{name: getattr(row, name) for name in s.FeedOut.model_fields})


@api.delete("/feeds/{feed_id}", response=s.StatusOut, tags=["Sources"])
def delete_feed(request, feed_id: UUID):
    get_object_or_404(FeedSubscription, owner=request.auth, pk=feed_id).delete()
    return {"ok": True}
