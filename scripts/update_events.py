"""Validate reviewed events and embed them in the static homepage. No network writes."""
import datetime
import json
from pathlib import Path
import re
import sys
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
STATES = set('AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY'.split())
CATEGORIES = {'Track / Drag', 'Cars & Coffee', 'Car Show', 'Cruise Night', 'Pop-Up Meet', 'Autocross', 'Road Rally', 'Rallycross'}
PATTERN = re.compile(r'let eventsData = (\[[\s\S]*?\]);')


def http_url(value):
    if not isinstance(value, str):
        return False
    parsed = urlsplit(value)
    return parsed.scheme in {'http', 'https'} and bool(parsed.hostname) and not parsed.username and not parsed.password


def validate_events(records, today=None, verification_today=None):
    now = datetime.datetime.now(datetime.timezone.utc)
    verification_today = verification_today or today or now.date()
    # Retain dates until the day ends in Hawaii; each browser filters locally.
    today = today or (now - datetime.timedelta(hours=10)).date()
    if not isinstance(records, list):
        raise ValueError('events.json must contain an array')
    result, seen = [], set()
    for number, event in enumerate(records, 1):
        if not isinstance(event, dict):
            raise ValueError(f'Event {number} must be an object')
        for field in ('title', 'state', 'city', 'venue', 'category', 'date', 'url', 'verified_at'):
            if not isinstance(event.get(field), str) or not event[field].strip():
                raise ValueError(f'Event {number}: missing {field}')
        date = datetime.date.fromisoformat(event['date'])
        end = datetime.date.fromisoformat(event.get('end_date', event['date']))
        if end < date:
            raise ValueError(f'Event {number}: end date precedes start date')
        verified = datetime.date.fromisoformat(event['verified_at'])
        if verified > verification_today:
            raise ValueError(f'Event {number}: verification date is in the future')
        if event['state'] not in STATES or event['category'] not in CATEGORIES:
            raise ValueError(f'Event {number}: invalid state or category')
        if not http_url(event['url']) or (event.get('image') and not http_url(event['image'])):
            raise ValueError(f'Event {number}: invalid source or image URL')
        for field in ('time', 'description', 'image'):
            if field in event and not isinstance(event[field], str):
                raise ValueError(f'Event {number}: {field} must be text')
        key = (event['title'].strip().casefold(), event['date'], event['city'].strip().casefold(), event['state'])
        if end >= today and key not in seen:
            result.append(event)
            seen.add(key)
    return sorted(result, key=lambda event: (event['date'], event['title']))


def build(root=ROOT, today=None):
    events = validate_events(json.loads((root / 'events.json').read_text(encoding='utf-8')), today)
    index = root / 'index.html'
    html = index.read_text(encoding='utf-8')
    matches = list(PATTERN.finditer(html))
    if len(matches) != 1:
        raise ValueError('Expected exactly one eventsData marker; homepage left unchanged')
    match = matches[0]
    payload = json.dumps(events, indent=6).replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')
    updated = html[:match.start(1)] + payload + html[match.end(1):]
    if updated != html:
        temporary = index.with_suffix('.html.tmp')
        temporary.write_text(updated, encoding='utf-8')
        temporary.replace(index)
    print(f'Validated {len(events)} upcoming events. No dates invented; no database changes.')


if __name__ == '__main__':
    try:
        build()
    except (OSError, ValueError) as error:
        print(f'Event refresh failed: {error}', file=sys.stderr)
        sys.exit(1)
