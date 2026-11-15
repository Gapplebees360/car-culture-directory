import datetime as dt
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import quote

from scripts.sync_public_community_events import BASE, SNAPSHOT, NoRedirect, sync, validate_public_events

TODAY = dt.date(2026, 11, 13)


def community_event(number=1, **changes):
    key = f'community:00000000-0000-4000-8000-{number:012d}'
    event = dict(event_key=key, source='Community', title='Local Car Show',
                 date='2026-12-05', state='AK', city='Anchorage', venue='Test Garage',
                 category='Car Show', url='https://organizer.example/events', verified_at='2026-11-13',
                 image=BASE + '/public-flyer?event=' + quote(key, safe=''))
    return event | changes


class PublicExportTests(unittest.TestCase):
    def opener(self, pages, requests):
        iterator = iter(pages)
        def open_page(request, timeout):
            requests.append(request.full_url)
            page = next(iterator)
            if isinstance(page, Exception):
                raise page
            return io.BytesIO(json.dumps(page).encode())
        return open_page

    def run_sync(self, root, pages, requests=None):
        return sync(root, self.opener(pages, requests if requests is not None else []), TODAY, TODAY)

    def test_pagination_whitelist_and_fixed_endpoint(self):
        with tempfile.TemporaryDirectory() as directory, patch('scripts.sync_public_community_events.MAX_PAGE', 2):
            root = Path(directory)
            events = [community_event(n) for n in (1, 2)]
            events[0].update(user_id='private', flyer_path='private/file', profile={'email': 'secret'})
            requests = []
            result = self.run_sync(root, [dict(events=events, next_cursor=events[-1]['event_key']),
                                          dict(events=[], next_cursor=None)], requests)
            self.assertEqual(len(result), 2)
            self.assertNotIn('user_id', result[0])
            self.assertNotIn('flyer_path', result[0])
            self.assertNotIn('profile', result[0])
            self.assertEqual(requests, [BASE + '/public-events', BASE + '/public-events?cursor=' + quote(events[-1]['event_key'], safe='')])
            self.assertEqual(json.loads((root / SNAPSHOT).read_text()), result)

    def test_invalid_or_failed_export_keeps_previous_snapshot(self):
        bad_records = [community_event(event_key='imported:bad'), community_event(source='Organizer'),
                       community_event(image='https://storage.example/signed?token=secret'),
                       community_event(state='ZZ'), community_event(date='invalid'),
                       community_event(city=''), community_event(verified_at='2026-12-01')]
        scenarios = [[dict(events=[event], next_cursor=None)] for event in bad_records]
        scenarios += [[OSError('unavailable')], [dict(events=[])],
                      [dict(events=[], next_cursor='https://evil.example')],
                      [dict(events=[community_event(2), community_event(1)], next_cursor=None)],
                      [dict(events=[community_event(), community_event()], next_cursor=None)]]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / SNAPSHOT
            for pages in scenarios:
                with self.subTest(pages=pages):
                    target.write_text('["previous"]')
                    with self.assertRaises((ValueError, OSError)):
                        self.run_sync(root, pages)
                    self.assertEqual(target.read_text(), '["previous"]')
                    self.assertFalse(target.with_suffix('.json.tmp').exists())

    def test_partial_network_failure_and_repeated_cursor_keep_snapshot(self):
        with tempfile.TemporaryDirectory() as directory, patch('scripts.sync_public_community_events.MAX_PAGE', 1):
            root = Path(directory)
            event = community_event()
            first = dict(events=[event], next_cursor=event['event_key'])
            for second in (OSError('interrupted'), first):
                (root / SNAPSHOT).write_text('[]')
                with self.assertRaises((OSError, ValueError)):
                    self.run_sync(root, [first, second])
                self.assertEqual((root / SNAPSHOT).read_text(), '[]')

    def test_page_total_and_incomplete_pagination_limits(self):
        with tempfile.TemporaryDirectory() as directory, patch('scripts.sync_public_community_events.MAX_PAGE', 2), patch('scripts.sync_public_community_events.MAX_EVENTS', 2):
            root = Path(directory)
            events = [community_event(1), community_event(2)]
            scenarios = [[dict(events=events, next_cursor=None)],
                         [dict(events=events + [community_event(3)], next_cursor=None)],
                         [dict(events=events, next_cursor=events[-1]['event_key']), dict(events=[community_event(3)], next_cursor=None)]]
            for pages in scenarios:
                with self.assertRaises(ValueError):
                    self.run_sync(root, pages)
                self.assertFalse((root / SNAPSHOT).exists())

    def test_same_title_location_date_does_not_collapse_distinct_keys(self):
        self.assertEqual(len(validate_public_events([community_event(1), community_event(2)], TODAY, TODAY)), 2)

    def test_redirects_and_short_page_continuations_are_rejected(self):
        with self.assertRaises(ValueError):
            NoRedirect().redirect_request(None, None, 302, '', {}, 'https://untrusted.example')
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                self.run_sync(Path(directory), [dict(events=[community_event()], next_cursor=community_event()['event_key'])])

    def test_response_size_limit_preserves_snapshot(self):
        with tempfile.TemporaryDirectory() as directory, patch('scripts.sync_public_community_events.MAX_RESPONSE_BYTES', 10):
            root = Path(directory)
            (root / SNAPSHOT).write_text('[]')
            with self.assertRaises(ValueError):
                self.run_sync(root, [dict(events=[community_event()], next_cursor=None)])
            self.assertEqual((root / SNAPSHOT).read_text(), '[]')
