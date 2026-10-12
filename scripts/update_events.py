import os
import re
import json
import datetime
import urllib.request
import json5
from icalendar import Calendar

today = datetime.datetime.now(datetime.timezone.utc).date()
today_str = today.strftime('%Y-%m-%d')
INDEX_PATH = 'index.html'

SUPABASE_URL = "https://lswnpxeiagureogrlopy.supabase.co"
SUPABASE_ANON_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imxzd25weGVpYWd1cmVvZ3Jsb3B5Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3OTE3NjkwNDcsImV4cCI6MjEwNzM0NTA0N30.yg0B_yyMAgdM692J9s-HevvfaykqZoVV0a0AiS6mZ_s"

HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) USAAutoMeets/1.0'}

# Common iCal paths used by WordPress, Google Calendar, and Squarespace
ICAL_PATHS = [
    "/events/?ical=1",
    "/events.ics",
    "/calendar/?ical=1",
    "/feed/ical/"
]

def discover_tracks_from_msr():
    """Dynamically queries MotorsportReg Venue Directory for US tracks and websites"""
    discovered_feeds = []
    url = "https://api.motorsportreg.com/rest/venues.json?country=USA"
    
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=12) as resp:
            data = json.loads(resp.read().decode())
            venues = data.get('recordset', {}).get('venues', [])
            
            for v in venues:
                website = v.get('url', '')
                state = (v.get('state', '') or 'WA')[:2].upper()
                city = v.get('city', 'Regional')
                name = v.get('name', '')
                
                if website and website.startswith('http'):
                    # Clean base domain
                    base_url = website.rstrip('/')
                    for path in ICAL_PATHS:
                        discovered_feeds.append({
                            "name": name,
                            "state": state,
                            "city": city,
                            "venue": f"{name}, {city} {state}",
                            "category": "Track / Drag",
                            "feed_url": f"{base_url}{path}"
                        })
    except Exception as e:
        print(f"MSR Venue Discovery notice: {e}")
        
    return discovered_feeds

def probe_and_parse_ical_feeds(feed_list):
    """Probes discovered track calendar URLs and parses active VEVENT dates"""
    events = []
    successful_hosts = set()

    for track in feed_list:
        host = track['feed_url'].split('/')[2]
        if host in successful_hosts:
            continue # Skip alternative paths if host already succeeded

        try:
            req = urllib.request.Request(track['feed_url'], headers=HEADERS)
            with urllib.request.urlopen(req, timeout=6) as resp:
                content = resp.read()
                if b"BEGIN:VCALENDAR" in content:
                    gcal = Calendar.from_ical(content)
                    successful_hosts.add(host)
                    
                    for component in gcal.walk():
                        if component.name == "VEVENT":
                            summary = str(component.get('summary', ''))
                            dtstart = component.get('dtstart')
                            
                            if dtstart:
                                ev_date = dtstart.dt
                                if isinstance(ev_date, datetime.datetime):
                                    ev_date = ev_date.date()
                                
                                ev_date_str = ev_date.strftime('%Y-%m-%d')
                                
                                if ev_date_str >= today_str:
                                    events.append({
                                        "title": f"{track['name']} - {summary}"[:80],
                                        "state": track['state'],
                                        "city": track['city'],
                                        "venue": track['venue'][:80],
                                        "category": track['category'],
                                        "date": ev_date_str,
                                        "time": "08:00 AM - 05:00 PM",
                                        "description": str(component.get('description', ''))[:200] or f"Event at {track['name']}."
                                    })
        except Exception:
            continue # Silently skip invalid or 404 feed endpoints

    print(f"Discovered and parsed {len(events)} events from active track calendar feeds.")
    return events

