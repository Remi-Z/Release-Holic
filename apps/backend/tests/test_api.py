from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.test import Client, override_settings

from tracker.ingestion.byom import encrypt_credential, extract, reserve_usage
from tracker.ingestion.contracts import AdapterError, Metadata, Snapshot, SourceEvent, SourceUnit, parse_release_time
from tracker.ingestion.http import get_bytes, safe_url
from tracker.models import AdapterState, Claim, Event, EventRevision, ExternalIdentity, Follow, Franchise, IngestionRun, ModelConfig, Relationship, ReviewProposal, SavedFilter, SourceDocument, Unit, Work
from tracker.services import apply_snapshot, document_for, issue_token, library_work_ids, upsert_event
from tracker.tasks import refresh_work

pytestmark = pytest.mark.django_db


@pytest.fixture
def users():
    model = get_user_model()
    return model.objects.create_user('alice', password='fixture-password', is_staff=True), model.objects.create_user('bob', password='fixture-password')


@pytest.fixture
def alice(users):
    client = Client(HTTP_AUTHORIZATION='Bearer ' + issue_token(users[0]))
    return client


@pytest.fixture
def bob(users):
    return Client(HTTP_AUTHORIZATION='Bearer ' + issue_token(users[1]))


@pytest.fixture
def work():
    return Work.objects.create(title='Fixture story', kind='anime')


def source(owner=None, text='Releasing in 2027.'):
    return document_for('fixture', 'https://www.apple.com/tv-pr/news/fixture/', {'text': text}, owner=owner, excerpt=text)


def event_data(key='release:1', date='2027', region='JP'):
    return SourceEvent(external_key=key, kind='release', title='A future release', release=parse_release_time(date), region=region, url='https://www.apple.com/tv-pr/news/fixture/')


def test_anonymous_requests_cannot_read_library():
    assert Client().get('/api/library').status_code == 401


def test_duplicate_ingestion_keeps_one_event_and_claim(work):
    doc = source()
    upsert_event(work, 'fixture', event_data(), doc)
    upsert_event(work, 'fixture', event_data(), doc)
    assert Event.objects.count() == Claim.objects.count() == 1
    assert EventRevision.objects.count() == 0


def test_delay_preserves_first_projection_in_revision(work):
    old = upsert_event(work, 'fixture', event_data(date='2027-01'), source())
    incoming = event_data(date='2027-04')
    incoming.lifecycle = 'delayed'
    changed = upsert_event(work, 'fixture', incoming, source(text='Postponed until April 2027.'))
    assert changed.id == old.id
    revision = changed.revisions.get()
    assert revision.before['date_label'] == '2027-01'
    assert revision.after['date_label'] == '2027-04'


def test_announcement_with_year_creates_two_distinct_calendar_facts(work):
    incoming = event_data()
    incoming.kind = 'announcement'
    incoming.published_at = datetime(2026, 10, 6, 12, tzinfo=timezone.utc)
    upsert_event(work, 'fixture', incoming, source())
    announced = Event.objects.get(kind='announcement')
    projected = Event.objects.get(kind='release')
    assert announced.window_start.isoformat() == '2026-10-06'
    assert projected.precision == 'year'
    assert projected.window_start.isoformat() == '2027-01-01'
    assert projected.window_end.isoformat() == '2027-12-31'
    assert Claim.objects.count() == 2


def test_timezone_equivalent_polls_do_not_create_fake_revisions(work):
    incoming = event_data(date='2027-04-02T21:00:00+09:00')
    doc = source()
    upsert_event(work, 'fixture', incoming, doc)
    upsert_event(work, 'fixture', incoming, doc)
    assert EventRevision.objects.count() == 0


def test_streaming_poll_keeps_first_observed_availability(work):
    first = event_data(date='2026-10-01T00:00:00Z'); first.kind = 'availability'
    later = event_data(date='2026-10-02T00:00:00Z'); later.kind = 'availability'
    row = upsert_event(work, 'fixture', first, source())
    updated = upsert_event(work, 'fixture', later, source(text='Still available'))
    assert updated.scheduled_at == row.scheduled_at
    assert not updated.revisions.exists()


