import datetime
import json
from pathlib import Path
import tempfile
import unittest

from scripts.import_scca import calendar, category, convert, import_events
from scripts.update_events import validate_events

TODAY = datetime.date(2026, 11, 12)
RECORD = dict(id=123, date='2020-01-01', link='https://www.scca.com/event/test/',
              title={'rendered': 'Test &amp; Tune'}, custom={'start_datetime': '2026-11-14', 'end_datetime': '2026-11-15'},
              class_list=['program_type-autocross-local-events'])
PAGE = '<a href="https://calendar.google.com/calendar/render?action=TEMPLATE&amp;location=Test%20Track%2C%20123%20Main%20St%2C%20Kent%2C%20WA">Calendar</a>'


class SccaTests(unittest.TestCase):
    def test_track_night_and_time_attack_categories_are_included(self):
        for slug in ['program_type-track-night-in-america', 'program_type-time-attack-challenge']:
            self.assertEqual(category({'class_list': [slug]}), 'Track / Drag')

    def test_uses_event_date_not_wordpress_publication_date(self):
        event = convert(RECORD, PAGE, TODAY)
        self.assertEqual(event['date'], '2026-11-14')
        self.assertEqual(event['end_date'], '2026-11-15')
        self.assertEqual(event['state'], 'WA')
        self.assertEqual(event['city'], 'Kent')
        self.assertEqual(event['title'], 'Test & Tune')
        self.assertEqual(event['category'], 'Autocross')
        self.assertEqual(event['source_id'], '123')

    def test_does_not_guess_missing_or_foreign_locations(self):
        for body in ['', PAGE.replace('WA', 'BC'), PAGE.replace('%2C%20WA', '')]:
            with self.subTest(body=body), self.assertRaises(ValueError):
                convert(RECORD, body, TODAY)

    def test_pagination_reads_all_pages(self):
        requests = []
        def fetcher(url):
            requests.append(url)
            return json.dumps([RECORD]), {'X-WP-TotalPages': '2'}
        self.assertEqual(len(calendar(fetcher)), 2)
        self.assertIn('page=2', requests[-1])

    def test_failed_source_preserves_previous_data(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original = '[{"title":"Previous"}]'
            (root / 'events.json').write_text(original, encoding='utf-8')
            def failing(url):
                raise OSError('Source unavailable')
            with self.assertRaises(OSError):
                import_events(root, failing, TODAY)
            self.assertEqual((root / 'events.json').read_text(), original)

    def test_successful_import_and_state_coverage(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'events.json').write_text('[]', encoding='utf-8')
            def fetcher(url):
                if '/wp-json/' in url:
                    return json.dumps([RECORD]), {'X-WP-TotalPages': '1'}
                return PAGE, {}
            import_events(root, fetcher, TODAY)
            report = json.loads((root / 'coverage.json').read_text())
            self.assertEqual(report['coverage']['WA'], 1)
            self.assertEqual(report['coverage']['CA'], 0)
            self.assertEqual(report['states_with_events'], 1)

    def test_ongoing_multiday_event_is_kept(self):
        event = convert(RECORD, PAGE, TODAY)
        self.assertEqual(len(validate_events([event], datetime.date(2026, 11, 15))), 1)
        self.assertEqual(validate_events([event], datetime.date(2026, 11, 16)), [])

    def test_utc_verification_can_follow_local_event_date(self):
        event = convert(RECORD, PAGE, datetime.date(2026, 11, 16))
        self.assertEqual(len(validate_events([event], datetime.date(2026, 11, 15),
                                            verification_today=datetime.date(2026, 11, 16))), 1)

    def test_empty_import_keeps_previous_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original = json.dumps([convert(RECORD, PAGE, TODAY)])
            (root / 'events.json').write_text(original, encoding='utf-8')
            with self.assertRaises(ValueError):
                import_events(root, lambda url: ('[]', {'X-WP-TotalPages': '1'}), TODAY)
            self.assertEqual((root / 'events.json').read_text(), original)


if __name__ == '__main__':
    unittest.main()
