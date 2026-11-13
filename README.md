# USA Auto Meets

Static event directory. `index.html` is the homepage and `events.json` is the reviewed event dataset. Python 3.11 is sufficient; there are no Python package dependencies.

## Local checks

```sh
python -m unittest discover -s tests -v
python scripts/update_events.py
node tests/frontend.cjs
python -m http.server 8000
```

Open http://localhost:8000. Scheduled refreshes remove past listings; they do not discover or invent events.

## Adding a verified event

Add an object to `events.json` with these required text fields: `title`, `state` (two-letter US abbreviation), `city`, `venue`, `category`, `date` (YYYY-MM-DD), `url` (original organizer listing), and `verified_at` (YYYY-MM-DD, when a person checked the source). Optional text fields: `time`, `description`, `image`. Dates must come from the source. Allowed categories match the homepage filters.

Run the checks and builder, then include both the dataset and generated homepage in the change. Validation errors leave the existing homepage intact. An intentionally empty array clears listings. Keep imports staged separately until checked.

Submissions and alerts are unavailable until their backend services are implemented. See ROADMAP.md for sequence and release requirements.
