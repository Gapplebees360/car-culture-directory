import re

path = "index.html"
with open(path, "r", encoding="utf-8") as f:
    html = f.read()

# Frontend card link HTML snippet using event object properties
link_js_snippet = '  <div class="event-card-link-container"><a href="${e.url || e.link || e.event_url || \'#\'}" target="_blank" rel="noopener noreferrer" class="event-source-link">View Original Event Listing &rarr;</a></div>\n'

if "View Original Event Listing" not in html:
    # Find where event cards are dynamically constructed in JS (e.g. innerHTML or template string)
    if 'class="event-card"' in html or "class='event-card'" in html:
        # Inject link container before closing tag of card div inside the template literal
        html = re.sub(r'(<div[^>]*class=["\']event-card["\'][^>]*>[\s\S]*?)(</div>)', r'\1' + link_js_snippet + r'\2', html, count=1)
    else:
        # Fallback: Find where card innerHTML ends in JS loop and append link
        html = html.replace('${e.location || \'\'}', '${e.location || \'\'}\n' + link_js_snippet)

    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    print("Successfully added origin link template to index.html!")
else:
    print("Origin link template already present in index.html.")