def test_progress_credentials_filters_and_runs_are_account_scoped(users, alice, bob, work):
    follow = Follow.objects.create(owner=users[0], work=work, progress=4)
    saved = SavedFilter.objects.create(owner=users[0], name='Private', filters={'medium': 'anime'})
    run = IngestionRun.objects.create(owner=users[0], work=work, provider='fixture')
    ModelConfig.objects.create(owner=users[0], endpoint='https://api.openai.com/v1', model='fixture', credential_ciphertext=encrypt_credential('private-api-key'))
    assert bob.get('/api/library').json() == []
    assert bob.patch(f'/api/library/{follow.pk}', data='{"status":"completed","progress":99,"include_related":false,"progress_kind":"episode"}', content_type='application/json').status_code == 404
    assert bob.delete(f'/api/filters/{saved.pk}').status_code == 404
    assert bob.get(f'/api/runs/{run.pk}').status_code == 404
    assert bob.get('/api/model').json() is None
    assert bob.get('/api/runs').json() == []
    returned = alice.get('/api/model')
    assert returned.json()['has_credential']
    assert 'private-api-key' not in returned.content.decode()
    assert 'credential_ciphertext' not in returned.content.decode()


def test_private_claim_cannot_be_seen_in_other_timeline_or_evidence(users, alice, bob, work):
    own = upsert_event(work, 'review', event_data(), source(users[0]), owner=users[0])
    Follow.objects.create(owner=users[1], work=work)
    assert bob.get('/api/timeline').json()['events'] == []
    assert bob.get(f'/api/events/{own.pk}').status_code == 404
    assert alice.get(f'/api/events/{own.pk}').status_code == 200


def test_regional_filter_includes_global_but_excludes_other_countries(users, alice, work):
    Follow.objects.create(owner=users[0], work=work)
    doc = source()
    for country in ['JP', 'US', '']:
        upsert_event(work, 'fixture', event_data(key='release:' + country, region=country), doc)
    result = alice.get('/api/timeline?region=JP').json()
    assert {event['region'] for event in result['events']} == {'JP', ''}


def test_partial_year_intersects_month_filter_and_undated_stays_tba(users, alice, work):
    Follow.objects.create(owner=users[0], work=work)
    upsert_event(work, 'fixture', event_data(), source())
    unknown = event_data(key='sequel:1', date=None); unknown.kind = 'sequel'
    upsert_event(work, 'fixture', unknown, source())
    dated = alice.get('/api/timeline?date_from=2027-05-01&date_to=2027-05-31&include_tba=false').json()
    assert len(dated['events']) == 1
    assert dated['events'][0]['precision'] == 'year'
    undated = alice.get('/api/timeline?tba_only=true').json()
    assert len(undated['events']) == 1 and undated['events'][0]['window_start'] is None


def test_local_day_filter_matches_instant_without_shifting_calendar_dates(users, alice, work):
    Follow.objects.create(owner=users[0], work=work)
    upsert_event(work, 'fixture', event_data(date='2027-07-31T23:30:00Z'), source())
    upsert_event(work, 'fixture', event_data(key='book:1', date='2027-08-01'), source())
    japan = alice.get('/api/timeline?date_from=2027-08-01&date_to=2027-08-01&display_timezone=Asia/Tokyo').json()
    utc = alice.get('/api/timeline?date_from=2027-08-01&date_to=2027-08-01&display_timezone=UTC').json()
    assert len(japan['events']) == 2
    assert len(utc['events']) == 1 and utc['events'][0]['precision'] == 'day'


def test_ambiguous_local_titles_remain_separate(alice):
    for index, kind in enumerate(['anime', 'light_novel']):
        record = Work.objects.create(title='Ｓｔａｒ', kind=kind)
        ExternalIdentity.objects.create(work=record, provider='fixture', namespace=kind, external_id=str(index))
    with patch('tracker.api.adapter_for', side_effect=AdapterError('Offline')):
        result = alice.get('/api/search?query=Star').json()
    assert len(result['candidates']) == 2
    assert len({row['existing_work_id'] for row in result['candidates']}) == 2


