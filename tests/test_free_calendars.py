import datetime as dt
import json
from pathlib import Path
import tempfile
import unittest

from scripts.import_free_calendars import SOURCES, convert, import_events, read_calendar
from scripts.import_facebook import budget_cap
from scripts.discover_organizers import Leads

TODAY = dt.date(2026,11,13)


def record(**changes):
    return dict(id=123, title='Cars &amp; Coffee', status='publish',
                start_date='2026-11-14 08:00:00', end_date='2026-11-14 10:00:00',
                url='https://eventswithcars.com/event/test/', categories=[],
                venue={'venue':'Cars &amp; Cafe','city':'Austin','state':'TX','country':'United States'},
                image={'url':'https://eventswithcars.com/image.jpg'}) | changes


class FreeCalendarTests(unittest.TestCase):
    def test_actual_dates_and_source_artwork(self):
        event = convert(record(), SOURCES[0], TODAY)
        self.assertEqual(event['date'],'2026-11-14')
        self.assertEqual(event['venue'],'Cars & Cafe')
        self.assertEqual(event['category'],'Cars & Coffee')
        self.assertEqual(event['image_kind'],'source_artwork')
        self.assertEqual(event['state'],'TX')

    def test_missing_location_cancelled_and_virtual_rejected(self):
        for changes in [dict(venue=[]),dict(is_virtual=True),dict(title='Cancelled Cars & Coffee'),dict(title='Postponed car show'),dict(end_date='2026-11-13 07:00:00')]:
            with self.subTest(changes=changes),self.assertRaises(ValueError):
                convert(record(**changes),SOURCES[0],TODAY)

    def test_pagination_cannot_leave_source_host(self):
        def bad_fetch(url):
            return json.dumps({'events':[record()],'next_rest_url':'https://example.org/private'}),{}
        with self.assertRaises(ValueError):
            read_calendar(SOURCES[0],TODAY,bad_fetch)

    def test_failed_free_source_does_not_erase_other_sources(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original='[{"title":"Previous event"}]'
            (root/'events.json').write_text(original,encoding='utf-8')
            def fail(url):
                raise OSError('Outage')
            with self.assertRaises(ValueError):
                import_events(root,fail,TODAY)
            self.assertEqual((root/'events.json').read_text(),original)

    def test_daily_import_reuses_explicit_occurrences(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            (root/'events.json').write_text('[]',encoding='utf-8')
            def fetch(url):
                return json.dumps({'events':[record()],'next_rest_url':None}),{}
            import_events(root,fetch,TODAY)
            first=(root/'events.json').read_text()
            import_events(root,fetch,TODAY)
            self.assertEqual((root/'events.json').read_text(),first)
            self.assertEqual(len(json.loads(first)),1)

    def test_registry_leads_are_not_dated_events(self):
        parser=Leads()
        parser.feed('<a href="/events/test"><div class="font-archivo">Coffee Meet</div><div>Austin, Texas</div></a>')
        lead=list(parser.records.values())[0]
        self.assertEqual(lead['state'],'TX')
        self.assertEqual(lead['status'],'needs_organizer_verification')
        self.assertNotIn('date',lead)


class BudgetTests(unittest.TestCase):
    def test_remaining_monthly_credit_limits_next_run(self):
        self.assertEqual(budget_cap(5,{'totalUsageCreditsUsdAfterVolumeDiscount':4.5}),0.25)

    def test_per_run_maximum_is_one_dollar(self):
        self.assertEqual(budget_cap(5,{'totalUsageCreditsUsdAfterVolumeDiscount':0.91}),1.0)

    def test_budget_check_fails_closed(self):
        for usage in [{},{'totalUsageCreditsUsdAfterVolumeDiscount':4.9},{'totalUsageCreditsUsdAfterVolumeDiscount':-1}]:
            with self.subTest(usage=usage),self.assertRaises(ValueError):
                budget_cap(0.5,usage)


if __name__=='__main__':
    unittest.main()
