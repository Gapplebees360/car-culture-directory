"""Notify IndexNow participants after publication. Verification key is public."""
import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET

try:
    from .update_events import ROOT
except ImportError:
    from update_events import ROOT


def notify(root=ROOT,opener=urlopen):
    config=json.loads((root/'search-config.json').read_text(encoding='utf8'))
    urls=[node.text for node in ET.parse(root/'sitemap.xml').iter('{http://www.sitemaps.org/schemas/sitemap/0.9}loc')]
    if len(urls)>10000 or any(not url.startswith('https://usautomeets.com/') for url in urls):
        raise ValueError('Unexpected sitemap host or URL count')
    payload=dict(host='usautomeets.com',key=config['indexnow_key'],
                 keyLocation='https://usautomeets.com/'+config['indexnow_key_file'],urlList=urls)
    request=Request('https://api.indexnow.org/indexnow',data=json.dumps(payload).encode(),
                    headers={'Content-Type':'application/json','User-Agent':'USAAutoMeets/1.0'},method='POST')
    try:
        with opener(request,timeout=30) as response:
            if response.status not in (200,202):
                raise ValueError(f'Unexpected IndexNow status: {response.status}')
            print(f'IndexNow accepted {len(urls)} URLs (HTTP {response.status}). Acceptance is not proof of indexing.')
    except (HTTPError,URLError,TimeoutError) as error:
        print(f'::warning::IndexNow notification failed: {error}. Sitemap remains published; check domain/key accessibility and retry.')


if __name__=='__main__':
    notify()
