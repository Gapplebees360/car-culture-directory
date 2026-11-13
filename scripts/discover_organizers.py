"""Free organizer discovery. Leads are never published as dated events."""
import datetime as dt
from html.parser import HTMLParser
import json
import re

try:
    from .import_facebook import STATE_NAMES
    from .import_scca import fetch
    from .update_events import ROOT
except ImportError:
    from import_facebook import STATE_NAMES
    from import_scca import fetch
    from update_events import ROOT

DIRECTORY = 'https://www.carsandcoffeedirectory.com'


class Leads(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.current = None
        self.last_class = ''
        self.records = {}
        self.locations = {name: code for code, name in STATE_NAMES.items()}

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        self.last_class = attrs.get('class', '')
        if tag == 'a' and re.fullmatch(r'/events/[a-z0-9-]+', attrs.get('href', '')):
            self.current = {'discovery_url':DIRECTORY + attrs['href'], 'status':'needs_organizer_verification'}

    def handle_data(self, data):
        if self.current is None:
            return
        if 'font-archivo' in self.last_class and data.strip():
            self.current['name'] = data.strip()
        for name, code in self.locations.items():
            match = re.fullmatch(r'(.+),\s*' + re.escape(name), data.strip())
            if match:
                self.current.update(city=match[1], state=code)

    def handle_endtag(self, tag):
        if tag == 'a' and self.current is not None:
            if all(key in self.current for key in ['name','city','state']):
                self.records[self.current['discovery_url']] = self.current
            self.current = None
        self.last_class = ''


def discover(root=ROOT, fetcher=fetch):
    body, _ = fetcher(DIRECTORY + '/events')
    parser = Leads()
    parser.feed(body)
    if not parser.records:
        raise ValueError('Discovery page yielded no usable leads; prior registry retained')
    leads = sorted(parser.records.values(), key=lambda lead:(lead['state'],lead['city'],lead['name']))
    report = dict(checked_at=dt.datetime.now(dt.timezone.utc).date().isoformat(), source=DIRECTORY + '/events',
                  note='Discovery leads only. Verify official organizers, exact dates, seasonal exceptions, and permissions before enabling an importer. No recurring dates are generated from this directory.',
                  states={code:{'name':name, 'leads':sum(lead['state']==code for lead in leads),
                                'status':'needs_organizer_verification' if any(lead['state']==code for lead in leads) else 'needs_discovery'}
                          for code,name in STATE_NAMES.items()}, leads=leads)
    temporary = root / 'organizer-registry.json.tmp'
    temporary.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    temporary.replace(root / 'organizer-registry.json')
    print(f'Discovered {len(leads)} leads across {len({lead["state"] for lead in leads})} states; no dates published.')


if __name__ == '__main__':
    discover()
