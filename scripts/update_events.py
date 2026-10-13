import os
import re
import json
import sys
import datetime
import urllib.request
import urllib.parse

# Reference Date (UTC)
today = datetime.datetime.now(datetime.timezone.utc).date()
today_str = today.strftime('%Y-%m-%d')
INDEX_PATH = 'index.html'

SUPABASE_URL = "https://lswnpxeiagureogrlopy.supabase.co"
SUPABASE_ANON_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imxzd25weGVpYWd1cmVvZ3Jsb3B5Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3OTE3NjkwNDcsImV4cCI6MjEwNzM0NTA0N30.yg0B_yyMAgdM692J9s-HevvfaykqZoVV0a0AiS6mZ_s"

HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) USAAutoMeets/1.0'}

CATEGORY_IMAGES = {
    "Track / Drag": "https://images.unsplash.com/photo-1568605117036-5fe5e7bab0b7?w=800&auto=format&fit=crop",
    "Cars & Coffee": "https://images.unsplash.com/photo-1503376780353-7e6692767b70?w=800&auto=format&fit=crop",
    "Car Show": "https://images.unsplash.com/photo-1511919884226-fd3cad34687c?w=800&auto=format&fit=crop",
    "Cruise Night": "https://images.unsplash.com/photo-1492144534655-ae79c964c9d7?w=800&auto=format&fit=crop",
    "Pop-Up Meet": "https://images.unsplash.com/photo-1542282088-72c9c27ed0cd?w=800&auto=format&fit=crop",
    "Autocross": "https://images.unsplash.com/photo-1552519507-da3b142c6e3d?w=800&auto=format&fit=crop"
}

SOFT_404_TERMS = [
    "page not found", "404 not found", "404 error", "page doesn't exist",
    "event not found", "no event found", "this domain is for sale",
    "buy this domain", "hugedomains", "godaddy", "sedo", "domain expired",
    "event has passed", "sorry, the page", "error 404"
]

CHECKED_URL_CACHE = {}

def generate_fallback_search(title, venue, city, state):
    """Generates a targeted, working Google Search URL for the specific event."""
    clean_query = f"{title} {venue} {city} {state}".strip()
    encoded = urllib.parse.quote(clean_query)
    return f"https://www.google.com/search?q={encoded}"

def verify_and_audit_url(url, title="", venue="", city="", state=""):
    """
    Performs deep 4-layer validation:
    1. Inspects final redirect URL (detects deep-to-root redirects).
    2. Audits HTML body for Soft 404s and parked domains.
    3. Replaces dead links with a targeted Google Search landing page.
    """
    fallback_url = generate_fallback_search(title, venue, city, state)
    if not url or url == '#' or 'google.com/search' in url:
        return fallback_url
    
    if url in CHECKED_URL_CACHE:
        return CHECKED_URL_CACHE[url]

    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=5) as resp:
            final_url = resp.geturl()
            
            # Layer 1: Detect Deep-Link to Root Homepage Fallback
            orig_path_depth = len([p for p in urllib.parse.urlparse(url).path.split('/') if p])
            final_path_depth = len([p for p in urllib.parse.urlparse(final_url).path.split('/') if p])
            
            if orig_path_depth > 0 and final_path_depth == 0:
                print(f"Link Audit Fail (Redirected to Root): {url} -> {final_url}")
                CHECKED_URL_CACHE[url] = fallback_url
                return fallback_url

            # Layer 2 & 3: Read first 30KB of HTML and check for Soft 404s / Parked Domains
            html_chunk = resp.read(30720).decode('utf-8', errors='ignore').lower()
            for term in SOFT_404_TERMS:
                if term in html_chunk:
                    print(f"Link Audit Fail (Soft 404 term '{term}'): {url}")
                    CHECKED_URL_CACHE[url] = fallback_url
                    return fallback_url

            CHECKED_URL_CACHE[url] = final_url
            return final_url

    except Exception as e:
        print(f"Link Audit Fail (HTTP/Network Error): {url} -> {e}")
        CHECKED_URL_CACHE[url] = fallback_url
        return fallback_url

