"""Capped public Facebook event discovery through Apify's official actor.

Start once, poll with status, collect only a successful run. No Facebook login/cookies.
"""
import argparse
import datetime as dt
import json
import os
from pathlib import Path
import re
import sys
import time
from urllib.parse import parse_qs, urlencode, urlsplit
from urllib.request import Request, urlopen

try:
    from .update_events import ROOT, validate_events
except ImportError:
    from update_events import ROOT, validate_events

STATE_NAMES = dict(zip(
    'AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY'.split(),
    'Alabama|Alaska|Arizona|Arkansas|California|Colorado|Connecticut|Delaware|Florida|Georgia|Hawaii|Idaho|Illinois|Indiana|Iowa|Kansas|Kentucky|Louisiana|Maine|Maryland|Massachusetts|Michigan|Minnesota|Mississippi|Missouri|Montana|Nebraska|Nevada|New Hampshire|New Jersey|New Mexico|New York|North Carolina|North Dakota|Ohio|Oklahoma|Oregon|Pennsylvania|Rhode Island|South Carolina|South Dakota|Tennessee|Texas|Utah|Vermont|Virginia|Washington|West Virginia|Wisconsin|Wyoming'.split('|')))
SOURCE = 'Facebook'
ACTOR = 'apify~facebook-events-scraper'
CACHE = ROOT / '.cache' / 'facebook-run.json'
THEMES = ['car show', 'cars and coffee', 'car meet']


def api(path, payload=None):
    token = os.environ.get('APIFY_TOKEN')
    if not token:
        raise ValueError('APIFY_TOKEN is not configured; existing events retained')
    request = Request('https://api.apify.com/v2/' + path,
                      data=json.dumps(payload).encode() if payload is not None else None,
                      headers={'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'})
    with urlopen(request, timeout=45) as response:
        return json.load(response)


def queries():
    # Interleave states so a partial provider run is not dominated by one state.
    return [f'{theme} {name} United States' for theme in THEMES for name in STATE_NAMES.values()]


def start(max_charge=5):
    if not 0 < max_charge <= 5:
        raise ValueError('This importer limits each run to at most $5')
    if CACHE.exists():
        previous = json.loads(CACHE.read_text())
        status = api('actor-runs/' + previous['id'])['data']['status']
        if status in {'READY', 'RUNNING', 'TIMING-OUT', 'ABORTING'}:
            raise ValueError('A Facebook run is already active; use status instead of starting another')
    input_data = {'searchQueries': queries(), 'maxEvents': 2}
    options = urlencode({'timeout': 1200, 'memory': 4096, 'maxTotalChargeUsd': max_charge})
    run = api(f'acts/{ACTOR}/runs?{options}', input_data)['data']
    CACHE.parent.mkdir(exist_ok=True)
    CACHE.write_text(json.dumps({'id': run['id'], 'planned_states': list(STATE_NAMES),
                                 'planned_queries': queries(), 'max_charge_usd': max_charge}), encoding='utf-8')
    print(json.dumps({'run_id': run['id'], 'status': run['status'], 'states_requested': 50,
                      'query_count': len(queries()), 'max_events_per_query': 2, 'max_charge_usd': max_charge}))


def location(record):
    place = record.get('location') or {}
    if place.get('countryCode') and place['countryCode'] != 'US':
        raise ValueError('Non-US location')
    for raw in [place.get('city'), place.get('contextualName'), record.get('address'), place.get('streetAddress'), place.get('name')]:
        if not isinstance(raw, str):
            continue
        for code, name in STATE_NAMES.items():
            match = re.search(r',\s*(' + re.escape(code) + r'|' + re.escape(name) + r')(?:\s+\d{5}(?:-\d{4})?)?(?:,\s*(?:United States|USA|US))?\s*$', raw, re.I)
            if match:
                city = raw[:match.start()].rsplit(',', 1)[-1].strip()
                if city and not any(char.isdigit() for char in city):
                    return city, code, place.get('name') or raw
    raise ValueError('No unambiguous US city/state in event location; search state is never used as location')


