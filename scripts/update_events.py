import os
import re
import json
import sys
import datetime
import urllib.request
import urllib.parse
import hashlib

# Reference Date (UTC)
today = datetime.datetime.now(datetime.timezone.utc).date()
today_str = today.strftime('%Y-%m-%d')
current_year = today.year
INDEX_PATH = 'index.html'

SUPABASE_URL = "https://lswnpxeiagureogrlopy.supabase.co"
SUPABASE_ANON_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imxzd25weGVpYWd1cmVvZ3Jsb3B5Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3OTE3NjkwNDcsImV4cCI6MjEwNzM0NTA0N30.yg0B_yyMAgdM692J9s-HevvfaykqZoVV0a0AiS6mZ_s"

HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) USAAutoMeets/1.0'}

# ---------------------------------------------------------
# DIVERSE CATEGORY IMAGE POOLS
# ---------------------------------------------------------
CATEGORY_IMAGE_POOLS = {
    "Track / Drag": [
        "https://images.unsplash.com/photo-1568605117036-5fe5e7bab0b7?w=800&auto=format&fit=crop",
        "https://images.unsplash.com/photo-1541348263662-e082662d82da?w=800&auto=format&fit=crop",
        "https://images.unsplash.com/photo-1617814076367-b759c7d7e738?w=800&auto=format&fit=crop",
        "https://images.unsplash.com/photo-1544829099-b9a0c07fad1a?w=800&auto=format&fit=crop"
    ],
    "Cars & Coffee": [
        "https://images.unsplash.com/photo-1503376780353-7e6692767b70?w=800&auto=format&fit=crop",
        "https://images.unsplash.com/photo-1580273916550-e323be2ae537?w=800&auto=format&fit=crop",
        "https://images.unsplash.com/photo-1552519507-da3b142c6e3d?w=800&auto=format&fit=crop",
        "https://images.unsplash.com/photo-1618843479313-40f8afb4b4d8?w=800&auto=format&fit=crop"
    ],
    "Car Show": [
        "https://images.unsplash.com/photo-1511919884226-fd3cad34687c?w=800&auto=format&fit=crop",
        "https://images.unsplash.com/photo-1563720223185-11003d516935?w=800&auto=format&fit=crop",
        "https://images.unsplash.com/photo-1542282088-72c9c27ed0cd?w=800&auto=format&fit=crop",
        "https://images.unsplash.com/photo-1514316454349-750a7fd3da3a?w=800&auto=format&fit=crop"
    ],
    "Cruise Night": [
        "https://images.unsplash.com/photo-1492144534655-ae79c964c9d7?w=800&auto=format&fit=crop",
        "https://images.unsplash.com/photo-1517524008697-84bbe3c3fd98?w=800&auto=format&fit=crop",
        "https://images.unsplash.com/photo-1508974239320-0a029497e820?w=800&auto=format&fit=crop"
    ],
    "Pop-Up Meet": [
        "https://images.unsplash.com/photo-1542282088-72c9c27ed0cd?w=800&auto=format&fit=crop",
        "https://images.unsplash.com/photo-1519641471654-76ce0107ad1b?w=800&auto=format&fit=crop",
        "https://images.unsplash.com/photo-1568605117036-5fe5e7bab0b7?w=800&auto=format&fit=crop"
    ],
    "Autocross": [
        "https://images.unsplash.com/photo-1552519507-da3b142c6e3d?w=800&auto=format&fit=crop",
        "https://images.unsplash.com/photo-1541348263662-e082662d82da?w=800&auto=format&fit=crop"
    ]
}

DEFAULT_FALLBACK = "https://images.unsplash.com/photo-1511919884226-fd3cad34687c?w=800&auto=format&fit=crop"

SOFT_404_TERMS = [
    "page not found", "404 not found", "404 error", "page doesn't exist",
    "event not found", "no event found", "this domain is for sale",
    "buy this domain", "hugedomains", "godaddy", "sedo", "domain expired",
    "event has passed", "sorry, the page", "error 404"
]

