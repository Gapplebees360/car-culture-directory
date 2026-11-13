"""Weekly free discovery checks for business event pages; never publishes events."""
from concurrent.futures import ThreadPoolExecutor
import datetime as dt
from html.parser import HTMLParser
import json
import re
from urllib.parse import urljoin, urlsplit
from urllib.request import Request, urlopen

try:
    from .update_events import ROOT
except ImportError:
    from update_events import ROOT


class Links(HTMLParser):
    def __init__(self, url):
        super().__init__(convert_charrefs=True)
        self.url, self.links, self.anchor = url, set(), None

    def handle_starttag(self, tag, attrs):
        if tag == 'a':
            self.anchor = [dict(attrs).get('href',''), '']

    def handle_data(self, text):
        if self.anchor:
            self.anchor[1] += text

    def handle_endtag(self, tag):
        if tag != 'a' or self.anchor is None:
            return
        href, text = self.anchor
        self.anchor = None
        url = urljoin(self.url,href)
        parsed, base = urlsplit(url), urlsplit(self.url)
        # Only suggest same-site pages; social accounts need a separate review.
        if parsed.scheme=='https' and parsed.hostname==base.hostname and not parsed.username and not parsed.password:
            if re.search(r'(?<![a-z])(?:events?|car[-_ ]?shows?|cars?[-_ ](?:and|&)[-_ ]coffee|cruise[-_ ]?ins?|open[-_ ]?house|dyno[-_ ]?day)(?![a-z])',href+' '+text,re.I):
                self.links.add(url.split('#')[0])


def fetch_page(url):
    request = Request(url,headers={'User-Agent':'USAAutoMeets/1.0 (+https://usautomeets.com/)'})
    with urlopen(request,timeout=12) as response:
        if 'text/html' not in response.headers.get('Content-Type',''):
            raise ValueError('Not an HTML calendar/discovery page')
        # Use the actual response URL for relative links, not a guessed location.
        return response.read(1500000).decode('utf8',errors='replace'),response.url


def check(source, today, fetcher=fetch_page):
    report = dict(name=source['name'],url=source['url'],checked_at=today.isoformat(),event_dates_verified=False)
    try:
        body,url = fetcher(source['url'])
        if re.search(r'Pardon Our Interruption|Just a moment|verify you are human',body,re.I):
            raise ValueError('Automated access blocked; manual review or organizer feed needed')
        parser = Links(url)
        parser.feed(body)
        report.update(status='page_readable_needs_calendar_review',calendar_candidates=sorted(parser.links)[:20])
        if source.get('parser'):
            report['status']='calendar_adapter_available_see_import_report'
        if not report['calendar_candidates'] and not source.get('parser'):
            report['status']='no_calendar_link_found_needs_review'
    except (OSError,ValueError) as error:
        report.update(status='unavailable_needs_review',error=str(error))
    return report


def run(root=ROOT, today=None, fetcher=fetch_page):
    today = today or dt.datetime.now(dt.timezone.utc).date()
    sources = json.loads((root/'business-sources.json').read_text(encoding='utf8'))['businesses']
    path = root/'business-watch-report.json'
    old = json.loads(path.read_text(encoding='utf8')) if path.exists() else {'businesses':[]}
    cached = {item['name']:item for item in old['businesses']}
    due = [s for s in sources if s['name'] not in cached or cached[s['name']]['url']!=s['url'] or
           (today-dt.date.fromisoformat(cached[s['name']]['checked_at'])).days>=7]
    with ThreadPoolExecutor(max_workers=3) as pool:
        for result in pool.map(lambda s:check(s,today,fetcher),due):
            cached[result['name']]=result
    records = [cached[s['name']] for s in sources]
    report = dict(checked_at=today.isoformat(),service_cost_usd=0,checked_this_run=len(due),
                  note='Discovery only. A readable business page or candidate calendar is not a verified event. Imports are separately validated in business-calendar-report.json.',businesses=records)
    temporary = path.with_suffix('.json.tmp')
    temporary.write_text(json.dumps(report,indent=2)+'\n',encoding='utf8')
    temporary.replace(path)
    print(f'Business watchlist: {len(sources)} businesses; {len(due)} checked this run; no events inferred.')


if __name__=='__main__':
    run()
