from datetime import timedelta

from celery import shared_task
from django.db import transaction
from django.utils import timezone

from .ingestion.contracts import AdapterError, Identity, TransientAdapterError
from .ingestion.registry import ADAPTERS, adapter_for
from .models import AdapterState, ExternalIdentity, FeedSubscription, IngestionRun, ModelConfig, ReviewProposal
from .services import apply_snapshot, document_for, library_work_ids


def dispatch(task, run):
    try:
        task.delay(str(run.id))
    except Exception:
        run.status = "failed"
        run.message = "The ingestion queue is unavailable. Start RabbitMQ and the worker, then retry."
        run.finished_at = timezone.now()
        run.save()
        raise AdapterError(run.message)


@shared_task(bind=True, max_retries=3)
def refresh_work(self, run_id):
    run = IngestionRun.objects.select_related("identity__work").get(pk=run_id)
    if run.status in {"succeeded", "failed"}:
        return
    identity = run.identity
    state, _ = AdapterState.objects.get_or_create(identity=identity)
    with transaction.atomic():
        state = AdapterState.objects.select_for_update().get(pk=state.pk)
        if state.lease_until and state.lease_until > timezone.now():
            run.status, run.message = "succeeded", "Another worker is already refreshing this source"
            run.finished_at = timezone.now()
            run.save()
            return
        state.lease_until = timezone.now() + timedelta(minutes=5)
        state.last_checked_at = timezone.now()
        state.save()
        run.status = "running"
        run.save()
    retrying = False
    try:
        snapshot = adapter_for(identity.provider).fetch_snapshot(Identity(provider=identity.provider, namespace=identity.namespace, external_id=identity.external_id))
        apply_snapshot(identity, snapshot)
        run.status, run.message = "succeeded", "Source metadata refreshed"
    except Exception as exc:
        message = str(exc)[:1000] if isinstance(exc, AdapterError) else "Adapter failed validation; last successful data was retained"
        AdapterState.objects.filter(pk=state.pk).update(last_error=message)
        retrying = isinstance(exc, TransientAdapterError) and self.request.retries < self.max_retries
        run.status, run.message = ("queued", message + f" · Retry {self.request.retries + 1}/{self.max_retries} pending") if retrying else ("failed", message)
    finally:
        AdapterState.objects.filter(pk=state.pk).update(lease_until=None)
        run.finished_at = None if retrying else timezone.now()
        run.save()
    if retrying:
        raise self.retry(exc=AdapterError(run.message), countdown=60 * 2 ** self.request.retries)


@shared_task
def import_article(run_id):
    from .ingestion.byom import extract
    from .ingestion.news import article, suggested_event

    run = IngestionRun.objects.select_related("owner", "work").get(pk=run_id)
    if run.status in {"succeeded", "failed"}:
        return
    run.status = "running"
    run.save()
    try:
        item = article(run.input['url'])
        source_text = (item['title'] + '\n\n' + item['text'])[:30000]
        source = document_for("article", item['url'], {"title": item['title'], "text": source_text, "publication_date": item['publication_date']}, owner=run.owner, title=item['title'], excerpt=source_text, published_at=item['published_at'])
        if ReviewProposal.objects.filter(owner=run.owner, work=run.work, source=source).exists():
            run.status, run.message = 'succeeded', 'This source version has already been sent for review'
            run.finished_at = timezone.now()
            run.save()
            return
        if run.input.get("use_model"):
            config = ModelConfig.objects.filter(owner=run.owner).first()
            if not config:
                raise AdapterError("Configure your model before requesting model extraction")
            events = extract(config, source, source_text, work_title=run.work.title)
            model_name = config.model
        else:
            events = [suggested_event({**item, "id": item['url']})]
            model_name = ""
        for event in events:
            ReviewProposal.objects.get_or_create(owner=run.owner, work=run.work, source=source, external_key=event.external_key, defaults={"payload": event.model_dump(mode="json"), "model": model_name})
        run.status, run.message = "succeeded", f"{len(events)} supported claims sent for review"
    except Exception as exc:
        run.status = "failed"
        run.message = str(exc)[:1000] if isinstance(exc, AdapterError) else "Article extraction failed; no timeline changes were made"
    run.finished_at = timezone.now()
    run.save()


@shared_task
def poll_feed(subscription_id):
    from .ingestion.news import feed_entries, suggested_event

    subscription = FeedSubscription.objects.select_related("work", "owner").get(pk=subscription_id)
    try:
        entries = feed_entries(subscription.url, source_kind=subscription.source_kind, work=subscription.work)
        seen = list(subscription.seen_ids)
        for entry in entries:
            if entry['id'] in seen:
                continue
            event = suggested_event(entry, source_kind=subscription.source_kind)
            source = document_for(subscription.source_kind, entry['url'], {"id": entry['id'], "title": entry['title'], "text": entry['text']}, owner=subscription.owner, title=entry['title'], excerpt=entry['text'], published_at=entry['published_at'])
            ReviewProposal.objects.get_or_create(owner=subscription.owner, work=subscription.work, source=source, external_key=event.external_key, defaults={"payload": event.model_dump(mode="json")})
            seen.append(entry['id'])
        subscription.seen_ids = seen[-1000:]
        subscription.last_error = ""
    except Exception as exc:
        subscription.last_error = str(exc)[:1000] if isinstance(exc, AdapterError) else "Feed collection failed"
    subscription.last_checked_at = timezone.now()
    subscription.save()


@shared_task
def schedule_refreshes():
    from django.contrib.auth import get_user_model

    followed = set()
    for user in get_user_model().objects.filter(is_active=True).iterator():
        followed.update(library_work_ids(user))
    for identity in ExternalIdentity.objects.filter(work_id__in=followed, provider__in=ADAPTERS).iterator():
        state = AdapterState.objects.filter(identity=identity).first()
        # Match API caching and minimize publisher traffic: catalogue six hours, serials hourly.
        interval = timedelta(hours=1 if identity.provider == "kakuyomu" else 6)
        if state and state.last_checked_at and state.last_checked_at > timezone.now() - interval:
            continue
        run = IngestionRun.objects.create(identity=identity, work=identity.work, provider=identity.provider)
        refresh_work.delay(str(run.id))
    for subscription in FeedSubscription.objects.all().iterator():
        if not subscription.last_checked_at or subscription.last_checked_at < timezone.now() - timedelta(hours=1):
            poll_feed.delay(str(subscription.id))
