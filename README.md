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
python scripts/import_facebook.py start --max-charge 5
python scripts/import_facebook.py status
python scripts/import_facebook.py collect
python scripts/update_events.py
python scripts/coverage_report.py
```

`run` combines start/poll/collect for unattended execution. In GitHub Actions, manually dispatch the refresh workflow with the Facebook option selected; it reads the repository's `APIFY_TOKEN` secret. Daily runs retain existing Facebook listings and refresh SCCA without starting a paid Facebook search. No automatic daily Facebook charges are enabled.

See SOURCES.md for exact sources, the previous scraper defects, normalization rules, and known search gaps. `.cache/` contains local run metadata and is ignored. Never commit API tokens, Facebook cookies, or raw attendee/organizer profiles.

## Frontend

The page is buildless: `index.html` embeds generated event data, `assets/app.js` handles filtering/pagination, and `assets/site.css` defines the responsive motorsport design. Stock scene photography is labelled separately from event photography. Browser checks in `tests/browser.html` exercise the real page through an HTTP preview.
