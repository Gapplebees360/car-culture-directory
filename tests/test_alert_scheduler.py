import io
import unittest
from contextlib import redirect_stdout
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

    def test_unconfigured_provider_is_inactive_without_logging_private_details(self):
        def opener(request,timeout):
            raise HTTPError(ENDPOINT,503,'Unavailable',{},io.BytesIO(b'private provider details'))
        output=io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(run('test-only-value',opener),{'inactive':True})
        self.assertNotIn('private provider details',output.getvalue())
        self.assertNotIn('test-only-value',output.getvalue())

    def test_failed_batches_fail_job_instead_of_reporting_success(self):
        with self.assertRaisesRegex(RuntimeError,'Some alert batches failed'):
            run('test-only-value',lambda *args,**kwargs:io.BytesIO(b'{"sent":1,"failed":1}'))

    def test_provider_rejection_hides_response_details(self):
        def opener(request,timeout):
            raise HTTPError(ENDPOINT,502,'Bad Gateway',{},io.BytesIO(b'private recipient@example.test'))
        with self.assertRaisesRegex(RuntimeError,'HTTP 502') as caught:
            run('test-only-value',opener)
        self.assertNotIn('recipient@example.test',str(caught.exception))

    def test_invalid_delivery_counts_fail_closed(self):
        for body in (b'[]',b'{}',b'{"sent":-1,"failed":0}',b'{"sent":0,"failed":"0"}'):
            with self.subTest(body=body),self.assertRaises(ValueError):
                run('test-only-value',lambda *args,**kwargs:io.BytesIO(body))

    def test_retry_reuses_fixed_request_and_bounded_wait(self):
        requests=[]
        def opener(request,timeout):
            requests.append((request.full_url,request.data,request.get_header('Authorization'),timeout))
            if len(requests)==1:
                raise HTTPError(ENDPOINT,502,'Bad Gateway',{},io.BytesIO(b'private'))
            return io.BytesIO(b'{"sent":1,"failed":0}')
        with self.assertRaises(RuntimeError):run('test-only-value',opener)
        self.assertEqual(run('test-only-value',opener),{'sent':1,'failed':0})
        self.assertEqual(requests[0],requests[1])
        self.assertEqual(requests[1][3],120)