def test_related_follow_expands_cycles_and_franchise(users, work):
    other = Work.objects.create(title='Sequel', kind='anime')
    adaptation = Work.objects.create(title='Novel', kind='light_novel')
    Relationship.objects.create(from_work=other, to_work=work, kind='sequel_to')
    Relationship.objects.create(from_work=work, to_work=adaptation, kind='adaptation_of')
    Relationship.objects.create(from_work=adaptation, to_work=other, kind='part_of')
    row = Follow.objects.create(owner=users[0], work=work, include_related=False)
    assert library_work_ids(users[0]) == {work.id}
    row.include_related = True; row.save()
    assert library_work_ids(users[0]) == {work.id, other.id, adaptation.id}
    franchise = Franchise.objects.create(title='Second franchise')
    extra = Work.objects.create(title='In franchise', kind='movie', franchise=franchise)
    Follow.objects.create(owner=users[0], franchise=franchise)
    assert extra.id in library_work_ids(users[0])


def test_incomplete_snapshot_leaves_last_successful_work_and_units(work):
    identity = ExternalIdentity.objects.create(work=work, provider='kakuyomu', namespace='work', external_id='1')
    meta = Metadata(provider='kakuyomu', namespace='work', external_id='1', title='Good title', kind='web_novel', url='https://kakuyomu.jp/works/1')
    good = Snapshot(metadata=meta, units=[SourceUnit(external_id='2', title='First', kind='chapter')])
    apply_snapshot(identity, good)
    partial = Snapshot(metadata=meta.model_copy(update={'title': 'Bad partial title'}), complete=False)
    with pytest.raises(AdapterError):
        apply_snapshot(identity, partial)
    work.refresh_from_db()
    assert work.title == 'Good title'
    assert Unit.objects.filter(work=work, active=True).count() == 1
    assert AdapterState.objects.get(identity=identity).last_good_snapshot['metadata']['title'] == 'Good title'


def test_curator_correction_survives_ingestion(alice, work):
    identity = ExternalIdentity.objects.create(work=work, provider='tvmaze', namespace='show', external_id='1')
    response = alice.patch(f'/api/works/{work.pk}', data='{"title":"Curated title","aliases":["Alias"],"franchise_id":null}', content_type='application/json')
    assert response.status_code == 200
    apply_snapshot(identity, Snapshot(metadata=Metadata(provider='tvmaze', namespace='show', external_id='1', title='Source title', kind='show', url='https://www.tvmaze.com/shows/1')))
    work.refresh_from_db()
    assert work.title == 'Curated title' and work.aliases == ['Alias']


def test_curated_release_window_survives_source_refresh(work):
    doc = source()
    event = upsert_event(work, 'fixture', event_data(date='2027-01'), doc)
    event.curated_fields = {'precision': 'month', 'window_start': '2027-04-01', 'window_end': '2027-04-30', 'date_label': '2027-04', 'verification': 'confirmed'}
    event.save()
    changed = upsert_event(work, 'fixture', event_data(date='2027-01'), doc)
    assert changed.window_start.isoformat() == '2027-04-01'
    assert changed.verification == 'confirmed'


def test_adapter_failure_retains_baseline_and_marks_job(users, work):
    identity = ExternalIdentity.objects.create(work=work, provider='tvmaze', namespace='show', external_id='1')
    state = AdapterState.objects.create(identity=identity, last_good_snapshot={'retained': True})
    run = IngestionRun.objects.create(owner=users[0], work=work, identity=identity, provider='tvmaze')
    with patch('tracker.tasks.adapter_for', side_effect=AdapterError('Fixture outage')):
        refresh_work(str(run.id))
    state.refresh_from_db(); run.refresh_from_db()
    assert state.last_good_snapshot == {'retained': True}
    assert state.last_error == 'Fixture outage'
    assert run.status == 'failed' and state.lease_until is None


