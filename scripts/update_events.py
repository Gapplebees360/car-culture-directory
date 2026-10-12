import os
import re
import json
import datetime
import json5

# Current reference date (YYYY-MM-DD)
today = datetime.datetime.now(datetime.timezone.utc).date()
today_str = today.strftime('%Y-%m-%d')
INDEX_PATH = 'index.html'

def update_index():
    if not os.path.exists(INDEX_PATH):
        print(f"Error: {INDEX_PATH} not found in repository root.")
        exit(1)

    with open(INDEX_PATH, 'r', encoding='utf-8') as f:
        html = f.read()

    match = re.search(r'let eventsData = (\[[\s\S]*?\]);', html)
    if not match:
        print("Error: Could not locate 'let eventsData = [...]' in index.html.")
        exit(1)

    raw_js = match.group(1)
    
    try:
        # JSON5 parses JS object literals (unquoted keys, single quotes, etc.) effortlessly
        events = json5.loads(raw_js)
    except Exception as e:
        print(f"Error parsing eventsData with json5: {e}")
        exit(1)

    if not isinstance(events, list):
        print("Error: Parsed events data is not a valid list.")
        exit(1)

    # Purge past events prior to current reference date
    valid_events = [e for e in events if isinstance(e, dict) and e.get('date', '') >= today_str]
    valid_events.sort(key=lambda x: x.get('date', ''))

    # Format array back into strict JSON for index.html
    updated_json = json.dumps(valid_events, indent=6)
    new_html = html[:match.start(1)] + updated_json + html[match.end(1):]

    with open(INDEX_PATH, 'w', encoding='utf-8') as f:
        f.write(new_html)

    print(f"Success: Updated index.html with {len(valid_events)} active events on or after {today_str}.")

if __name__ == '__main__':
    update_index()
