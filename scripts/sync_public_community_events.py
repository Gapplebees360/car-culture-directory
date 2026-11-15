"""Export approved public community events to a separate, atomic SEO snapshot.

No database credentials or caller-selected endpoints are accepted. The Edge
endpoint is responsible for checking approval, moderation and flyer visibility.
"""
import datetime
import json
import re
import sys
from urllib.parse import quote
from urllib.request import HTTPRedirectHandler, Request, build_opener

try:
    from .update_events import ROOT, validate_events
    from .seo import event_key
except ImportError:
    from update_events import ROOT, validate_events
    from seo import event_key

BASE = 'https://lswnpxeiagureogrlopy.supabase.co/functions/v1/community'
SNAPSHOT = 'community-events.json'
MAX_PAGE = 250
MAX_EVENTS = 10000
MAX_RESPONSE_BYTES = 5 * 1024 * 1024
FIELDS = frozenset(('event_key', 'source', 'title', 'date', 'end_date', 'state',
                    'city', 'venue', 'category', 'url', 'verified_at', 'time',
                    'description', 'image'))


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError('Public event export must not redirect')


def validate_public_events(records, today=None, verification_today=None):
    if not isinstance(records, list) or len(records) > MAX_EVENTS:
        raise ValueError('Invalid public community event array')
    now = datetime.datetime.now(datetime.timezone.utc)
    today = today or (now - datetime.timedelta(hours=10)).date()
    verification_today = verification_today or now.date()
    result, seen = [], set()
    for record in records:
        if not isinstance(record, dict) or record.get('source') != 'Community':
            raise ValueError('Expected a public Community event')
        key = event_key(record)
        if key in seen:
            raise ValueError('Duplicate public community event identity')
        seen.add(key)
        event = {field: value for field, value in record.items() if field in FIELDS}
        for field, value in event.items():
            if not isinstance(value, str) or len(value) > (12000 if field == 'description' else 2048):
                raise ValueError('Invalid public event field')
        for field in ('date', 'end_date', 'verified_at'):
            if field in event and not re.fullmatch(r'\d{4}-\d{2}-\d{2}', event[field]):
                raise ValueError('Public event dates must be ISO calendar dates')
        expected_image = BASE + '/public-flyer?event=' + quote(key, safe='')
        if event.get('image') != expected_image:
            raise ValueError('Public event requires its stable public flyer URL')
        # Validate separately so distinct UUIDs never collapse by title/location.
        result.extend(validate_events([event], today, verification_today))
    return sorted(result, key=lambda event: (event['date'], event['title'], event['event_key']))


def sync(root=ROOT, opener=None, today=None, verification_today=None):
    opener = opener or build_opener(NoRedirect()).open
    records, seen_cursors = [], set()
    cursor = None
    while True:
        url = BASE + '/public-events'
        if cursor is not None:
            url += '?cursor=' + quote(cursor, safe='')
        with opener(Request(url, headers={'Accept': 'application/json'}), timeout=30) as response:
            raw = response.read(MAX_RESPONSE_BYTES + 1)
        if len(raw) > MAX_RESPONSE_BYTES:
            raise ValueError('Public event response exceeds size limit')
        page = json.loads(raw)
        if not isinstance(page, dict) or set(page) != {'events', 'next_cursor'}:
            raise ValueError('Incomplete public event response')
        events, next_cursor = page['events'], page['next_cursor']
        if not isinstance(events, list) or len(events) > MAX_PAGE:
            raise ValueError('Public event page exceeds record limit')
        records.extend(events)
        if len(records) > MAX_EVENTS:
            raise ValueError('Public event export exceeds total limit')
        keys = [event_key(event) if isinstance(event, dict) and event.get('source') == 'Community' else '' for event in events]
        if any(not key for key in keys) or keys != sorted(set(keys)) or (keys and cursor is not None and keys[0] <= cursor):
            raise ValueError('Public event page is not in deterministic identity order')
        if next_cursor is None:
            if len(events) == MAX_PAGE:
                raise ValueError('Full public event page lacks continuation cursor')
            break
        if (not isinstance(next_cursor, str) or not next_cursor or len(next_cursor) > 512
                or re.search(r'[\x00-\x20\x7f]', next_cursor) or next_cursor in seen_cursors
                or not events or len(events) != MAX_PAGE or next_cursor != keys[-1]):
            raise ValueError('Invalid or repeated public event cursor')
        seen_cursors.add(next_cursor)
        cursor = next_cursor
    events = validate_public_events(records, today, verification_today)
    target = root / SNAPSHOT
    temporary = target.with_suffix('.json.tmp')
    try:
        temporary.write_text(json.dumps(events, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)
    print(f'Public community snapshot refreshed: {len(events)} upcoming events.')
    return events


if __name__ == '__main__':
    try:
        sync()
    except (OSError, ValueError) as error:
        print(f'Public community export failed: {error}', file=sys.stderr)
        sys.exit(1)