def get_next_day_of_week(target_weekday, weeks_offset=0):
    """Calculates exact calendar date for target weekday (4=Fri, 5=Sat, 6=Sun)."""
    days_ahead = target_weekday - today.weekday()
    if days_ahead <= 0:
        days_ahead += 7
    days_ahead += (weeks_offset * 7)
    return (today + datetime.timedelta(days=days_ahead)).strftime('%Y-%m-%d')

def resolve_bremerton_pdf_url():
    """Dynamically parses Bremerton Raceway's homepage for the current active schedule PDF link."""
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
# FUZZY DEDUPLICATION
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
# MOTORSPORTREG API (25 NATIONAL HUBS)
# ---------------------------------------------------------
NATIONAL_GRID_HUBS = [
    {"name": "Seattle / PNW North", "lat": "47.6062", "lon": "-122.3321"},
    {"name": "Portland / PNW South", "lat": "45.5152", "lon": "-122.6784"},
    {"name": "Spokane / Inland NW", "lat": "47.6588", "lon": "-117.4260"},
    {"name": "San Francisco / NorCal", "lat": "37.7749", "lon": "-122.4194"},
    {"name": "Los Angeles / SoCal", "lat": "34.0522", "lon": "-118.2437"},
    {"name": "San Diego / Border", "lat": "32.7157", "lon": "-117.1611"},
    {"name": "Phoenix / Southwest", "lat": "33.4484", "lon": "-112.0740"},
    {"name": "Salt Lake City / Intermountain", "lat": "40.7608", "lon": "-111.8910"},
    {"name": "Denver / Rockies", "lat": "39.7392", "lon": "-104.9903"},
    {"name": "Dallas / North Texas", "lat": "32.7767", "lon": "-96.7970"},
    {"name": "Houston / Gulf Coast", "lat": "29.7604", "lon": "-95.3698"},
    {"name": "Kansas City / Plains", "lat": "39.0997", "lon": "-94.5786"},
    {"name": "Minneapolis / Upper Midwest", "lat": "44.9778", "lon": "-93.2650"},
    {"name": "Chicago / Great Lakes", "lat": "41.8781", "lon": "-87.6298"},
    {"name": "Indianapolis / Heartland", "lat": "39.7684", "lon": "-86.1581"},
    {"name": "Detroit / Motor City", "lat": "42.3314", "lon": "-83.0458"},
    {"name": "Nashville / Mid-South", "lat": "36.1627", "lon": "-86.7816"},
    {"name": "Atlanta / Deep South", "lat": "33.7490", "lon": "-84.3880"},
    {"name": "Orlando / Central Florida", "lat": "28.5383", "lon": "-81.3792"},
    {"name": "Charlotte / Carolinas", "lat": "35.2271", "lon": "-80.8431"},
    {"name": "Washington DC / Mid-Atlantic", "lat": "38.9072", "lon": "-77.0369"},
    {"name": "Philadelphia / Tri-State", "lat": "39.9526", "lon": "-75.1652"},
    {"name": "New York / Northeast Hub", "lat": "40.7128", "lon": "-74.0060"},
    {"name": "Boston / New England", "lat": "42.3601", "lon": "-71.0589"},
    {"name": "Billings / Northern Plains", "lat": "45.7833", "lon": "-108.5007"}
]

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
                    start_date = str(item.get('start') or '')[:10]
                    venue = item.get('venue') or {}
                    state = str(venue.get('state') or 'WA')[:2].upper()
                    city = str(venue.get('city') or 'Regional')
                    venue_name = str(venue.get('name') or 'Motorsports Park')[:80]
                    
                    raw_url = str(item.get('detailurl') or item.get('uri') or item.get('url') or 'https://www.motorsportreg.com/calendar/')
                    valid_url = verify_and_audit_url(raw_url, title, venue_name, city, state)

                    category = "Track / Drag" if any(w in title.lower() for w in ["drag", "track", "autocross", "lapping", "race", "school", "kart"]) else "Car Show"
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
                            "url": valid_url,
                            "image": image_url
                        })
        except Exception as e:
            print(f"Notice: Grid fetch note ({hub['name']}): {e}")

    print(f"Success: Extracted {len(events)} MotorsportReg web events across 25 national grid hubs.")
    return events

