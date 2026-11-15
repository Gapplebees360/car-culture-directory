"""Free bounded website inspection worker, authenticated with a short-lived GitHub job identity."""
import datetime as dt
import json
import os
from pathlib import Path
import time
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen

try:
    from .website_inspector import inspect_website, InspectionError
    from .update_events import ROOT, validate_events
except ImportError:
    from website_inspector import inspect_website, InspectionError
    from update_events import ROOT, validate_events

BASE='https://lswnpxeiagureogrlopy.supabase.co/functions/v1/community/websites/worker/'
AUDIENCE='https://usautomeets.com/website-inspector'


def github_identity(opener=urlopen):
    endpoint=os.environ.get('ACTIONS_ID_TOKEN_REQUEST_URL','')
    credential=os.environ.get('ACTIONS_ID_TOKEN_REQUEST_TOKEN','')
    parsed=urlsplit(endpoint)
    if not endpoint or not credential:
        raise RuntimeError('Website inspection requires the authorized GitHub workflow identity')
    # Runtime issuer URL is supplied by GitHub, never by a submitted website.
    if parsed.scheme!='https' or not parsed.hostname or not parsed.hostname.endswith('.actions.githubusercontent.com') or parsed.username or parsed.password:
        raise ValueError('Unexpected GitHub identity endpoint')
    url=endpoint+('&' if '?' in endpoint else '?')+urlencode({'audience':AUDIENCE})
    request=Request(url,headers={'Authorization':'Bearer '+credential})
    with opener(request,timeout=20) as response:
        data=json.load(response)
    token=data.get('value')
    if not isinstance(token,str) or token.count('.')!=2:
        raise ValueError('GitHub did not return a signed job identity')
    return token


def rpc(route,payload=None,opener=urlopen,identity=github_identity):
    if route not in {'claim','finish','export'}:
        raise ValueError('Unsupported inspection operation')
    request=Request(BASE+route,data=json.dumps(payload or {}).encode(),method='POST',
                    headers={'Content-Type':'application/json','Authorization':'Bearer '+identity()})
    with opener(request,timeout=45) as response:
        raw=response.read(5*1024*1024+1)
    if len(raw)>5*1024*1024:
        raise ValueError('Inspection service response exceeds the limit')
    return json.loads(raw)


def run(root=ROOT,call=rpc,inspector=inspect_website,today=None,clock=time.monotonic):
    today=today or (dt.datetime.now(dt.timezone.utc)-dt.timedelta(hours=10)).date()
    existing=json.loads((root/'events.json').read_text(encoding='utf8'))
    started=clock()
    claims=call('claim')
    if not isinstance(claims,list) or len(claims)>3:
        raise ValueError('Unexpected inspection claim response')
    totals=dict(inspected=0,imported=0,duplicates=0,rejected=0,failed=0,enrolled=0)
    for item in claims:
        if clock()-started>180:
            break  # Unstarted leases expire safely; never increase a site's inspection budget.
        try:
            report=inspector(item['url'],existing_events=existing,today=today)
            if not isinstance(report,dict) or not isinstance(report.get('events'),list) or len(report['events'])>100:
                raise ValueError('Unexpected inspection report')
        except Exception as error:
            # Keep submitted URLs, remote response bodies and user identity out of public logs.
            reason=str(error)[:300] if isinstance(error,InspectionError) else 'Inspection unavailable or unsafe'
            report=dict(automotive=False,events=[],duplicates=[],rejected=[],notes=[reason],safety_failure=True,error=reason)
            totals['failed']+=1
        result=call('finish',{'id':item['id'],'lease_token':item['lease_token'],'report':report})
        totals['inspected']+=1
        totals['imported']+=int(result.get('accepted',0))
        totals['duplicates']+=int(result.get('duplicates',0))
        totals['rejected']+=len(report.get('rejected',[]))
        totals['enrolled']+=int(bool(result.get('source_enrolled')))
        existing.extend(report['events'])
    exported=call('export')
    if not isinstance(exported,list) or len(exported)>10000:
        raise ValueError('Unexpected website event export; prior published data retained')
    for event in exported:
        if not isinstance(event,dict) or not str(event.get('source','')).startswith('Website: '):
            raise ValueError('Unexpected website source identity; prior published data retained')
    combined=validate_events([event for event in json.loads((root/'events.json').read_text(encoding='utf8')) if not str(event.get('source','')).startswith('Website: ')]+exported,today)
    temporary=root/'events.json.tmp'
    temporary.write_text(json.dumps(combined,indent=2)+'\n',encoding='utf8')
    temporary.replace(root/'events.json')
    report=dict(checked_at=dt.datetime.now(dt.timezone.utc).isoformat(),service_cost_usd=0,**totals)
    (root/'website-import-report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf8')
    print(json.dumps(report))
    return report


if __name__=='__main__':
    run()
