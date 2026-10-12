import os
import re
import json
import datetime
import urllib.request
import xml.etree.ElementTree as ET
import json5

# 1. Establish current reference date (YYYY-MM-DD)
today = datetime.datetime.now(datetime.timezone.utc).date()
today_str = today.strftime('%Y-%m-%d')
INDEX_PATH = 'index.html'

# Supabase REST Configuration
SUPABASE_URL = "https://lswnpxeiagureogrlopy.supabase.co"
SUPABASE_ANON_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imxzd25weGVpYWd1cmVvZ3Jsb3B5Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3OTE3NjkwNDcsImV4cCI6MjEwNzM0NTA0N30.yg0B_yyMAgdM692J9s-HevvfaykqZoVV0a0AiS6mZ_s"

def fetch_external_motorsports_events():
    """Fetches real upcoming automotive events from public RSS and JSON directory feeds"""
    fetched_events = []
    
    # Public motorsports and track event RSS feed endpoint
    rss_sources = [
        "https://www.motorsportreg.com/index.cfm/event/rss"
    ]

    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) USAAutoMeets/1.0'}

    for feed_url in rss_sources:
        try:
            req = urllib.request.Request(feed_url, headers=headers)
            with urllib.request.urlopen(req, timeout=10) as response:
                xml_data = response.read()
                root = ET.fromstring(xml_data)

                for item in root.findall('.//item'):
                    title = item.find('title').text if item.find('title') is not None else ''
                    desc = item.find('description').text if item.find('description') is not None else ''
                    link = item.find('link').text if item.find('link') is not None else ''
                    
                    # Parse location and state regex patterns from feed title/desc
                    state_match = re.search(r'\b([A-Z]{2})\b', title)
                    state = state_match.group(1) if state_match else 'WA'

                    # Clean event date string
                    pub_date_node = item.find('pubDate')
                    if pub_date_node is not None:
                        try:
                            # Standard RSS date format parsing
                            dt = datetime.datetime.strptime(pub_date_node.text[:16], '%a, %d %b %Y')
                            ev_date = dt.strftime('%Y-%m-%d')
                        except Exception:
                            ev_date = (today + datetime.timedelta(days=7)).strftime('%Y-%m-%d')
                    else:
                        ev_date = today_str

                    if ev_date >= today_str:
                        fetched_events.append({
                            "id": f"feed-{len(fetched_events)+1}",
                            "title": title[:70],
                            "state": state,
                            "city": "Regional Venue",
                            "venue": "Motorsports Park / Track",
                            "category": "Track / Drag" if "drag" in title.lower() or "track" in title.lower() else "Car Show",
                            "date": ev_date,
                            "time": "08:00 AM - 04:00 PM",
                            "description": desc[:200] if desc else "Upcoming motorsports event and track day."
                        })
        except Exception as e:
            print(f"Notice: Source fetch skipped for {feed_url}: {e}")

    print(f"Successfully scraped {len(fetched_events)} external upcoming events.")
    return fetched_events

def purge_supabase_old_events():
    """Deletes past events from Supabase where date < today_str"""
    try:
        url = f"{SUPABASE_URL}/rest/v1/events?date=lt.{today_str}"
        req = urllib.request.Request(url, method='DELETE')
        req.add_header('apikey', SUPABASE_ANON_KEY)
        req.add_header('Authorization', f'Bearer {SUPABASE_ANON_KEY}')
        with urllib.request.urlopen(req) as response:
            print(f"Supabase purge completed: Status {response.status}")
    except Exception as e:
        print(f"Notice: Supabase purge skipped: {e}")

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

    # 1. Retain valid static events
    valid_existing = [e for e in existing_events if isinstance(e, dict) and e.get('date', '') >= today_str]
    
    # 2. Fetch fresh external events
    scraped_events = fetch_external_motorsports_events()

    # 3. Merge & Deduplicate by Title + Date + State
    merged = []
    seen = set()

    for ev in valid_existing + scraped_events:
        key = f"{ev.get('title')}_{ev.get('date')}_{ev.get('state')}".lower()
        if key not in seen:
            seen.add(key)
            merged.append(ev)

    merged.sort(key=lambda x: x.get('date', ''))

    updated_json = json.dumps(merged, indent=6)
    new_html = html[:match.start(1)] + updated_json + html[match.end(1):]

    with open(INDEX_PATH, 'w', encoding='utf-8') as f:
        f.write(new_html)

    print(f"Success: Updated index.html with {len(merged)} active events starting from {today_str}.")

if __name__ == '__main__':
    purge_supabase_old_events()
    update_index()
