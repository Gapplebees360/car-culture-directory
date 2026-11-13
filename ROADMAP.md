# USA Auto Meets recovery roadmap

## Phase 1 — Honest, reliable foundation (published)

- Remove fabricated rolling dates and the unaudited Supabase write/delete path.
- Use reviewed `events.json` as the source of truth; require a source URL and verification date.
- Validate the full dataset before replacing the homepage. Reject bad data, remove expired events, sort and deduplicate listings.
- Consolidate daily refresh automation; validate pull requests without publishing them.
- Disable unfinished submission and email features with clear availability messages.
- Escape event text and validate link/image protocols; fix narrow-screen grid overflow and label filters.
- Remove obsolete patch helpers and redirect the alternate stale directory page to the homepage.

Acceptance: regression tests pass, invalid input leaves the published page intact, no generated dates or misleading form confirmations remain.

## Phase 2 — Restore useful event coverage

Implemented: SCCA public calendar plus a capped, manual Facebook discovery adapter. Facebook searches request all 50 states, require actual event geography/dates, and reject unrelated, private, online, and cancelled listings. The first corrected run added 9 accepted events; combined coverage is 167 events in 33 states. The provider reported partial request failures, so comprehensive 50-state coverage remains unfinished. SOURCES.md documents the exact inputs and limitations.

1. Start with an agreed pilot region and official organizer calendars.
2. Add one adapter per source with fixtures, source attribution, actual dates, time zone, and last verification time.
3. Stage imports for review. Distinguish a successful empty calendar from a failed request; never replace good data on a failed import.
4. Add stable source IDs and duplicate matching. Track source health and alert on failures or unexpected drops in coverage.
5. Expand state by state; show coverage and freshness honestly.

Acceptance: every published date is traceable to an organizer listing; an adapter outage preserves the last verified data; expired events do not display.

## Phase 3 — Real submissions and alerts

1. Confirm Cloudflare hosting/origin and choose the backend location.
2. Add a server endpoint for event proposals, server-side Turnstile verification, validation, rate limits, and moderation storage.
3. Review database permissions before enabling public access; keep privileged keys on the server.
4. Add confirmed email opt-in, state preferences, unsubscribe support, and delivery tracking with an email provider.
5. Restore the UI only when end-to-end success and failure paths work.

Acceptance: submissions enter a review queue, browser requests cannot publish directly, subscriptions are confirmed, and unsuccessful requests never display success.

## Phase 4 — Search, mobile, and publishing

Implemented: motorsport-inspired responsive redesign, separated frontend assets, date filters, reset controls, source counts, load-more pagination, desktop screenshots, and real-browser checks for phone overflow and filtering. Submission/email backend work remains in Phase 3.

- Add shareable filters, full state names, useful date filters, and clear no-results recovery.
- Perform real browser checks at phone and desktop sizes, keyboard navigation, and assistive-technology checks.
- Add canonical URLs, social metadata, sitemap, and structured event pages after event accuracy is established.
- Confirm whether Cloudflare fronts GitHub Pages or hosts the application. Document DNS, SSL, caching, preview deployment, and rollback.
- Verify how automated commits trigger publishing; GitHub-token commits may need an explicit Pages deployment rather than relying on another workflow trigger.

Acceptance: verified deployment reaches the custom domain, refreshes appear without stale caching, and rollback is documented.

## Release notes and limits

The initial cleanup removed three fabricated dates. The SCCA importer now restores actual calendar listings. Remaining coverage work is to add car-show organizers, cars-and-coffee calendars, and regional sources for states with no listings. Full 50-state coverage is not yet achieved.

The cleanup was transferred onto a fresh clone with the original upstream history before publishing. The initial API-reconstructed local snapshot is not used as upstream Git history.
