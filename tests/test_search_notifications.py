import json
from pathlib import Path
import tempfile
import unittest
from urllib.error import HTTPError

from scripts.notify_search_engines import notify


class SearchTests(unittest.TestCase):
    def test_public_proof_propagation_retries_then_submits_sitemap_urls(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            (root/'search-config.json').write_text(json.dumps({'indexnow_key':'a'*32,'indexnow_key_file':'proof.txt'}))
            (root/'sitemap.xml').write_text('<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><url><loc>https://usautomeets.com/</loc></url></urlset>')
            calls=[];delays=[]
            class Response:
                status=200
                def __enter__(self):return self
                def __exit__(self,*args):pass
            def opener(request,timeout):
                calls.append(json.loads(request.data))
                if len(calls)==1:raise HTTPError(request.full_url,403,'Pending verification',{},None)
                return Response()
            self.assertTrue(notify(root,opener,delays.append))
            self.assertEqual(delays,[10])
            self.assertEqual(calls[0],calls[1])
            self.assertEqual(calls[1]['urlList'],['https://usautomeets.com/'])

    def test_notification_failure_stays_bounded(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            (root/'search-config.json').write_text(json.dumps({'indexnow_key':'a'*32,'indexnow_key_file':'proof.txt'}))
            (root/'sitemap.xml').write_text('<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><url><loc>https://usautomeets.com/</loc></url></urlset>')
            calls=[]
            def fail(request,timeout):
                calls.append(1)
                raise HTTPError(request.full_url,403,'Forbidden',{},None)
            self.assertFalse(notify(root,fail,lambda seconds:None))
            self.assertEqual(len(calls),3)
