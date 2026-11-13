"""Write combined event coverage without confusing requested states with results."""
from collections import Counter
import datetime
import json

try:
    from .update_events import ROOT, STATES, validate_events
except ImportError:
    from update_events import ROOT, STATES, validate_events


def write_report(root=ROOT):
    events = validate_events(json.loads((root / 'events.json').read_text(encoding='utf-8')))
    counts = Counter(event['state'] for event in events)
    sources = Counter(event.get('source', 'Reviewed listing') for event in events)
    report = dict(checked_at=datetime.datetime.now(datetime.timezone.utc).date().isoformat(),
                  imported=len(events), states_with_events=len(counts),
                  coverage={state: counts[state] for state in sorted(STATES)},
                  sources=dict(sources), facebook_report='facebook-report.json',
                  free_calendar_report='free-calendar-report.json', organizer_registry='organizer-registry.json',
                  business_calendar_report='business-calendar-report.json', business_sources='business-sources.json',
                  business_watch_report='business-watch-report.json',
                  cars_and_coffee_occurrences=sum(event['category']=='Cars & Coffee' for event in events),
                  distinct_cars_and_coffee_series=len({(event['title'],event['city'],event['state']) for event in events if event['category']=='Cars & Coffee'}),
                  with_source_artwork=sum(bool(event.get('image')) for event in events),
                  note='Searches target all 50 states; listings require an explicit source date and US location. Empty states indicate no accepted listings, not proof that no events exist.')
    temporary = root / 'coverage.json.tmp'
    temporary.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    temporary.replace(root / 'coverage.json')
    print(f'Coverage: {len(events)} events, {len(counts)} states, {len(sources)} sources.')


if __name__ == '__main__':
    write_report()
