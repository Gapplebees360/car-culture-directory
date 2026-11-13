"""Free, paginated public calendar imports. No API key or paid scraping service."""
import datetime as dt
import html
import json
import re
import sys
from urllib.parse import urlencode, urlsplit

try:
    from .import_scca import fetch
    from .import_facebook import STATE_NAMES
    from .update_events import ROOT, STATES, http_url, validate_events
except ImportError:
    from import_scca import fetch
    from import_facebook import STATE_NAMES
    from update_events import ROOT, STATES, http_url, validate_events

SOURCES = [{'name': 'Events With Cars', 'url': 'https://eventswithcars.com/wp-json/tribe/events/v1/events'}]


def event_category(record):
    text = html.unescape(record.get('title', '') + ' ' + ' '.join(item.get('name', '') for item in record.get('categories', []))).lower()
    for category, pattern in [
        ('Cars & Coffee', r'coffee|caffeine'), ('Autocross', r'autocross'),
        ('Track / Drag', r'drag rac|track day|test.?and.?tune'),
        ('Cruise Night', r'cruise'), ('Car Show', r'car show|auto show|truck show|concours'),
        ('Pop-Up Meet', r'car meet|cars?\s*(?:and|&)\s*chill')]:
        if re.search(pattern, text):
            return category
    raise ValueError('No supported automotive event category')


def convert(record, source, checked_date):
    if record.get('status') != 'publish' or record.get('is_virtual') or record.get('hide_from_listings'):
        raise ValueError('Not a public in-person listing')
    title = html.unescape(record.get('title', '')).strip()
    if not title or re.search(r'\bcancel[le]?[le]?d\b|\bpostponed\b', title, re.I):
        raise ValueError('Missing title, cancelled, or postponed')
    venue = record.get('venue')
    if not isinstance(venue, dict):
        raise ValueError('No structured venue')
    if venue.get('country') not in {'United States', 'United States of America', 'US', 'USA'}:
        raise ValueError('US location not explicit')
    state = venue.get('state') or venue.get('stateprovince')
    if state not in STATES:
        state = next((code for code, name in STATE_NAMES.items() if name.lower() == str(state).lower()), None)
    if not state or not venue.get('city') or not venue.get('venue'):
        raise ValueError('Incomplete US city, state, or venue')
    start = dt.datetime.fromisoformat(record['start_date'])
    end = dt.datetime.fromisoformat(record['end_date'])
    if end < start:
        raise ValueError('End precedes start')
    url = record.get('url', '')
    if not http_url(url) or urlsplit(url).hostname != urlsplit(source['url']).hostname:
        raise ValueError('Unexpected event listing URL')
    event = dict(title=title, date=start.date().isoformat(), end_date=end.date().isoformat(),
                 time=f'{start:%H:%M}–{end:%H:%M} (source local time)' if not record.get('all_day') else 'All day',
                 city=html.unescape(venue['city']).strip(), state=state, venue=html.unescape(venue['venue']).strip(),
                 category=event_category(record), url=url, source=source['name'],
                 source_id=f'{record["id"]}:{start.date().isoformat()}', verified_at=checked_date.isoformat(),
                 description=f'Listed by {source["name"]}. Check the original listing for current details, admission, and schedule changes.')
    artwork = record.get('image')
    if isinstance(artwork, dict) and http_url(artwork.get('url')):
        event.update(image=artwork['url'], image_kind='source_artwork', image_source=url)
    return event


def read_calendar(source, today, fetcher=fetch):
    url = source['url'] + '?' + urlencode({'per_page':100, 'start_date':today.isoformat(),
                                         'end_date':(today + dt.timedelta(days=180)).isoformat()})
    records, visited = [], set()
    while url:
        parsed = urlsplit(url)
        if parsed.scheme != 'https' or parsed.hostname != urlsplit(source['url']).hostname or not parsed.path.rstrip('/').endswith('/tribe/events/v1/events'):
            raise ValueError('Calendar pagination points outside its declared endpoint')
        if url in visited or len(visited) >= 30:
            raise ValueError('Pagination loop or unexpected page count')
        visited.add(url)
        body, _ = fetcher(url)
        data = json.loads(body)
        if not isinstance(data.get('events'), list):
            raise ValueError('Unexpected calendar response')
        records.extend(data['events'])
        url = data.get('next_rest_url') or ''
    return records


def import_events(root=ROOT, fetcher=fetch, today=None):
    now = dt.datetime.now(dt.timezone.utc)
    checked = now.date() if today is None else today
    today = today or (now - dt.timedelta(hours=10)).date()
    existing = json.loads((root / 'events.json').read_text(encoding='utf-8'))
    reports, successful = [], 0
    for source in SOURCES:
        try:
            records = read_calendar(source, today, fetcher)
            accepted, rejected = [], []
            for record in records:
                try:
                    event = convert(record, source, checked)
                    if event['end_date'] >= today.isoformat():
                        accepted.append(event)
                except (ValueError, KeyError, TypeError) as error:
                    rejected.append({'id':record.get('id'), 'reason':str(error)})
            if not accepted:
                raise ValueError('No usable events; retained prior source data')
            previous = [event for event in existing if event.get('source') == source['name'] and event.get('end_date',event['date']) >= today.isoformat()]
            if previous and len(accepted) < len(previous) / 2:
                raise ValueError('Coverage dropped by more than half; retained prior source data')
            existing = validate_events([event for event in existing if event.get('source') != source['name']] + accepted,
                                       today, verification_today=checked)
            reports.append(dict(source=source['name'], status='success', fetched=len(records), accepted=len(accepted),
                                cars_and_coffee=sum(event['category']=='Cars & Coffee' for event in accepted),
                                distinct_coffee_series=len({(event['title'],event['city'],event['state']) for event in accepted if event['category']=='Cars & Coffee'}),
                                with_artwork=sum(bool(event.get('image')) for event in accepted), skipped=rejected))
            successful += 1
        except (OSError, ValueError, KeyError, TypeError) as error:
            reports.append(dict(source=source['name'], status='failed', error=str(error), prior_data_retained=True))
    report = dict(checked_at=checked.isoformat(), service_cost_usd=0, sources=reports)
    (root / 'free-calendar-report.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    if not successful:
        raise ValueError('All free calendar sources failed; existing event dataset retained')
    temporary = root / 'events.json.tmp'
    temporary.write_text(json.dumps(existing, indent=2) + '\n', encoding='utf-8')
    temporary.replace(root / 'events.json')
    print(json.dumps({**report, 'sources':[{k:v for k,v in item.items() if k!='skipped'} for item in reports]}, indent=2))


if __name__ == '__main__':
    try:
        import_events()
    except (OSError, ValueError) as error:
        print(f'Free calendar import failed: {error}', file=sys.stderr)
        sys.exit(1)
