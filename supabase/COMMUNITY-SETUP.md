# USA Auto Meets community activation

## Implemented behavior

- Registered and email-verified members can save events and RSVP. This does not purchase tickets or reserve organizer admission. Organizer links remain the official registration destination.
- Each member can save state-wide or exact city/state alert preferences. Email alerts require separate explicit consent and include an unsubscribe route.
- Every submission requires a JPG, PNG, or WebP flyer, permission to publish it, exact dates, city/state, venue, local time, and a public HTTPS organizer/source link.
- New flyers remain private while pending. The first four distinct human-approved submissions require moderation. The fifth may auto-publish if the member is not suspended and has no unresolved event reports. Rejected submissions and automatic approvals do not increase the four-approval count.
- Registered users may flag a published event. A flag enters the admin queue without immediately hiding the event. Confirming a violation hides it and suspends that organizer's automatic submissions. Dismissing a report clears that open-report obstacle.
- Administrators must attest that they compared the flyer, date, venue, and organizer evidence before approving. These checks reduce abuse; neither flyer upload nor automatic validation proves legitimacy.
- The initial administrator is insertcoinwa1@gmail.com. They must verify their email. Admin transfer in the dashboard requires the replacement to register and verify first.

## Backend

Use the existing Supabase project `usautomeets-db` (`lswnpxeiagureogrlopy`). The new `uam_*` tables are isolated from the legacy `events` and `subscribers` tables. The legacy tables are not imported or altered.

1. Approve and apply `migrations/20261113_community.sql` through Supabase's migration tool.
2. The migration seeds the initial administrator. If restoring that allowlist later, use a privileged database session:

```sql
insert into public.uam_admins(email) values ('insertcoinwa1@gmail.com') on conflict do nothing;
```

3. Deploy `functions/community/index.ts`, with `validation.mjs` included. Use `verify_jwt=false` because public health/catalog refresh/unsubscribe endpoints have their own controls and user endpoints explicitly verify the access token with Supabase Auth. Privileged keys are read from the server's built-in environment; they are never placed in browser assets.
4. The public catalog sync uses only `https://usautomeets.com/events.json`, not client-supplied event data. A database lease limits it to once per hour. Invoke `POST /functions/v1/community/sync` after initial activation and after publishing refreshed events. Confirmed reports remain hidden across catalog refreshes.
5. Inspect the project's security advisors and run the access-control tests before enabling community traffic.

The function's `/health` reports readiness. The community page disables forms if database/function activation is incomplete; it never reports a successful submission without a server success response.

## Email: Resend free tier

Email delivery needs a user-owned Resend account and a verified sending domain. No paid Resend plan is required by this implementation. Do not assume free-plan account allowances or domain verification are already active.

1. Verify a sending domain, preferably `mail.usautomeets.com`, in Resend by adding the exact DNS records Resend provides to Cloudflare. Do not change the site's existing web-hosting records.
2. In Supabase Auth, set the Site URL to `https://usautomeets.com` and allow `https://usautomeets.com/community.html` as a redirect. Require email confirmations. Configure custom SMTP with the values Resend provides. The default Supabase email sender is unsuitable for unrestricted public signups.
3. In Supabase Edge Function secrets, set `RESEND_API_KEY`, `EMAIL_FROM` (a verified sender), and a long random `ALERT_CRON_SECRET`. Never paste these values into this repository, browser code, screenshots, or public chat output.
4. After setup, test account confirmation and password recovery with the administrator's real account. Only after SMTP/redirect verification, set the Edge Function secret `AUTH_EMAIL_READY=true`. Confirm `/health` returns `signup_ready:true` to open public registration, and `alerts_ready:true` before enabling email consent in the UI.
5. Schedule a server-side POST to `/functions/v1/community/alerts/run` every 15 minutes with `Authorization: Bearer <ALERT_CRON_SECRET>`. Store that secret in the scheduler's secure secret store. A Supabase Cron job with pg_net/Vault or an authenticated external scheduler can do this. No scheduler secret is embedded in SQL committed here.
6. Test a genuinely new approved listing against a consented matching subscription. Previously listed events and events published before a subscription's creation do not trigger a backlog of email.

The outbox leases batches, retains the same batch ID across retries, and uses Resend idempotency keys. Unsubscribe requires an explicit confirmation; visiting a link alone does not change preferences. The application limits event-alert batches to 80 per day / 2,400 per calendar month, leaving room for auth email under a typical free-tier allowance. These are application limits, not a guarantee about unrelated usage in the same provider account.

## Tests

```sh
npm ci --ignore-scripts
npm run test:community
python -m unittest discover -s tests -q
node tests/frontend.cjs
```

The PostgreSQL tests run the actual migration in an isolated local PostgreSQL WASM runtime and test the first-four approval rule, fifth auto-approval, private data access, forbidden self-promotion, flyer requirement, report suspension, leased alert retries, and admin transfer. They do not send email or touch production users.

## Activation blockers

After the user's explicit production approval, the `uam_*` migration and helper-permission hardening were applied to the existing project. The community Edge Function is active, the public event catalog is loaded, and anonymous requests were verified to return no private member/admin rows. The earlier approval expiry/rejections were not bypassed.

Email activation remains pending: Resend credentials, verified SMTP/sending domain, and the alert scheduler are not yet configured. Health currently reports `accounts:true`, `submissions:true`, `signup_ready:false`, and `alerts_ready:false`. Public registration and alert opt-in remain disabled rather than claiming email is working. Existing verified accounts can sign in. The initial administrator email is allowlisted but must still create and verify its account.
