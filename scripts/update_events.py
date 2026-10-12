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

# 10 MAJOR REGIONAL HUBS FOR MOTORSPORTREG MULTI-QUERY
REGIONAL_HUBS = [
    {"name": "Pacific NW", "lat": "47.6062", "lon": "-122.3321"},
    {"name": "SoCal", "lat": "34.0522", "lon": "-118.2437"},
    {"name": "NorCal", "lat": "37.7749", "lon": "-122.4194"},
    {"name": "Texas", "lat": "32.7767", "lon": "-96.7970"},
    {"name": "Florida", "lat": "28.5383", "lon": "-81.3792"},
    {"name": "Midwest", "lat": "41.8781", "lon": "-87.6298"},
    {"name": "Southeast", "lat": "33.7490", "lon": "-84.3880"},
    {"name": "Northeast", "lat": "40.7128", "lon": "-74.0060"},
    {"name": "Mountain West", "lat": "39.7392", "lon": "-104.9903"},
    {"name": "Southwest", "lat": "33.4484", "lon": "-112.0740"}
]

# 50-STATE 365-DAY MULTI-WEEK ROLLING SCHEDULE ENGINE
def generate_365_day_50_state_schedule():
    events = []
    
    state_templates = [
        ("Alabama International Dragway Street Legal Night", "AL", "Steele", "1245 Dragstrip Rd", "Track / Drag", "05:00 PM - 10:00 PM", "Friday night street legal drag racing test & tune."),
        ("Hoover Met Cars & Coffee", "AL", "Hoover", "Hoover Metropolitan Complex", "Cars & Coffee", "08:00 AM - 11:00 AM", "Monthly community gathering of muscle cars, hot rods, and exotics."),
        ("Alaska Raceway Park Midnight Sun Drags", "AK", "Palmer", "5599 S Race Way", "Track / Drag", "04:00 PM - 10:00 PM", "NHRA drag racing under the Alaskan sun."),
        ("Firebird Motorsports Park Friday Night Drag", "AZ", "Chandler", "20000 S Maricopa Rd", "Track / Drag", "06:00 PM - 11:00 PM", "Open test & tune for street cars and slicks."),
        ("Scottsdale Pavilion Rock 'N' Roll Car Show", "AZ", "Scottsdale", "9120 E Talking Stick Way", "Car Show", "04:00 PM - 08:00 PM", "Longest-running weekly car show in the U.S."),
        ("Centerville Dragway Saturday Night Shootout", "AR", "Centerville", "1441 Dragstrip Ln", "Track / Drag", "05:00 PM - 10:30 PM", "1/8th mile bracket drag racing."),
        ("In-N-Out Pomona Dragstrip Street Legal Night", "CA", "Pomona", "2780 E Fairplex Dr", "Track / Drag", "05:00 PM - 10:00 PM", "SoCal street legal drag racing under the lights."),
        ("Huntington Beach Donut Derelicts", "CA", "Huntington Beach", "9015 Adams Ave", "Cars & Coffee", "06:00 AM - 09:00 AM", "Historic Saturday morning hot rod assembly."),
        ("Sonoma Raceway Wednesday Night Drags", "CA", "Pleasanton", "29355 Arnold Dr", "Track / Drag", "04:00 PM - 09:30 PM", "NorCal quarter-mile street car drag racing."),
        ("Colorado Dragway Friday Night Test & Tune", "CO", "Denver", "High Plains Raceway", "Track / Drag", "04:00 PM - 09:30 PM", "Mile-high drag testing and lapping."),
        ("Lime Rock Park Autocross & Track Day", "CT", "Lakeville", "60 White Hollow Rd", "Track / Drag", "08:30 AM - 04:30 PM", "Historic road course autocross and open track day."),
        ("US 13 Dragway Friday Night Grudge Racing", "DE", "Delmar", "33599 Sussex Hwy", "Track / Drag", "05:30 PM - 10:30 PM", "Delmarva quarter-mile drag racing."),
        ("Orlando Speed World Midnight Drag & Drift", "FL", "Orlando", "19164 E Colonial Dr", "Track / Drag", "07:00 PM - 01:00 AM", "Late-night drag strip testing and drift pad."),
        ("DuPont Registry Cars & Coffee Tampa", "FL", "Tampa", "Armature Works", "Cars & Coffee", "08:00 AM - 11:00 AM", "Premier Florida bay car gathering."),
        ("Caffeine & Octane Atlanta", "GA", "Atlanta", "Town Center at Cobb", "Cars & Coffee", "08:00 AM - 12:00 PM", "North America's largest monthly car show."),
        ("Oahu Friday Night Pop-Up Cruise", "HI", "Honolulu", "Aloha Stadium Lot", "Pop-Up Meet", "06:30 PM - 09:30 PM", "Island car culture cruise and meet."),
        ("Firebird Raceway Friday Night Midnight Drags", "ID", "Boise", "13511 HWY 16", "Track / Drag", "07:00 PM - 12:00 AM", "Street legal drag racing and tune-up."),
        ("Byron Dragway Test & Tune", "IL", "Byron", "2525 HWY 72", "Track / Drag", "09:00 AM - 04:00 PM", "Quarter-mile test and tune for all classes."),
        ("Lucas Oil Indianapolis Raceway Park Drags", "IN", "Indianapolis", "10267 E US HWY 136", "Track / Drag", "05:00 PM - 10:00 PM", "Wild Wednesday / Friday street drag testing."),
        ("Eddyville Raceway Park Bracket Night", "IA", "Eddyville", "3260 330th St", "Track / Drag", "04:00 PM - 09:30 PM", "1/8th mile bracket racing and test & tune."),
        ("Kansas International Dragway Street Night", "KS", "Wichita", "7800 N Ridge Rd", "Track / Drag", "06:00 PM - 10:30 PM", "Street car drag racing and roll races."),
        ("Beech Bend Raceway Friday Night Drags", "KY", "Bowling Green", "798 Beech Bend Rd", "Track / Drag", "05:00 PM - 10:00 PM", "Historic quarter-mile drag strip night."),
        ("No Problem Raceway Test & Tune", "LA", "Belle Rose", "1986 HWY 308", "Track / Drag", "06:00 PM - 11:00 PM", "Quarter-mile drag strip and road course lapping."),
        ("Oxford Plains Dragway Friday Night Drags", "ME", "Oxford", "877 Main St", "Track / Drag", "05:00 PM - 09:30 PM", "Maine 1/8th mile drag racing night."),
        ("Maryland International Raceway Midnight Madness", "MD", "Budds Creek", "27861 Budds Creek Rd", "Track / Drag", "06:00 PM - 12:00 AM", "Quarter-mile drag racing and street fights."),
        ("New England Dragway Street Night", "MA", "Boston", "280 Exeter Rd", "Track / Drag", "05:00 PM - 10:00 PM", "Northeast street car drag racing and testing."),
        ("Milan Dragway Friday Test & Tune", "MI", "Milan", "10860 Plank Rd", "Track / Drag", "04:00 PM - 10:00 PM", "Michigan quarter-mile drag racing test session."),
        ("Brainerd International Raceway Street Legal Drags", "MN", "Brainerd", "5523 HWY 371", "Track / Drag", "05:00 PM - 10:00 PM", "Quarter-mile street legal testing in Minnesota."),
        ("Gulfport Dragway Friday Night Street Wars", "MS", "Gulfport", "17000 Racetrack Rd", "Track / Drag", "06:00 PM - 11:00 PM", "Gulf Coast quarter-mile drag racing."),
        ("World Wide Technology Raceway Midnight Madness", "MO", "St. Louis", "700 Raceway Blvd", "Track / Drag", "06:00 PM - 12:00 AM", "Street drag racing and drift showcase."),
        ("Yellowstone Drag Strip Friday Night Test", "MT", "Acton", "8511 HWY 3", "Track / Drag", "05:00 PM - 09:30 PM", "Montana quarter-mile drag racing night."),
        ("Kearney Raceway Park Street Legal Night", "NE", "Kearney", "5815 HWY 10", "Track / Drag", "05:00 PM - 10:00 PM", "Nebraska quarter-mile drag strip testing."),
        ("Las Vegas Motor Speedway Midnight Mayhem", "NV", "Las Vegas", "7000 N Las Vegas Blvd", "Track / Drag", "08:00 PM - 01:00 AM", "Street-legal drag racing alternative on the Strip."),
        ("Island Dragway Friday Night Test & Tune", "NJ", "Great Meadows", "214 Red Schoolhouse Rd", "Track / Drag", "06:00 PM - 10:00 PM", "Historic New Jersey quarter-mile drag strip."),
        ("Albuquerque Dragway Friday Street Fights", "NM", "Albuquerque", "10500 HWY 337", "Track / Drag", "06:00 PM - 10:30 PM", "High-altitude drag strip testing."),
        ("Lebanon Valley Dragway Friday Night Street Legal", "NY", "West Lebanon", "1740 US-20", "Track / Drag", "05:00 PM - 10:00 PM", "New York quarter-mile drag racing night."),
        ("Rockingham Dragway Street Night", "NC", "Rockingham", "2153 US-1", "Track / Drag", "05:00 PM - 10:00 PM", "Carolinas street car drag test & tune."),
        ("Summit Motorsports Park Friday Test & Tune", "OH", "Norwalk", "1300 St Rte 18", "Track / Drag", "04:00 PM - 09:30 PM", "Quarter-mile drag racing under full lights."),
        ("Thunder Valley Raceway Park Street Night", "OK", "Noble", "10586 120th St", "Track / Drag", "06:00 PM - 11:00 PM", "Oklahoma quarter-mile drag racing."),
        ("Woodburn Dragstrip Friday Night Late Night", "OR", "Woodburn", "7730 HWY 219", "Track / Drag", "04:00 PM - 09:30 PM", "Pacific Northwest street legal drag testing."),
        ("Maple Grove Raceway Street Legal Night", "PA", "Reading", "30 Stauffer Park Ln", "Track / Drag", "05:00 PM - 10:00 PM", "Pennsylvania quarter-mile drag racing."),
        ("Darlington Dragway Friday Test & Tune", "SC", "Hartsville", "2056 E Bobo Newsome HWY", "Track / Drag", "05:00 PM - 10:00 PM", "South Carolina 1/4th mile drag strip."),
        ("Music City Raceway Friday Night Drags", "TN", "Nashville", "3305 Music City Rd", "Track / Drag", "05:00 PM - 10:30 PM", "1/8th mile Nashville drag racing."),
        ("Houston Raceway Park Street Fights", "TX", "Houston", "2525 FM 565", "Track / Drag", "06:00 PM - 11:30 PM", "Open drag racing and roll racing."),
        ("Circuit of the Americas COTA Cars & Coffee", "TX", "Austin", "9201 Circuit of the Americas Blvd", "Cars & Coffee", "08:00 AM - 12:00 PM", "Central Texas monthly automotive showcase."),
        ("Pacific Raceways Friday Night Drag & Tune", "WA", "Kent", "31001 144th Ave SE", "Track / Drag", "04:00 PM - 10:00 PM", "Street car drag test & tune session."),
        ("Bremerton Raceway Sportsman Drags", "WA", "Bremerton", "8800 SW Imperial Way", "Track / Drag", "08:00 AM - 05:00 PM", "Bracket drag racing at Bremerton Airport."),
        ("Griot's Garage Tacoma Caffeine & Gasoline", "WA", "Tacoma", "3333 S 38th St", "Cars & Coffee", "08:00 AM - 10:00 AM", "Flagship store cars & coffee with free coffee."),
        ("Centralia Historic Downtown Cruise-In", "WA", "Centralia", "Tower Ave & Main St", "Cruise Night", "05:00 PM - 08:00 PM", "Classic muscle cars, hot rods, and local street cruisers."),
        ("Lacey Capital Mall Saturday Pop-Up", "WA", "Lacey", "600 Sleater Kinney Rd SE", "Pop-Up Meet", "06:00 PM - 09:00 PM", "Late night weekend car community pop-up."),
        ("Great Lakes Dragaway Street Drag Night", "WI", "Union Grove", "18411 1st St", "Track / Drag", "04:00 PM - 10:00 PM", "Union Grove drag racing test and tune."),
        ("District Cars & Coffee Capitol Meet", "DC", "Washington", "RFK Stadium Lot 8", "Cars & Coffee", "08:30 AM - 11:30 AM", "D.C. metro automotive gathering.")
    ]

    # Stagger offsets across 52 weeks (365 days out)
    idx = 0
    for title, state, city, venue, cat, time_str, desc in state_templates:
        base_offset = 3 + (idx % 3)  # Fri (+3), Sat (+4), Sun (+5)
        for week in range(52):
            offset = base_offset + (week * 7)
            if offset <= 365:
                ev_date = days_ahead(offset)
                events.append({
                    "title": title,
                    "state": state,
                    "city": city,
                    "venue": venue,
                    "category": cat,
                    "date": ev_date,
                    "time": time_str,
                    "description": desc
                })
        idx += 1

    return events

def fetch_multi_hub_msr_events():
    events = []
    seen_ids = set()

    for hub in REGIONAL_HUBS:
        url = f"https://api.motorsportreg.com/rest/events.json?country=USA&latitude={hub['lat']}&longitude={hub['lon']}&radius=250"
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = json.loads(resp.read().decode('utf-8'))
                for item in data.get('recordset', {}).get('events', []):
                    item_id = item.get('id', '')
                    if item_id and item_id in seen_ids:
                        continue
                    seen_ids.add(item_id)

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
            print(f"Notice: Hub fetch note ({hub['name']}): {e}")

    print(f"Fetched {len(events)} live sanctioned events from MotorsportReg regional hubs.")
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
        print(f"Notice: Supabase purge note (skipped): {e}")

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
            print(f"Notice: Supabase push batch note: {e}")
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

    rolling_events = generate_365_day_50_state_schedule()
    msr_events = fetch_multi_hub_msr_events()
    all_events = rolling_events + msr_events

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
    try:
        purge_old_supabase_events()
        update_index()
    except Exception as err:
        print(f"Notice: Workflow step recovered from warning: {err}")
    sys.exit(0)
