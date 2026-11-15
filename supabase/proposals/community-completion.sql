-- DRAFT ONLY: review and explicit approval required before migration/deployment.
-- Apply to a local disposable database after the existing community migration.
-- No production changes have been performed by preparing this proposal.

create or replace function public.uam_reconcile_catalog(p_rows jsonb) returns jsonb
language plpgsql security invoker set search_path=public,pg_temp as $$
declare retired integer; synced integer;
begin
 if jsonb_typeof(p_rows) is distinct from 'array' or jsonb_array_length(p_rows)>10000 then
  raise exception 'Expected bounded catalog snapshot';
 end if;
 if exists(select 1 from jsonb_array_elements(p_rows) item
  where jsonb_typeof(item)<>'object' or coalesce(item->>'event_key','') !~ '^imported:[a-f0-9]{64}$'
  or jsonb_typeof(item->'event_data') is distinct from 'object'
  or coalesce(item->'event_data'->>'source','') in ('','Community')
  or coalesce(item->'event_data'->>'title','')=''
  or coalesce(item->'event_data'->>'date','') !~ '^\d{4}-\d{2}-\d{2}$') then
  raise exception 'Invalid catalog snapshot row';
 end if;
 if (select count(*) from jsonb_array_elements(p_rows))<>(select count(distinct item->>'event_key') from jsonb_array_elements(p_rows) item) then
  raise exception 'Duplicate catalog identity';
 end if;
 -- An explicit empty array is an authoritative clear of imported rows only.
 -- Fetch/parse failures and NULL are rejected by the caller/preflight instead.
 perform pg_advisory_xact_lock(hashtext('uam-catalog-reconcile'));
 insert into public.uam_events(event_key,event_data,approved,updated_at)
 select row.event_key,row.event_data,not exists(select 1 from public.uam_flags f where f.event_key=row.event_key and f.status='confirmed'),now()
 from jsonb_to_recordset(p_rows) as row(event_key text,event_data jsonb)
 on conflict(event_key) do update set event_data=excluded.event_data,approved=excluded.approved,updated_at=excluded.updated_at;
 get diagnostics synced=row_count;
 update public.uam_events e set approved=false,updated_at=now()
 where e.event_key like 'imported:%' and e.approved
 and not exists(select 1 from jsonb_array_elements(p_rows) item where item->>'event_key'=e.event_key);
 get diagnostics retired=row_count;
 return jsonb_build_object('synced',synced,'retired',retired);
end $$;
revoke all on function public.uam_reconcile_catalog(jsonb) from public,anon,authenticated;
grant execute on function public.uam_reconcile_catalog(jsonb) to service_role;

-- A failed fixed-source fetch should not consume the full successful refresh lease.
-- Keep a one-minute failure cooldown so the public /sync route cannot retry freely.
create function public.uam_fail_catalog_refresh() returns void
language sql security invoker set search_path=public,pg_temp as $$
 update public.uam_job_locks set last_run=now()-interval '59 minutes'
 where name='catalog' and last_run>now()-interval '1 hour' $$;
revoke all on function public.uam_fail_catalog_refresh() from public,anon,authenticated;
grant execute on function public.uam_fail_catalog_refresh() to service_role;

-- A source disappearance is not a permanent moderation ban. Only confirmed reports
-- belong in the public opaque static-publishing suppression list.
create or replace function public.uam_hidden_event_keys() returns setof text language sql stable security definer set search_path=public,pg_temp as $$
 select distinct event_key from public.uam_flags where status='confirmed' and event_key like 'imported:%' $$;
revoke all on function public.uam_hidden_event_keys() from public;
grant execute on function public.uam_hidden_event_keys() to anon,authenticated;

create or replace function public.uam_resolve_flag(p_id uuid,p_confirmed boolean,p_note text) returns void
language plpgsql security definer set search_path=public,pg_temp as $$
declare f public.uam_flags; owner_id uuid;
begin
 if not public.uam_is_admin() or length(btrim(p_note))<10 then raise exception 'Administrator review and explanation required'; end if;
 select * into strict f from public.uam_flags where id=p_id for update;
 update public.uam_flags set status=case when p_confirmed then 'confirmed' else 'dismissed' end,review_note=p_note where id=p_id;
 if p_confirmed then
  update public.uam_events set approved=false,updated_at=now() where event_key=f.event_key;
  update public.uam_submissions set status='hidden',review_note=p_note,reviewed_at=now()
  where id=(select submission_id from public.uam_events where event_key=f.event_key);
  select s.user_id into owner_id from public.uam_submissions s join public.uam_events e on e.submission_id=s.id where e.event_key=f.event_key;
  update public.uam_profiles set suspended=true where user_id=owner_id;
 end if;
end $$;
revoke all on function public.uam_resolve_flag(uuid,boolean,text) from public,anon;
grant execute on function public.uam_resolve_flag(uuid,boolean,text) to authenticated;


-- Persist only rendered email fields for retry comparisons. This table already denies
-- client reads through RLS. No new public grants or policy exceptions are introduced.
alter table public.uam_alert_delivery add column payload_fingerprint jsonb;
-- Existing attempted batches have unknown previous provider payloads. Do not replay them
-- under a newly computed fingerprint. Fresh rows without a batch identity remain eligible.
update public.uam_alert_delivery set status='suppressed',lease_until=null
 where batch_id is not null and payload_fingerprint is null and status in('pending','sending');

