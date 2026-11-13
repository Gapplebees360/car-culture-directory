import datetime
import json
from pathlib import Path
import tempfile
import unittest

from scripts.update_events import build, validate_events

TODAY = datetime.date(2026, 11, 12)


def event(**changes):
    record = dict(title='Organizer listing', state='WA', city='Kent', venue='Track',
                  category='Track / Drag', date='2026-11-15',
                  url='https://example.org/events/123', verified_at='2026-11-12')
    return record | changes


class EventTests(unittest.TestCase):
    def test_actual_dates_preserved_sorted_and_deduplicated(self):
        early = event(title='Earlier', date='2026-11-12')
        records = [event(), event(), event(date='2026-11-11'), early]
        self.assertEqual(validate_events(records, TODAY), [early, event()])

    def test_invalid_records_rejected(self):
        for changes in [dict(date='2026-02-30'), dict(state='XX'), dict(category='Unknown'),
                        dict(url='javascript:alert(1)'), dict(image='data:text/html,test'),
                        dict(verified_at='2026-11-13'), dict(verified_at=''), dict(title=''),
                        dict(time=123), dict(url='https://user:password@example.org')]:
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                validate_events([event(**changes)], TODAY)

    def test_failed_validation_keeps_last_published_page(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original = 'let eventsData = [{"title":"Previous"}];'
            (root / 'index.html').write_text(original, encoding='utf-8')
            (root / 'events.json').write_text(json.dumps([event(url='bad')]), encoding='utf-8')
            with self.assertRaises(ValueError):
                build(root, TODAY)
            self.assertEqual((root / 'index.html').read_text(), original)

    def test_marker_failure_keeps_page(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'index.html').write_text('No marker', encoding='utf-8')
            (root / 'events.json').write_text('[]', encoding='utf-8')
            with self.assertRaises(ValueError):
                build(root, TODAY)
            self.assertEqual((root / 'index.html').read_text(), 'No marker')

    def test_inline_script_cannot_be_terminated_by_event_text(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'index.html').write_text('<script>let eventsData = [];</script>', encoding='utf-8')
            (root / 'events.json').write_text(json.dumps([event(title='</script><script>alert(1)</script>')]), encoding='utf-8')
            build(root, TODAY)
            first = (root / 'index.html').read_text()
            self.assertEqual(first.count('</script>'), 1)
            build(root, TODAY)
            self.assertEqual((root / 'index.html').read_text(), first)

    def test_explicit_empty_dataset_clears_old_listings(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'index.html').write_text('let eventsData = [{"title":"Old"}];', encoding='utf-8')
            (root / 'events.json').write_text('[]', encoding='utf-8')
            build(root, TODAY)
            self.assertEqual((root / 'index.html').read_text(), 'let eventsData = [];')

    def test_description_brackets_do_not_truncate_the_embedded_array(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            previous = json.dumps([event(description='A bracket sequence ]; is ordinary text')])
            (root / 'index.html').write_text('let eventsData = ' + previous + ';\nKEEP THIS;', encoding='utf-8')
            (root / 'events.json').write_text('[]', encoding='utf-8')
            build(root, TODAY)
            self.assertEqual((root / 'index.html').read_text(), 'let eventsData = [];\nKEEP THIS;')


if __name__ == '__main__':
    unittest.main()