def local_date(record):
    raw = record.get('utcStartDate')
    if not isinstance(raw, str):
        raise ValueError('No exact event timestamp')
    timestamp = dt.datetime.fromisoformat(raw.replace('Z', '+00:00'))
    if timestamp.tzinfo is None:
        raise ValueError('Event timestamp lacks timezone')
    sentence = record.get('dateTimeSentence') or record.get('startTime') or ''
    offsets = {'EST': -5, 'EDT': -4, 'CST': -6, 'CDT': -5, 'MST': -7, 'MDT': -6,
               'PST': -8, 'PDT': -7, 'AKST': -9, 'AKDT': -8, 'HST': -10}
    for name, offset in offsets.items():
        if re.search(r'\b' + name + r'\b', sentence):
            return timestamp.astimezone(dt.timezone(dt.timedelta(hours=offset))).date()
    months = {name.lower(): i for i, name in enumerate(['January','February','March','April','May','June','July','August','September','October','November','December'], 1)}
    match = re.search(r'\b(' + '|'.join(months) + r')\s+(\d{1,2})(?:,?\s+(20\d{2}))?', sentence, re.I)
    if match:
        year = int(match[3]) if match[3] else timestamp.year
        date = dt.date(year, months[match[1].lower()], int(match[2]))
        if abs((date - timestamp.date()).days) <= 1:
            return date
    raise ValueError('No trustworthy local event date')


def category(record):
    title = record.get('name', '').lower()
    description = record.get('description', '').lower()
    if re.search(r'\brockers\b|\bconcert\b|\blivestream\b', title) and not re.search(r'car show|car meet', title):
        raise ValueError('Performance or livestream, not an automotive gathering')
    if 'party' in title and not re.search(r'car show|car meet', title) and not re.search(r'bring your car|car display|car show|car meet', description):
        raise ValueError('Social party without a stated automotive gathering')
    # Ignore incidental mentions deep in artist biographies or unrelated listings.
    text = title + ' ' + description[:800]
    checks = [('Cars & Coffee', r'cars?\s*(?:and|&)\s*coffee|caffeine\s*(?:and|&)\s*gasoline'),
              ('Autocross', r'\bautocross\b'), ('Track / Drag', r'\bdrag rac|\btrack day|\btest\s*(?:and|&)\s*tune'),
              ('Cruise Night', r'\bcruise[ -]?(?:in|night)'), ('Car Show', r'\bcar show|\bauto show|\btruck show|\bclassic cars'),
              ('Pop-Up Meet', r'\bcar meet|\bauto meet|\bcars?\s*(?:and|&)\s*chill')]
    for result, pattern in checks:
        if re.search(pattern, text):
            return result
    raise ValueError('No clear automotive event relevance')


def convert(record, today=None):
    now = dt.datetime.now(dt.timezone.utc)
    today = today or (now - dt.timedelta(hours=10)).date()
    if record.get('isCanceled') or record.get('isOnline') or record.get('isPast'):
        raise ValueError('Cancelled, online, or past event')
    if record.get('eventType') != 'PUBLIC':
        raise ValueError('Event is not explicitly public')
    title = record.get('name')
    if not isinstance(title, str) or not title.strip():
        raise ValueError('Missing event title')
    url = urlsplit(record.get('url', ''))
    match = re.fullmatch(r'/events/(\d+)/?', url.path)
    if url.scheme != 'https' or url.hostname not in {'www.facebook.com', 'facebook.com'} or not match:
        raise ValueError('Not a canonical Facebook event URL')
    date = local_date(record)
    if date < today or date > today + dt.timedelta(days=365):
        raise ValueError('Event outside upcoming one-year window')
    city, state, venue = location(record)
    return dict(title=title.strip(), date=date.isoformat(), city=city, state=state, venue=venue,
                category=category(record), url=f'https://www.facebook.com/events/{match[1]}/',
                source=SOURCE, source_id=match[1], verified_at=now.date().isoformat(),
                description=(record.get('description') or 'See the original public Facebook event for details.')[:1200])