NON_EVENT_KEYWORDS = [
    "announced", "announcement", "dates", "schedule", "membership",
    "season pass", "banquet", "meeting", "officials", "board",
    "rules", "points", "registration open", "info only", "placeholder",
    "tbd", "postponed", "cancelled", "canceled"
]

CHECKED_URL_CACHE = {}

# ---------------------------------------------------------
# 1. ANNOUNCEMENT, STALE YEAR & DATE VALIDATION FILTERS
# ---------------------------------------------------------
def is_non_event_listing(title, description=""):
    text = f"{title} {description}".lower()
    for kw in NON_EVENT_KEYWORDS:
        if re.search(r'\b' + re.escape(kw) + r'\b', text):
            return True
    return False

def is_stale_year_title(title):
    if not title:
        return False
    title_str = str(title)
    for yr in range(2015, current_year):
        if re.search(r'\b' + str(yr) + r'\b', title_str):
            return True
    return False

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

    title = event_dict.get('title', '')
    desc = event_dict.get('description', '')
    date_str = normalize_date(event_dict.get('date'))

    if not date_str or date_str < today_str:
        return False

    try:
        yr = int(date_str[:4])
        if yr < current_year:
            return False
    except ValueError:
        return False

    if is_stale_year_title(title):
        return False

    if is_non_event_listing(title, desc):
        return False

    return True

def get_varied_category_image(category, title_seed):
    pool = CATEGORY_IMAGE_POOLS.get(category, [DEFAULT_FALLBACK])
    hash_val = int(hashlib.md5(title_seed.encode('utf-8')).hexdigest(), 16)
    return pool[hash_val % len(pool)]

def get_root_domain(url):
    try:
        netloc = urllib.parse.urlparse(url).netloc.lower()
        netloc = re.sub(r'^www\.', '', netloc)
        parts = netloc.split('.')
        if len(parts) >= 2:
            return parts[-2]
        return netloc
    except Exception:
        return ""

def generate_fallback_search(title, venue, city, state):
    clean_query = f"{title} {venue} {city} {state}".strip()
    encoded = urllib.parse.quote(clean_query)
    return f"https://www.google.com/search?q={encoded}"

def verify_and_audit_url(url, title="", venue="", city="", state=""):
    fallback_url = generate_fallback_search(title, venue, city, state)
    if not url or url == '#' or 'google.com/search' in url:
        return fallback_url
    
    if url in CHECKED_URL_CACHE:
        return CHECKED_URL_CACHE[url]

    orig_domain = get_root_domain(url)

    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=5) as resp:
            final_url = resp.geturl()
            final_domain = get_root_domain(final_url)
            
            allowed_social = {'facebook', 'instagram', 'linktr', 'youtube', 'google'}
            if orig_domain and final_domain and orig_domain != final_domain:
                if final_domain not in allowed_social and orig_domain not in allowed_social:
                    CHECKED_URL_CACHE[url] = fallback_url
                    return fallback_url

            orig_path_depth = len([p for p in urllib.parse.urlparse(url).path.split('/') if p])
            final_path_depth = len([p for p in urllib.parse.urlparse(final_url).path.split('/') if p])
            if orig_path_depth > 0 and final_path_depth == 0:
                CHECKED_URL_CACHE[url] = fallback_url
                return fallback_url

            html_chunk = resp.read(30720).decode('utf-8', errors='ignore').lower()
            for term in SOFT_404_TERMS:
                if term in html_chunk:
                    CHECKED_URL_CACHE[url] = fallback_url
                    return fallback_url

            CHECKED_URL_CACHE[url] = final_url
            return final_url

    except Exception:
        CHECKED_URL_CACHE[url] = fallback_url
        return fallback_url

