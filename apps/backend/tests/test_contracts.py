"""These domain tests also run with just Python and Pydantic: unittest discover."""
import unittest
from datetime import date

from pydantic import ValidationError

from tracker.ingestion.contracts import AdapterError, Metadata, ReleaseTime, Snapshot, SourceEvent, SourceUnit, diff_snapshots, parse_release_time
from tracker.ingestion.identifiers import normalize_isbn, shogakukan_product_id


def snapshot(*units, complete=True, external_id="16817330699999999999"):
    return Snapshot(metadata=Metadata(provider="kakuyomu", namespace="work", external_id=external_id, title="星を待つ物語", kind="web_novel", url=f"https://kakuyomu.jp/works/{external_id}"), units=list(units), complete=complete)


def chapter(external_id="16817330699999999998", title="第一話", ordinal=0):
    return SourceUnit(external_id=external_id, title=title, kind="chapter", ordinal=ordinal)


class ReleasePrecisionTests(unittest.TestCase):
    def test_year_is_a_full_window(self):
        result = parse_release_time("2027")
        self.assertEqual((result.start, result.end, result.timestamp), (date(2027, 1, 1), date(2027, 12, 31), None))

    def test_month_respects_leap_year(self):
        self.assertEqual(parse_release_time("2028-02").end, date(2028, 2, 29))

    def test_day_has_no_invented_time(self):
        result = parse_release_time("2027-04-02")
        self.assertEqual(result.start, result.end)
        self.assertIsNone(result.timestamp)

    def test_instant_preserves_source_date_and_offset(self):
        result = parse_release_time("2027-04-02T00:30:00+09:00")
        self.assertEqual(result.start, date(2027, 4, 2))
        self.assertEqual(result.timestamp.utcoffset().total_seconds(), 32400)

    def test_undated_schedule_does_not_infer_year(self):
        result = parse_release_time("毎週月曜日 / 春予定")
        self.assertEqual(result.precision, "unknown")
        self.assertIsNone(result.start)

    def test_provider_zero_date_sentinels_are_unknown(self):
        for value in ['0000', '0000-00', '0000-00-00']:
            result = parse_release_time(value)
            self.assertEqual(result.precision, 'unknown')
            self.assertIsNone(result.start)

    def test_unknown_cannot_hide_a_date(self):
        with self.assertRaises(ValidationError):
            ReleaseTime(precision="unknown", start=date(2027, 1, 1))

    def test_naive_instant_is_invalid(self):
        with self.assertRaises(ValidationError):
            parse_release_time("2027-04-02T21:00:00")

    def test_invalid_model_year_window_is_rejected(self):
        with self.assertRaises(ValidationError):
            SourceEvent(external_key="model:1", kind="release", title="Release", url="https://www.apple.com/tv-pr/", release={"precision": "year", "start": "2027-01-01", "end": "2027-01-01"})

    def test_month_cannot_be_a_single_day(self):
        with self.assertRaises(ValidationError):
            ReleaseTime(precision="month", start=date(2027, 3, 1), end=date(2027, 3, 1))

    def test_day_cannot_span_two_days(self):
        with self.assertRaises(ValidationError):
            ReleaseTime(precision="day", start=date(2027, 3, 1), end=date(2027, 3, 2))

    def test_reversed_window_rejected(self):
        with self.assertRaises(ValidationError):
            ReleaseTime(precision="season", start=date(2027, 6, 1), end=date(2027, 3, 1))

    def test_publication_requires_timezone(self):
        with self.assertRaises(ValidationError):
            SourceEvent(external_key="news:1", kind="announcement", title="News", url="https://www.apple.com/", published_at="2026-10-06T12:00:00")


class ChapterReconciliationTests(unittest.TestCase):
    def test_ids_remain_strings_beyond_javascript_integer_limit(self):
        source = snapshot(chapter())
        restored = Snapshot.model_validate_json(source.model_dump_json())
        self.assertEqual(restored.units[0].external_id, "16817330699999999998")
        self.assertIsInstance(restored.units[0].external_id, str)

    def test_first_snapshot_emits_additions(self):
        self.assertEqual([change.kind for change in diff_snapshots(None, snapshot(chapter())).changes], ["added"])

    def test_duplicate_ingestion_emits_nothing(self):
        source = snapshot(chapter())
        self.assertFalse(diff_snapshots(source, source).changes)

    def test_new_chapter_does_not_repeat_existing_chapter(self):
        result = diff_snapshots(snapshot(chapter()), snapshot(chapter(), chapter("2", "第二話", 1)))
        self.assertEqual([(change.kind, change.unit.external_id) for change in result.changes], [("added", "2")])

    def test_edit_and_reordering_are_independent(self):
        result = diff_snapshots(snapshot(chapter()), snapshot(chapter(title="改訂・第一話", ordinal=4)))
        self.assertEqual([change.kind for change in result.changes], ["edited", "reordered"])

    def test_one_missing_observation_retains_chapter(self):
        result = diff_snapshots(snapshot(chapter()), snapshot())
        self.assertFalse(result.changes)
        self.assertEqual(len(result.baseline.units), 1)
        self.assertEqual(result.missing_counts, {"16817330699999999998": 1})

    def test_two_complete_observations_confirm_removal(self):
        first = diff_snapshots(snapshot(chapter()), snapshot())
        second = diff_snapshots(first.baseline, snapshot(), first.missing_counts)
        self.assertEqual([change.kind for change in second.changes], ["removed"])
        self.assertFalse(second.baseline.units)
        self.assertFalse(second.missing_counts)

    def test_reappearance_resets_removal_count(self):
        first = diff_snapshots(snapshot(chapter()), snapshot())
        second = diff_snapshots(first.baseline, snapshot(chapter()), first.missing_counts)
        self.assertFalse(second.changes)
        self.assertFalse(second.missing_counts)

    def test_incomplete_snapshot_does_not_count_toward_removal(self):
        baseline = snapshot(chapter())
        with self.assertRaises(AdapterError):
            diff_snapshots(baseline, snapshot(complete=False), {"16817330699999999998": 1})
        self.assertEqual(len(baseline.units), 1)

    def test_identity_change_rejected(self):
        with self.assertRaises(AdapterError):
            diff_snapshots(snapshot(chapter()), snapshot(chapter(), external_id="2"))

    def test_duplicate_chapter_identifiers_rejected(self):
        with self.assertRaises(AdapterError):
            diff_snapshots(None, snapshot(chapter(), chapter(title="Duplicate")))


class EditionIdentityTests(unittest.TestCase):
    def test_isbn_10_and_13_reconcile(self):
        self.assertEqual(normalize_isbn("4-09-453313-3"), "9784094533132")

    def test_shogakukan_product_key(self):
        self.assertEqual(shogakukan_product_id("9784094533132"), "09453313")

    def test_invalid_isbn_checksum_rejected(self):
        with self.assertRaises(AdapterError):
            normalize_isbn("9784094533131")

    def test_x_inside_isbn_rejected(self):
        with self.assertRaises(AdapterError):
            normalize_isbn("4X94533133")

    def test_non_book_ean_is_not_an_isbn(self):
        with self.assertRaises(AdapterError):
            normalize_isbn("4006381333931")


if __name__ == "__main__":
    unittest.main()
