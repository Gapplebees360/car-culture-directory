"""Free official business calendars. Explicit dates only; no recurrence guesses."""
import datetime as dt
from html.parser import HTMLParser
import hashlib
import json
import re
import sys
from urllib.parse import urljoin

try:
    from .import_scca import fetch
    from .update_events import ROOT, validate_events
except ImportError:
    from import_scca import fetch
    from update_events import ROOT, validate_events


class Node:
    def __init__(self, tag='', attrs=(), parent=None):
        self.tag, self.attrs, self.parent, self.children = tag, dict(attrs), parent, []

    def has_class(self, name):
        return name in self.attrs.get('class', '').split()

    def text(self):
        return ''.join(c.text() if isinstance(c, Node) else c for c in self.children)

    def find(self, predicate):
        for child in self.children:
            if isinstance(child, Node):
                if predicate(child):
                    yield child
                yield from child.find(predicate)


class Document(HTMLParser):
    def __init__(self, body):
        super().__init__(convert_charrefs=True)
        self.root = self.current = Node()
        self.feed(body)

    def handle_starttag(self, tag, attrs):
        node = Node(tag, attrs, self.current)
        self.current.children.append(node)
        if tag == 'br':
            self.current.children.append('\n')
        if tag not in {'area','base','br','col','embed','hr','img','input','link','meta','param','source','track','wbr'}:
            self.current = node

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if self.current.tag == tag:
            self.current = self.current.parent

    def handle_endtag(self, tag):
        node = self.current
        while node.parent is not None:
            if node.tag == tag:
                self.current = node.parent
                return
            node = node.parent

    def handle_data(self, data):
        self.current.children.append(data)


def clean(text):
    return re.sub(r'\s+', ' ', text).strip().replace('\ufffd', '')


def dates(text):
    text = re.sub(r'(\d)(?:st|nd|rd|th)\b', r'\1', clean(text))
    match = re.fullmatch(r'([A-Za-z]+) (\d{1,2})(?:\s*[-–]\s*(\d{1,2}))?,? (20\d{2})', text)
    if not match:
        raise ValueError('No explicit complete date including year')
    month, day, end, year = match.groups()
    start = dt.datetime.strptime(f'{month} {day} {year}', '%B %d %Y').date()
    finish = start.replace(day=int(end)) if end else start
    if finish < start:
        raise ValueError('Reversed date range')
    return start, finish


def listing(source, title, start, end, city, state, venue, checked, time='', description='', image=''):
    category = 'Cars & Coffee' if re.search(r'coffee|caffeine|motoring meet', title, re.I) else (
        'Cruise Night' if re.search(r'cruise', title, re.I) else 'Car Show')
    key = '|'.join([title, start.isoformat(), city, state])
    event = dict(title=title, date=start.isoformat(), end_date=end.isoformat(), city=city, state=state,
                 venue=venue, category=category, time=time or 'See organizer for schedule',
                 source=source['name'], source_id=hashlib.sha256(key.encode()).hexdigest()[:24],
                 url=source['url'], verified_at=checked.isoformat(),
                 description=description or 'Listed on the official business calendar. Check organizer details, admission, and schedule changes before attending.')
    if image:
        event.update(image=image, image_kind='source_artwork', image_source=source['url'])
    return event


def griots(body, source, today):
    root = Document(body).root
    accepted, skipped = [], []
    for block in root.find(lambda n:n.has_class('eventMonth')):
        headings = list(block.find(lambda n:n.has_class('eventMonth-header')))
        if len(headings) != 1:
            raise ValueError('Calendar month heading missing or ambiguous')
        month = dt.datetime.strptime(clean(headings[0].text()).title(), '%B %Y')
        for node in block.find(lambda n:n.tag=='li' and n.has_class('event')):
            title = ''
            try:
                title = clean(next(node.find(lambda n:n.tag=='h3')).text())
                lines = [clean(s) for s in next(node.find(lambda n:n.tag=='p')).text().split('\n') if clean(s)]
                start, end = dates(lines[0])
                if (start.year,start.month) != (month.year,month.month):
                    raise ValueError('Event date conflicts with its calendar month; needs organizer clarification')
                if end < today:
                    continue
                if re.search(r'cancel|postpon|\bSEMA\b|bike show', title, re.I):
                    raise ValueError('Cancelled, trade-only, or motorcycle listing excluded')
                # Club business meetings are not advertised as public meets.
                if re.search(r'meeting|tech session', title, re.I):
                    raise ValueError('Club meeting/technical session; public attendance not established')
                location = next((i for i,line in enumerate(lines) if re.fullmatch(r'.+, [A-Z]{2}',line)), None)
                if location is None or location < 2:
                    raise ValueError('Missing explicit venue and city/state')
                city, state = lines[location].rsplit(', ',1)
                venue = lines[location-1]
                theme = next((s for s in lines if s.startswith('Theme:')), '')
                if theme:
                    title += ' — ' + theme.removeprefix('Theme:').strip()
                time = next((s for s in lines[location+1:] if re.search(r'\d.*[ap]\.m\.',s)), '')
                accepted.append(listing(source,title,start,end,city,state,venue,today,time))
            except (ValueError, StopIteration, IndexError) as error:
                skipped.append(dict(title=title,reason=str(error)))
    return accepted, skipped