def resolve_bremerton_pdf_url():
    fallback_url = "https://www.facebook.com/BremertonRaceway/"
    try:
        url = "https://bremertonraceway.com/"
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=5) as resp:
            html = resp.read().decode('utf-8', errors='ignore')
            match = re.search(r'href=["\'](/files/[^"\']+\.pdf|https?://[^"\']+\.pdf)["\']', html, re.IGNORECASE)
            if match:
                pdf_path = match.group(1)
                return f"https://bremertonraceway.com{pdf_path}" if pdf_path.startswith('/') else pdf_path
    except Exception as e:
        print(f"Notice: Bremerton PDF lookup note: {e}")
    return fallback_url

# ---------------------------------------------------------
# 2. FUZZY DEDUPLICATION ENGINE
# ---------------------------------------------------------
NOISE_WORDS = {'and', 'the', 'at', 'in', 'of', 'for', '2026', '2027', 'annual', 'weekly', 'monthly', 'show', 'meet', 'car', 'cars', 'meetup'}

def tokenize_title(title):
    clean = re.sub(r'[^a-z0-9\s]', '', str(title or '').lower())
    tokens = set(clean.split())
    return tokens - NOISE_WORDS

def is_fuzzy_duplicate(ev1, ev2):
    d1 = normalize_date(ev1.get('date'))
    d2 = normalize_date(ev2.get('date'))
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
# 3. MOTORSPORTREG LIVE API WITH DYNAMIC PHOTO EXTRACTION
# ---------------------------------------------------------
NATIONAL_GRID_HUBS = [
    {"name": "Seattle / PNW North", "lat": "47.6062", "lon": "-122.3321"},
    {"name": "Portland / PNW South", "lat": "45.5152", "lon": "-122.6784"},
    {"name": "Spokane / Inland NW", "lat": "47.6588", "lon": "-117.4260"},
    {"name": "San Francisco / NorCal", "lat": "37.7749", "lon": "-122.4194"},
    {"name": "Los Angeles / SoCal", "lat": "34.0522", "lon": "-118.2437"},
    {"name": "Phoenix / Southwest", "lat": "33.4484", "lon": "-112.0740"},
    {"name": "Denver / Rockies", "lat": "39.7392", "lon": "-104.9903"},
    {"name": "Dallas / North Texas", "lat": "32.7767", "lon": "-96.7970"},
    {"name": "Houston / Gulf Coast", "lat": "29.7604", "lon": "-95.3698"},
    {"name": "Chicago / Great Lakes", "lat": "41.8781", "lon": "-87.6298"},
    {"name": "Indianapolis / Heartland", "lat": "39.7684", "lon": "-86.1581"},
    {"name": "Detroit / Motor City", "lat": "42.3314", "lon": "-83.0458"},
    {"name": "Atlanta / Deep South", "lat": "33.7490", "lon": "-84.3880"},
    {"name": "Orlando / Central Florida", "lat": "28.5383", "lon": "-81.3792"},
    {"name": "New York / Northeast Hub", "lat": "40.7128", "lon": "-74.0060"}
]

def extract_live_msr_image(item, category, title):
    candidate_urls = [
        item.get('imageUrl'), item.get('image'), item.get('photo'),
        item.get('avatarUrl'), item.get('logoUrl')
    ]
    venue = item.get('venue') or {}
    candidate_urls.extend([venue.get('imageUrl'), venue.get('logoUrl')])

    for candidate in candidate_urls:
        if candidate and isinstance(candidate, str) and candidate.startswith('http'):
            return candidate

    return get_varied_category_image(category, title)

