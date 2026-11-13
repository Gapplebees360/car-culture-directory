"""Import dated US events from SCCA's public WordPress calendar, with attribution."""
from concurrent.futures import ThreadPoolExecutor
import datetime
import html
from html.parser import HTMLParser
import json
from pathlib import Path
import sys
import time
from urllib.parse import parse_qs, urlsplit, urlencode
from urllib.request import Request, urlopen

try:
    from .update_events import ROOT, STATES, validate_events
except ImportError:
    from update_events import ROOT, STATES, validate_events

ENDPOINT = 'https://www.scca.com/wp-json/wp/v2/event'
SOURCE = 'SCCA'


def fetch(url, opener=urlopen):
    for attempt in range(3):
        try:
            request = Request(url, headers={'User-Agent': 'USAAutoMeets/1.0 (+https://usautomeets.com/)'} )
            with opener(request, timeout=30) as response:
                return response.read().decode('utf-8'), response.headers
        except OSError:
            if attempt == 2:
                raise
            time.sleep(attempt + 1)


def calendar(fetcher=fetch):
    records = []
    page, pages = 1, 1
    while page <= pages:
        query = urlencode({'per_page': 100, 'page': page, '_fields': 'id,link,title,custom,class_list'})
        body, headers = fetcher(ENDPOINT + '?' + query)
        batch = json.loads(body)
        if not isinstance(batch, list):
            raise ValueError('SCCA calendar returned an unexpected response')
        pages = int(headers.get('X-WP-TotalPages', '1'))
        if pages > 100:
            raise ValueError('Calendar exceeds pagination safety limit; review before importing')
        records.extend(batch)
        page += 1
    return records


class LocationLinks(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.locations = []

    def handle_starttag(self, tag, attrs):
        if tag != 'a':
            return
        href = dict(attrs).get('href', '')
        url = urlsplit(href)
        if url.hostname == 'calendar.google.com' and url.path == '/calendar/render':
            value = parse_qs(url.query).get('location', [''])[0]
            if value:
                self.locations.append(html.unescape(value))


def category(record):
    types = ' '.join(record.get('class_list', []))
    if 'program_type-roadrally' in types or 'program_type-national-course' in types or 'program_type-divisional-course' in types or 'program_type-divisional-tour' in types:
        return 'Road Rally'
    if 'program_type-rallycross' in types:
        return 'Rallycross'
    if 'program_type-autocross' in types or 'program_type-solo' in types:
        return 'Autocross'
    if any(value in types for value in ('road-racing', 'trackday', 'track-night', 'time-trials', 'time-attack', 'super-tour', 'us-majors', 'race-experience', 'drivers-school')):
        return 'Track / Drag'
    return None


def convert(record, page, today):
    parser = LocationLinks()
    parser.feed(page)
    if not parser.locations:
        raise ValueError('No explicit venue location on source page')
    parts = [part.strip() for part in parser.locations[0].rsplit(',', 2)]
    if len(parts) != 3 or parts[-1] not in STATES or not parts[0] or not parts[1]:
        raise ValueError('Source location is not an unambiguous US city and state')
    start = datetime.date.fromisoformat(record['custom']['start_datetime'][:10])
    end = datetime.date.fromisoformat(record['custom'].get('end_datetime', record['custom']['start_datetime'])[:10])
    if end < start:
        raise ValueError('Source end date precedes start date')
    mapped = category(record)
    if not mapped:
        raise ValueError('Unmapped event category')
    return dict(title=html.unescape(record['title']['rendered']), date=start.isoformat(),
                end_date=end.isoformat(), state=parts[-1], city=parts[-2], venue=parts[0],
                category=mapped, url=record['link'], source=SOURCE, source_id=str(record['id']),
                verified_at=today.isoformat(), description='Listed on the official SCCA calendar. Check the original listing for registration, schedule, and eligibility.')


def import_events(root=ROOT, fetcher=fetch, today=None):
    now = datetime.datetime.now(datetime.timezone.utc)
    checked_date = today or now.date()
    today = today or (now - datetime.timedelta(hours=10)).date()
    existing = json.loads((root / 'events.json').read_text(encoding='utf-8'))
    records = calendar(fetcher)
    print(f'Read {len(records)} calendar records; checking upcoming event pages...', flush=True)
    candidates = []
    skipped = []
    for record in records:
        custom = record.get('custom', {})
        try:
            date = datetime.date.fromisoformat(custom.get('start_datetime', '')[:10])
            end = datetime.date.fromisoformat((custom.get('end_datetime') or custom.get('start_datetime', ''))[:10])
        except ValueError:
            skipped.append({'id': record.get('id'), 'reason': 'Missing or invalid event date'})
            continue
        if end >= today and date <= today + datetime.timedelta(days=365):
            candidates.append(record)

    def detail(record):
        link = urlsplit(record['link'])
        if link.scheme != 'https' or link.hostname != 'www.scca.com' or not link.path.startswith('/event/'):
            raise ValueError('Unexpected source detail URL')
        body, _ = fetcher(record['link'])
        try:
            return convert(record, body, checked_date), None
        except ValueError as error:
            return None, {'id': record['id'], 'url': record['link'], 'reason': str(error)}

    imported = []
    # A transport failure aborts the batch before any published files change.
    with ThreadPoolExecutor(max_workers=3) as pool:
        for event, issue in pool.map(detail, candidates):
            if event:
                imported.append(event)
            if issue:
                skipped.append(issue)
    if not imported:
        raise ValueError('Source produced no usable events; previous dataset retained')
    previous = [event for event in existing if event.get('source') == SOURCE and event.get('end_date', event['date']) >= today.isoformat()]
    if previous and len(imported) < len(previous) / 2:
        raise ValueError('Source coverage dropped by more than 50%; previous dataset retained')
    merged = validate_events([event for event in existing if event.get('source') != SOURCE] + imported, today, verification_today=checked_date)
    counts = {state: sum(event['state'] == state for event in merged) for state in sorted(STATES)}
    report = dict(checked_at=checked_date.isoformat(), source=SOURCE, calendar_records=len(records),
                  candidate_records=len(candidates), imported=len(imported), states_with_events=sum(bool(n) for n in counts.values()),
                  coverage=counts, skipped=skipped)
    dataset = root / 'events.json'
    temporary = dataset.with_suffix('.json.tmp')
    temporary.write_text(json.dumps(merged, indent=2) + '\n', encoding='utf-8')
    temporary.replace(dataset)
    (root / 'coverage.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({key: value for key, value in report.items() if key != 'skipped'}, indent=2))
    print(f'Skipped {len(skipped)} records; see coverage.json for reasons.')


if __name__ == '__main__':
    try:
        import_events()
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f'Import failed; previous dataset retained: {error}', file=sys.stderr)
        sys.exit(1)
