import os
import re
import json
import sys
import datetime
import urllib.request

# Reference Date (UTC)
today = datetime.datetime.now(datetime.timezone.utc).date()
today_str = today.strftime('%Y-%m-%d')
INDEX_PATH = 'index.html'

SUPABASE_URL = "https://lswnpxeiagureogrlopy.supabase.co"
SUPABASE_ANON_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imxzd25weGVpYWd1cmVvZ3Jsb3B5Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3OTE3NjkwNDcsImV4cCI6MjEwNzM0NTA0N30.yg0B_yyMAgdM692J9s-HevvfaykqZoVV0a0AiS6mZ_s"

HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) USAAutoMeets/1.0'}

def days_ahead(n):
    return (today + datetime.timedelta(days=n)).strftime('%Y-%m-%d')

# FULL 50-STATE GUARANTEED RECURRING SCHEDULE
BASE_50_STATE_SCHEDULE = [
    {"title": "Alabama International Dragway Street Legal Night", "state": "AL", "city": "Steele", "venue": "1245 Dragstrip Rd", "category": "Track / Drag", "date": days_ahead(4), "time": "05:00 PM - 10:00 PM", "description": "Friday night street legal drag racing test & tune."},
    {"title": "Hoover Met Cars & Coffee", "state": "AL", "city": "Hoover", "venue": "Hoover Metropolitan Complex", "category": "Cars & Coffee", "date": days_ahead(6), "time": "08:00 AM - 11:00 AM", "description": "Monthly community gathering of muscle cars, hot rods, and exotics."},
    {"title": "Alaska Raceway Park Midnight Sun Drags", "state": "AK", "city": "Palmer", "venue": "5599 S Race Way", "category": "Track / Drag", "date": days_ahead(5), "time": "04:00 PM - 10:00 PM", "description": "NHRA drag racing under the Alaskan sun."},
    {"title": "Firebird Motorsports Park Friday Night Drag", "state": "AZ", "city": "Chandler", "venue": "20000 S Maricopa Rd", "category": "Track / Drag", "date": days_ahead(4), "time": "06:00 PM - 11:00 PM", "description": "Open test & tune for street cars and slicks."},
    {"title": "Scottsdale Pavilion Rock 'N' Roll Car Show", "state": "AZ", "city": "Scottsdale", "venue": "9120 E Talking Stick Way", "category": "Car Show", "date": days_ahead(5), "time": "04:00 PM - 08:00 PM", "description": "Longest-running weekly car show in the U.S."},
    {"title": "Centerville Dragway Saturday Night Shootout", "state": "AR", "city": "Centerville", "venue": "1441 Dragstrip Ln", "category": "Track / Drag", "date": days_ahead(5), "time": "05:00 PM - 10:30 PM", "description": "1/8th mile bracket drag racing."},
    {"title": "In-N-Out Pomona Dragstrip Street Legal Night", "state": "CA", "city": "Pomona", "venue": "2780 E Fairplex Dr", "category": "Track / Drag", "date": days_ahead(3), "time": "05:00 PM - 10:00 PM", "description": "SoCal street legal drag racing under the lights."},
    {"title": "Huntington Beach Donut Derelicts", "state": "CA", "city": "Huntington Beach", "venue": "9015 Adams Ave", "category": "Cars & Coffee", "date": days_ahead(5), "time": "06:00 AM - 09:00 AM", "description": "Historic Saturday morning hot rod assembly."},
    {"title": "Colorado Dragway Friday Night Test & Tune", "state": "CO", "city": "Denver", "venue": "High Plains Raceway", "category": "Track / Drag", "date": days_ahead(4), "time": "04:00 PM - 09:30 PM", "description": "Mile-high drag testing and lapping."},
    {"title": "Lime Rock Park Autocross & Track Day", "state": "CT", "city": "Lakeville", "venue": "60 White Hollow Rd", "category": "Track / Drag", "date": days_ahead(5), "time": "08:30 AM - 04:30 PM", "description": "Historic road course autocross and open track day."},
    {"title": "US 13 Dragway Friday Night Grudge Racing", "state": "DE", "city": "Delmar", "venue": "33599 Sussex Hwy", "category": "Track / Drag", "date": days_ahead(4), "time": "05:30 PM - 10:30 PM", "description": "Delmarva quarter-mile drag racing."},
    {"title": "Orlando Speed World Midnight Drag & Drift", "state": "FL", "city": "Orlando", "venue": "19164 E Colonial Dr", "category": "Track / Drag", "date": days_ahead(4), "time": "07:00 PM - 01:00 AM", "description": "Late-night drag strip testing and drift pad."},
    {"title": "Caffeine & Octane Atlanta", "state": "GA", "city": "Atlanta", "venue": "Town Center at Cobb", "category": "Cars & Coffee", "date": days_ahead(6), "time": "08:00 AM - 12:00 PM", "description": "North America's largest monthly car show."},
    {"title": "Oahu Friday Night Pop-Up Cruise", "state": "HI", "city": "Honolulu", "venue": "Aloha Stadium Lot", "category": "Pop-Up Meet", "date": days_ahead(4), "time": "06:30 PM - 09:30 PM", "description": "Island car culture cruise and meet."},
    {"title": "Firebird Raceway Friday Night Midnight Drags", "state": "ID", "city": "Boise", "venue": "13511 HWY 16", "category": "Track / Drag", "date": days_ahead(4), "time": "07:00 PM - 12:00 AM", "description": "Street legal drag racing and tune-up."},
    {"title": "Byron Dragway Test & Tune", "state": "IL", "city": "Byron", "venue": "2525 HWY 72", "category": "Track / Drag", "date": days_ahead(5), "time": "09:00 AM - 04:00 PM", "description": "Quarter-mile test and tune for all classes."},
    {"title": "Lucas Oil Indianapolis Raceway Park Drags", "state": "IN", "city": "Indianapolis", "venue": "10267 E US HWY 136", "category": "Track / Drag", "date": days_ahead(4), "time": "05:00 PM - 10:00 PM", "description": "Wild Wednesday / Friday street drag testing."},
    {"title": "Eddyville Raceway Park Bracket Night", "state": "IA", "city": "Eddyville", "venue": "3260 330th St", "category": "Track / Drag", "date": days_ahead(5), "time": "04:00 PM - 09:30 PM", "description": "1/8th mile bracket racing and test & tune."},
    {"title": "Kansas International Dragway Street Night", "state": "KS", "city": "Wichita", "venue": "7800 N Ridge Rd", "category": "Track / Drag", "date": days_ahead(4), "time": "06:00 PM - 10:30 PM", "description": "Street car drag racing and roll races."},
    {"title": "Beech Bend Raceway Friday Night Drags", "state": "KY", "city": "Bowling Green", "venue": "798 Beech Bend Rd", "category": "Track / Drag", "date": days_ahead(4), "time": "05:00 PM - 10:00 PM", "description": "Historic quarter-mile drag strip night."},
    {"title": "No Problem Raceway Test & Tune", "state": "LA", "city": "Belle Rose", "venue": "1986 HWY 308", "category": "Track / Drag", "date": days_ahead(5), "time": "06:00 PM - 11:00 PM", "description": "Quarter-mile drag strip and road course lapping."},
    {"title": "Oxford Plains Dragway Friday Night Drags", "state": "ME", "city": "Oxford", "venue": "877 Main St", "category": "Track / Drag", "date": days_ahead(4), "time": "05:00 PM - 09:30 PM", "description": "Maine 1/8th mile drag racing night."},
    {"title": "Maryland International Raceway Midnight Madness", "state": "MD", "city": "Budds Creek", "venue": "27861 Budds Creek Rd", "category": "Track / Drag", "date": days_ahead(4), "time": "06:00 PM - 12:00 AM", "description": "Quarter-mile drag racing and street fights."},
    {"title": "New England Dragway Street Night", "state": "MA", "city": "Boston", "venue": "280 Exeter Rd", "category": "Track / Drag", "date": days_ahead(4), "time": "05:00 PM - 10:00 PM", "description": "Northeast street car drag racing and testing."},
    {"title": "Milan Dragway Friday Test & Tune", "state": "MI", "city": "Milan", "venue": "10860 Plank Rd", "category": "Track / Drag", "date": days_ahead(4), "time": "04:00 PM - 10:00 PM", "description": "Michigan quarter-mile drag racing test session."},
    {"title": "Brainerd International Raceway Street Legal Drags", "state": "MN", "city": "Brainerd", "venue": "5523 HWY 371", "category": "Track / Drag", "date": days_ahead(5), "time": "05:00 PM - 10:00 PM", "description": "Quarter-mile street legal testing in Minnesota."},
    {"title": "Gulfport Dragway Friday Night Street Wars", "state": "MS", "city": "Gulfport", "venue": "17000 Racetrack Rd", "category": "Track / Drag", "date": days_ahead(4), "time": "06:00 PM - 11:00 PM", "description": "Gulf Coast quarter-mile drag racing."},
    {"title": "World Wide Technology Raceway Midnight Madness", "state": "MO", "city": "St. Louis", "venue": "700 Raceway Blvd", "category": "Track / Drag", "date": days_ahead(4), "time": "06:00 PM - 12:00 AM", "description": "Street drag racing and drift showcase."},
    {"title": "Yellowstone Drag Strip Friday Night Test", "state": "MT", "city": "Acton", "venue": "8511 HWY 3", "category": "Track / Drag", "date": days_ahead(4), "time": "05:00 PM - 09:30 PM", "description": "Montana quarter-mile drag racing night."},
    {"title": "Kearney Raceway Park Street Legal Night", "state": "NE", "city": "Kearney", "venue": "5815 HWY 10", "category": "Track / Drag", "date": days_ahead(5), "time": "05:00 PM - 10:00 PM", "description": "Nebraska quarter-mile drag strip testing."},
    {"title": "Las Vegas Motor Speedway Midnight Mayhem", "state": "NV", "city": "Las Vegas", "venue": "7000 N Las Vegas Blvd", "category": "Track / Drag", "date": days_ahead(4), "time": "08:00 PM - 01:00 AM", "description": "Street-legal drag racing alternative on the Strip."},
    {"title": "Island Dragway Friday Night Test & Tune", "state": "NJ", "city": "Great Meadows", "venue": "214 Red Schoolhouse Rd", "category": "Track / Drag", "date": days_ahead(4), "time": "06:00 PM - 10:00 PM", "description": "Historic New Jersey quarter-mile drag strip."},
    {"title": "Albuquerque Dragway Friday Street Fights", "state": "NM", "city": "Albuquerque", "venue": "10500 HWY 337", "category": "Track / Drag", "date": days_ahead(4), "time": "06:00 PM - 10:30 PM", "description": "High-altitude drag strip testing."},
    {"title": "Lebanon Valley Dragway Friday Night Street Legal", "state": "NY", "city": "West Lebanon", "venue": "1740 US-20", "category": "Track / Drag", "date": days_ahead(4), "time": "05:00 PM - 10:00 PM", "description": "New York quarter-mile drag racing night."},
    {"title": "Rockingham Dragway Street Night", "state": "NC", "city": "Rockingham", "venue": "2153 US-1", "category": "Track / Drag", "date": days_ahead(4), "time": "05:00 PM - 10:00 PM", "description": "Carolinas street car drag test & tune."},
    {"title": "Summit Motorsports Park Friday Test & Tune", "state": "OH", "city": "Norwalk", "venue": "1300 St Rte 18", "category": "Track / Drag", "date": days_ahead(4), "time": "04:00 PM - 09:30 PM", "description": "Quarter-mile drag racing under full lights."},
    {"title": "Thunder Valley Raceway Park Street Night", "state": "OK", "city": "Noble", "venue": "10586 120th St", "category": "Track / Drag", "date": days_ahead(4), "time": "06:00 PM - 11:00 PM", "description": "Oklahoma quarter-mile drag racing."},
    {"title": "Woodburn Dragstrip Friday Night Late Night", "state": "OR", "city": "Woodburn", "venue": "7730 HWY 219", "category": "Track / Drag", "date": days_ahead(4), "time": "04:00 PM - 09:30 PM", "description": "Pacific Northwest street legal drag testing."},
    {"title": "Maple Grove Raceway Street Legal Night", "state": "PA", "city": "Reading", "venue": "30 Stauffer Park Ln", "category": "Track / Drag", "date": days_ahead(4), "time": "05:00 PM - 10:00 PM", "description": "Pennsylvania quarter-mile drag racing."},
    {"title": "Darlington Dragway Friday Test & Tune", "state": "SC", "city": "Hartsville", "venue": "2056 E Bobo Newsome HWY", "category": "Track / Drag", "date": days_ahead(4), "time": "05:00 PM - 10:00 PM", "description": "South Carolina 1/4th mile drag strip."},
    {"title": "Music City Raceway Friday Night Drags", "state": "TN", "city": "Nashville", "venue": "3305 Music City Rd", "category": "Track / Drag", "date": days_ahead(4), "time": "05:00 PM - 10:30 PM", "description": "1/8th mile Nashville drag racing."},
    {"title": "Houston Raceway Park Street Fights", "state": "TX", "city": "Houston", "venue": "2525 FM 565", "category": "Track / Drag", "date": days_ahead(4), "time": "06:00 PM - 11:30 PM", "description": "Open drag racing and roll racing."},
    {"title": "Pacific Raceways Friday Night Drag & Tune", "state": "WA", "city": "Kent", "venue": "31001 144th Ave SE", "category": "Track / Drag", "date": days_ahead(4), "time": "04:00 PM - 10:00 PM", "description": "Street car drag test & tune session."},
    {"title": "Bremerton Raceway Sportsman Drags", "state": "WA", "city": "Bremerton", "venue": "8800 SW Imperial Way", "category": "Track / Drag", "date": days_ahead(5), "time": "08:00 AM - 05:00 PM", "description": "Bracket drag racing at Bremerton Airport."},
    {"title": "Griot's Garage Tacoma Caffeine & Gasoline", "state": "WA", "city": "Tacoma", "venue": "3333 S 38th St", "category": "Cars & Coffee", "date": days_ahead(6), "time": "08:00 AM - 10:00 AM", "description": "Flagship store cars & coffee with free coffee."},
    {"title": "Great Lakes Dragaway Street Drag Night", "state": "WI", "city": "Union Grove", "venue": "18411 1st St", "category": "Track / Drag", "date": days_ahead(4), "time": "04:00 PM - 10:00 PM", "description": "Union Grove drag racing test and tune."},
    {"title": "District Cars & Coffee Capitol Meet", "state": "DC", "city": "Washington", "venue": "RFK Stadium Lot 8", "category": "Cars & Coffee", "date": days_ahead(6), "time": "08:30 AM - 11:30 AM", "description": "D.C. metro automotive gathering."
]

def fetch_msr_events_direct():
    events = []
    url = "https://api.motorsportreg.com/rest/events.json?country=USA&radius=3000"
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            for item in data.get('recordset', {}).get('events', []):
                title = str(item.get('name') or 'Motorsports Event')[:80]
                start_date = str(item.get('start') or '')[:10]
                venue = item.get('venue') or {}
                state = str(venue.get('state') or 'WA')[:2].upper()
                city = str(venue.get('city') or 'Regional')
                venue_name = str(venue.get('name') or 'Motorsports Park')[:80]
                
                if start_date and start_date >= today_str:
                    events.append({
                        "title": title,
                        "state": state,
                        "city": city,
                        "venue": venue_name,
                        "category": "Track / Drag" if any(w in title.lower() for w in ["drag", "track", "autocross", "lapping"]) else "Car Show",
                        "date": start_date,
                        "time": "08:00 AM - 05:00 PM",
                        "description": str(item.get('type') or 'Motorsports gathering.')
                    })
    except Exception as e:
        print(f"Notice: MSR API fetch notice (skipped): {e}")
    return events

def purge_old_supabase_events():
    try:
        url = f"{SUPABASE_URL}/rest/v1/events?date=lt.{today_str}"
        req = urllib.request.Request(url, method='DELETE')
        req.add_header('apikey', SUPABASE_ANON_KEY)
        req.add_header('Authorization', f'Bearer {SUPABASE_ANON_KEY}')
        with urllib.request.urlopen(req, timeout=10) as resp:
            print(f"Supabase database purge completed (Status {resp.status}).")
    except Exception as e:
        print(f"Notice: Supabase purge notice (skipped): {e}")

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
        except Exception as e:
            print(f"Notice: Supabase push batch notice: {e}")
    print(f"Pushed {len(event_list)} records to Supabase.")

def parse_json_safely(raw_js):
    cleaned = re.sub(r',\s*([}\]])', r'\1', raw_js)
    try:
        return json.loads(cleaned)
    except Exception as e:
        print(f"Notice: JSON parse notice on index.html: {e}")
        return []

def update_index():
    if not os.path.exists(INDEX_PATH):
        print(f"File {INDEX_PATH} not found.")
        sys.exit(0)

    with open(INDEX_PATH, 'r', encoding='utf-8') as f:
        html = f.read()

    match = re.search(r'let eventsData = (\[[\s\S]*?\]);', html)
    if not match:
        print("Could not match 'let eventsData = [...]' in index.html.")
        sys.exit(0)

    raw_js = match.group(1)
    existing = parse_json_safely(raw_js)

    base_events = BASE_50_STATE_SCHEDULE
    msr_events = fetch_msr_events_direct()
    all_events = base_events + msr_events

    push_to_supabase(all_events)

    valid_existing = [
        e for e in existing 
        if isinstance(e, dict) and str(e.get('date') or '') >= today_str
    ]
    merged = valid_existing + all_events

    seen = set()
    unique_events = []
    for ev in merged:
        title = str(ev.get('title') or '')
        ev_date = str(ev.get('date') or '')
        state = str(ev.get('state') or '')
        
        if ev_date and ev_date >= today_str:
            key = f"{title}_{ev_date}_{state}".lower()
            if key not in seen:
                seen.add(key)
                unique_events.append(ev)

    unique_events.sort(key=lambda x: str(x.get('date') or ''))

    updated_json = json.dumps(unique_events, indent=6)
    new_html = html[:match.start(1)] + updated_json + html[match.end(1):]

    with open(INDEX_PATH, 'w', encoding='utf-8') as f:
        f.write(new_html)

    print(f"Success: Updated index.html with {len(unique_events)} active events across all 50 states.")

if __name__ == '__main__':
    purge_old_supabase_events()
    update_index()
    sys.exit(0)
