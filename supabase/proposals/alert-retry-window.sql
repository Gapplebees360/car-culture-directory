-- REVIEW ONLY: apply after uam_completion_fixes_20261114; no hosted changes made.
-- Unknown historical attempts are suppressed rather than assigned a new retry clock.
alter table public.uam_alert_delivery add column first_attempt_at timestamptz;
update public.uam_alert_delivery set status='suppressed',lease_until=null
 where batch_id is not null and status in('pending','sending');

create or replace function public.uam_claim_alerts() returns setof jsonb language plpgsql security definer set search_path=public,pg_temp as $$
declare member public.uam_profiles; bid uuid; payload jsonb; email_slots int; fingerprint jsonb; previous_fingerprint jsonb;
begin
 -- Conservative app-level free-tier allowance, leaving room for auth emails.
 perform pg_advisory_xact_lock(hashtext('uam-alert-claims'));
 email_slots:=least(20,
  80-(select count(distinct batch_id)::int from public.uam_alert_delivery where sent_at>=date_trunc('day',now()) or(status='sending' and lease_until>now())),
  2400-(select count(distinct batch_id)::int from public.uam_alert_delivery where sent_at>=date_trunc('month',now()) or(status='sending' and lease_until>now())));
 -- Resend retains idempotency keys for 24 hours. Stop uncertain retries
 -- after 23 hours, with a margin for queueing and bounded provider requests.
 update public.uam_alert_delivery set status='suppressed',lease_until=null
 where status in('pending','sending') and batch_id is not null
 and (first_attempt_at is null or first_attempt_at<=now()-interval '23 hours');
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
  update public.uam_alert_delivery set status='sending',lease_until=now()+interval '15 minutes',first_attempt_at=coalesce(first_attempt_at,now()) where user_id=member.user_id and batch_id=bid and status in('pending','sending');
  select jsonb_build_object('user_id',member.user_id,'email',u.email,'batch_id',bid,'retry_before',(select min(first_attempt_at)+interval '23 hours' from public.uam_alert_delivery where user_id=member.user_id and batch_id=bid),'unsubscribe_token',member.unsubscribe_token,
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
