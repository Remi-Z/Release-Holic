from pathlib import Path
from unittest.mock import patch

import pytest

from tracker.ingestion.books import PublisherAdapter, parse_product
from tracker.ingestion.contracts import AdapterError, diff_snapshots
from tracker.ingestion.kakuyomu import KakuyomuAdapter, parse_kakuyomu

FIXTURES = Path(__file__).parent / "fixtures"
WORK_ID = "16817330699999999999"


def fixture(name):
    return (FIXTURES / name).read_text()


def test_complete_index_scopes_links_and_preserves_precision():
    source = parse_kakuyomu(fixture("kakuyomu_complete.html"), WORK_ID)
    assert source.complete
    assert len(source.units) == 3
    assert source.metadata.creators == ["架空の作者"]
    assert source.metadata.extra['author_url'].endswith('/users/fixture-author')
    assert source.units[0].release.precision == 'instant'
    assert source.units[1].release.precision == 'day'
    assert source.units[2].release.start.isoformat() == '2026-09-05'
    assert not source.events  # An author expectation does not create a promised release.


def test_incomplete_index_cannot_remove_last_known_chapters():
    previous = parse_kakuyomu(fixture("kakuyomu_complete.html"), WORK_ID)
    partial = parse_kakuyomu(fixture("kakuyomu_partial.html"), WORK_ID)
    assert not partial.complete
    with pytest.raises(AdapterError, match="Incomplete"):
        diff_snapshots(previous, partial)


def test_recommendation_count_cannot_prove_work_index_coverage():
    html = '<h1 id="workTitle">星を待つ物語</h1><ol id="table-of-contents"><li><a href="/works/16817330699999999999/episodes/1">Chapter</a></li></ol><aside>おすすめ：全1話</aside>'
    assert not parse_kakuyomu(html, WORK_ID).complete


def test_disabled_load_more_does_not_block_complete_index():
    html = fixture('kakuyomu_complete.html').replace('</ol>', '<button data-load-more disabled>もっと見る</button></ol>')
    assert parse_kakuyomu(html, WORK_ID).complete


def test_plain_html_pagination_fetches_complete_index_without_browser():
    adapter = KakuyomuAdapter()
    with patch('tracker.ingestion.scrapy_runner.fetch_html', side_effect=[fixture('kakuyomu_partial.html'), fixture('kakuyomu_page2.html')]) as fetch:
        source = adapter.fetch_snapshot(adapter.resolve(f'kakuyomu:work:{WORK_ID}'))
    assert source.complete
    assert len(source.units) == 3
    assert fetch.call_count == 2
    assert [unit.ordinal for unit in source.units] == [0, 1, 2]


def test_missing_title_signals_selector_drift():
    with pytest.raises(AdapterError, match='title missing'):
        parse_kakuyomu(fixture('kakuyomu_drift.html'), WORK_ID)


def test_kakuyomu_episode_url_resolves_parent_identity():
    result = KakuyomuAdapter().resolve(f'https://kakuyomu.jp/works/{WORK_ID}/episodes/16817330699999999998')
    assert result.external_id == WORK_ID
    assert result.namespace == 'work'


def test_publisher_date_volume_wording_and_ebook_identity():
    html = '<main><h1>星を待つ物語 上</h1><script type="application/ld+json">{"@type":"Book","name":"星を待つ物語 上","isbn":"9784094533132","bookFormat":"https://schema.org/EBook","datePublished":"2027-04","author":{"name":"架空の作者"}}</script></main>'
    source = parse_product(html, 'https://www.shogakukan.co.jp/books/09453313', 'gagaga')
    assert source.editions[0].release.precision == 'month'
    assert source.editions[0].volume_label == '上'
    assert source.editions[0].format == 'ebook'
    assert source.metadata.creators == ['架空の作者']


def test_enrichment_outage_does_not_discard_publisher_metadata():
    html = '<main><h1>星を待つ物語</h1><p>ISBN 9784094533132 発売日：2027年4月2日</p></main>'
    with patch('tracker.ingestion.scrapy_runner.fetch_html', return_value=html), patch('tracker.ingestion.books.openbd_lookup', side_effect=AdapterError('HTTP 503')):
        source = PublisherAdapter('gagaga').fetch_snapshot(PublisherAdapter('gagaga').resolve('gagaga:product:09453313'))
    assert source.editions[0].isbn == '9784094533132'
    assert source.metadata.title == '星を待つ物語'
    assert source.diagnostics