create or replace function public.uam_claim_alerts() returns setof jsonb language plpgsql security definer set search_path=public,pg_temp as $$
declare member public.uam_profiles; bid uuid; payload jsonb; email_slots int; fingerprint jsonb; previous_fingerprint jsonb;
begin
 -- Conservative app-level free-tier allowance, leaving room for auth emails.
 perform pg_advisory_xact_lock(hashtext('uam-alert-claims'));
 email_slots:=least(20,
  80-(select count(distinct batch_id)::int from public.uam_alert_delivery where sent_at>=date_trunc('day',now()) or(status='sending' and lease_until>now())),
  2400-(select count(distinct batch_id)::int from public.uam_alert_delivery where sent_at>=date_trunc('month',now()) or(status='sending' and lease_until>now())));
 if email_slots<=0 then return; end if;
 update public.uam_alert_delivery d set status='suppressed',lease_until=null where d.status in('pending','sending') and not exists(
  select 1 from public.uam_events e join public.uam_profiles p on p.user_id=d.user_id
  join public.uam_alert_locations l on l.user_id=p.user_id
  where e.event_key=d.event_key and e.approved and p.alerts_enabled
  and e.first_seen_at>greatest(l.created_at,p.consented_at)
  and e.event_data->>'state'=l.state and(l.city is null or lower(btrim(l.city))=lower(btrim(e.event_data->>'city')))
  and coalesce(e.event_data->>'end_date',e.event_data->>'date')::date>=current_date-1);
 insert into public.uam_alert_delivery(user_id,event_key)
 select distinct p.user_id,e.event_key from public.uam_profiles p
 join public.uam_alert_locations l on l.user_id=p.user_id
 join public.uam_events e on e.approved and e.event_data->>'state'=l.state
 where p.alerts_enabled and p.consented_at is not null
 and (l.city is null or lower(btrim(l.city))=lower(btrim(e.event_data->>'city')))
 and e.first_seen_at>greatest(l.created_at,p.consented_at)
 and (coalesce(e.event_data->>'end_date',e.event_data->>'date'))::date>=current_date-1
 on conflict do nothing;
 for member in select p.* from public.uam_profiles p where p.alerts_enabled and exists(
  select 1 from public.uam_alert_delivery d where d.user_id=p.user_id and (d.status='pending' or(d.status='sending' and d.lease_until<now())))
  limit email_slots for update skip locked
 loop
  select batch_id into bid from public.uam_alert_delivery where user_id=member.user_id and batch_id is not null
   and (status='pending' or(status='sending' and lease_until<now())) limit 1;
  if bid is null then
   bid:=gen_random_uuid();
   update public.uam_alert_delivery set batch_id=bid where user_id=member.user_id and event_key in(
    select event_key from public.uam_alert_delivery where user_id=member.user_id and status='pending' and batch_id is null order by event_key limit 20);
  end if;
  update public.uam_alert_delivery set status='sending',lease_until=now()+interval '15 minutes' where user_id=member.user_id and batch_id=bid and status in('pending','sending');
  select jsonb_build_object('user_id',member.user_id,'email',u.email,'batch_id',bid,'unsubscribe_token',member.unsubscribe_token,
   'events',(select jsonb_agg(jsonb_build_object('event_key',e.event_key,'event_data',e.event_data) order by e.event_key) from public.uam_events e
    join public.uam_alert_delivery d on d.event_key=e.event_key where d.user_id=member.user_id and d.batch_id=bid and d.status='sending' and e.approved))
  into payload from auth.users u where u.id=member.user_id and u.email_confirmed_at is not null;
  if payload is null or payload->'events' is null or payload->'events'='null'::jsonb then
   update public.uam_alert_delivery set status='suppressed',lease_until=null where user_id=member.user_id and batch_id=bid and status in('pending','sending');
   continue;
  end if;
  -- Compare only fields rendered into the actual email, not scrape timestamps or artwork.
  -- A later template/from-address change must suppress existing attempted batches
  -- or migrate their template version before deployment; those fields live in Edge secrets/code.
  select jsonb_build_object('email',payload->'email','unsubscribe_token',payload->'unsubscribe_token',
   'events',jsonb_agg(jsonb_build_object('event_key',item->'event_key','title',item->'event_data'->'title',
    'url',item->'event_data'->'url','date',item->'event_data'->'date','city',item->'event_data'->'city',
    'state',item->'event_data'->'state') order by item->>'event_key'))
  into fingerprint from jsonb_array_elements(payload->'events') item;
  select payload_fingerprint into previous_fingerprint from public.uam_alert_delivery
   where user_id=member.user_id and batch_id=bid and payload_fingerprint is not null limit 1;
  if previous_fingerprint is not null and previous_fingerprint<>fingerprint then
   -- Delivery may already have happened before a timeout. Suppress the entire old batch
   -- rather than reusing its provider key with changed content or assigning a duplicate key.
   update public.uam_alert_delivery set status='suppressed',lease_until=null
    where user_id=member.user_id and batch_id=bid and status in('pending','sending');
   continue;
  end if;
  update public.uam_alert_delivery set payload_fingerprint=fingerprint
   where user_id=member.user_id and batch_id=bid and payload_fingerprint is null;
  return next payload;
 end loop;
end $$;

revoke all on function public.uam_claim_alerts() from public,anon,authenticated;
grant execute on function public.uam_claim_alerts() to service_role;
