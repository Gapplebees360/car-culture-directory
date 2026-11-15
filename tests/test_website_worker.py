import datetime as dt
import json
from pathlib import Path
import tempfile
import unittest
from scripts.process_website_submissions import run

TODAY=dt.date(2026,11,14)
def event(source='Official'):
    return dict(title='Fixture Car Show',date='2026-12-05',city='Tacoma',state='WA',venue='Garage',category='Car Show',url='https://cars.example.org/show',source=source,source_id='show',verified_at='2026-11-14')

class WebsiteWorkerTests(unittest.TestCase):
    def test_utc_verification_date_can_follow_us_local_event_date(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            original=event()|{'verified_at':'2026-11-15'}
            (root/'events.json').write_text(json.dumps([original]))
            def call(route,payload=None):return []
            result=run(root,call,today=TODAY,verification_date=dt.date(2026,11,15))
            self.assertEqual(result['failed'],0)
            self.assertEqual(json.loads((root/'events.json').read_text()),[original])

    def test_inspection_uses_claim_and_exports_only_approved_website_data(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);original=event();website=event('Website: cars.example.org')|{'title':'Second Car Show'}
            (root/'events.json').write_text(json.dumps([original]))
            calls=[]
            def call(route,payload=None):
                calls.append((route,payload))
                if route=='claim':return [{'id':'fixture','lease_token':'lease','url':'https://cars.example.org/'}]
                if route=='finish':return {'accepted':1,'duplicates':0,'source_enrolled':True}
                return [website]
            def inspect(url,existing_events,today):
                self.assertEqual(existing_events,[original]);return {'automotive':True,'events':[website],'rejected':[],'duplicates':[]}
            result=run(root,call,inspect,TODAY)
            self.assertEqual(result['imported'],1)
            self.assertEqual([route for route,_ in calls],['claim','finish','export'])
            self.assertEqual(len(json.loads((root/'events.json').read_text())),2)

    def test_failed_inspection_preserves_prior_source_export_without_leaking_url(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);old=event('Website: cars.example.org');(root/'events.json').write_text(json.dumps([old]))
            def inspect(*args,**kwargs):raise ValueError('private query token in remote failure')
            def call(route,payload=None):
                if route=='claim':return [{'id':'fixture','lease_token':'lease','url':'https://cars.example.org/'}]
                if route=='finish':
                    self.assertNotIn('private query',json.dumps(payload));self.assertTrue(payload['report']['safety_failure']);return {'accepted':0,'duplicates':0,'source_enrolled':False}
                return [old]
            run(root,call,inspect,TODAY)
            self.assertEqual(json.loads((root/'events.json').read_text()),[old])

    def test_bad_export_does_not_modify_published_events(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);original=json.dumps([event()]);(root/'events.json').write_text(original)
            def call(route,payload=None):return [] if route=='claim' else [{'source':'Unexpected'}]
            with self.assertRaises(ValueError):run(root,call,today=TODAY)
            self.assertEqual((root/'events.json').read_text(),original)
