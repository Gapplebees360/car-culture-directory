import os
import re
import json
import sys
import datetime
import urllib.request
import urllib.parse
import hashlib

# Reference Dates (UTC)
today = datetime.datetime.now(datetime.timezone.utc).date()
today_str = today.strftime('%Y-%m-%d')
max_future_date = today + datetime.timedelta(days=365)
max_future_str = max_future_date.strftime('%Y-%m-%d')
current_year = today.year

INDEX_PATH = 'index.html'

SUPABASE_URL = "https://lswnpxeiagureogrlopy.supabase.co"
SUPABASE_ANON_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imxzd25weGVpYWd1cmVvZ3Jsb3B5Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3OTE3NjkwNDcsImV4cCI6MjEwNzM0NTA0N30.yg0B_yyMAgdM692J9s-HevvfaykqZoVV0a0AiS6mZ_s"

HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) USAAutoMeets/1.0'}

CATEGORY_IMAGE_POOLS = {
    "Track / Drag": [
        "https://images.unsplash.com/photo-1568605117036-5fe5e7bab0b7?w=800&auto=format&fit=crop",
        "https://images.unsplash.com/photo-1541348263662-e082662d82da?w=800&auto=format&fit=crop"
    ],
    "Cars & Coffee": [
        "https://images.unsplash.com/photo-1503376780353-7e6692767b70?w=800&auto=format&fit=crop"
    ],
    "Car Show": [
        "https://images.unsplash.com/photo-1511919884226-fd3cad34687c?w=800&auto=format&fit=crop"
    ]
}

DEFAULT_FALLBACK = "https://images.unsplash.com/photo-1511919884226-fd3cad34687c?w=800&auto=format&fit=crop"
NON_EVENT_KEYWORDS = ["announced", "announcement", "dates announced", "season pass", "annual banquet"]

def normalize_date(date_input):
    if not date_input:
        return None
    clean_str = str(date_input).strip()[:10]
    for fmt in ('%Y-%m-%d', '%m/%d/%Y', '%Y/%m/%d', '%d-%m-%Y'):
        try:
            dt = datetime.datetime.strptime(clean_str, fmt).date()
            return dt.strftime('%Y-%m-%d')
        except ValueError:
            continue
    return None

def is_valid_future_event(event_dict):
    if not isinstance(event_dict, dict):
        return False
    date_str = normalize_date(event_dict.get('date'))
    if not date_str or date_str < today_str or date_str > max_future_str:
        return False
    return True

def fetch_multi_hub_msr_events():
    events = []
    # Simplified stable endpoint query for MotorsportReg API
    url = "https://api.motorsportreg.com/rest/events.json?country=USA"
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            for item in data.get('recordset', {}).get('events', []):
                title = str(item.get('name') or 'Motorsports Event')[:80]
                raw_start = str(item.get('start') or '')[:10]
                start_date = normalize_date(raw_start)

                candidate = {"title": title, "date": start_date}
                if not is_valid_future_event(candidate):
                    continue

                venue = item.get('venue') or {}
                state = str(venue.get('state') or 'WA')[:2].upper()
                city = str(venue.get('city') or 'Regional')
                venue_name = str(venue.get('name') or 'Motorsports Park')[:80]
                raw_url = str(item.get('detailurl') or item.get('uri') or 'https://www.motorsportreg.com/calendar/')

                events.append({
                    "title": title,
                    "state": state,
                    "city": city,
                    "venue": venue_name,
                    "category": "Track / Drag",
                    "date": start_date,
                    "time": "08:00 AM - 05:00 PM",
                    "description": 'Official Motorsports & Track gathering via MotorsportReg.',
                    "url": raw_url,
                    "image": DEFAULT_FALLBACK
                })
    except Exception as e:
        print(f"Notice: API fetch note: {e}")

    print(f"Success: Extracted {len(events)} real published events.")
    return events

def update_index():
    if not os.path.exists(INDEX_PATH):
        sys.exit(0)

    with open(INDEX_PATH, 'r', encoding='utf-8') as f:
        html = f.read()

    match = re.search(r'let eventsData = (\[[\s\S]*?\]);', html)
    if not match:
        sys.exit(0)

    msr_events = fetch_multi_hub_msr_events()
    updated_json = json.dumps(msr_events, indent=6)
    new_html = html[:match.start(1)] + updated_json + html[match.end(1):]

    with open(INDEX_PATH, 'w', encoding='utf-8') as f:
        f.write(new_html)

    print(f"Success: Directory rebuilt with {len(msr_events)} events.")

if __name__ == '__main__':
    update_index()
    sys.exit(0)
