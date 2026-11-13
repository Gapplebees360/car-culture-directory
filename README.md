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