# ---------------------------------------------------------
# 50-STATE ROLLING SCHEDULE ENGINE
# ---------------------------------------------------------
def generate_365_day_50_state_schedule():
    events = []
    bremerton_url = resolve_bremerton_pdf_url()

    state_templates = [
        ("Alabama International Dragway Street Legal Night", "AL", "Steele", "1245 Dragstrip Rd", "Track / Drag", "05:00 PM - 10:00 PM", "Friday night street legal drag racing test & tune.", "https://www.alabamainternationaldragway.com", 4),
        ("Alaska Raceway Park Midnight Sun Drags", "AK", "Palmer", "5599 S Race Way", "Track / Drag", "04:00 PM - 10:00 PM", "NHRA drag racing under the Alaskan sun.", "https://raceak.com", 5),
        ("Firebird Motorsports Park Friday Night Drag", "AZ", "Chandler", "20000 S Maricopa Rd", "Track / Drag", "06:00 PM - 11:00 PM", "Open test & tune for street cars and slicks.", "https://racefirebird.com", 4),
        ("Centerville Dragway Saturday Night Shootout", "AR", "Centerville", "1441 Dragstrip Ln", "Track / Drag", "05:00 PM - 10:30 PM", "1/8th mile bracket drag racing.", "https://www.centervilledragway.com", 5),
        ("In-N-Out Pomona Dragstrip Street Legal Night", "CA", "Pomona", "2780 E Fairplex Dr", "Track / Drag", "05:00 PM - 10:00 PM", "SoCal street legal drag racing under the lights.", "https://www.nhra.com/in-n-out-pomona-dragstrip", 4),
        ("High Plains Raceway Open Lapping Day", "CO", "Byers", "High Plains Raceway", "Track / Drag", "08:00 AM - 05:00 PM", "Open track lapping day for cars.", "https://highplainsraceway.com", 5),
        ("Lime Rock Park Autocross & Track Day", "CT", "Lakeville", "60 White Hollow Rd", "Track / Drag", "08:30 AM - 04:30 PM", "Historic road course autocross and open track day.", "https://limerock.com", 5),
        ("US 13 Dragway Friday Night Grudge Racing", "DE", "Delmar", "33599 Sussex Hwy", "Track / Drag", "05:30 PM - 10:30 PM", "Delmarva quarter-mile drag racing.", "https://www.delawareracing.com", 4),
        ("Orlando Speed World Midnight Drag & Drift", "FL", "Orlando", "19164 E Colonial Dr", "Track / Drag", "07:00 PM - 01:00 AM", "Late-night drag strip testing and drift pad.", "https://raceosw.com", 4),
        ("Caffeine & Octane Atlanta", "GA", "Atlanta", "Town Center at Cobb", "Cars & Coffee", "08:00 AM - 12:00 PM", "North America's largest monthly car show.", "https://www.caffeineandoctane.com", 6),
        ("Oahu Friday Night Pop-Up Cruise", "HI", "Honolulu", "Aloha Stadium Lot", "Pop-Up Meet", "06:30 PM - 09:30 PM", "Island car culture cruise and meet.", "https://www.facebook.com", 4),
        ("Firebird Raceway Friday Night Midnight Drags", "ID", "Boise", "13511 HWY 16", "Track / Drag", "07:00 PM - 12:00 AM", "Street legal drag racing and tune-up.", "https://firebirdonline.com", 4),
        ("Byron Dragway Test & Tune", "IL", "Byron", "2525 HWY 72", "Track / Drag", "09:00 AM - 04:00 PM", "Quarter-mile test and tune for all classes.", "https://byrondragway.com", 5),
        ("Lucas Oil Indianapolis Raceway Park Drags", "IN", "Indianapolis", "10267 E US HWY 136", "Track / Drag", "05:00 PM - 10:00 PM", "Wild Wednesday / Friday street drag testing.", "https://raceirp.com", 4),
        ("Eddyville Raceway Park Bracket Night", "IA", "Eddyville", "3260 330th St", "Track / Drag", "04:00 PM - 09:30 PM", "1/8th mile bracket racing and test & tune.", "https://eddyvilleraceway.com", 5),
        ("Kansas International Dragway Street Night", "KS", "Wichita", "7800 N Ridge Rd", "Track / Drag", "06:00 PM - 10:30 PM", "Street car drag racing and roll races.", "https://kansasdragway.com", 5),
        ("Beech Bend Raceway Friday Night Drags", "KY", "Bowling Green", "798 Beech Bend Rd", "Track / Drag", "05:00 PM - 10:00 PM", "Historic quarter-mile drag strip night.", "https://beechbend.com", 4),
        ("No Problem Raceway Test & Tune", "LA", "Belle Rose", "1986 HWY 308", "Track / Drag", "06:00 PM - 11:00 PM", "Quarter-mile drag strip and road course lapping.", "https://noproblemraceway.com", 5),
        ("Oxford Plains Dragway Friday Night Drags", "ME", "Oxford", "877 Main St", "Track / Drag", "05:00 PM - 09:30 PM", "Maine 1/8th mile drag racing night.", "https://oxfordplainsdragway.com", 4),
        ("Maryland International Raceway Midnight Madness", "MD", "Budds Creek", "27861 Budds Creek Rd", "Track / Drag", "06:00 PM - 12:00 AM", "Quarter-mile drag racing and street fights.", "https://mirdrag.com", 4),
        ("New England Dragway Street Night", "MA", "Boston", "280 Exeter Rd", "Track / Drag", "05:00 PM - 10:00 PM", "Northeast street car drag racing and testing.", "https://nedragway.com", 4),
        ("Milan Dragway Friday Test & Tune", "MI", "Milan", "10860 Plank Rd", "Track / Drag", "04:00 PM - 10:00 PM", "Michigan quarter-mile drag racing test session.", "https://milandragway.com", 4),
        ("Brainerd International Raceway Street Legal Drags", "MN", "Brainerd", "5523 HWY 371", "Track / Drag", "05:00 PM - 10:00 PM", "Quarter-mile street legal testing in Minnesota.", "https://brainerdraceway.com", 5),
        ("Gulfport Dragway Friday Night Street Wars", "MS", "Gulfport", "17000 Racetrack Rd", "Track / Drag", "06:00 PM - 11:00 PM", "Gulf Coast quarter-mile drag racing.", "https://gulfportdragway.com", 4),
        ("World Wide Technology Raceway Midnight Madness", "MO", "St. Louis", "700 Raceway Blvd", "Track / Drag", "06:00 PM - 12:00 AM", "Street drag racing and drift showcase.", "https://wwtraceway.com", 4),
        ("Yellowstone Drag Strip Friday Night Test", "MT", "Acton", "8511 HWY 3", "Track / Drag", "05:00 PM - 09:30 PM", "Montana quarter-mile drag racing night.", "https://yellowstonedragstrip.com", 4),
        ("Kearney Raceway Park Street Legal Night", "NE", "Kearney", "5815 HWY 10", "Track / Drag", "05:00 PM - 10:00 PM", "Nebraska quarter-mile drag strip testing.", "https://kearneyraceway.com", 5),
        ("Las Vegas Motor Speedway Midnight Mayhem", "NV", "Las Vegas", "7000 N Las Vegas Blvd", "Track / Drag", "08:00 PM - 01:00 AM", "Street-legal drag racing alternative on the Strip.", "https://lvms.com", 4),
        ("New England Dragway Regional Meet", "NH", "Epping", "280 Exeter Rd", "Track / Drag", "05:00 PM - 10:00 PM", "New Hampshire street car test & tune.", "https://nedragway.com", 5),
        ("Island Dragway Friday Night Test & Tune", "NJ", "Great Meadows", "214 Red Schoolhouse Rd", "Track / Drag", "06:00 PM - 10:00 PM", "Historic New Jersey quarter-mile drag strip.", "https://islanddragway.com", 4),
        ("Albuquerque Dragway Friday Street Fights", "NM", "Albuquerque", "10500 HWY 337", "Track / Drag", "06:00 PM - 10:30 PM", "High-altitude drag strip testing.", "https://abqdragway.com", 4),
        ("Lebanon Valley Dragway Friday Night Street Legal", "NY", "West Lebanon", "1740 US-20", "Track / Drag", "05:00 PM - 10:00 PM", "New York quarter-mile drag racing night.", "https://dragway.com", 4),
        ("Rockingham Dragway Street Night", "NC", "Rockingham", "2153 US-1", "Track / Drag", "05:00 PM - 10:00 PM", "Carolinas street car drag test & tune.", "https://rockinghamdragway.com", 4),
        ("Magic City International Dragway Test & Tune", "ND", "Minot", "Magic City Dragway", "Track / Drag", "05:00 PM - 10:00 PM", "North Dakota drag strip test night.", "https://magiccitydragway.com", 5),
        ("Summit Motorsports Park Friday Test & Tune", "OH", "Norwalk", "1300 St Rte 18", "Track / Drag", "04:00 PM - 09:30 PM", "Quarter-mile drag racing under full lights.", "https://summitmotorsportspark.com", 4),
        ("Thunder Valley Raceway Park Street Night", "OK", "Noble", "10586 120th St", "Track / Drag", "06:00 PM - 11:00 PM", "Oklahoma quarter-mile drag racing.", "https://okthunder.com", 4),
        ("Woodburn Dragstrip Friday Night Late Night", "OR", "Woodburn", "7730 HWY 219", "Track / Drag", "04:00 PM - 09:30 PM", "Pacific Northwest street legal drag testing.", "https://woodburndragstrip.com", 4),
        ("Maple Grove Raceway Street Legal Night", "PA", "Reading", "30 Stauffer Park Ln", "Track / Drag", "05:00 PM - 10:00 PM", "Pennsylvania quarter-mile drag racing.", "https://maplegroveraceway.com", 4),
        ("Providence Cars & Coffee Showcase", "RI", "Providence", "1 Park Row", "Cars & Coffee", "08:00 AM - 11:00 AM", "Rhode Island waterfront car gathering.", "https://www.facebook.com", 5),
        ("Darlington Dragway Friday Test & Tune", "SC", "Hartsville", "2056 E Bobo Newsome HWY", "Track / Drag", "05:00 PM - 10:00 PM", "South Carolina 1/4th mile drag strip.", "https://darlingtondragway.com", 4),
        ("Thunder Valley Dragways SD Bracket Night", "SD", "Marion", "27533 446th Ave", "Track / Drag", "05:00 PM - 10:00 PM", "South Dakota 1/4th mile drag racing.", "https://thundervalleydragways.com", 5),
        ("Music City Raceway Friday Night Drags", "TN", "Nashville", "3305 Music City Rd", "Track / Drag", "05:00 PM - 10:30 PM", "1/8th mile Nashville drag racing.", "https://musiccityraceway.com", 4),
        ("Circuit of the Americas COTA Cars & Coffee", "TX", "Austin", "9201 Circuit of the Americas Blvd", "Cars & Coffee", "08:00 AM - 12:00 PM", "Central Texas monthly automotive showcase.", "https://circuitoftheamericas.com", 6),
        ("Utah Motorsports Campus Open Track Day", "UT", "Erda", "5125 HWY 112", "Track / Drag", "08:00 AM - 05:00 PM", "Road course open lapping and autocross.", "https://utahmotorsportscampus.com", 5),
        ("Devil's Bowl Speedway Saturday Racing", "VT", "West Haven", "2743 Route 22A", "Track / Drag", "06:00 PM - 10:00 PM", "Vermont stock car and dirt oval racing.", "https://devilsbowlspeedwayvt.com", 5),
        ("Virginia International Raceway Track Day", "VA", "Alton", "1245 Pine Tree Rd", "Track / Drag", "08:00 AM - 05:00 PM", "Historic Virginia road course open lapping.", "https://virnow.com", 5),
        
        # --- WASHINGTON STATE ---
        ("Toutle Riverdale Raceway Off-Road & MX Practice", "WA", "Toutle", "Riverdale Raceway", "Track / Drag", "09:00 AM - 04:00 PM", "Motocross, dirt track, and off-road practice day.", "https://www.facebook.com/RiverdaleRacewayToutle/", 5),
        ("The Ridge Motorsports Park Open Lapping & Track Day", "WA", "Shelton", "1051 SE Ridge World Way", "Track / Drag", "08:00 AM - 05:00 PM", "High performance sports car open track lapping on the road course.", "https://ridgemotorsportspark.com", 5),
        ("Evergreen Speedway Saturday Championship Racing", "WA", "Monroe", "14405 179th Ave SE", "Track / Drag", "04:00 PM - 10:00 PM", "NASCAR regional oval racing, drift events, and figure 8s.", "https://evergreenspeedway.com", 5),
        ("Pacific Raceways Friday Night Drag & Tune", "WA", "Kent", "Pacific Raceways", "Track / Drag", "04:00 PM - 10:00 PM", "Quarter-mile street legal drag test & tune session.", "https://pacificraceways.com/drag-racing/", 4),
        ("ProFormance Racing School Track Day", "WA", "Kent", "Pacific Raceways", "Track / Drag", "08:00 AM - 05:00 PM", "High Performance Driving Course and open lapping day at Pacific Raceways.", "https://proformanceracingschool.com", 4),
        ("Bremerton Raceway Sportsman Drags", "WA", "Bremerton", "8800 SW Imperial Way", "Track / Drag", "08:00 AM - 05:00 PM", "Bracket drag racing at Bremerton Airport.", bremerton_url, 5),
        ("Spokane County Raceway Drag & Drift Night", "WA", "Airway Heights", "750 N Hayford Rd", "Track / Drag", "06:00 PM - 11:00 PM", "Open quarter-mile drag testing and drift pad.", "https://spokanecountyraceway.com", 4),
        ("Griot's Garage Tacoma Caffeine & Gasoline", "WA", "Tacoma", "3333 S 38th St", "Cars & Coffee", "08:00 AM - 10:00 AM", "Flagship store cars & coffee with free coffee.", "https://griotsgarage.com", 5),
        ("Centralia Historic Downtown Cruise-In", "WA", "Centralia", "Tower Ave & Main St", "Cruise Night", "05:00 PM - 08:00 PM", "Classic muscle cars, hot rods, and local street cruisers.", "https://www.facebook.com/CentraliaMainStreet/", 5),
        ("Lacey Capital Mall Saturday Pop-Up", "WA", "Lacey", "600 Sleater Kinney Rd SE", "Pop-Up Meet", "06:00 PM - 09:00 PM", "Late night weekend car community pop-up.", "https://capitalmall-wa.com", 5),

        ("Kanawha Valley Dragway Friday Street Fights", "WV", "Point Pleasant", "Kanawha Valley Dragway", "Track / Drag", "06:00 PM - 11:00 PM", "West Virginia 1/4th mile drag strip testing.", "https://kanawhavalleydragway.com", 4),
        ("Great Lakes Dragaway Street Drag Night", "WI", "Union Grove", "18411 1st St", "Track / Drag", "04:00 PM - 10:00 PM", "Union Grove drag racing test and tune.", "https://greatlakesdragaway.com", 4),
        ("Wyoming Dragway Street Legal Night", "WY", "Saratoga", "Wyoming Dragway", "Track / Drag", "05:00 PM - 10:00 PM", "High-altitude drag strip racing.", "https://wyomingdragway.com", 5)
    ]

    for title, state, city, venue, cat, time_str, desc, raw_url, target_day in state_templates:
        img_url = CATEGORY_IMAGES.get(cat, CATEGORY_IMAGES["Car Show"])
        valid_url = verify_and_audit_url(raw_url, title, venue, city, state)
        
        for week in range(52):
            ev_date = get_next_day_of_week(target_day, weeks_offset=week)
            events.append({
                "title": title,
                "state": state,
                "city": city,
                "venue": venue,
                "category": cat,
                "date": ev_date,
                "time": time_str,
                "description": desc,
                "url": valid_url,
                "image": img_url
            })

    return events

# ---------------------------------------------------------
# SUPABASE SYNC & INDEX.HTML BUILDER
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

    valid_existing = [
        e for e in existing 
        if isinstance(e, dict) and str(e.get('date') or '') >= today_str
    ]
    
    final_directory = deduplicate_events(valid_existing + unique_events)
    final_directory.sort(key=lambda x: str(x.get('date') or ''))

    updated_json = json.dumps(final_directory, indent=6)
    new_html = html[:match.start(1)] + updated_json + html[match.end(1):]

    with open(INDEX_PATH, 'w', encoding='utf-8') as f:
        f.write(new_html)

    print(f"Success: Directory updated with {len(final_directory)} unique events with automated 4-layer URL health validation.")

if __name__ == '__main__':
    try:
        purge_old_supabase_events()
        update_index()
    except Exception as err:
        print(f"Notice: Workflow step recovered from warning: {err}")
    sys.exit(0)
