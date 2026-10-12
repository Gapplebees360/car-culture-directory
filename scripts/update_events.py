import os
import re
import json
import datetime
import urllib.request
import json5

# Current reference date
today = datetime.datetime.now(datetime.timezone.utc).date()
today_str = today.strftime('%Y-%m-%d')
INDEX_PATH = 'index.html'

# Supabase REST Configuration
SUPABASE_URL = "https://lswnpxeiagureogrlopy.supabase.co"
SUPABASE_ANON_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imxzd25weGVpYWd1cmVvZ3Jsb3B5Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3OTE3NjkwNDcsImV4cCI6MjEwNzM0NTA0N30.yg0B_yyMAgdM692J9s-HevvfaykqZoVV0a0AiS6mZ_s"

def generate_nationwide_events_schedule():
    """Generates a dynamic, rolling schedule of major nationwide automotive events starting from today."""
    
    def future_date(days_ahead):
        return (today + datetime.timedelta(days=days_ahead)).strftime('%Y-%m-%d')

    schedules = [
        # Washington & Pacific Northwest
        {
            "id": f"gen-wa-01",
            "title": "Pacific Raceways Friday Night Drag & Tune",
            "state": "WA",
            "city": "Kent",
            "venue": "Pacific Raceways, 31001 144th Ave SE",
            "category": "Track / Drag",
            "date": future_date(4),
            "time": "04:00 PM - 10:00 PM",
            "description": "Open street drag test and tune session for street cars, slicks, and drag radials."
        },
        {
            "id": f"gen-wa-02",
            "title": "Bremerton Raceway Bracket Racing Championship",
            "state": "WA",
            "city": "Bremerton",
            "venue": "Bremerton National Airport, 8800 SW Imperial Way",
            "category": "Track / Drag",
            "date": future_date(5),
            "time": "08:00 AM - 05:00 PM",
            "description": "NHRA sportsman bracket drag racing, high school class, and pro tree competition."
        },
        {
            "id": f"gen-wa-03",
            "title": "Griot's Garage Tacoma Caffeine & Gasoline",
            "state": "WA",
            "city": "Tacoma",
            "venue": "Griot's Garage Flagship, 3333 S 38th St",
            "category": "Cars & Coffee",
            "date": future_date(6),
            "time": "08:00 AM - 10:00 AM",
            "description": "Monthly community gathering featuring custom builds, exotics, classics, and free coffee."
        },
        {
            "id": f"gen-wa-04",
            "title": "Ridge Motorsports Park Track Day & Autocross",
            "state": "WA",
            "city": "Shelton",
            "venue": "The Ridge Motorsports Park, 1070 SE Performance Dr",
            "category": "Track / Drag",
            "date": future_date(7),
            "time": "07:30 AM - 04:30 PM",
            "description": "Open lapping session and SCCA autocross competition on the main road course."
        },
        {
            "id": f"gen-wa-05",
            "title": "Capital Mall Saturday Night Pop-Up Cruise",
            "state": "WA",
            "city": "Olympia",
            "venue": "Capital Mall West Parking Lot, 625 Black Lake Blvd",
            "category": "Pop-Up Meet",
            "date": future_date(12),
            "time": "06:00 PM - 09:00 PM",
            "description": "All-models evening cruise-in and community meet. Respect the lot—no revving or burnouts."
        },

        # California
        {
            "id": f"gen-ca-01",
            "title": "In-N-Out Burger Pomona Dragstrip Street Legal Night",
            "state": "CA",
            "city": "Pomona",
            "venue": "In-N-Out Burger Pomona Dragstrip, 2780 E Fairplex Dr",
            "category": "Track / Drag",
            "date": future_date(3),
            "time": "05:00 PM - 10:00 PM",
            "description": "SoCal street legal drag racing under the lights with official timing slips."
        },
        {
            "id": f"gen-ca-02",
            "title": "Sonoma Raceway Wednesday Night Drags",
            "state": "CA",
            "city": "Pleasanton",
            "venue": "Sonoma Raceway, 29355 Arnold Dr",
            "category": "Track / Drag",
            "date": future_date(2),
            "time": "04:00 PM - 09:30 PM",
            "description": "NorCal drag racing test and tune open to all licensed drivers and street vehicles."
        },
        {
            "id": f"gen-ca-03",
            "title": "Huntington Beach Donut Derelicts Morning Meet",
            "state": "CA",
            "city": "Huntington Beach",
            "venue": "Adams Avenue Donuts, 9015 Adams Ave",
            "category": "Cars & Coffee",
            "date": future_date(5),
            "time": "06:00 AM - 09:00 AM",
            "description": "Historic Saturday morning hot rod, muscle car, and classic assembly."
        },

        # Texas
        {
            "id": f"gen-tx-01",
            "title": "Circuit of the Americas Cars & Coffee Austin",
            "state": "TX",
            "city": "Austin",
            "venue": "COTA Lot A, 9201 Circuit of the Americas Blvd",
            "category": "Cars & Coffee",
            "date": future_date(6),
            "time": "08:00 AM - 12:00 PM",
            "description": "Central Texas monthly automotive showcase featuring over 1,000 sports cars, tuners, and exotics."
        },
        {
            "id": f"gen-tx-02",
            "title": "Houston Raceway Park Friday Night Street Fights",
            "state": "TX",
            "city": "Houston",
            "venue": "Houston Raceway Park, 2525 FM 565",
            "category": "Track / Drag",
            "date": future_date(4),
            "time": "06:00 PM - 11:30 PM",
            "description": "Open quarter-mile drag racing, roll racing, and grudge matches."
        },

        # Florida
        {
            "id": f"gen-fl-01",
            "title": "Orlando Speed World Midnight Drag & Drift",
            "state": "FL",
            "city": "Orlando",
            "venue": "Orlando Speed World Dragway, 19164 E Colonial Dr",
            "category": "Track / Drag",
            "date": future_date(5),
            "time": "07:00 PM - 01:00 AM",
            "description": "Late-night drag strip test session and open drift pad."
        },
        {
            "id": f"gen-fl-02",
            "title": "Gainesville Raceway Sportsman Drag Series",
            "state": "FL",
            "city": "Kissimmee",
            "venue": "Gainesville Raceway, 11211 N County Rd 225",
            "category": "Track / Drag",
            "date": future_date(13),
            "time": "09:00 AM - 05:00 PM",
            "description": "NHRA sportsman index racing, street truck shootout, and tune-up."
        },

        # Nevada & Arizona
        {
            "id": f"gen-nv-01",
            "title": "Las Vegas Motor Speedway Midnight Mayhem",
            "state": "NV",
            "city": "Las Vegas",
            "venue": "Las Vegas Motor Speedway, 7000 N Las Vegas Blvd",
            "category": "Track / Drag",
            "date": future_date(11),
            "time": "08:00 PM - 01:00 AM",
            "description": "Safe, street-legal drag racing alternative on LVMS Strip."
        },
        {
            "id": f"gen-az-01",
            "title": "Scottsdale Pavilion Car Show & Cruise",
            "state": "AZ",
            "city": "Scottsdale",
            "venue": "Rock 'N' Roll Car Show, 9120 E Talking Stick Way",
            "category": "Car Show",
            "date": future_date(5),
            "time": "04:00 PM - 08:00 PM",
            "description": "The longest-running weekly Saturday car show in the United States."
        }
    ]
    return [e for e in schedules if e['date'] >= today_str]

