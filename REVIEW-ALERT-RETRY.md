# Alert failure/retry review — November 14, 2026

Review-only branch based on bade78c. No secret edits, production email requests,
SQL migrations, deployment, or publication were performed during this review.

## Finding and proposal

Resend keeps idempotency keys for 24 hours:
https://resend.com/docs/dashboard/emails/idempotency-keys
The released claim routine retains batch identity and payload but has no retry-age
limit. A request accepted before an unknown timeout could be replayed after the
provider forgets its key and deliver twice.

The proposed SQL records the first claim time, preserves it across retries, and
suppresses uncertain batches after 23 hours. Previously attempted rows with no
reliable timestamp are suppressed on migration. The Edge handler requires the
returned deadline, checks it before each send, and applies a 10-second timeout.
No new browser or public privileges are granted. Unknown delivery can result in
an omitted alert; the proposal prioritizes avoiding duplicate emails.

## Validation

74 released Python tests and website signed-identity, database, frontend and
completion database checks passed before edits. Five additional scheduler tests
cover inactive provider, failed counts, private rejection details, malformed
counts, and bounded repeat invocation. New local Edge boundaries cover missing/
expired deadlines, provider rejection, network failure, DB failure after send,
and unchanged provider key/payload. Expanded PostgreSQL checks cover active lease
exclusion, fixed retry deadlines, old/unknown attempt suppression, provider-failed
retry and no replay after recorded success. All test dependencies are local;
provider/network calls are mocks. No real emails were sent.

## Release dependency

Requires explicit approval of this new proposal; earlier preference and worker
approvals do not include it. Apply alert-retry-window.sql after the existing
completion migration, then deploy the paired Edge function before resuming alert
acceptance. Old Edge code can ignore the extra field; the new Edge code fails
closed without it. Reverting just the Edge handler removes its deadline check;
do not revert the SQL guard while uncertain batches remain.

## Remaining finite product dependencies

- Account domain, SMTP, invitation/recovery and owner account acceptance are
  confirmed; AUTH_EMAIL_READY was observed true. Older rollout notes describing
  those as unverified are historical and superseded by this review.
- Live alert readiness was last observed false. Remaining configuration requires
  dashboard access; both computer-control paths fail before attaching. Do not
  repeat those paths or expose/recover private keys through unrelated storage.
- Matching delivery, real inbox receipt, unsubscribe, and end-to-end retry
  acceptance require configured delivery and an explicit consented test. No
  real-event or subscriber mutations were made for this local audit.
- Website inspection/import/deduplication and recurring-crawl code are released;
  local signed-worker/UI/DB suites pass. Actual verified-member queue acceptance
  still requires an authenticated browser and an intended public website.
- Member event search pages are a separate unpublished draft in
  E:/USAAutoMeets-member-seo-review, requiring approval and backend-first release.
- Nationwide coverage depends on individually published official event dates.
  No recurrence was converted into invented events, and no paid scraping ran.
