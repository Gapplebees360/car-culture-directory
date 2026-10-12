import os
import re
import json
import datetime

# Get current UTC date string (YYYY-MM-DD)
today = datetime.datetime.now(datetime.timezone.utc).date()
today_str = today.strftime('%Y-%m-%d')
INDEX_PATH = 'index.html'

def update_index():
    if not os.path.exists(INDEX_PATH):
        print("index.html not found.")
        return

    with open(INDEX_PATH, 'r', encoding='utf-8') as f:
        html = f.read()

    match = re.search(r'let eventsData = (\[.*?\]);', html, re.DOTALL)
    if not match:
        print("Could not find eventsData array in index.html.")
        return

    events = json.loads(match.group(1))

    # Purge expired events prior to current date
    valid_events = [e for e in events if e.get('date', '') >= today_str]

    # Sort chronologically by date
    valid_events.sort(key=lambda x: x['date'])

    updated_json = json.dumps(valid_events, indent=6)
    new_html = html[:match.start(1)] + updated_json + html[match.end(1):]

    with open(INDEX_PATH, 'w', encoding='utf-8') as f:
        f.write(new_html)

    print(f"Updated index.html: Retained {len(valid_events)} upcoming events on or after {today_str}.")

if __name__ == '__main__':
    update_index()
