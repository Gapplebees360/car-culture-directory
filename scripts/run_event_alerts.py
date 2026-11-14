"""Server-side scheduled alert invocation; never exposes the scheduler secret."""
import json
import os
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ENDPOINT='https://lswnpxeiagureogrlopy.supabase.co/functions/v1/community/alerts/run'


def run(secret=None,opener=urlopen):
    secret=secret if secret is not None else os.environ.get('ALERT_CRON_SECRET','')
    if not secret:
        print('Alert scheduler is inactive: secure delivery setup is pending.')
        return {'inactive':True}
    request=Request(ENDPOINT,data=b'{}',headers={'Authorization':'Bearer '+secret,'Content-Type':'application/json'},method='POST')
    try:
        with opener(request,timeout=120) as response:
            data=json.load(response)
    except HTTPError as error:
        # Provider response bodies may contain private delivery details; do not log them.
        if error.code==503:
            print('Alert scheduler is inactive: email provider setup is pending.')
            return {'inactive':True}
        raise RuntimeError(f'Alert delivery request failed (HTTP {error.code}); check private server logs.') from None
    if not isinstance(data,dict) or not all(isinstance(data.get(k),int) and data[k]>=0 for k in ['sent','failed']):
        raise ValueError('Unexpected alert delivery response')
    print(f'Event alert batches sent: {data["sent"]}; failed: {data["failed"]}.')
    if data['failed']:
        raise RuntimeError('Some alert batches failed; server leases permit a later safe retry.')
    return {k:data[k] for k in ['sent','failed']}


if __name__=='__main__':
    run()