def fetch_multi_hub_msr_events():
    events = []
    seen_ids = set()

    for hub in NATIONAL_GRID_HUBS:
        url = f"https://api.motorsportreg.com/rest/events.json?country=USA&latitude={hub['lat']}&longitude={hub['lon']}&radius=350"
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
                    desc = str(item.get('type') or '')
                    raw_start = str(item.get('start') or '')[:10]
                    start_date = normalize_date(raw_start)

                    candidate = {
                        "title": title,
                        "description": desc,
                        "date": start_date
                    }

                    if not is_valid_future_event(candidate):
                        continue

                    venue = item.get('venue') or {}
                    state = str(venue.get('state') or 'WA')[:2].upper()
                    city = str(venue.get('city') or 'Regional')
                    venue_name = str(venue.get('name') or 'Motorsports Park')[:80]
                    
                    raw_url = str(item.get('detailurl') or item.get('uri') or item.get('url') or 'https://www.motorsportreg.com/calendar/')
                    valid_url = verify_and_audit_url(raw_url, title, venue_name, city, state)

                    category = "Track / Drag" if any(w in title.lower() for w in ["drag", "track", "autocross", "lapping", "race", "school", "kart"]) else "Car Show"
                    image_url = extract_live_msr_image(item, category, title)

                    events.append({
                        "title": title,
                        "state": state,
                        "city": city,
                        "venue": venue_name,
                        "category": category,
                        "date": start_date,
                        "time": "08:00 AM - 05:00 PM",
                        "description": desc or 'Official Motorsports & Track gathering via MotorsportReg.',
                        "url": valid_url,
                        "image": image_url
                    })
        except Exception as e:
            print(f"Notice: Grid fetch note ({hub['name']}): {e}")

    print(f"Success: Extracted {len(events)} MotorsportReg web events.")
    return events

# ---------------------------------------------------------
# 4. RECURRENCE & SEASONALITY ROLLING SCHEDULE ENGINE
# ---------------------------------------------------------
def is_date_valid_for_recurrence(dt, target_weekday, recurrence, active_months):
    start_m, end_m = active_months
    if start_m <= end_m:
        if not (start_m <= dt.month <= end_m):
            return False
    else:
        if not (dt.month >= start_m or dt.month <= end_m):
            return False

    if dt.weekday() != target_weekday:
        return False

    day_of_month = dt.day
    if recurrence == "weekly":
        return True
    elif recurrence == "1st_week":
        return 1 <= day_of_month <= 7
    elif recurrence == "2nd_week":
        return 8 <= day_of_month <= 14
    elif recurrence == "3rd_week":
        return 15 <= day_of_month <= 21
    elif recurrence == "4th_week":
        return 22 <= day_of_month <= 28
    elif recurrence == "biweekly":
        return dt.isocalendar()[1] % 2 == 0

    return True

