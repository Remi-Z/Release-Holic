import hashlib
import json
import secrets
from datetime import datetime, timedelta, timezone as utc_timezone

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from .ingestion.contracts import AdapterError, Snapshot, SourceEvent, diff_snapshots, parse_release_time
from .models import AdapterState, APIToken, Claim, Creator, Edition, Event, EventRevision, ExternalIdentity, Follow, SourceDocument, Unit, Work


def issue_token(user):
    raw = secrets.token_urlsafe(40)
    APIToken.objects.create(owner=user, digest=hashlib.sha256(raw.encode()).hexdigest(), expires_at=timezone.now() + timedelta(days=7))
    return raw


def event_payload(event):
    fields = ["kind", "title", "summary", "verification", "lifecycle", "precision", "date_label", "scheduled_at", "window_start", "window_end", "source_timezone", "region", "platform", "language", "published_at", "observed_at"]
    result = {}
    for field in fields:
        value = getattr(event, field)
        if isinstance(value, datetime):
            value = value.astimezone(utc_timezone.utc).isoformat()
        result[field] = value
    return json.loads(json.dumps(result, default=str))


def document_for(provider, url, payload, *, owner=None, title="", excerpt="", published_at=None, observed_at=None):
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()
    scope = str(owner.pk) if owner else "shared"
    document, _ = SourceDocument.objects.get_or_create(scope_key=scope, url=url, content_hash=digest, defaults={"owner": owner, "provider": provider, "title": title[:1000], "excerpt": excerpt[:30000], "published_at": published_at, "observed_at": observed_at or timezone.now(), "metadata": payload})
    return document


def stable_source_payload(incoming):
    payload = incoming.model_dump(mode='json')
    if incoming.kind == 'availability':
        # Providers establish availability, while the document records when the
        # system first observed it. Poll clocks are not new source versions.
        payload['release'] = {'precision': 'unknown', 'label': 'Availability observed by collector'}
    return payload


def upsert_event(work, provider, incoming: SourceEvent, document, *, owner=None, actor=None, reason="Source update"):
    scope = str(owner.pk) if owner else "shared"
    observed = document.observed_at
    release = incoming.release
    # “Announced today, releasing next year” is two calendar facts. Keep the
    # announcement at publication time and retain a distinct projected window.
    if incoming.kind in {"announcement", "sequel", "adaptation"}:
        if release.precision != "unknown" or incoming.kind in {"sequel", "adaptation"}:
            projection = incoming.model_copy(update={"kind": "volume_release" if work.kind == "light_novel" else "release", "external_key": "projection:" + hashlib.sha256(incoming.external_key.encode()).hexdigest(), "title": f"{work.title} · projected release"[:1000]})
            upsert_event(work, provider, projection, document, owner=owner, actor=actor, reason=reason)
        publication = incoming.published_at or document.published_at
        release = parse_release_time(publication.isoformat()) if publication else parse_release_time(document.metadata.get("publication_date"))
    data = {
        "owner": owner, "kind": incoming.kind, "title": incoming.title, "summary": incoming.summary,
        "verification": incoming.verification, "lifecycle": incoming.lifecycle,
        "precision": release.precision.value, "date_label": release.label,
        "scheduled_at": release.timestamp, "window_start": release.start,
        "window_end": release.end, "source_timezone": release.timezone,
        "region": incoming.region, "platform": incoming.platform, "language": incoming.language,
        "published_at": incoming.published_at, "observed_at": observed,
        "unit": Unit.objects.filter(work=work, provider=provider, external_id=incoming.unit_id).first() if incoming.unit_id else None,
        "edition": Edition.objects.filter(work=work, provider=provider, product_id=incoming.product_id).first() if incoming.product_id else None,
    }
    event, created = Event.objects.get_or_create(scope_key=scope, work=work, provider=provider, external_key=incoming.external_key, defaults=data)
    if not created:
        before = event_payload(event)
        # Polls do not rewrite the first observation or claim a new availability release.
        data["observed_at"] = event.observed_at
        if incoming.kind == "availability":
            for key in ["scheduled_at", "window_start", "window_end", "date_label"]:
                data[key] = getattr(event, key)
        for key, value in event.curated_fields.items():
            if key in data and key not in {"owner", "unit", "edition", "observed_at"}:
                data[key] = Event._meta.get_field(key).to_python(value)
        for key, value in data.items():
            setattr(event, key, value)
        after = event_payload(event)
        if before != after:
            event.save()
            EventRevision.objects.create(event=event, actor=actor, source=document, before=before, after=after, reason=reason)
    Claim.objects.get_or_create(source=document, event=event, defaults={"work": work, "payload": incoming.model_dump(mode="json"), "locator": incoming.locator, "original_text": incoming.original_text})
    return event