def collect(root=ROOT, run_id=None):
    metadata = json.loads(CACHE.read_text()) if CACHE.exists() else {}
    run_id = run_id or metadata.get('id')
    if not run_id:
        raise ValueError('Start a run first or specify --run-id')
    run = api('actor-runs/' + run_id)['data']
    if run['status'] != 'SUCCEEDED':
        raise ValueError(f'Run {run_id} is {run["status"]}; existing events retained')
    rows, offset = [], 0
    while True:
        batch = api(f'datasets/{run["defaultDatasetId"]}/items?clean=true&limit=1000&offset={offset}')
        if not isinstance(batch, list):
            raise ValueError('Unexpected provider dataset')
        rows.extend(batch)
        if len(batch) < 1000:
            break
        offset += len(batch)
    accepted, rejected, seen, withdrawn = [], [], set(), set()
    for row in rows:
        try:
            event = convert(row)
            if event['source_id'] not in seen:
                seen.add(event['source_id'])
                accepted.append(event)
        except (ValueError, TypeError, KeyError) as error:
            rejected.append({'url': row.get('url', ''), 'reason': str(error)})
            if any(reason in str(error) for reason in ['Cancelled, online, or past', 'Performance or livestream', 'Social party without', 'No clear automotive']):
                match = re.fullmatch(r'https://(?:www\.)?facebook\.com/events/(\d+)/?', row.get('url', ''))
                if match:
                    withdrawn.add(match[1])
    report = dict(source=SOURCE, run_id=run_id, run_status=run['status'],
                  queries_requested=len(metadata.get('planned_queries', [])), states_requested=metadata.get('planned_states', []),
                  returned=len(rows), accepted=len(accepted), rejected=rejected,
                  states_with_accepted_events=sorted({event['state'] for event in accepted}),
                  actual_charge_usd=run.get('usageTotalUsd'), provider_status_message=run.get('statusMessage'),
                  queries_with_returned_records=sorted({parse_qs(urlsplit(row.get('inputUrl', '')).query).get('q', [''])[0] for row in rows} - {''}))
    (root / 'facebook-report.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    if not accepted:
        raise ValueError('No usable upcoming US Facebook events; previous dataset retained; see facebook-report.json')
    existing = json.loads((root / 'events.json').read_text(encoding='utf-8'))
    # Merge discoveries by stable event ID; a capped search is not a complete replacement feed.
    indexed = {(event.get('source'), event.get('source_id', event['url'])): event for event in existing
               if not (event.get('source') == SOURCE and event.get('source_id') in withdrawn - seen)}
    indexed.update({(SOURCE, event['source_id']): event for event in accepted})
    merged = validate_events(list(indexed.values()))
    temporary = root / 'events.json.tmp'
    temporary.write_text(json.dumps(merged, indent=2) + '\n', encoding='utf-8')
    temporary.replace(root / 'events.json')
    print(json.dumps({key: value for key, value in report.items() if key != 'rejected'}, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['start', 'status', 'collect', 'run'])
    parser.add_argument('--max-charge', type=float, default=5)
    parser.add_argument('--run-id')
    args = parser.parse_args()
    if args.command == 'run':
        start(args.max_charge)
        run_id = json.loads(CACHE.read_text())['id']
        deadline = time.monotonic() + 1260
        while time.monotonic() < deadline:
            run = api('actor-runs/' + run_id)['data']
            print(run['status'], run.get('statusMessage', ''), flush=True)
            if run['status'] not in {'READY', 'RUNNING', 'TIMING-OUT', 'ABORTING'}:
                collect(run_id=run_id)
                return
            time.sleep(15)
        raise ValueError(f'Polling ended; resume with collect --run-id {run_id}; do not start a duplicate run')
    elif args.command == 'start':
        start(args.max_charge)
    elif args.command == 'collect':
        collect(run_id=args.run_id)
    else:
        run_id = args.run_id or json.loads(CACHE.read_text())['id']
        run = api('actor-runs/' + run_id)['data']
        print(json.dumps({key: run.get(key) for key in ['id', 'status', 'statusMessage', 'usageTotalUsd', 'defaultDatasetId']}, indent=2))


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f'Facebook import stopped: {error}', file=sys.stderr)
        sys.exit(1)
