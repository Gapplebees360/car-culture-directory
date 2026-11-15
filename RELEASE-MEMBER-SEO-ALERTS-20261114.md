# Approved member search pages and alert retry release

The owner explicitly approved both releases on November 14, 2026. The combined
release contains the two reviewed proposals, their tests, the generated empty
public member snapshot, and this rollout record. Base44 was not used.

## Applied and verified backend

- Hosted migration uam_alert_retry_window_20261114 applied successfully.
- community Edge function version 12 active with all four source modules.
- SQL inspection confirms first_attempt_at, 23-hour retry cutoff and service-only
  alert claim permissions. No existing delivery batches were present.
- Live GET /community/public-events returns {events:[],next_cursor:null}; there are
  currently no approved member events to generate detail pages for.
- Account signup readiness is true. Alert readiness remains false; no secrets were
  modified and no emails were sent as part of this release.
- Before/after security advisor names, levels and counts are unchanged. Existing
  intentional private RLS/RPC findings remain described in SECURITY-REVIEW.md;
  the pre-existing leaked-password-protection warning is not changed here.

## Local validation and publication

88 Python tests (83 member-search tests plus five scheduler regressions), community
UI, original/completion PostgreSQL, alert delivery mock boundaries, website
DB/UI/signed-worker restrictions, eight public feed/flyer/actual route tests, four
submission validation checks, Edge syntax and frontend smoke checks pass. Workflow
YAML and whitespace checks pass. Existing imported search pages rebuild cleanly.
The release workflow is checked after pushing this approved combined change.

## Remaining external acceptance

Real member submission/moderation/website queue interactions require an
authenticated browser. Actual alert delivery/unsubscribe acceptance additionally
requires completed private delivery configuration and an explicitly consented
test. Browser/desktop automation startup remains blocked; no retries of that
broken path or alternative credential extraction were attempted in this release.
Static member text updates after a successful scheduled rebuild; third-party
search caches update on crawler schedules. Flyers recheck approval per request.