@transaction.atomic
def apply_snapshot(identity, snapshot: Snapshot):
    state, _ = AdapterState.objects.select_for_update().get_or_create(identity=identity)
    previous = Snapshot.model_validate(state.last_good_snapshot) if state.last_good_snapshot else None
    diff = diff_snapshots(previous, snapshot, state.missing_counts)
    if snapshot.metadata.external_id != identity.external_id or snapshot.metadata.provider != identity.provider or snapshot.metadata.namespace != identity.namespace:
        raise AdapterError("The returned source identity did not match the requested work")
    work = Work.objects.select_for_update().get(pk=identity.work_id)
    meta = snapshot.metadata
    for key in ["title", "original_title", "aliases", "kind", "summary", "language", "status", "image_url"]:
        setattr(work, key, getattr(meta, key))
    work.canonical_url = meta.url
    work.metadata = {key: value for key, value in meta.extra.items() if key != 'source_payloads'}
    # Curator-selected display metadata survives every subsequent source refresh.
    for key in ["title", "original_title", "aliases", "kind", "summary", "language", "status", "canonical_url", "image_url", "franchise_id"]:
        if key in work.curated_fields:
            setattr(work, key, work.curated_fields[key])
    work.save()
    creators = []
    for name in work.curated_fields.get('creators', meta.creators):
        creator, _ = Creator.objects.get_or_create(name=name[:300])
        creators.append(creator)
    work.creators.set(creators)
    for unit in snapshot.units:
        Unit.objects.update_or_create(work=work, provider=identity.provider, external_id=unit.external_id, defaults={"title": unit.title, "kind": unit.kind, "label": unit.label, "ordinal": unit.ordinal, "canonical_url": unit.url, "published_at": unit.published_at, "modified_at": unit.modified_at, "active": True})
    for change in diff.changes:
        if change.kind == "removed":
            Unit.objects.filter(work=work, provider=identity.provider, external_id=change.unit.external_id).update(active=False)
    for edition in snapshot.editions:
        Edition.objects.update_or_create(provider=identity.provider, product_id=edition.product_id, format=edition.format, language=edition.language, defaults={"work": work, "isbn": edition.isbn, "title": edition.title, "volume_label": edition.volume_label, "publisher": edition.publisher, "imprint": edition.imprint, "release_date": edition.release.start if edition.release.precision == "day" else None, "canonical_url": edition.url})
    payload = snapshot.model_dump(mode="json", exclude={"observed_at"})
    payload['events'] = [stable_source_payload(event) for event in snapshot.events]
    document = document_for(identity.provider, meta.url, payload, title=meta.title, observed_at=snapshot.observed_at)
    for incoming in snapshot.events:
        source = document
        if incoming.url != meta.url:
            source = document_for(identity.provider, incoming.url, stable_source_payload(incoming), title=incoming.title, excerpt=incoming.original_text, published_at=incoming.published_at, observed_at=snapshot.observed_at)
        upsert_event(work, identity.provider, incoming, source)
    if identity.provider == "kakuyomu":
        for change in diff.changes:
            unit = change.unit
            if change.kind == "added":
                incoming = SourceEvent(external_key=f"chapter:{unit.external_id}", kind="chapter_release", title=unit.title, release=unit.release, lifecycle="released", region="JP", language="ja", url=unit.url, unit_id=unit.external_id, published_at=unit.published_at, locator=f"chapter index / episodes/{unit.external_id}")
            else:
                # Metadata changes retain an observation time; they are not new releases.
                fingerprint = hashlib.sha256(unit.model_dump_json().encode()).hexdigest()[:16]
                incoming = SourceEvent(external_key=f"chapter-change:{unit.external_id}:{change.kind}:{fingerprint}", kind="metadata_change", title=f"Chapter {change.kind}: {unit.title}", summary="A complete source snapshot showed this metadata change.", url=meta.url, unit_id=unit.external_id, lifecycle="released", locator=f"chapter index / episodes/{unit.external_id}")
            upsert_event(work, identity.provider, incoming, document)
    from .models import Relationship

    for relation in snapshot.relationships:
        target = ExternalIdentity.objects.filter(provider=relation.target.provider, namespace=relation.target.namespace, external_id=relation.target.external_id).first()
        if target and target.work_id != work.id:
            from_work, to_work = (target.work, work) if relation.reverse else (work, target.work)
            Relationship.objects.get_or_create(from_work=from_work, to_work=to_work, kind=relation.kind, defaults={"source": document, "verification": "reported"})
    state.last_good_snapshot = diff.baseline.model_dump(mode="json")
    state.missing_counts = diff.missing_counts
    state.last_success_at = state.last_checked_at = timezone.now()
    state.last_error = ""
    state.diagnostics = snapshot.diagnostics
    state.save()
    return work


def library_work_ids(user, status=None):
    follows = Follow.objects.filter(owner=user)
    if status:
        follows = follows.filter(status=status)
    ids = set(follows.filter(work__isnull=False).values_list("work_id", flat=True))
    franchises = follows.filter(franchise__isnull=False).values_list("franchise_id", flat=True)
    ids.update(Work.objects.filter(franchise_id__in=franchises).values_list("id", flat=True))
    expanded = set(follows.filter(include_related=True, work__isnull=False).values_list("work_id", flat=True))
    expanded.update(Work.objects.filter(franchise_id__in=follows.filter(include_related=True, franchise__isnull=False).values_list("franchise_id", flat=True)).values_list("id", flat=True))
    from .models import Relationship

    frontier = set(expanded)
    while frontier:
        related = Relationship.objects.filter(Q(from_work_id__in=frontier) | Q(to_work_id__in=frontier), verification__in=["reported", "confirmed"], kind__in=["sequel_to", "adaptation_of", "spinoff_of", "part_of"])
        next_ids = set(related.values_list("from_work_id", flat=True)) | set(related.values_list("to_work_id", flat=True))
        frontier = next_ids - expanded
        expanded.update(frontier)
    return ids | expanded
