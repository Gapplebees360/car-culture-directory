import datetime as dt
import json
import socket
import unittest
from unittest.mock import patch, MagicMock

from scripts.website_inspector import (
    InspectionError, Robots, _PinnedHTTPS, canonical_url, convert_event,
    duplicate_reason, fetch_public, inspect_website, public_addresses, public_url,
)


TODAY = dt.date(2026, 11, 14)
BASE = 'https://cars.example.org'


def event(**changes):
    data = {'@type': 'Event', 'name': 'Downtown Cars & Coffee', 'startDate': '2026-12-05T08:00:00-08:00',
            'endDate': '2026-12-05T11:00:00-08:00', 'url': BASE + '/events/coffee/',
            'location': {'@type': 'Place', 'name': 'Example Garage', 'address': {'@type': 'PostalAddress',
                'addressCountry': 'US', 'addressRegion': 'WA', 'addressLocality': 'Tacoma'}},
            'description': 'Public car gathering with coffee and classic cars.', 'image': BASE + '/images/flyer.jpg'}
    data.update(changes)
    return data


def page(data, links=''):
    return '<html><title>Example automotive club</title><body><h1>Car club events</h1>' + links + '<script type="application/ld+json">' + json.dumps(data) + '</script></body></html>'


class Fetcher:
    def __init__(self, pages=None, robots='User-agent: *\nAllow: /'):
        self.pages = pages or {BASE + '/': page(event())}
        self.robots = robots
        self.calls = []

    def __call__(self, url):
        self.calls.append(url)
        if url == BASE + '/robots.txt':
            return {'status': 200, 'headers': {'Content-Type': 'text/plain'}, 'body': self.robots, 'url': url}
        data = self.pages.get(url)
        if isinstance(data, dict):
            return data
        return {'status': 200 if data is not None else 404, 'headers': {'Content-Type': 'text/html'}, 'body': data or '', 'url': url}


class URLSafetyTests(unittest.TestCase):
    def test_rejects_nonpublic_or_credentialled_targets(self):
        for value in ['http://cars.example.org/', 'https://127.0.0.1/', 'https://[::1]/',
                      'https://user:pass@cars.example.org/', 'https://localhost/', 'https://a.local/',
                      'https://metadata.internal/', 'https://a.test/', 'https://cars.example.org:8443/',
                      'https://cars.example.org\\@127.0.0.1/', 'https://cars.example.org/\nsecret']:
            with self.subTest(value=value), self.assertRaises(InspectionError):
                public_url(value)
        self.assertEqual(public_url('https://Cars.Example.org:443/events#fragment'), BASE + '/events')
        self.assertEqual(public_url(BASE + '/caf\u00e9'), BASE + '/caf%C3%A9')

    def test_all_dns_results_must_be_public(self):
        def resolver(*args, **kwargs):
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('93.184.216.34', 443)),
                    (socket.AF_INET, socket.SOCK_STREAM, 6, '', ('169.254.169.254', 443))]
        with self.assertRaisesRegex(InspectionError, 'non-public'):
            public_addresses('cars.example.org', resolver)
        self.assertEqual(public_addresses('cars.example.org', lambda *a, **k:[(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('93.184.216.34', 443))]), ['93.184.216.34'])

    def test_transport_pins_socket_and_preserves_tls_hostname(self):
        raw, tls = MagicMock(), MagicMock()
        with patch('scripts.website_inspector.socket.create_connection', return_value=raw) as connect:
            connection = _PinnedHTTPS('cars.example.org', '93.184.216.34')
            connection._context = tls
            connection.connect()
        connect.assert_called_once_with(('93.184.216.34', 443), timeout=10)
        tls.wrap_socket.assert_called_once_with(raw, server_hostname='cars.example.org')

    def test_transport_does_not_follow_private_or_cross_origin_redirect(self):
        response = MagicMock(status=302)
        response.getheaders.return_value = [('location', 'https://127.0.0.1/secret')]
        connection = MagicMock()
        connection.getresponse.return_value = response
        with patch('scripts.website_inspector.public_addresses', return_value=['93.184.216.34']), patch('scripts.website_inspector._PinnedHTTPS', return_value=connection):
            with self.assertRaises(InspectionError):
                fetch_public(BASE + '/')
        self.assertEqual(connection.request.call_count, 1)

    def test_transport_rechecks_dns_on_each_same_origin_redirect(self):
        first, last = MagicMock(status=302), MagicMock(status=200)
        first.getheaders.return_value = [('location', '/events')]
        last.getheaders.return_value = [('content-type', 'text/html')]
        last.read1.side_effect = [b'<html></html>', b'']
        connection = MagicMock()
        connection.getresponse.side_effect = [first, last]
        with patch('scripts.website_inspector.public_addresses', return_value=['93.184.216.34']) as resolve, patch('scripts.website_inspector._PinnedHTTPS', return_value=connection):
            result = fetch_public(BASE + '/')
        self.assertEqual(resolve.call_count, 2)
        self.assertEqual(result['url'], BASE + '/events')