def fcp(body, source, today):
    root = Document(body).root
    accepted, skipped = [], []
    for node in root.find(lambda n:n.tag=='a' and n.has_class('connected-group')):
        title = ''
        try:
            title = clean(next(node.find(lambda n:n.tag=='h3')).text())
            start,end = dates(next(node.find(lambda n:n.has_class('connected-group-link'))).text())
            if end < today:
                continue
            details = clean(next(node.find(lambda n:n.has_class('connected-group-details'))).text())
            match = re.match(r'(.+?), ([A-Z]{2}) -- (.+)',details)
            if not match:
                raise ValueError('Missing explicit city/state')
            city,state,description = match.groups()
            if 'Sunday Motoring Meet' not in title:
                raise ValueError('Needs event-specific venue and public access verification')
            if 'Robinson Helicopter' in description:
                venue = 'Robinson Helicopter'
            elif 'AZ HQ' in description and (city,state)==('Mesa','AZ'):
                venue = 'FCP Euro Arizona headquarters'
            else:
                raise ValueError('Venue not explicit in official listing')
            images = list(node.find(lambda n:n.has_class('connected-group-image')))
            image = images[0].attrs.get('data-retina','') if images else ''
            accepted.append(listing(source,title,start,end,city,state,venue,today,
                                    description=description+' Check the official registration link for times and access.',image=image))
        except (ValueError, StopIteration) as error:
            skipped.append(dict(title=title,reason=str(error)))
    return accepted, skipped


def speedway_coffee(body, source, today):
    root = Document(body).root
    paragraphs = [clean(n.text()).replace('\u200b','') for n in root.find(lambda n:n.has_class('paragraph'))]
    text = ' '.join(paragraphs)
    if not re.search(r'Address\s+340 Victory Lane\s+Lincoln,\s*NE\s+68528',text):
        raise ValueError('Speedway campus address changed or is not explicit')
    if not re.search(r'8 am until noon',text,re.I):
        raise ValueError('Published Cars & Coffee hours changed; review required')
    schedules = [p for p in paragraphs if re.match(r'20\d{2} Show Dates:',p)]
    if len(schedules)!=1:
        raise ValueError('Explicit year/date schedule missing or ambiguous')
    year, schedule = schedules[0].split(' Show Dates:',1)
    matches = list(re.finditer(r'([A-Za-z]+)\s+(\d{1,2})(?:st|nd|rd|th)?',schedule))
    if not matches or re.sub(r'([A-Za-z]+)\s+(\d{1,2})(?:st|nd|rd|th)?','',schedule).strip():
        raise ValueError('Unexpected schedule text; no recurrence dates inferred')
    events=[]
    for match in matches:
        start,end = dates(f'{match[1]} {match[2]}, {year}')
        if end>=today:
            events.append(listing(source,'Speedway Motors Cars & Coffee',start,end,'Lincoln','NE',
                'Speedway Motors campus, 340 Victory Lane',today,'8:00 a.m.–12:00 p.m. (organizer local time)',
                'Official Museum of American Speed schedule. Specialty-vehicle gathering at the Speedway Motors campus. Check the original page for current details and museum admission.'))
    return events,[]


PARSERS = {'griots':griots,'fcp':fcp,'speedway_coffee':speedway_coffee}


def import_events(root=ROOT, fetcher=fetch, today=None):
    checked = today or dt.datetime.now(dt.timezone.utc).date()
    today = today or (dt.datetime.now(dt.timezone.utc)-dt.timedelta(hours=10)).date()
    existing = json.loads((root/'events.json').read_text(encoding='utf8'))
    registry = json.loads((root/'business-sources.json').read_text(encoding='utf8'))
    reports, successes = [], 0
    for source in registry['businesses']:
        if source.get('parser') not in PARSERS:
            continue
        try:
            body,_ = fetcher(source['url'])
            accepted,skipped = PARSERS[source['parser']](body,source,today)
            previous = [e for e in existing if e.get('source')==source['name'] and e.get('end_date',e['date'])>=today.isoformat()]
            if not accepted or (previous and len(accepted)<len(previous)/2):
                raise ValueError('Empty or unexpectedly reduced calendar; prior data retained')
            # Validate each source before replacing it; malformed US state/image URLs fail closed.
            accepted = validate_events(accepted,today,verification_today=checked)
            for event in accepted:
                event['verified_at'] = checked.isoformat()
            existing = validate_events([e for e in existing if e.get('source')!=source['name']]+accepted,today,verification_today=checked)
            reports.append(dict(source=source['name'],status='success',accepted=len(accepted),skipped=skipped))
            successes += 1
        except (OSError,ValueError,KeyError,TypeError) as error:
            reports.append(dict(source=source['name'],status='failed',error=str(error),prior_data_retained=True))
    (root/'business-calendar-report.json').write_text(json.dumps(dict(checked_at=checked.isoformat(),service_cost_usd=0,sources=reports),indent=2)+'\n',encoding='utf8')
    if not successes:
        raise ValueError('All business calendar imports failed; event dataset retained')
    temporary = root/'events.json.tmp'
    temporary.write_text(json.dumps(existing,indent=2)+'\n',encoding='utf8')
    temporary.replace(root/'events.json')
    print(json.dumps(reports,indent=2))


if __name__=='__main__':
    try:
        import_events()
    except (OSError,ValueError) as error:
        print(str(error),file=sys.stderr)
        sys.exit(1)
