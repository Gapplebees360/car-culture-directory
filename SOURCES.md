# Event sources and collection logic

## Active sources

| Source | Entry point | Importer | Refresh |
| --- | --- | --- | --- |
| SCCA official public calendar | https://www.scca.com/wp-json/wp/v2/event | scripts/import_scca.py | Daily, plus changes to main |
| Events With Cars public calendar API | https://eventswithcars.com/wp-json/tribe/events/v1/events | scripts/import_free_calendars.py | Daily; no paid service |
| Public Facebook events via Apify's official actor | https://apify.com/apify/facebook-events-scraper | scripts/import_facebook.py | Manual; default $0.50, maximum $1 per run and $5 per billing cycle |

SCCA uses all paginated records, `custom.start_datetime` / `custom.end_datetime` for dates, the organizer's calendar link for city/state, and the event's original page URL. The WordPress post date is not the event date.

Facebook runs 150 queries: car show, cars and coffee, and car meet for each of the 50 full state names. The actor's supported `maxEvents` input limits each query to two records. It has a 20-minute provider timeout. Before a paid run, current billing-cycle usage must be available; the cap is the smaller of the requested amount, $1, and the remainder of $5 less a $0.25 reserve. Another running actor blocks the start. Neither Facebook cookies nor a Facebook login are needed by this actor. Credentials are read only from `APIFY_TOKEN` and sent in an authorization header.

The free calendar importer reads all published pages within a 180-day window. Its first import supplied 215 accepted event occurrences, including 113 cars-and-coffee occurrences representing 15 recurring series. Those series are concentrated in four states, so the number must not be presented as 113 different meetups or national coverage. Listing artwork was available for 209 occurrences; repeated occurrences may share an image. Dates are explicit feed dates, not generated recurrence rules. All source pages remain linked.

Organizer discovery is separate from publication. The free carsandcoffeedirectory.com index supplied 377 leads across 50 states, recorded in organizer-registry.json with `needs_organizer_verification` status. The importer does not copy its recurring schedule hints into future events. Direct museum/organizer feed checks also found unpublished dates and inaccessible endpoints; those are not silently treated as live sources.

Facebook search is not exhaustive or a reliable geographic filter. The initial corrected run returned 70 records, included 111 failed provider requests, and yielded 9 accepted automotive events in 7 states after normalization. These results do not establish that every requested query completed or that the other states have no events. `facebook-report.json` distinguishes requested searches from returned records and accepted locations.

## Data acceptance

- Accept only explicitly public, offline, non-cancelled Facebook events with a canonical event URL.
- Require an exact timestamp plus a trustworthy local calendar date; never publish a generated relative date.
- Require an actual US city/state from event geography. Never assign a state's search term to an event.
- Reject non-automotive results, incidental band-biography matches, and social parties without an automotive gathering.
- Merge Facebook discoveries by stable Facebook event ID. A capped search is not a replacement for the entire existing event dataset.
- Keep other sources' records when an importer refreshes its own records. Validate and deduplicate before rebuilding the homepage.
- Preserve existing data on failed or unusable imports. Record rejected records and their reasons. Missing data is not filled with guesses.
- Retain multi-day events through their final day. The build retains the latest US calendar day; the browser applies its local current date.

## Historical findings

The original workflow supplied Apify and Gemini secret names, but its checked-in update script did not use either service. It returned three preset Washington listings with dates relative to each run. A declared GitHub events feed was never fetched.

The existing Apify account's earlier actor input used generic car queries without state names and `maxItems`, which is not this actor's documented per-query event limit. Three recent historical runs timed out. The current code uses `maxEvents`, state-specific queries, a server-enforced timeout/charge cap, explicit validation, and a separate coverage report.

## Next coverage improvements

Seed public organizer/page URLs in low-coverage states and add city-level searches. Increase per-query limits only after measuring useful-event yield and costs. Facebook search returns unrelated, missing-location, and foreign results even when US state names are present; acceptance counts, not raw result counts, measure coverage.
