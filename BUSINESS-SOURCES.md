# Automotive business event discovery

`business-sources.json` is a growing US aftermarket business watchlist: parts retailers, manufacturers, tuners, custom builders, wheel/tire businesses, and detailing stores. It is separate from the Cars & Coffee organizer registry. Business names are discovery leads, not proof of a scheduled event or a complete inventory of local shops.

The daily refresh imports exact dated public listings from Griot's Garage, FCP Euro, and Speedway Motors Nebraska through the official Museum of American Speed calendar. It does not generate dates from descriptions such as “first Saturday.” Each listing links to its official business calendar. FCP Euro's event-specific artwork is carried with source attribution. Unsupported or ambiguous events remain in the report rather than receiving invented venues or times.

The Griot's calendar currently has an April 2027 section containing a March 6 date. That record is explicitly rejected for organizer clarification. Club business meetings and trade-only SEMA attendance are excluded. The calendar's public car meets and shows are imported.

`scripts/check_business_sources.py` checks each business at most weekly, with three concurrent requests, a 12-second timeout, no paid provider, and a limited response size. It records readable pages, same-site candidate event links, and blocked/dead sources in `business-watch-report.json`. A blocked page is never treated as an empty calendar. Summit Racing, Speedway Motors Arizona, and Holley require further access/feed work when their protections reject automatic requests. Do not bypass their access controls.

`scripts/import_business_events.py` validates source-specific dates, venues, states, and categories. A failed or unexpectedly reduced source retains its last accepted data. The report is `business-calendar-report.json`; the combined geographic coverage remains `coverage.json`.

To expand: add the business's official URL and category to the watchlist, review its candidate calendar and public access rules, then implement and test an adapter for its actual structure. A homepage, social caption, old show recap, sponsored race name, or undated recurrence is insufficient to publish an upcoming occurrence. Local shops in every state are in scope; this initial national-brand list is not exhaustive.

Run free discovery/imports with:

```sh
python scripts/check_business_sources.py
python scripts/import_business_events.py
python scripts/update_events.py
python scripts/coverage_report.py
```

Speedway Motors Nebraska is imported through `https://www.museumofamericanspeed.org/carsandcoffee.html`. The museum lists six explicit 2027 Show Dates and the campus address. This adapter requires that date block, address, and published hours; it does not generate last-Saturday dates from the general recurring description. The first Nebraska import adds six Cars & Coffee occurrences and extends coverage to 34 states.
