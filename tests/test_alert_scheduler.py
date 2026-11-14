import io
import unittest
from urllib.error import HTTPError

from scripts.run_event_alerts import run,ENDPOINT


class SchedulerTests(unittest.TestCase):
    def test_missing_secret_does_not_send_any_request(self):
        def forbidden(*args,**kwargs):raise AssertionError('Unexpected request')
        self.assertEqual(run('',forbidden),{'inactive':True})

    def test_delivery_uses_fixed_endpoint_and_private_bearer_header(self):
        class Response(io.BytesIO):
            def __init__(self):super().__init__(b'{"sent":2,"failed":0}')
        def opener(request,timeout):
            self.assertEqual(request.full_url,ENDPOINT)
            self.assertEqual(request.get_header('Authorization'),'Bearer test-only-value')
            self.assertEqual(request.get_method(),'POST')
            return Response()
        self.assertEqual(run('test-only-value',opener),{'sent':2,'failed':0})

    def test_auth_failure_does_not_expose_response_body(self):
        def opener(request,timeout):raise HTTPError(ENDPOINT,401,'Unauthorized',{},io.BytesIO(b'private provider details'))
        with self.assertRaisesRegex(RuntimeError,'HTTP 401') as caught:run('test-only-value',opener)
        self.assertNotIn('private provider details',str(caught.exception))
