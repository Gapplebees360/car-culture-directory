import os
import re
import json
import datetime
import urllib.request
import json5
from bs4 import BeautifulSoup
from icalendar import Calendar

# Reference Date
today = datetime.datetime.now(datetime.timezone.utc).date()
today_str = today.strftime('%Y-%m-%d')
INDEX_PATH = 'index.html'

# Supabase REST Configuration
SUPABASE_URL = "https://lswnpxeiagureogrlopy.supabase.co"
SUPABASE_ANON_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imxzd25weGVpYWd1cmVvZ3Jsb3B5Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3OTE3NjkwNDcsImV4cCI6MjEwNzM0NTA0N30.yg0B_yyMAgdM692J9s-HevvfaykqZoVV0a0AiS6mZ_s"

HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) USAAutoMeets/1.0'}

# ==========================================
# 1. NATIONWIDE TRACK REGISTRY (ICS / iCal)
# ==========================================
# Any track using WordPress Events Calendar, Google Calendar, or iCal can be added here
TRACK_ICAL_REGISTRY = [
    {
        "name": "Pacific Raceways",
        "state": "WA",
        "city": "Kent",
        "venue": "Pacific Raceways, 31001 144th Ave SE",
        "category": "Track / Drag",
        "feed_url": "https://pacificraceways.com/events/?ical=1"
    },
    {
        "name": "The Ridge Motorsports Park",
        "state": "WA",
        "city": "Shelton",
        "venue": "1070 SE Performance Dr",
        "category": "Track / Drag",
        "feed_url": "https://www.ridgemotorsportspark.com/events/?ical=1"
    },
    {
        "name": "Sonoma Raceway",
        "state": "CA",
        "city": "Pleasanton",
        "venue": "Sonoma Raceway, 29355 Arnold Dr",
        "category": "Track / Drag",
        "feed_url": "https://www.sonomaraceway.com/events/?ical=1"
    },
    {
        "name": "Circuit of the Americas",
        "state": "TX",
        "city": "Austin",
        "venue": "9201 Circuit of the Americas Blvd",
        "category": "Track / Drag",
        "feed_url": "https://circuitoftheamericas.com/events/?ical=1"
    }
]

def parse_ical_track_feeds():
    """Generic parser for iCal / ICS track feeds across the US"""
    events = []
    
    for track in TRACK_ICAL_REGISTRY:
        try:
            req = urllib.request.Request(track['feed_url'], headers=HEADERS)
            with urllib.request.urlopen(req, timeout=10) as resp:
                gcal = Calendar.from_ical(resp.read())
                
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
                                    "venue": track['venue'],
                                    "category": track['category'],
                                    "date": ev_date_str,
                                    "time": "08:00 AM - 05:00 PM",
                                    "description": str(component.get('description', ''))[:200] or f"Official race event at {track['name']}."
                                })
        except Exception as e:
            print(f"Notice: iCal feed note for {track['name']}: {e}")
            
    print(f"Scraped {len(events)} events via iCal Track Registry.")
    return events

# ==========================================
# 2. MOTORSPORTREG API NATIONWIDE SCRAPER
# ==========================================
def scrape_motorsportreg_nationwide():
    """Queries MotorsportReg API for active track days, drag races, and autocross across all US states"""
    events = []
    url = "https://api.motorsportreg.com/rest/events.json?country=USA&radius=3000"
    
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=12) as resp:
            data = json.loads(resp.read().decode())
            events_list = data.get('recordset', {}).get('events', [])
            
            for item in events_list:
                start_date = item.get('start', '')[:10]
                if start_date >= today_str:
                    venue = item.get('venue', {})
                    events.append({
                        "title": item.get('name', 'Motorsports Event')[:80],
                        "state": (venue.get('state', 'WA') or 'WA')[:2].upper(),
                        "city": venue.get('city', 'Regional') or 'Regional',
                        "venue": (venue.get('name', 'Motorsports Park') or 'Motorsports Park')[:80],
                        "category": "Track / Drag" if any(w in item.get('name','').lower() for w in ["drag", "track", "autocross", "lapping"]) else "Car Show",
                        "date": start_date,
                        "time": "08:00 AM - 05:00 PM",
                        "description": item.get('type', 'Motorsports gathering.')
                    })
    except Exception as e:
        print(f"Notice: MotorsportReg API note: {e}")
        
    print(f"Scraped {len(events)} events via MotorsportReg API.")
    return events

# ==========================================
# 3. SUPABASE SYNC & INDEX BUILDER
# ==========================================
def purge_old_supabase_events():
    """Deletes past events prior to current date"""
    try:
        url = f"{SUPABASE_URL}/rest/v1/events?date=lt.{today_str}"
        req = urllib.request.Request(url, method='DELETE')
        req.add_header('apikey', SUPABASE_ANON_KEY)
        req.add_header('Authorization', f'Bearer {SUPABASE_ANON_KEY}')
        with urllib.request.urlopen(req, timeout=10) as resp:
            print(f"Supabase purge completed: Status {resp.status}")
    except Exception as e:
        print(f"Supabase purge note: {e}")

def push_to_supabase(event_list):
    """Pushes fresh events to Supabase database"""
    if not event_list:
        return
        
    url = f"{SUPABASE_URL}/rest/v1/events"
    headers = {
        'apikey': SUPABASE_ANON_KEY,
        'Authorization': f'Bearer {SUPABASE_ANON_KEY}',
        'Content-Type': 'application/json',
        'Prefer': 'ignore-duplicates'
    }

    # Process in batches of 50
    batch_size = 50
    for i in range(0, len(event_list), batch_size):
        batch = event_list[i:i + batch_size]
        try:
            data_json = json.dumps(batch).encode('utf-8')
            req = urllib.request.Request(url, data=data_json, headers=headers, method='POST')
            with urllib.request.urlopen(req, timeout=10) as resp:
                pass
        except Exception as e:
            print(f"Supabase batch push note: {e}")
            
    print(f"Pushed {len(event_list)} records into Supabase.")

def update_index():
    if not os.path.exists(INDEX_PATH):
        return

    with open(INDEX_PATH, 'r', encoding='utf-8') as f:
        html = f.read()

    match = re.search(r'let eventsData = (\[[\s\S]*?\]);', html)
    if not match:
        return

    # Ingest from all sources
    ical_events = parse_ical_track_feeds()
    msr_events = scrape_motorsportreg_nationwide()
    all_scraped = ical_events + msr_events

    # Push to Supabase database
    push_to_supabase(all_scraped)

    # Read existing static dataset from index.html
    try:
        existing = json5.loads(match.group(1))
    except Exception:
        existing = []

    valid_existing = [e for e in existing if isinstance(e, dict) and e.get('date', '') >= today_str]
    merged = valid_existing + all_scraped

    # Deduplicate by Title + Date + State
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

    print(f"Success: Directory updated with {len(unique_events)} upcoming US track & car events.")

if __name__ == '__main__':
    purge_old_supabase_events()
    update_index()
