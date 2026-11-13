import datetime as dt
import unittest

from scripts.import_facebook import STATE_NAMES, category, convert, local_date, location, queries

TODAY = dt.date(2026, 11, 12)


def event(**changes):
    return dict(name='Cars and Coffee', url='https://www.facebook.com/events/123456/',
                eventType='PUBLIC', utcStartDate='2026-11-20T01:30:00Z',
                dateTimeSentence='Thursday, November 19, 2026 at 5:30 PM PST',
                location={'countryCode':'US', 'name':'Test Cafe', 'city':'Seattle, WA, United States'},
                description='Meet other car enthusiasts.') | changes


class FacebookTests(unittest.TestCase):
    def test_every_state_has_each_search_theme(self):
        self.assertEqual(len(STATE_NAMES), 50)
        self.assertEqual(len(queries()), 150)
        for name in STATE_NAMES.values():
            for theme in ['car show', 'cars and coffee', 'car meet']:
                self.assertIn(f'{theme} {name} United States', queries())

    def test_utc_midnight_is_not_used_as_local_date(self):
        self.assertEqual(local_date(event()), dt.date(2026, 11, 19))

    def test_valid_public_event(self):
        converted = convert(event(), TODAY)
        self.assertEqual(converted['state'], 'WA')
        self.assertEqual(converted['city'], 'Seattle')
        self.assertEqual(converted['source_id'], '123456')
        self.assertEqual(converted['category'], 'Cars & Coffee')

    def test_query_state_is_never_used_as_event_location(self):
        with self.assertRaises(ValueError):
            location(event(location=None, address=None, inputUrl='/events/search/?q=car+show+Washington'))

    def test_full_state_and_postal_address(self):
        self.assertEqual(location(event(location=None, address='123 Main St, Portland, Maine 04101, United States'))[:2], ('Portland', 'ME'))

    def test_invalid_events_rejected(self):
        for changes in [dict(isCanceled=True), dict(isOnline=True), dict(isPast=True),
                        dict(eventType='PRIVATE'), dict(utcStartDate=None),
                        dict(url='javascript:alert(1)'), dict(utcStartDate='2025-11-20T01:30:00Z'),
                        dict(location={'countryCode':'AU', 'city':'Seattle, WA'}),
                        dict(name='Concert', description='Live music'),
                        dict(dateTimeSentence='Tomorrow at noon')]:
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                convert(event(**changes), TODAY)

    def test_relevance_is_required(self):
        with self.assertRaises(ValueError):
            category({'name': 'Swimming state meet', 'description': 'Join us'})

    def test_band_biography_is_not_an_event(self):
        with self.assertRaises(ValueError):
            category({'name':'Richie and the High Street Rockers', 'description':'A band that performs at car shows.'})

    def test_host_name_does_not_make_a_party_a_car_meet(self):
        with self.assertRaises(ValueError):
            category({'name':'Bluff Cars and Coffee New Years Eve Party', 'description':'Join our family for dinner and catering.'})


if __name__ == '__main__':
    unittest.main()
