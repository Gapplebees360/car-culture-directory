import os
import re
import json
import datetime
import ast

# Establish current reference date (YYYY-MM-DD)
today = datetime.datetime.now(datetime.timezone.utc).date()
today_str = today.strftime('%Y-%m-%d')
INDEX_PATH = 'index.html'

def parse_js_array(js_str):
    """Parses standard JSON or JavaScript object array containing single quotes."""
    try:
        return json.loads(js_str)
    except json.JSONDecodeError:
        pass

    try:
        # Normalize JavaScript literals to Python-compatible literal syntax
        cleaned = re.sub(r'\btrue\b', 'True', js_str)
        cleaned = re.sub(r'\bfalse\b', 'False', cleaned)
        cleaned = re.sub(r'\bnull\b', 'None', cleaned)
        return ast.literal_eval(cleaned)
    except Exception as e:
        print(f"Parsing error: {e}")
        return None

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
    events = parse_js_array(raw_js)

    if events is None or not isinstance(events, list):
        print("Error: Failed to convert events array into a valid dataset list.")
        exit(1)

    # Purge events prior to current reference date
    valid_events = [e for e in events if isinstance(e, dict) and e.get('date', '') >= today_str]
    valid_events.sort(key=lambda x: x.get('date', ''))

    # Format array into strict JSON
    updated_json = json.dumps(valid_events, indent=6)
    new_html = html[:match.start(1)] + updated_json + html[match.end(1):]

    with open(INDEX_PATH, 'w', encoding='utf-8') as f:
        f.write(new_html)

    print(f"Success: Updated index.html with {len(valid_events)} active events on or after {today_str}.")

if __name__ == '__main__':
    update_index()