class EventInspectionTests(unittest.TestCase):
    def test_nested_jsonld_imports_exact_occurrence_and_artwork(self):
        report = inspect_website(BASE + '/', today=TODAY, fetcher=Fetcher({BASE + '/': page({'@graph': [{'@type':'ItemList', 'itemListElement':[{'@type':'ListItem', 'item':event()}]}]})}))
        self.assertTrue(report['automotive'])
        self.assertEqual(len(report['events']), 1)
        result = report['events'][0]
        self.assertEqual((result['date'], result['city'], result['state']), ('2026-12-05', 'Tacoma', 'WA'))
        self.assertEqual(result['source'], 'Website: cars.example.org')
        self.assertRegex(result['source_id'], '^https://cars.example.org/events/coffee\\|[a-f0-9]{16}$')
        self.assertEqual(result['image_kind'], 'source_artwork')
        self.assertEqual(report['pages_checked'], 1)

    def test_unrelated_party_is_rejected_even_at_car_business(self):
        report = inspect_website(BASE + '/', today=TODAY, fetcher=Fetcher({BASE + '/':page([{'@type':'AutoPartsStore', 'name':'Parts Garage'}, event(name='Holiday Party at the Garage')])}))
        self.assertTrue(report['automotive'])
        self.assertEqual(report['events'], [])
        self.assertIn('title', report['rejected'][0]['reason'])

    def test_strict_dates_venue_country_status_and_physical_attendance(self):
        bad = [event(startDate='First Saturday every month'), event(startDate='2026-02-30'),
               event(startDate='2028-12-05'), event(startDate='2025-01-01', endDate='2025-01-01'),
               event(eventStatus='https://schema.org/EventCancelled'),
               event(eventAttendanceMode='https://schema.org/OnlineEventAttendanceMode'),
               event(location={'@type':'VirtualLocation', 'url':BASE + '/live'}),
               event(audience={'audienceType':'Members only'}), event(url='https://foreign.example.org/event')]
        missing = event()
        missing['location']['address'].pop('addressCountry')
        bad.append(missing)
        report = inspect_website(BASE + '/', today=TODAY, fetcher=Fetcher({BASE + '/':page(bad)}))
        self.assertEqual(report['events'], [])
        self.assertEqual(len(report['rejected']), len(bad))

    def test_duplicate_tracking_urls_and_normalized_titles_preserve_dates(self):
        original = convert_event(event(), BASE + '/', TODAY)
        new = event(url=BASE + '/events/coffee/?utm_source=mail&fbclid=test')
        later = event(startDate='2027-01-02', endDate='2027-01-02', url=BASE + '/events/coffee/')
        report = inspect_website(BASE + '/', existing_events=[original], today=TODAY, fetcher=Fetcher({BASE + '/':page([new, later])}))
        self.assertEqual(len(report['duplicates']), 1)
        self.assertEqual([e['date'] for e in report['events']], ['2027-01-02'])
        renamed = original | {'title':'DOWNTOWN Cars and Coffee!!', 'url':BASE + '/other'}
        self.assertTrue(duplicate_reason(renamed, [original]))
        distinct = original | {'title':'Entirely Different Car Show', 'url':BASE + '/another'}
        self.assertEqual(duplicate_reason(distinct, [original]), '')

    def test_robots_longest_rule_specific_agent_and_deny(self):
        robots = Robots('User-agent: *\nAllow: /\nDisallow: /private\nAllow: /private/public$')
        self.assertFalse(robots.allowed(BASE + '/private/event'))
        self.assertTrue(robots.allowed(BASE + '/private/public'))
        self.assertFalse(robots.allowed(BASE + '/%70rivate/event'))
        self.assertFalse(Robots('User-agent: *\nDisallow: /caf\u00e9').allowed(BASE + '/caf%C3%A9'))
        specific = Robots('User-agent: *\nDisallow: /\nUser-agent: USAAutoMeets\nAllow: /events')
        self.assertTrue(specific.allowed(BASE + '/events'))
        fetch = Fetcher(robots='User-agent: *\nDisallow: /')
        with self.assertRaisesRegex(InspectionError, 'robots policy'):
            inspect_website(BASE + '/', today=TODAY, fetcher=fetch)
        self.assertEqual(fetch.calls, [BASE + '/robots.txt'])

    def test_robots_many_stars_use_deterministic_matching(self):
        # The previous ^/a.*a.*...b regex has exponentially many failing paths.
        # Assert the old regex engine is never invoked for these policy rules.
        pattern = '/' + 'a*' * 300 + 'b'
        policy = Robots('User-agent: *\nDisallow: ' + pattern)
        with patch('scripts.website_inspector.re.search', side_effect=AssertionError('No regex matching for robots wildcards')):
            self.assertTrue(policy.allowed(BASE + '/' + 'a' * 10000 + 'c'))
            self.assertFalse(policy.allowed(BASE + '/' + 'a' * 10000 + 'b/extra'))
        terminal = Robots('User-agent: *\nDisallow: ' + pattern + '$')
        self.assertFalse(terminal.allowed(BASE + '/' + 'a' * 10000 + 'b'))
        self.assertTrue(terminal.allowed(BASE + '/' + 'a' * 10000 + 'b/extra'))
        # A trailing star can consume the complete remaining suffix, including empty.
        trailing = Robots('User-agent: *\nDisallow: /a*b*$')
        self.assertFalse(trailing.allowed(BASE + '/ab'))
        self.assertFalse(trailing.allowed(BASE + '/axbyz'))
        self.assertTrue(trailing.allowed(BASE + '/axc'))

    def test_excessive_robots_policy_fails_closed_instead_of_truncating(self):
        for body in [
            'User-agent: *\n' + 'Allow: /\n' * 1000 + 'Disallow: /',
            'User-agent: *\nDisallow: /' + 'a' * 2048,
        ]:
            with self.subTest(length=len(body)), self.assertRaisesRegex(InspectionError, 'Robots policy'):
                inspect_website(BASE + '/', today=TODAY, fetcher=Fetcher(robots=body))
        # Unicode normalization can expand a short raw rule past the same bound.
        unicode_policy = Robots('User-agent: *\nDisallow: /' + '\u00e9' * 400)
        with self.assertRaisesRegex(InspectionError, 'Normalized robots pattern'):
            unicode_policy.allowed(BASE + '/safe')

    def test_discovery_is_same_origin_bounded_and_never_executes_page_code(self):
        links = '<a href="/events/a">A</a><a href="/events/b">B</a><a href="/events/c">C</a><a href="https://foreign.example.org/events">External</a><script>throw new Error("not executed")</script>'
        fetch = Fetcher({BASE + '/':page({'@type':'AutoRepair'}, links), BASE + '/events/a':page(event()), BASE + '/events/b':page(event()), BASE + '/events/c':page(event())})
        with patch('scripts.website_inspector.time.sleep'):
            report = inspect_website(BASE + '/', today=TODAY, fetcher=fetch)
        self.assertEqual(report['pages_checked'], 3)
        self.assertEqual(len(fetch.calls), 4)
        self.assertFalse(any('foreign' in u for u in fetch.calls))
        self.assertEqual(len(report['events']), 1)
        self.assertEqual(len(report['duplicates']), 1)

    def test_automotive_site_without_dates_is_monitorable_not_an_event(self):
        report = inspect_website(BASE + '/', today=TODAY, fetcher=Fetcher({BASE + '/':page({'@type':'AutoRepair', 'name':'Example Tuning'})}))
        self.assertTrue(report['automotive'])
        self.assertEqual(report['events'], [])
        self.assertIn('no recurring dates', report['notes'][0])
        html_calendar = '<html><title>Event calendar</title><body>Cars &amp; Coffee next month. Classic Car Show schedule coming soon.</body></html>'
        report = inspect_website(BASE + '/', today=TODAY, fetcher=Fetcher({BASE + '/':html_calendar}))
        self.assertTrue(report['automotive'])
        self.assertEqual(report['events'], [])

    def test_blocked_initial_page_and_oversized_response_fail_closed(self):
        for data in [{'status':429, 'headers':{}, 'body':''}, {'status':200, 'headers':{'content-type':'text/html'}, 'body':'Just a moment'},
                     {'status':200, 'headers':{'content-type':'text/html'}, 'body':'x' * (1024*1024 + 1)}]:
            with self.subTest(status=data['status']), self.assertRaises(InspectionError):
                inspect_website(BASE + '/', today=TODAY, fetcher=Fetcher({BASE + '/':data}))

    def test_at_most_100_new_events_are_emitted(self):
        events = [event(name=f'Car Show Number {i}', url=BASE + f'/events/{i}') for i in range(101)]
        report = inspect_website(BASE + '/', today=TODAY, fetcher=Fetcher({BASE + '/':page(events)}))
        self.assertEqual(len(report['events']), 100)
        self.assertIn('100-event limit', report['rejected'][-1]['reason'])

    def test_shared_calendar_urls_keep_distinct_events_and_skip_aliases(self):
        first, second = event(), event(name='Classic Car Show')
        first.pop('url')
        second.pop('url')
        alias = first | {'name':'DOWNTOWN Cars and Coffee!!'}
        report = inspect_website(BASE + '/', today=TODAY, fetcher=Fetcher({BASE + '/':page([first, second, alias])}))
        self.assertEqual(len(report['events']), 2)
        self.assertEqual(len(report['duplicates']), 1)
        self.assertEqual(len({e['source_id'] for e in report['events']}), 2)
        self.assertTrue(all(e['url']==BASE+'/' for e in report['events']))
