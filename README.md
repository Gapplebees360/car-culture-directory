# USA Auto Meets

Static event directory. `index.html` is the homepage and `events.json` is the reviewed event dataset. Python 3.11 is sufficient; there are no Python package dependencies.

## Local checks

```sh
python -m unittest discover -s tests -v
python scripts/update_events.py
node tests/frontend.cjs
python -m http.server 8000
```

Open http://localhost:8000. Scheduled refreshes import SCCA's official public calendar, then rebuild the homepage. The importer reads every API page, uses custom event dates rather than WordPress publication dates, and reads city/state from the organizer's calendar link. It never invents locations or dates.

For a network import, run `python scripts/import_scca.py` before the builder. `coverage.json` reports all 50 states and skipped records. Transport errors, unusable empty results, or a drop of more than half the previous upcoming SCCA coverage stop the import and retain the previous dataset. Scheduled runs deploy the generated site explicitly, since automated commits do not reliably trigger a separate Pages build.

## Adding a verified event

Add an object to `events.json` with these required text fields: `title`, `state` (two-letter US abbreviation), `city`, `venue`, `category`, `date` (YYYY-MM-DD), `url` (original organizer listing), and `verified_at` (YYYY-MM-DD, when the source was checked, UTC). Optional text fields: `time`, `description`, `image`, `end_date`. Imported records also have `source` and `source_id`. Dates must come from the source. Allowed categories match the homepage filters. Multi-day events stay visible through their end date. Automated source checking does not guarantee an organizer has not changed or cancelled an event; users should follow the original listing.

Run the checks and builder, then include both the dataset and generated homepage in the change. Validation errors leave the existing homepage intact. An intentionally empty array clears listings. Keep imports staged separately until checked.

Submissions and alerts are unavailable until their backend services are implemented. See ROADMAP.md for sequence and release requirements.

## Public Facebook imports

The existing Apify connection can run the official Facebook Events actor. Set `APIFY_TOKEN` securely in the environment, then run:

```sh
python scripts/import_facebook.py start --max-charge 0.5
python scripts/import_facebook.py status
python scripts/import_facebook.py collect
python scripts/update_events.py
python scripts/coverage_report.py
```

`run` combines start/poll/collect for unattended execution. Paid searches default to $0.50 and cannot exceed $1 per run. Before starting, the importer reads the account's current billing-cycle usage, reserves $0.25 for storage/reads, and caps the run to the remaining $5 monthly allowance. Missing usage data or another running actor blocks the paid run. The existing Apify account platform limit was verified as $5; it was not increased. No paid run was started while implementing this change.

In GitHub Actions, manually dispatch the refresh workflow with the Facebook option selected; it reads the repository's `APIFY_TOKEN` secret. Daily runs retain existing Facebook listings and refresh SCCA and free calendars without starting a paid Facebook search. No automatic daily Facebook charges are enabled.

## Free cars-and-coffee coverage

```sh
python scripts/import_free_calendars.py
python scripts/update_events.py
python scripts/coverage_report.py
```

The free Events With Cars public feed supplies explicitly dated occurrences in a 180-day window, venue data, and source artwork. These are third-party calendar listings; verify the original listing before travelling. The daily workflow refreshes them without an Apify account. `free-calendar-report.json` distinguishes occurrences from distinct recurring series and records rejected listings.

Run `python scripts/discover_organizers.py` to rebuild the research registry. `organizer-registry.json` currently contains 377 discovery leads across all 50 states. Leads are marked for verification; they do not create any future dates or published events. The next step is to follow each lead to its official organizer calendar/feed, prioritizing states without coverage.

See SOURCES.md for exact sources, the previous scraper defects, normalization rules, and known search gaps. `.cache/` contains local run metadata and is ignored. Never commit API tokens, Facebook cookies, or raw attendee/organizer profiles.

## Frontend

The page is buildless: `index.html` embeds generated event data, `assets/app.js` handles filtering/pagination, and `assets/site.css` defines the responsive motorsport design. Stock scene photography is labelled separately from event photography. Browser checks in `tests/browser.html` exercise the real page through an HTTP preview.
