"""Refresh the public opaque suppression list before publishing static pages."""
import json
import re
from urllib.request import Request, urlopen

try:
    from .update_events import ROOT
except ImportError:
    from update_events import ROOT


def sync(root=ROOT,opener=urlopen):
    config=(root/'assets/community-config.js').read_text(encoding='utf8')
    url=re.search(r"supabaseUrl:\s*'([^']+)'",config).group(1)
    key=re.search(r"publishableKey:\s*'([^']+)'",config).group(1)
    request=Request(url+'/rest/v1/rpc/uam_hidden_event_keys',data=b'{}',
                    headers={'apikey':key,'Content-Type':'application/json'},method='POST')
    with opener(request,timeout=30) as response:
        hidden=json.load(response)
    if not isinstance(hidden,list) or any(not isinstance(k,str) or not re.fullmatch(r'imported:[a-f0-9]{64}',k) for k in hidden):
        raise ValueError('Unexpected public moderation response; publication stopped')
    (root/'seo-moderation.json').write_text(json.dumps(sorted(set(hidden)),indent=2)+'\n',encoding='utf8')
    print(f'Static SEO suppression list refreshed: {len(hidden)} withdrawn imported events.')


if __name__=='__main__':
    sync()
