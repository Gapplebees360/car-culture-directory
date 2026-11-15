# Completion fixes awaiting approval

Originally prepared in `E:\USAAutoMeets-completion-review`, branch `review/completion-20261114`, based on `2952964`. The owner approved publishing on November 14, 2026. Database proposals have now been applied and the matching backend deployed; frontend release verification is tracked in RELEASE-20261114.md. Base44 was not used. Email delivery remains disabled pending dashboard configuration.

## Proposed behavior

- A successful flyer submission clears its captured form and keeps the success message, instead of throwing after the upload succeeds. A failed upload preserves entered information.
- Password-recovery events are observed before account/readiness requests can delay setup.
- Saving already-enabled alert preferences preserves the original consent time. A provider outage cannot prevent an existing subscriber from opting out.
- Upcoming community listings are filtered before deterministic pagination, so historical records cannot consume the first 500 positions and hide newer events.
- A complete imported catalog is reconciled atomically. Missing imports are retired, human-confirmed suppressions remain hidden, and community submissions remain separate. Invalid snapshots do not partially modify the catalog. Source withdrawals do not become permanent moderation bans.
- A failed catalog refresh keeps a 60-second retry cooldown instead of an hour; successful refreshes retain their existing hourly limit. The source fetch has a 30-second timeout, and cleanup errors do not replace the original failure.
- Confirming a community-event report also updates the submitter's visible submission status to hidden.
- Alert retries compare the recipient and rendered event fields with their original batch fingerprint. Changed or partially withdrawn batches are suppressed rather than reusing a provider idempotency key with different content.

## Alert retry tradeoff

An uncertain prior attempt may already have reached the recipient. Conservatively suppressing a changed retry batch avoids duplicate/stale mail but can omit an unsent alert for an otherwise valid event in that batch. This is deliberate. It does not claim exactly-once delivery. The fingerprint covers the current rendered recipient/event fields; future changes to the email template or From sender need coordinated handling of existing pending batches.

## Release ordering if explicitly approved

1. Rebase the reviewed proposal onto the latest main branch and re-run checks; review any conflicts or scope changes.
2. Promote `supabase/proposals/community-completion.sql` to a proper migration and apply it through the approved deployment mechanism. It must precede the Edge Function release because catalog sync calls a new service-only database function. Existing attempted pending alert batches without a known fingerprint are suppressed; fresh unattempted rows remain eligible.
3. Deploy the matching community Edge Function, then release the frontend and test wiring. Verify production permission boundaries and catalog behavior without sending real member emails.
4. Keep signup and email alerts disabled until the separately paused sender/domain/SMTP and real-account tests are completed. Approval of this code proposal does not unpause those dashboard actions.

## Validation record

Passed after integration:

- 53 existing Python checks (Python implementation unchanged by this review).
- Existing frontend smoke checks and new community UI regressions for all five confirmed frontend defects; the regression cases fail against the original code.
- Original PostgreSQL access-control/trust suite and new proposal suite running the actual SQL in isolated PGlite databases.
- Four submission/flyer validation checks and the Edge Function TypeScript syntax check.
- Real local-browser pagination, search, reset, state/category filtering, image fallback and 390-pixel phone overflow checks. The old browser check assumed Maine always had a future event; it now selects a state with actual fixture listings.
- `git diff --check`.

The local PostgreSQL tests include service-only function permissions, private outbox fields, invalid/null snapshot rollback, explicit authoritative empty catalog handling, retirement/reappearance, confirmed report preservation, hidden submission status, stable retries, changed-recipient/partial-withdrawal suppression, and failed-versus-successful refresh cooldowns.

Automated mocks/local PostgreSQL tests do not replace real email delivery, user verification, or a hosted Auth/browser acceptance test. The approved database/backend release is now recorded in RELEASE-20261114.md. Real email/account acceptance checks remain incomplete.
