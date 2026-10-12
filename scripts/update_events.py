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

# Curated High-Res Category Imagery
CATEGORY_IMAGES = {
    "Track / Drag": "https://images.unsplash.com/photo-1568605117036-5fe5e7bab0b7?w=800&auto=format&fit=crop",
    "Cars & Coffee": "https://images.unsplash.com/photo-1503376780353-7e6692767b70?w=800&auto=format&fit=crop",
    "Car Show": "https://images.unsplash.com/photo-1511919884226-fd3cad34687c?w=800&auto=format&fit=crop",
    "Cruise Night": "https://images.unsplash.com/photo-1492144534655-ae79c964c9d7?w=800&auto=format&fit=crop",
    "Pop-Up Meet": "https://images.unsplash.com/photo-1542282088-72c9c27ed0cd?w=800&auto=format&fit=crop",
    "Autocross": "https://images.unsplash.com/photo-1552519507-da3b142c6e3d?w=800&auto=format&fit=crop"
}

def days_ahead(n):
    return (today + datetime.timedelta(days=n)).strftime('%Y-%m-%d')

# ---------------------------------------------------------
# 1. INTELLIGENT FUZZY DEDUPLICATION ENGINE
# ---------------------------------------------------------
NOISE_WORDS = {'and', 'the', 'at', 'in', 'of', 'for', '2026', '2027', 'annual', 'weekly', 'monthly', 'show', 'meet', 'car', 'cars', 'meetup'}

def tokenize_title(title):
    clean = re.sub(r'[^a-z0-9\s]', '', str(title or '').lower())
    tokens = set(clean.split())
    return tokens - NOISE_WORDS

def is_fuzzy_duplicate(ev1, ev2):
    d1, d2 = str(ev1.get('date') or ''), str(ev2.get('date') or '')
    if not d1 or not d2 or d1 != d2:
        return False

    s1, s2 = str(ev1.get('state') or '').upper(), str(ev2.get('state') or '').upper()
    if s1 and s2 and s1 != s2:
        return False

    t1 = tokenize_title(ev1.get('title'))
    t2 = tokenize_title(ev2.get('title'))
    
    if not t1 or not t2:
        return False

    intersection = len(t1.intersection(t2))
    union = len(t1.union(t2))
    jaccard_score = intersection / union if union > 0 else 0

    if jaccard_score >= 0.45:
        return True

    v1 = re.sub(r'[^a-z0-9]', '', str(ev1.get('venue') or '').lower())
    v2 = re.sub(r'[^a-z0-9]', '', str(ev2.get('venue') or '').lower())
    if v1 and v2 and len(v1) > 6 and (v1 in v2 or v2 in v1):
        return True

    return False

def deduplicate_events(event_list):
    unique_list = []
    for incoming in event_list:
        duplicate_found = False
        for existing in unique_list:
            if is_fuzzy_duplicate(incoming, existing):
                duplicate_found = True
                if len(incoming.get('description', '')) > len(existing.get('description', '')):
                    existing['description'] = incoming['description']
                break
        if not duplicate_found:
            unique_list.append(incoming)
    return unique_list

# ---------------------------------------------------------
# 2. MOTORSPORTREG LIVE WEB API INGESTION
# ---------------------------------------------------------
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
                    
                    # Pull direct MotorsportReg event link
                    event_url = str(item.get('detailurl') or item.get('url') or 'https://www.motorsportreg.com')
                    
                    category = "Track / Drag" if any(w in title.lower() for w in ["drag", "track", "autocross", "lapping", "race"]) else "Car Show"
                    image_url = CATEGORY_IMAGES.get(category, CATEGORY_IMAGES["Track / Drag"])

                    if start_date and start_date >= today_str:
                        events.append({
                            "title": title,
                            "state": state,
                            "city": city,
                            "venue": venue_name,
                            "category": category,
                            "date": start_date,
                            "time": "08:00 AM - 05:00 PM",
                            "description": str(item.get('type') or 'Official Motorsports & Track gathering via MotorsportReg.'),
                            "url": event_url,
                            "image": image_url
                        })
        except Exception as e:
            print(f"Notice: Hub fetch note ({hub['name']}): {e}")

    print(f"Success: Extracted {len(events)} MotorsportReg web events across national hubs.")
    return events

# ---------------------------------------------------------
# 3. 50-STATE 365-DAY ROLLING SCHEDULE WITH TRACK LINKS
# ---------------------------------------------------------
def generate_365_day_50_state_schedule():
    events = []
    state_templates = [
        ("Alabama International Dragway Street Legal Night", "AL", "Steele", "1245 Dragstrip Rd", "Track / Drag", "05:00 PM - 10:00 PM", "Friday night street legal drag racing test & tune.", "https://www.alabamainternationaldragway.com"),
        ("Hoover Met Cars & Coffee", "AL", "Hoover", "Hoover Metropolitan Complex", "Cars & Coffee", "08:00 AM - 11:00 AM", "Monthly community gathering of muscle cars, hot rods, and exotics.", "https://hoovermetcomplex.com"),
        ("Alaska Raceway Park Midnight Sun Drags", "AK", "Palmer", "5599 S Race Way", "Track / Drag", "04:00 PM - 10:00 PM", "NHRA drag racing under the Alaskan sun.", "https://raceak.com"),
        ("Firebird Motorsports Park Friday Night Drag", "AZ", "Chandler", "20000 S Maricopa Rd", "Track / Drag", "06:00 PM - 11:00 PM", "Open test & tune for street cars and slicks.", "https://racefirebird.com"),
        ("Scottsdale Pavilion Rock 'N' Roll Car Show", "AZ", "Scottsdale", "9120 E Talking Stick Way", "Car Show", "04:00 PM - 08:00 PM", "Longest-running weekly car show in the U.S.", "https://thepaviilionsattalkingstick.com"),
        ("In-N-Out Pomona Dragstrip Street Legal Night", "CA", "Pomona", "2780 E Fairplex Dr", "Track / Drag", "05:00 PM - 10:00 PM", "SoCal street legal drag racing under the lights.", "
