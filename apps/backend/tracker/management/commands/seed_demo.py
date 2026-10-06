"""Optional, explicitly fictional data. No passwords or real release claims are seeded."""
from datetime import datetime, timedelta, timezone
from uuid import NAMESPACE_URL, uuid5

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from tracker.ingestion.contracts import SourceEvent, parse_release_time
from tracker.models import Creator, ExternalIdentity, Follow, Franchise, ReviewProposal, Work
from tracker.services import document_for, upsert_event

DEMO_URL = 'https://github.com/Remi-Z/Release-Holic#fictional-demo'


class Command(BaseCommand):
    help = 'Add clearly labelled fictional demonstration stories to an existing account'

    def add_arguments(self, parser):
        parser.add_argument('--user', required=True, help='Existing username; creates no account or password')

    @transaction.atomic
    def handle(self, *args, **options):
        user = get_user_model().objects.filter(username=options['user']).first()
        if not user:
            raise CommandError('Create an account first, then pass its username with --user')
        now = datetime.now(timezone.utc)
        day = now.date()
        franchise, _ = Franchise.objects.get_or_create(id=uuid5(NAMESPACE_URL, 'release-holic.demo/franchise'), defaults={'title': 'The Starbound Stories · Demo'})
        entries = [
            ('signal', 'The Last Signal', 'show', 'Orion Pictures · Fictional', 'episode_release', 'S02 E04 · A voice from the dark', (day + timedelta(days=2)).isoformat(), 'Apple TV', 'US', 'confirmed'),
            ('bloom', 'After the Rain, We Bloom', 'anime', 'Studio Petal · Fictional', 'pv', 'Second promotional video', (day + timedelta(days=5)).isoformat(), 'YouTube', 'JP', 'reported'),
            ('station', '星を待つ駅 / The Station Between Stars', 'web_novel', '架空の作者', 'chapter_release', 'Chapter 38 · A letter for tomorrow', (day + timedelta(days=1)).isoformat(), 'Kakuyomu', 'JP', 'confirmed'),
            ('atlas', 'The Atlas of Quiet Worlds', 'light_novel', 'Mira Ito · Fictional', 'volume_release', 'Volume 3 · The northern passage', (day.replace(day=1) + timedelta(days=40)).strftime('%Y-%m'), '', 'JP', 'reported'),
            ('orbit', 'A Small Orbit', 'movie', 'Sora Films · Fictional', 'release', 'Theatrical premiere', (day + timedelta(days=15)).isoformat(), 'Cinema', 'US', 'confirmed'),
            ('starbound', 'Starbound: The Next Voyage', 'anime', 'Studio Petal · Fictional', 'sequel', 'A sequel has been announced', '', '', 'JP', 'reported'),
            ('margins', 'Stories in the Margins', 'light_novel', 'Mira Ito · Fictional', 'adaptation', 'Animated adaptation in development', str(day.year + 1), '', 'JP', 'unverified'),
        ]
        for slug, title, kind, creator_name, event_kind, event_title, when, platform, region, verification in entries:
            record, _ = Work.objects.update_or_create(id=uuid5(NAMESPACE_URL, 'release-holic.demo/work/' + slug), defaults={'title': title, 'original_title': title, 'kind': kind, 'status': 'fictional_demo', 'language': 'ja' if region == 'JP' else 'en', 'franchise': franchise if slug in {'bloom', 'starbound'} else None, 'summary': 'Fictional demonstration story, used to explore the interface. Dates are illustrative.', 'metadata': {'demo': True}})
            creator, _ = Creator.objects.get_or_create(name=creator_name)
            record.creators.set([creator])
            ExternalIdentity.objects.get_or_create(work=record, provider='demo', namespace=kind, external_id=slug)
            Follow.objects.get_or_create(owner=user, work=record, defaults={'status': 'in_progress' if slug in {'signal', 'station'} else 'planned', 'progress': 37 if slug == 'station' else 3 if slug == 'signal' else 0, 'progress_kind': 'chapter' if kind == 'web_novel' else 'volume' if kind == 'light_novel' else 'episode', 'include_related': slug == 'bloom'})
            text = f'FICTIONAL DEMO: {title}: {event_title}. Illustrative date: {when or "TBA"}.'
            document = document_for('demo', DEMO_URL, {'slug': slug, 'text': text}, owner=user, title='Fictional demo evidence', excerpt=text, published_at=now - timedelta(days=2))
            event = SourceEvent(external_key='demo:' + slug, kind=event_kind, title=event_title, summary='Fictional demonstration event. This is not a factual source report.', release=parse_release_time(when), verification=verification, lifecycle='announced' if not when else 'scheduled', region=region, platform=platform, url=DEMO_URL, original_text=text, locator='seed_demo / fictional fixture', published_at=now - timedelta(days=2))
            upsert_event(record, 'demo', event, document, owner=user, reason='Fictional demonstration data')
            if slug == 'starbound':
                proposal = event.model_copy(update={'external_key': 'demo:review', 'verification': 'unverified', 'title': 'Possible spin-off: a source worth checking'})
                ReviewProposal.objects.get_or_create(owner=user, work=record, source=document, external_key=proposal.external_key, defaults={'payload': proposal.model_dump(mode='json'), 'message': 'Fictional demo proposal'})
        self.stdout.write(self.style.SUCCESS('Added 7 fictional stories, private timeline events, and a review example.'))
