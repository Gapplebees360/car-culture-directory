import datetime as dt
import json
from pathlib import Path
import tempfile
import unittest

from scripts.import_business_events import dates, griots, fcp, import_events
from scripts.check_business_sources import Links, check, run


TODAY=dt.date(2026,11,13)
SOURCE={'name':"Griot's Garage",'url':'https://www.griotsgarage.com/events/','parser':'griots'}


def calendar(date='December 5, 2026',month='DECEMBER 2026',title='CAFFEINE &amp; GASOLINE',extra=''):
    return f'''<div class="eventMonth"><h2 class="eventMonth-header">{month}</h2><ul>
    <li class="event"><h3>{title}</h3><p>{date}<br/><strong>Theme: Lowriders</strong><br/>
    Griot's Garage<br/>Tacoma, WA<br/>8:00 a.m.</p></li></ul></div>{extra}'''


class BusinessTests(unittest.TestCase):
    def test_exact_date_location_theme_and_time(self):
        events,skipped=griots(calendar(),SOURCE,TODAY)
        self.assertFalse(skipped)
        event=events[0]
        self.assertEqual((event['date'],event['city'],event['state']),('2026-12-05','Tacoma','WA'))
        self.assertEqual(event['title'],'CAFFEINE & GASOLINE — Lowriders')
        self.assertEqual(event['category'],'Cars & Coffee')
        self.assertEqual(event['time'],'8:00 a.m.')

    def test_source_month_conflict_is_flagged_not_corrected(self):
        events,skipped=griots(calendar('March 6, 2027','APRIL 2027'),SOURCE,TODAY)
        self.assertFalse(events)
        self.assertIn('conflicts',skipped[0]['reason'])

    def test_comments_and_private_meetings_do_not_publish(self):
        body='<!--'+calendar()+'-->'+calendar(title='Club Meeting & Tech Session')
        events,skipped=griots(body,SOURCE,TODAY)
        self.assertFalse(events)
        self.assertEqual(len(skipped),1)

    def test_explicit_range_required_no_recurrence_inference(self):
        self.assertEqual(dates('November 13 - 14, 2026'),(TODAY,TODAY+dt.timedelta(days=1)))
        for value in ['First Saturday every month','December 5','November 14 - 13, 2026']:
            with self.assertRaises(ValueError):dates(value)

    def test_fcp_explicit_venue_and_source_artwork(self):
        body='''<a class="cell connected-group"><div class="connected-group-image" data-retina="https://info.fcpeuro.com/flyer.jpg"></div>
        <h3>FCP Euro Sunday Motoring Meet CA</h3><p class="connected-group-details">Torrance, CA -- Join us at Robinson Helicopter.</p>
        <p class="connected-group-link">November 15th 2026</p></a>'''
        events,skipped=fcp(body,{'name':'FCP Euro','url':'https://info.fcpeuro.com/event-schedule'},TODAY)
        self.assertFalse(skipped)
        self.assertEqual(events[0]['venue'],'Robinson Helicopter')
        self.assertEqual(events[0]['image_kind'],'source_artwork')
        self.assertFalse(fcp(body.replace('Robinson Helicopter','our favorite venue'),SOURCE,TODAY)[0])

    def test_fetch_failure_preserves_existing_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            existing=griots(calendar(),SOURCE,TODAY)[0]
            (root/'events.json').write_text(json.dumps(existing))
            (root/'business-sources.json').write_text(json.dumps({'businesses':[SOURCE]}))
            def failed(url):raise OSError('blocked')
            with self.assertRaises(ValueError):import_events(root,failed,TODAY)
            self.assertEqual(json.loads((root/'events.json').read_text()),existing)

    def test_watchlist_links_stay_on_official_site(self):
        parser=Links('https://www.example.com/')
        parser.feed('<a href="/events">Events</a><a href="https://attacker.test/events">Events</a><a href="javascript:alert(1)">Events</a><a href="/toyota-land-cruiser-exhaust">Land Cruiser</a>')
        self.assertEqual(parser.links,{'https://www.example.com/events'})
        result=check({'name':'Example','url':'https://www.example.com/'},TODAY,lambda u:('Pardon Our Interruption',u))
        self.assertEqual(result['status'],'unavailable_needs_review')
        self.assertFalse(result['event_dates_verified'])

    def test_weekly_watch_cache_does_not_recheck_every_daily_run(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            (root/'business-sources.json').write_text(json.dumps({'businesses':[SOURCE]}))
            calls=[]
            def fetcher(url):
                calls.append(url)
                return '<a href="/events/">Events</a>',url
            run(root,TODAY,fetcher)
            run(root,TODAY+dt.timedelta(days=6),fetcher)
            self.assertEqual(len(calls),1)
            run(root,TODAY+dt.timedelta(days=7),fetcher)
            self.assertEqual(len(calls),2)
