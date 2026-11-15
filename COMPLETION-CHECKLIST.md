# USA Auto Meets completion checklist

Review baseline: `origin/main` at `2952964` on November 14, 2026. This worktree began as an isolated proposal. The owner approved publication on November 14, 2026, including the website-submission feature; RELEASE-20261114.md records rollout status.

## Agreed requirements and completion evidence

| Requirement | Current evidence | Remaining acceptance check |
| --- | --- | --- |
| Car-inspired responsive directory | Published dark/lime design; mobile and filter checks passed in earlier work | Regression-check any proposed UI fixes |
| Real dated events across all 50 states in scope | Validated importers, source attribution, budget guard, 50-state discovery registry; coverage is reported honestly | Close documented source gaps through verified public calendars; no promise that every event is discovered |
| Parts retailers, tuners, builders, detailing businesses | 60-business watchlist; Griot's, FCP Euro, Speedway Nebraska adapters | Review remaining blocked/undated calendars; retain discovery-only status until verified |
| More representative images | Source artwork where available and labelled stock fallback | Keep artwork/fallback labels accurate; do not invent flyers |
| Registered accounts, save/RSVP, organizer ticket links | Backend and UI implemented; local access-control tests passed | Real verified-member signup, recovery, save/RSVP tests after email setup resumes |
| State/city email alerts | Consent, location matching, leased delivery, unsubscribe, scheduler implemented | Configure sender and private secrets, then prove real matching delivery, unsubscribe, and retry behavior |
| Registered submissions with required flyer | Private upload and validation; first four human approvals then eligible auto-publishing | Test actual member upload and admin queue after activation; fix local audit regressions before release |
| Flag events and check validity | Registered reports, moderator evidence attestation, hide/suspend controls | Exercise real admin/report flow after activation; automate any uncovered local regressions |
| Changeable admin | Initial address allowlisted; verified-account transfer tested locally | Initial admin must register/verify; verify UI transfer using real accounts when authorized |
| Search availability | Static event/state/type pages, sitemap, metadata, schema, IndexNow; owner reported Google and Bing verified and Google live inspection passed | Owner-dashboard sitemap status and ongoing indexing observation; do not claim universal ranking |

## Finite current review batch

1. Audit existing community UI and backend for reproducible defects in the requirements above.
2. Fix the highest-impact unblocked defects in this isolated worktree, with regression tests.
3. Run the relevant local checks and document exact proposed changes and limitations.
4. Present the patch and validation for explicit approval. Continue independent review preparation while approval is pending; never push or deploy without approval.

Current review-batch status: audit and nine defect fixes prepared; local regression suites and phone-browser checks passed. `REVIEW-NOTES.md` describes behavior, tradeoffs and release order. The owner approved this patch; rollout verification is recorded in RELEASE-20261114.md. `ACTIVATION-ACCEPTANCE.md` lists the remaining paused real-service acceptance checks.

## Paused / external acceptance work

- Email/dashboard setup is blocked by the browser-control error. The owner is signed into Resend and can complete guided domain verification; sender readiness remains disabled until real tests pass.
- Resend verified domain and SMTP; Supabase sender, redirect and secret settings; matching GitHub scheduler secret; and real administrator verification are still required.
- No production email sends, new accounts, or moderation mutations are authorized by this draft review.

## Source coverage backlog boundary

Use `coverage.json`, `business-calendar-report.json`, `business-watch-report.json`, and `organizer-registry.json` as the finite inventory for subsequent source proposals. A missing state is a discovery gap, not permission to create recurring dates. Blocked sources require an accessible official calendar/feed or manual verified evidence. Paid Facebook work remains subject to the $5 monthly allowance and existing fail-closed budget checks.

At the review baseline, the coverage snapshot contains 412 events across 33 states. The states without accepted listings are AR, DE, HI, IA, KY, MD, ME, MS, MT, ND, NM, RI, SC, SD, UT, VT, and WY. These counts change as dated events expire or new sources publish schedules.

Separate remaining search work: approved member submissions currently enter the browser directory, while generated individual search pages cover imported listings. A static export of approved member events, with moderation-safe flyer URLs, needs a separate reviewed proposal. Do not call those member-event detail pages complete.
