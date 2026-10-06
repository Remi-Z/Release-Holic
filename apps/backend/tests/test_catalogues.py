from unittest.mock import patch

from django.test import override_settings

from tracker.ingestion.catalogues import BangumiAdapter, TMDBAdapter, TVmazeAdapter
from tracker.ingestion.contracts import Identity


def movie_snapshot(regional):
    detail = {'id': 1, 'title': 'Fixture film', 'release_date': '2027-04-02', 'videos': {'results': []}}
    provider = {'results': {'JP': {'link': 'https://www.themoviedb.org/movie/1/watch', 'flatrate': [{'provider_id': 8, 'provider_name': 'Netflix'}]}}}
    with override_settings(TMDB_TOKEN='fixture-token'), patch.object(TMDBAdapter, 'request', side_effect=[detail, {'results': [{'iso_3166_1': 'JP', 'release_dates': regional}]}, provider]):
        return TMDBAdapter().fetch_snapshot(Identity(provider='tmdb', namespace='movie', external_id='1'))


def test_tmdb_release_midnight_is_a_date_but_availability_is_an_observation():
    result = movie_snapshot([{'release_date': '2027-04-02T00:00:00.000Z', 'type': 3}])
    regional = next(event for event in result.events if event.kind == 'release' and event.region == 'JP')
    availability = next(event for event in result.events if event.kind == 'availability')
    assert regional.release.precision == 'day' and regional.release.timestamp is None
    assert availability.release.precision == 'instant'
    assert 'not the original release date' in availability.summary
    assert result.metadata.extra['availability_attribution'] == 'JustWatch'


def test_tmdb_regional_release_identity_survives_reordering_and_delay():
    entries = [{'release_date': '2027-04-02T00:00:00Z', 'type': 3}, {'release_date': '2027-06-02T00:00:00Z', 'type': 4}]
    before = movie_snapshot(entries)
    changed = movie_snapshot([entries[1], {**entries[0], 'release_date': '2027-05-02T00:00:00Z'}])
    keys = lambda snapshot: {event.title: event.external_key for event in snapshot.events if event.kind == 'release'}
    assert keys(before) == keys(changed)


def test_tvmaze_preserves_specials_without_inventing_episode_zero():
    show = {'id': 1, 'name': 'Fixture series', 'url': 'https://www.tvmaze.com/shows/1', 'summary': '<p>Summary</p>', 'webChannel': {'name': 'Netflix', 'country': None}}
    episode = {'id': 10, 'season': 2, 'number': None, 'type': 'significant_special', 'name': 'Special episode', 'airdate': '2027-04-02', 'airstamp': None, 'url': 'https://www.tvmaze.com/episodes/10'}
    with patch('tracker.ingestion.catalogues.get_json', side_effect=[show, [episode]]):
        result = TVmazeAdapter().fetch_snapshot(Identity(provider='tvmaze', namespace='show', external_id='1'))
    assert result.units[0].label == 'S02 Special'
    assert result.units[0].release.precision == 'day'
    assert result.events[0].region == ''


def test_bangumi_missing_page_coverage_is_incomplete():
    subject = {'id': 1, 'name': 'Fixture anime', 'type': 2}
    with patch.object(BangumiAdapter, 'request', side_effect=[subject, {'data': [{'id': 2, 'name': 'First episode', 'sort': 1}]}, []]):
        result = BangumiAdapter().fetch_snapshot(Identity(provider='bangumi', namespace='subject', external_id='1'))
    assert not result.complete
    assert result.diagnostics


def test_bangumi_successor_relationship_keeps_direction():
    subject = {'id': 1, 'name': 'Fixture anime', 'type': 2}
    with patch.object(BangumiAdapter, 'request', side_effect=[subject, {'data': [], 'total': 0}, [{'id': 2, 'relation': '续集'}]]):
        result = BangumiAdapter().fetch_snapshot(Identity(provider='bangumi', namespace='subject', external_id='1'))
    assert result.complete
    assert result.relationships[0].kind == 'sequel_to'
    assert result.relationships[0].reverse