def test_review_decision_is_private_once_and_evidence_bound(users, alice, bob, work):
    doc = source(users[0])
    incoming = event_data(); incoming.original_text = doc.excerpt
    proposal = ReviewProposal.objects.create(owner=users[0], work=work, source=doc, external_key=incoming.external_key, payload=incoming.model_dump(mode='json'))
    assert bob.post(f'/api/review/{proposal.pk}', data='{"action":"approve"}', content_type='application/json').status_code == 404
    assert alice.post(f'/api/review/{proposal.pk}', data='{"action":"approve"}', content_type='application/json').status_code == 200
    assert alice.post(f'/api/review/{proposal.pk}', data='{"action":"approve"}', content_type='application/json').status_code == 409
    assert Event.objects.get().owner_id == users[0].pk


def test_review_rejects_a_fabricated_quotation(users, alice, work):
    incoming = event_data()
    proposal = ReviewProposal.objects.create(owner=users[0], work=work, source=source(users[0]), external_key=incoming.external_key, payload=incoming.model_dump(mode='json'))
    incoming.original_text = 'Not in the source'
    result = alice.post(f'/api/review/{proposal.pk}', data={'action': 'approve', 'payload': incoming.model_dump(mode='json')}, content_type='application/json')
    assert result.status_code == 422 and not Event.objects.exists()


def test_model_usage_limit_and_encrypted_credential(users):
    config = ModelConfig.objects.create(owner=users[0], endpoint='https://api.openai.com/v1', model='fixture', daily_requests=1, credential_ciphertext=encrypt_credential('secret'))
    assert config.credential_ciphertext != 'secret'
    reserve_usage(config)
    with pytest.raises(AdapterError, match='Daily'):
        reserve_usage(config)


def test_invalid_model_output_makes_no_timeline_changes(users, work):
    config = ModelConfig.objects.create(owner=users[0], endpoint='https://api.openai.com/v1', model='fixture')
    with patch('pydantic_ai.Agent.run_sync', side_effect=ValueError('Invalid model response with secret')):
        with pytest.raises(AdapterError, match='invalid structured output'):
            extract(config, source(users[0]), 'Releasing in 2027.', work_title=work.title)
    assert not Event.objects.exists()


def test_model_claim_without_verbatim_evidence_is_discarded(users, work):
    config = ModelConfig.objects.create(owner=users[0], endpoint='https://api.openai.com/v1', model='fixture')
    output = SimpleNamespace(output=SimpleNamespace(events=[event_data()]))
    with patch('pydantic_ai.Agent.run_sync', return_value=output):
        assert extract(config, source(users[0]), 'Releasing in 2027.', work_title=work.title) == []


def test_source_url_blocks_private_hosts_and_credentials():
    for value in ['http://127.0.0.1/', 'https://169.254.169.254/', 'https://localhost/', 'https://user:secret@api.tvmaze.com/shows/1', 'https://api.tvmaze.com:444/shows/1', 'https://evil.example/', 'https://kakuyomu.jp/works/1/episodes/2', 'https://kakuyomu.jp/_next/data/build/works/1/episodes/2.json']:
        with pytest.raises(AdapterError):
            safe_url(value)
    with override_settings(ALLOW_LOCAL_MODELS=True):
        assert safe_url('http://127.0.0.1:11434/v1', model=True).startswith('http://')
        with pytest.raises(AdapterError):
            safe_url('http://127.0.0.1:11434/v1')


def test_redirect_to_private_host_is_revalidated():
    import httpx

    original = httpx.Client
    transport = httpx.MockTransport(lambda request: httpx.Response(302, headers={'Location': 'http://169.254.169.254/'}))
    with patch('tracker.ingestion.http.httpx.Client', side_effect=lambda **kwargs: original(transport=transport, **kwargs)):
        with pytest.raises(AdapterError):
            get_bytes('https://api.tvmaze.com/shows/1')


def test_duplicate_exact_import_creates_one_identity_and_follow(users, alice):
    with patch('tracker.api.dispatch'):
        for _ in range(2):
            assert alice.post('/api/catalogue/import', data={'provider': 'tvmaze', 'namespace': 'show', 'external_id': '42'}, content_type='application/json').status_code == 200
    assert Work.objects.count() == ExternalIdentity.objects.count() == Follow.objects.count() == 1