def fetch_msr_events_direct():
    """Direct API ingestion for all nationwide events"""
    events = []
    url = "https://api.motorsportreg.com/rest/events.json?country=USA&radius=3000"
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=12) as resp:
            data = json.loads(resp.read().decode())
            for item in data.get('recordset', {}).get('events', []):
                start_date = item.get('start', '')[:10]
                if start_date >= today_str:
                    venue = item.get('venue', {})
                    events.append({
                        "title": item.get('name', 'Motorsports Event')[:80],
                        "state": (venue.get('state', 'WA') or 'WA')[:2].upper(),
                        "city": venue.get('city', 'Regional') or 'Regional',
                        "venue": (venue.get('name', 'Motorsports Park') or 'Motorsports Park')[:80],
                        "category": "Track / Drag" if any(w in item.get('name','').lower() for w in ["drag", "track", "autocross"]) else "Car Show",
                        "date": start_date,
                        "time": "08:00 AM - 05:00 PM",
                        "description": item.get('type', 'Motorsports gathering.')
                    })
    except Exception as e:
        print(f"Direct MSR API notice: {e}")
    return events

def purge_old_supabase_events():
    try:
        url = f"{SUPABASE_URL}/rest/v1/events?date=lt.{today_str}"
        req = urllib.request.Request(url, method='DELETE')
        req.add_header('apikey', SUPABASE_ANON_KEY)
        req.add_header('Authorization', f'Bearer {SUPABASE_ANON_KEY}')
        with urllib.request.urlopen(req, timeout=10) as resp:
            print(f"Supabase database purge completed.")
    except Exception as e:
        print(f"Purge notice: {e}")

def push_to_supabase(event_list):
    if not event_list:
        return
    url = f"{SUPABASE_URL}/rest/v1/events"
    headers = {
        'apikey': SUPABASE_ANON_KEY,
        'Authorization': f'Bearer {SUPABASE_ANON_KEY}',
        'Content-Type': 'application/json',
        'Prefer': 'ignore-duplicates'
    }
    batch_size = 50
    for i in range(0, len(event_list), batch_size):
        batch = event_list[i:i + batch_size]
        try:
            data_json = json.dumps(batch).encode('utf-8')
            req = urllib.request.Request(url, data=data_json, headers=headers, method='POST')
            with urllib.request.urlopen(req, timeout=10) as resp:
                pass
        except Exception:
            pass
    print(f"Pushed {len(event_list)} records directly into Supabase DB.")

def update_index():
    if not os.path.exists(INDEX_PATH):
        return

    with open(INDEX_PATH, 'r', encoding='utf-8') as f:
        html = f.read()

    match = re.search(r'let eventsData = (\[[\s\S]*?\]);', html)
    if not match:
        return

    # 1. Automated venue discovery & probing
    discovered_tracks = discover_tracks_from_msr()
    discovered_events = probe_and_parse_ical_feeds(discovered_tracks)
    
    # 2. Direct event feed API
    direct_events = fetch_msr_events_direct()

    all_scraped = discovered_events + direct_events

    # Sync database
    push_to_supabase(all_scraped)

    # Read existing static dataset
    try:
        existing = json5.loads(match.group(1))
    except Exception:
        existing = []

    valid_existing = [e for e in existing if isinstance(e, dict) and e.get('date', '') >= today_str]
    merged = valid_existing + all_scraped

    # Deduplicate
    seen = set()
    unique_events = []
    for ev in merged:
        key = f"{ev.get('title')}_{ev.get('date')}_{ev.get('state')}".lower()
        if key not in seen:
            seen.add(key)
            unique_events.append(ev)

    unique_events.sort(key=lambda x: x.get('date', ''))

    updated_json = json.dumps(unique_events, indent=6)
    new_html = html[:match.start(1)] + updated_json + html[match.end(1):]

    with open(INDEX_PATH, 'w', encoding='utf-8') as f:
        f.write(new_html)

    print(f"Directory updated with {len(unique_events)} automatically discovered events.")

if __name__ == '__main__':
    purge_old_supabase_events()
    update_index()
