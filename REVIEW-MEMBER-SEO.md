# Approved member-event search pages — review proposal

Prepared November 14, 2026; baseline b63173e. No backend deployment, production
snapshot fetch, database mutation, commit, push or publication occurred.

## Result

Approved manual submissions gain stable individual pages, state/type browse pages,
homepage crawlable content, schema and sitemap entries. The imported events.json
and browser embedded array stay imported-only, so live community loading does not
double-add records. Community UUID identity determines each detail path; separate
occurrences sharing an organizer URL stay separate.

The public feed exposes only whitelisted approved/current fields. It is paginated
by canonical key, 250 rows/page, capped at 10,000 exported events. Failed, truncated,
malformed or redirected exports do not replace the last valid local snapshot.
The production workflows require a fresh successful export before static publish.

Flyers use an approval-checked endpoint instead of expiring signed storage URLs.
It rechecks current approval on each request, validates raster format/size, and
returns no-store/nosniff. Private storage paths, account IDs and review notes stay
out of the export. Static text disappears on a successful rebuild; search caches
update on crawler schedules. Runtime cards keep existing organizer links until
the generated detail pages are published, avoiding a new-event 404 window.

The half-hour website workflow now stages moderation/member page changes before
deciding whether to publish. It previously checked only imported events.json,
which could miss member-only or moderation-only changes.

## Validation

83 Python tests; eight public feed/flyer/actual Edge route tests; original frontend,
community UI, PostgreSQL, completion, website database/UI/signed-worker and flyer
validation suites all pass. Workflow YAML parses and diff checks pass. All new
public-feed/storage/network boundaries were fixtures. No real member data was
exported, no source calendars changed, and no paid services ran.

## Release dependencies

Explicit proposal approval is required. Deploy the Edge routes plus
public-community.mjs/validation.mjs first, check the public feed, then publish
Python/workflow changes and allow the regular validated build to generate the
snapshot/pages. No new migration is needed; no public table grants are added.
For rollback restore the publishing workflows/builders together; the extra public
routes can remain unused or be removed afterward. Do not publish an old snapshot
as a workaround for an unavailable approval feed.

## Other finite dependencies

- Existing website inspector/importer/deduplication and recurring-source suites
  pass. Existing production worker success was recorded as run 43666100643;
  preferences release 43668400858 passed and is retained by bade78c. A genuine
  member-submitted website acceptance still needs an authenticated browser and
  an intended source submission; no synthetic queue entries were created.
- Account email activation has passed invitation/recovery and owner login;
  AUTH_EMAIL_READY was confirmed true. Alerts were last observed false, and
  dashboard access is blocked by the computer-control startup error.
- Alert retry-window review is separate at E:/USAAutoMeets-alert-audit-review.
- All-state coverage depends on explicit official schedules. Read-only research
  found Iowa PCA Cars & Coffee on Dec 12, 2026 and Feb 13, 2027 at Cozy Cafe
  Johnston: https://schonesland.com/event/cars-and-coffee-cozy-cafe-johnston/2026-12-12/
  and https://schonesland.com/event/cars-and-coffee-cozy-cafe-johnston/2027-02-13/.
  A new adapter/import needs its own reviewed proposal. Utah leads lack a clear
  future date or have conflicting organizer times; retain as leads, not events.
