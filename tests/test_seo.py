import datetime as dt
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import tempfile
import unittest
import xml.etree.ElementTree as ET

from scripts.seo import build_pages, event_path, event_key, event_schema, homepage_content
from scripts.update_events import validate_events, build


def event(**changes):
    return dict(title='Cars & Coffee <Meet>',date='2026-12-05',state='WA',city='Tacoma',venue='Test Garage',
                category='Cars & Coffee',url='https://example.org/events/1',source='Organizer',source_id='1',
                verified_at='2026-11-13',description='Open meet <script>bad()</script>',**changes)


class SEOTests(unittest.TestCase):
    def test_event_identity_stays_stable_when_title_or_image_changes(self):
        original=event()
        self.assertEqual(event_path(original),event_path(original|{'title':'Corrected title','image':'https://example.org/new.jpg'}))
        self.assertNotEqual(event_path(original),event_path(original|{'date':'2026-12-06'}))

    def test_schema_keeps_unknown_details_unknown(self):
        schema=event_schema(event())
        self.assertEqual(schema['startDate'],'2026-12-05')
        self.assertNotIn('offers',schema)
        self.assertNotIn('image',schema)
        self.assertNotIn('organizer',schema)
        self.assertNotIn('streetAddress',schema['location']['address'])

    def test_generated_pages_crawl_without_javascript_and_match_sitemap(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            events=validate_events([event()],dt.date(2026,11,13))
            build_pages(root,events)
            target=root/event_path(events[0]).lstrip('/')/'index.html'
            page=target.read_text(encoding='utf8')
            self.assertIn('Cars &amp; Coffee &lt;Meet&gt;',page)
            self.assertNotIn('<script>bad()',page)
            schema=json.loads(re.search(r'application/ld\+json">(.*?)</script>',page).group(1))
            self.assertEqual(schema['name'],events[0]['title'])
            self.assertNotIn('noindex',page)
            urls=[n.text for n in ET.parse(root/'sitemap.xml').iter('{http://www.sitemaps.org/schemas/sitemap/0.9}loc')]
            for url in urls:
                self.assertTrue(url.startswith('https://usautomeets.com/'))
                if url!='https://usautomeets.com/':self.assertTrue((root/url.removeprefix('https://usautomeets.com/').lstrip('/')/'index.html').exists())
            self.assertNotIn('https://usautomeets.com/states/alaska/',urls)
            self.assertNotIn('https://usautomeets.com/community.html',urls)
            old=target
            build_pages(root,[])
            self.assertFalse(old.exists())

    def test_homepage_has_real_event_links_and_escaped_content(self):
        document='<!-- SEO_GRID_START --><!-- SEO_GRID_END --><!-- SEO_STATES_START --><!-- SEO_STATES_END -->'
        page=homepage_content(document,[event()])
        self.assertIn(event_path(event()),page)
        self.assertIn('/states/washington/',page)
        self.assertNotIn('<Meet>',page)
        self.assertEqual(homepage_content(page,[event()]),page)

    def test_moderated_events_are_not_embedded_or_linked_for_crawling(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            (root/'events.json').write_text(json.dumps([event()]))
            (root/'seo-moderation.json').write_text(json.dumps([event_key(event())]))
            (root/'index.html').write_text('<div><!-- SEO_GRID_START --><!-- SEO_GRID_END --></div><script>let eventsData = [];</script>')
            build(root,dt.date(2026,11,13))
            self.assertNotIn('Cars &amp; Coffee', (root/'index.html').read_text())
            self.assertNotIn(event_path(event()), (root/'sitemap.xml').read_text())
