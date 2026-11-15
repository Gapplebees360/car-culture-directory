# Community access review

The actual migration is exercised in isolated PostgreSQL. Tests cover denied self-promotion, denied cross-user reads, required private flyers, four distinct human approvals before automatic publication, reported-event hiding, organizer suspension, leased email retries, and administrator transfer.

Production checks after explicit activation:

- All `uam_*` tables have row-level security enabled.
- Anonymous profile and administrator queries return no records; published event catalog rows are available.
- `uam_submit` and email-claim/finish functions are executable only by the server service role. User identity for submission is obtained from Auth, not from the request body.
- Moderation/admin RPCs are executable by signed-in users but check administrator identity inside the privileged function. Ordinary members cannot approve, hide, transfer admin access, or update their own moderation status.
- The upload endpoint requires a confirmed account, limits request/file size, checks supported image headers/dimensions, and stores pending flyers privately. File checks and account history do not prove event legitimacy; moderators compare flyer/date/place/source before the first four approvals.

## Intentional advisor findings

The three server-only tables `uam_admins`, `uam_alert_delivery`, and `uam_job_locks` have RLS with no client policies. This denies direct client access intentionally. See [RLS without policies](https://supabase.com/docs/guides/database/database-linter?lint=0008_rls_enabled_no_policy).

`uam_hidden_event_keys` intentionally exposes only opaque IDs of withdrawn imported listings so the static directory can suppress them. It exposes no report contents or member data. Other privileged helpers that are not needed anonymously had anonymous/PUBLIC execution revoked. See [public privileged functions](https://supabase.com/docs/guides/database/database-linter?lint=0028_anon_security_definer_function_executable).

Signed-in moderation RPCs intentionally use privileged operations after checking the current verified administrator; ordinary table updates remain denied. These are expected [signed-in privileged-function notices](https://supabase.com/docs/guides/database/database-linter?lint=0029_authenticated_security_definer_function_executable), not blanket authorization to all members. Their denied-caller paths are covered by the PostgreSQL tests.

## Release limits

Registration is gated until verified SMTP/auth redirect setup is marked ready. Event alerts are gated until the sender, API credential, and cron secret are configured. The scheduler and real email delivery still need an end-to-end check. Privileged database keys, mail credentials, and cron secrets are never committed to browser code.

## Website import release, November 14, 2026

The approved completion and website-submission proposals were applied as `uam_completion_fixes_20261114` and `uam_website_submissions_20261114`. The community function is version 3. All three website tables have RLS. Live permission checks confirm anonymous users cannot claim inspections or reconcile the catalog, registered users cannot finish inspections, and only authenticated members can call the submission RPC (which verifies their email and rate limit in its body). An unauthenticated worker request returns 401. Signup and email-alert readiness remain false.

The advisor adds two intentional authenticated SECURITY DEFINER notices: `uam_submit_website` checks verified identity and daily quota, and `uam_set_website_source` checks administrator identity. Browser execution is necessary for those specific operations; no general table-write privilege is granted. The service-only worker RPCs use SECURITY INVOKER and are unavailable to browser roles. See [authenticated function advisory](https://supabase.com/docs/guides/database/database-linter?lint=0029_authenticated_security_definer_function_executable).

`uam_website_event_links` has RLS and no client policy deliberately, denying browser reads/writes; the service role handles links. See [deny-by-default table advisory](https://supabase.com/docs/guides/database/database-linter?lint=0008_rls_enabled_no_policy). The existing anonymous opaque confirmed-event suppression helper remains intentional; see [public helper advisory](https://supabase.com/docs/guides/database/database-linter?lint=0028_anon_security_definer_function_executable). No new public privileged inspection function was exposed.
