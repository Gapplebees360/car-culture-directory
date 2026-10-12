import re

path = "scripts/update_events.py"
with open(path, "r", encoding="utf-8") as f:
    code = f.read()

link_code = '  <p><a href="{event.get(\'url\') or event.get(\'link\') or \'#\'}" target="_blank" rel="noopener noreferrer" class="event-link">View Original Event Listing &rarr;</a></p>\n'

if "View Original Event Listing" not in code:
    if 'class="event-card"' in code or "class='event-card'" in code:
        code = re.sub(r'(<div[^>]*class=["\']event-card["\'][^>]*>[\s\S]*?)(</div>)', r'\1' + link_code + r'\2', code, count=1)
    else:
        code = code.replace('</div>', link_code + '</div>', 1)

    with open(path, "w", encoding="utf-8") as f:
        f.write(code)
    print("Successfully patched scripts/update_events.py with event source links!")
else:
    print("Link logic is already present in scripts/update_events.py.")