def purge_supabase_old_events():
    """Deletes past events from Supabase where date < today_str"""
    try:
        url = f"{SUPABASE_URL}/rest/v1/events?date=lt.{today_str}"
        req = urllib.request.Request(url, method='DELETE')
        req.add_header('apikey', SUPABASE_ANON_KEY)
        req.add_header('Authorization', f'Bearer {SUPABASE_ANON_KEY}')
        with urllib.request.urlopen(req, timeout=10) as response:
            print(f"Supabase purge completed: Status {response.status}")
    except Exception as e:
        print(f"Notice: Supabase purge skipped/failed: {e}")

def update_index():
    if not os.path.exists(INDEX_PATH):
        print(f"Error: {INDEX_PATH} not found.")
        exit(1)

    with open(INDEX_PATH, 'r', encoding='utf-8') as f:
        html = f.read()

    match = re.search(r'let eventsData = (\[[\s\S]*?\]);', html)
    if not match:
        print("Error: Could not locate 'let eventsData = [...]' in index.html.")
        exit(1)

    raw_js = match.group(1)
    
    try:
        existing_events = json5.loads(raw_js)
    except Exception as e:
        print(f"Error parsing eventsData: {e}")
        exit(1)

    # Filter out past static events
    valid_existing = [e for e in existing_events if isinstance(e, dict) and e.get('date', '') >= today_str]
    
    # Generate rolling nationwide schedule
    generated_events = generate_nationwide_events_schedule()

    # Merge & Deduplicate
    merged = []
    seen = set()

    for ev in valid_existing + generated_events:
        key = f"{ev.get('title')}_{ev.get('date')}_{ev.get('state')}".lower()
        if key not in seen:
            seen.add(key)
            merged.append(ev)

    merged.sort(key=lambda x: x.get('date', ''))

    # Format into index.html
    updated_json = json.dumps(merged, indent=6)
    new_html = html[:match.start(1)] + updated_json + html[match.end(1):]

    with open(INDEX_PATH, 'w', encoding='utf-8') as f:
        f.write(new_html)

    print(f"Success: Updated index.html with {len(merged)} active events starting from {today_str}.")

if __name__ == '__main__':
    purge_supabase_old_events()
    update_index()