def generate_365_day_50_state_schedule():
    events = []
    bremerton_url = resolve_bremerton_pdf_url()

    state_templates = [
        # --- WASHINGTON STATE ---
        ("Pacific Raceways Friday Night Drag & Tune", "WA", "Kent", "Pacific Raceways", "Track / Drag", "04:00 PM - 10:00 PM", "Quarter-mile street legal drag test & tune session.", "https://pacificraceways.com/drag-racing/", 4, "weekly", (4, 10)),
        ("ProFormance Racing School Track Day", "WA", "Kent", "Pacific Raceways", "Track / Drag", "08:00 AM - 05:00 PM", "High Performance Driving Course and open lapping day.", "https://proformanceracingschool.com", 4, "weekly", (4, 10)),
        ("Bremerton Raceway Sportsman Drags", "WA", "Bremerton", "8800 SW Imperial Way", "Track / Drag", "08:00 AM - 05:00 PM", "Bracket drag racing at Bremerton Airport.", bremerton_url, 5, "weekly", (4, 10)),
        ("The Ridge Motorsports Park Open Lapping & Track Day", "WA", "Shelton", "1051 SE Ridge World Way", "Track / Drag", "08:00 AM - 05:00 PM", "High performance sports car open track lapping.", "https://ridgemotorsportspark.com", 5, "weekly", (4, 10)),
        ("Evergreen Speedway Saturday Championship Racing", "WA", "Monroe", "14405 179th Ave SE", "Track / Drag", "04:00 PM - 10:00 PM", "NASCAR regional oval racing and drift events.", "https://evergreenspeedway.com", 5, "weekly", (4, 10)),
        ("Toutle Riverdale Raceway Off-Road & MX Practice", "WA", "Toutle", "Riverdale Raceway", "Track / Drag", "09:00 AM - 04:00 PM", "Motocross and off-road practice day.", "https://www.facebook.com/RiverdaleRacewayToutle/", 5, "weekly", (4, 10)),
        ("Spokane County Raceway Drag & Drift Night", "WA", "Airway Heights", "750 N Hayford Rd", "Track / Drag", "06:00 PM - 11:00 PM", "Open quarter-mile drag testing and drift pad.", "https://www.facebook.com/SpokaneCountyRaceway/", 4, "weekly", (5, 9)),
        ("Griot's Garage Tacoma Caffeine & Gasoline", "WA", "Tacoma", "3333 S 38th St", "Cars & Coffee", "08:00 AM - 10:00 AM", "Flagship store cars & coffee with free coffee.", "https://griotsgarage.com", 5, "1st_week", (4, 10)),
        ("Centralia Historic Downtown Cruise-In", "WA", "Centralia", "Tower Ave & Main St", "Cruise Night", "05:00 PM - 08:00 PM", "Classic muscle cars, hot rods, and local street cruisers.", "https://www.facebook.com/CentraliaMainStreet/", 5, "3rd_week", (5, 9)),
        ("Lacey Capital Mall Saturday Pop-Up", "WA", "Lacey", "600 Sleater Kinney Rd SE", "Pop-Up Meet", "06:00 PM - 09:00 PM", "Late night weekend car community pop-up.", "https://capitalmall-wa.com", 5, "biweekly", (4, 10)),

        # --- OTHER US STATES ---
        ("Portland International Raceway Late Night Drags", "OR", "Portland", "1940 N Victory Blvd", "Track / Drag", "06:00 PM - 11:00 PM", "Street legal drag racing under the lights at PIR.", "https://portlandraceway.com", 4, "weekly", (4, 10)),
        ("Woodburn Dragstrip Friday Night Late Night", "OR", "Woodburn", "7730 HWY 219", "Track / Drag", "04:00 PM - 09:30 PM", "Pacific Northwest street legal drag testing.", "https://woodburndragstrip.com", 4, "weekly", (4, 10)),
        ("In-N-Out Pomona Dragstrip Street Legal Night", "CA", "Pomona", "2780 E Fairplex Dr", "Track / Drag", "05:00 PM - 10:00 PM", "SoCal street legal drag racing under the lights.", "https://www.nhra.com/in-n-out-pomona-dragstrip", 4, "biweekly", (1, 12)),
        ("Sonoma Raceway Wednesday Night Drags", "CA", "Pleasanton", "29355 Arnold Dr", "Track / Drag", "04:00 PM - 09:30 PM", "NorCal quarter-mile street car drag racing.", "https://sonomaraceway.com", 4, "weekly", (3, 11)),
        ("Firebird Motorsports Park Friday Night Drag", "AZ", "Chandler", "20000 S Maricopa Rd", "Track / Drag", "06:00 PM - 11:00 PM", "Open test & tune for street cars and slicks.", "https://racefirebird.com", 4, "weekly", (1, 12)),
        ("Las Vegas Motor Speedway Midnight Mayhem", "NV", "Las Vegas", "7000 N Las Vegas Blvd", "Track / Drag", "08:00 PM - 01:00 AM", "Street-legal drag racing alternative on the Strip.", "https://lvms.com", 4, "biweekly", (1, 12)),
        ("Circuit of the Americas COTA Cars & Coffee", "TX", "Austin", "9201 Circuit of the Americas Blvd", "Cars & Coffee", "08:00 AM - 12:00 PM", "Central Texas monthly automotive showcase.", "https://circuitoftheamericas.com", 6, "3rd_week", (1, 12)),
        ("Lucas Oil Indianapolis Raceway Park Drags", "IN", "Indianapolis", "10267 E US HWY 136", "Track / Drag", "05:00 PM - 10:00 PM", "Wild Wednesday / Friday street drag testing.", "https://raceirp.com", 4, "weekly", (4, 10)),
        ("Milan Dragway Friday Test & Tune", "MI", "Milan", "10860 Plank Rd", "Track / Drag", "04:00 PM - 10:00 PM", "Michigan quarter-mile drag racing test session.", "https://milandragway.com", 4, "weekly", (4, 10)),
        ("Summit Motorsports Park Friday Test & Tune", "OH", "Norwalk", "1300 St Rte 18", "Track / Drag", "04:00 PM - 09:30 PM", "Quarter-mile drag racing under full lights.", "https://summitmotorsportspark.com", 4, "weekly", (4, 10)),
        ("Orlando Speed World Midnight Drag & Drift", "FL", "Orlando", "19164 E Colonial Dr", "Track / Drag", "07:00 PM - 01:00 AM", "Late-night drag strip testing and drift pad.", "https://raceosw.com", 4, "weekly", (1, 12)),
        ("Caffeine & Octane Atlanta", "GA", "Atlanta", "Town Center at Cobb", "Cars & Coffee", "08:00 AM - 12:00 PM", "North America's largest monthly car show.", "https://www.caffeineandoctane.com", 6, "1st_week", (1, 12)),
        ("Maryland International Raceway Midnight Madness", "MD", "Budds Creek", "27861 Budds Creek Rd", "Track / Drag", "06:00 PM - 12:00 AM", "Quarter-mile drag racing and street fights.", "https://mirdrag.com", 4, "biweekly", (4, 11)),
        ("Alabama International Dragway Street Legal Night", "AL", "Steele", "1245 Dragstrip Rd", "Track / Drag", "05:00 PM - 10:00 PM", "Friday night street legal drag racing test & tune.", "https://www.alabamainternationaldragway.com", 4, "weekly", (3, 11))
    ]

    for day_offset in range(365):
        eval_date = today + datetime.timedelta(days=day_offset)
        eval_date_str = eval_date.strftime('%Y-%m-%d')
        
        if eval_date_str < today_str:
            continue

        for title, state, city, venue, cat, time_str, desc, raw_url, target_day, recurrence, active_months in state_templates:
            if is_date_valid_for_recurrence(eval_date, target_day, recurrence, active_months):
                img_url = get_varied_category_image(cat, title)
                valid_url = verify_and_audit_url(raw_url, title, venue, city, state)
                
                events.append({
                    "title": title,
                    "state": state,
                    "city": city,
                    "venue": venue,
                    "category": cat,
                    "date": eval_date_str,
                    "time": time_str,
                    "description": desc,
                    "url": valid_url,
                    "image": img_url
                })

    return events

# ---------------------------------------------------------
# 5. SUPABASE SYNC & INDEX.HTML BUILDER
# ---------------------------------------------------------
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
            req = urllib.request.Request(url, data_json, headers=headers, method='POST')
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
    
    raw_combined = rolling_events + msr_events
    unique_events = deduplicate_events(raw_combined)

    push_to_supabase(unique_events)

    valid_existing = []
    for e in existing:
        if is_valid_future_event(e):
            e['date'] = normalize_date(e.get('date'))
            valid_existing.append(e)

    final_directory = deduplicate_events(valid_existing + unique_events)
    final_directory.sort(key=lambda x: str(x.get('date') or ''))

    updated_json = json.dumps(final_directory, indent=6)
    new_html = html[:match.start(1)] + updated_json + html[match.end(1):]

    with open(INDEX_PATH, 'w', encoding='utf-8') as f:
        f.write(new_html)

    print(f"Success: Directory updated with {len(final_directory)} unique events.")

if __name__ == '__main__':
    try:
        purge_old_supabase_events()
        update_index()
    except Exception as err:
        print(f"Notice: Workflow step recovered from warning: {err}")
    sys.exit(0)
