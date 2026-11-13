-- Isolated from legacy events/subscribers. No legacy data is modified.
create table public.uam_admins(email text primary key check(email=lower(email)));
insert into public.uam_admins(email) values('insertcoinwa1@gmail.com');
create table public.uam_profiles(
 user_id uuid primary key references auth.users(id) on delete cascade,
 display_name text not null default '' check(length(display_name)<=80),
 suspended boolean not null default false, alerts_enabled boolean not null default false,
 unsubscribe_token uuid not null unique default gen_random_uuid(), consented_at timestamptz,
 created_at timestamptz not null default now());
create function public.uam_is_admin() returns boolean language sql stable security definer set search_path=public,pg_temp as $$
 select exists(select 1 from auth.users u join public.uam_admins a on a.email=lower(u.email)
 where u.id=auth.uid() and u.email_confirmed_at is not null) $$;
create function public.uam_verified() returns boolean language sql stable security definer set search_path=public,pg_temp as $$
 select exists(select 1 from auth.users where id=auth.uid() and email_confirmed_at is not null) $$;
create table public.uam_submissions(
 id uuid primary key default gen_random_uuid(), user_id uuid not null references public.uam_profiles(user_id),
 event_data jsonb not null, flyer_path text not null, flyer_hash text not null,
 event_date date not null, status text not null default 'pending' check(status in('pending','approved','rejected','hidden')),
 review_kind text check(review_kind in('human','automatic')), review_note text not null default '',
 created_at timestamptz not null default now(), reviewed_at timestamptz,
 unique(event_date,flyer_hash));
create table public.uam_events(
 event_key text primary key, event_data jsonb not null, flyer_path text,
 submission_id uuid unique references public.uam_submissions(id),
 approved boolean not null default false, first_seen_at timestamptz not null default now(), updated_at timestamptz not null default now());
create table public.uam_review_log(
 id bigint generated always as identity primary key, submission_id uuid references public.uam_submissions(id),
 action text not null, reviewer_id uuid references auth.users(id), note text not null,
 created_at timestamptz not null default now());
create unique index uam_one_human_approval on public.uam_review_log(submission_id) where action='approve';
create table public.uam_alert_locations(
 id uuid primary key default gen_random_uuid(), user_id uuid not null references public.uam_profiles(user_id) on delete cascade,
 state text not null check(state=any(string_to_array('AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY',' '))),
 city text check(city is null or (length(btrim(city)) between 1 and 80)), created_at timestamptz not null default now());
create unique index uam_location_unique on public.uam_alert_locations(user_id,state,coalesce(lower(btrim(city)),''));
create table public.uam_rsvps(
 user_id uuid references public.uam_profiles(user_id) on delete cascade,
 event_key text references public.uam_events(event_key) on delete cascade,
 status text not null check(status in('saved','going')), created_at timestamptz not null default now(), primary key(user_id,event_key));
create table public.uam_flags(
 id uuid primary key default gen_random_uuid(), event_key text not null references public.uam_events(event_key),
 user_id uuid not null references public.uam_profiles(user_id), reason text not null check(reason in('wrong_date','cancelled','spam','unsafe','not_real','other')),
 details text not null check(length(details) between 10 and 1000), status text not null default 'open' check(status in('open','dismissed','confirmed')),
 review_note text not null default '', created_at timestamptz not null default now(), unique(event_key,user_id));
create table public.uam_alert_delivery(
 user_id uuid references public.uam_profiles(user_id) on delete cascade,
 event_key text references public.uam_events(event_key) on delete cascade,
 status text not null default 'pending' check(status in('pending','sending','sent','suppressed')),
 lease_until timestamptz, sent_at timestamptz, batch_id uuid, primary key(user_id,event_key));
create index uam_submissions_user on public.uam_submissions(user_id,created_at);
create index uam_flags_open on public.uam_flags(event_key) where status='open';
create index uam_events_seen on public.uam_events(first_seen_at) where approved;
create index uam_alert_locations_user on public.uam_alert_locations(user_id);
create index uam_alert_delivery_pending on public.uam_alert_delivery(user_id,status);
create table public.uam_job_locks(name text primary key,last_run timestamptz not null);
alter table public.uam_job_locks enable row level security;
grant all on public.uam_job_locks to service_role;
create function public.uam_claim_catalog_refresh() returns boolean language plpgsql security definer set search_path=public,pg_temp as $$
declare claimed text;
begin
 insert into public.uam_job_locks(name,last_run) values('catalog',now()) on conflict(name) do update set last_run=now()
 where public.uam_job_locks.last_run<now()-interval '1 hour' returning name into claimed;
 return claimed is not null;
end $$;
revoke all on function public.uam_claim_catalog_refresh() from public,anon,authenticated;
grant execute on function public.uam_claim_catalog_refresh() to service_role;
create function public.uam_hidden_event_keys() returns setof text language sql stable security definer set search_path=public,pg_temp as $$
 select event_key from public.uam_events where not approved and event_key like 'imported:%' $$;
grant execute on function public.uam_hidden_event_keys() to anon,authenticated;

create function public.uam_new_profile() returns trigger language plpgsql security definer set search_path=public,pg_temp as $$
begin insert into public.uam_profiles(user_id) values(new.id) on conflict do nothing; return new; end $$;
create trigger uam_new_account after insert on auth.users for each row execute function public.uam_new_profile();
insert into public.uam_profiles(user_id) select id from auth.users on conflict do nothing;

-- Only the authenticated Edge Function service role can create submissions.
create function public.uam_submit(p_user uuid,p_data jsonb,p_flyer text,p_hash text) returns jsonb
language plpgsql security definer set search_path=public,pg_temp as $$
declare sid uuid:=gen_random_uuid(); trusted boolean; approvals int; d date;
begin
 if not exists(select 1 from auth.users where id=p_user and email_confirmed_at is not null) then raise exception 'Verify your email before submitting'; end if;
 perform 1 from public.uam_profiles where user_id=p_user for update;
 if (select suspended from public.uam_profiles where user_id=p_user) then raise exception 'Submissions are suspended pending review'; end if;
 if (select count(*) from public.uam_submissions where user_id=p_user and created_at>now()-interval '1 day')>=3 then raise exception 'Daily submission limit reached'; end if;
 if split_part(p_flyer,'/',1)<>p_user::text or length(p_hash)<>64 then raise exception 'Invalid flyer ownership'; end if;
 if not exists(select 1 from storage.objects where bucket_id='uam-flyers' and name=p_flyer) then raise exception 'A flyer upload is required'; end if;
 d:=(p_data->>'date')::date;
 if d<current_date-1 or d>current_date+366 then raise exception 'Event date is outside the allowed range'; end if;
 if length(btrim(p_data->>'title')) not between 5 and 160 or length(btrim(p_data->>'city')) not between 2 and 80 or length(btrim(p_data->>'venue')) not between 3 and 200 then raise exception 'Complete title, city, and venue are required'; end if;
 if exists(select 1 from public.uam_events where approved and lower(event_data->>'title')=lower(p_data->>'title') and event_data->>'date'=p_data->>'date' and lower(event_data->>'city')=lower(p_data->>'city') and event_data->>'state'=p_data->>'state') then raise exception 'This event is already listed'; end if;
 select count(*) into approvals from public.uam_review_log r join public.uam_submissions s on s.id=r.submission_id where s.user_id=p_user and r.action='approve';
 trusted:=approvals>=4 and not exists(select 1 from public.uam_flags f join public.uam_events e on e.event_key=f.event_key join public.uam_submissions s on s.id=e.submission_id where s.user_id=p_user and f.status='open');
 insert into public.uam_submissions(id,user_id,event_data,flyer_path,flyer_hash,event_date,status,review_kind,reviewed_at)
 values(sid,p_user,p_data,p_flyer,p_hash,d,case when trusted then 'approved' else 'pending' end,case when trusted then 'automatic' else null end,case when trusted then now() else null end);
 if trusted then insert into public.uam_events(event_key,event_data,flyer_path,submission_id,approved) values('community:'||sid,p_data,p_flyer,sid,true); end if;
 return jsonb_build_object('id',sid,'status',case when trusted then 'approved' else 'pending' end,'human_approvals',approvals);
end $$;
revoke all on function public.uam_submit(uuid,jsonb,text,text) from public,anon,authenticated;
grant execute on function public.uam_submit(uuid,jsonb,text,text) to service_role;

create function public.uam_review(p_id uuid,p_action text,p_note text,p_checked boolean) returns void
language plpgsql security definer set search_path=public,pg_temp as $$
declare s public.uam_submissions;
begin
 if not public.uam_is_admin() then raise exception 'Administrator access required'; end if;
 if p_action not in('approve','reject','hide') or length(btrim(p_note))<10 then raise exception 'A review decision and explanation are required'; end if;
 if p_action='approve' and not p_checked then raise exception 'Confirm flyer, date, venue, and organizer evidence first'; end if;
 select * into strict s from public.uam_submissions where id=p_id for update;
 if s.status='approved' and p_action='approve' then raise exception 'Already approved'; end if;
 update public.uam_submissions set status=case p_action when 'approve' then 'approved' when 'reject' then 'rejected' else 'hidden' end,review_kind='human',review_note=p_note,reviewed_at=now() where id=p_id;
 insert into public.uam_review_log(submission_id,action,reviewer_id,note) values(p_id,p_action,auth.uid(),p_note) on conflict do nothing;
 if p_action='approve' then
  insert into public.uam_events(event_key,event_data,flyer_path,submission_id,approved) values('community:'||s.id,s.event_data,s.flyer_path,s.id,true)
  on conflict(event_key) do update set approved=true,event_data=excluded.event_data,updated_at=now();
 else update public.uam_events set approved=false,updated_at=now() where submission_id=p_id;
 end if;
end $$;
revoke all on function public.uam_review(uuid,text,text,boolean) from public,anon;
grant execute on function public.uam_review(uuid,text,text,boolean) to authenticated;

create function public.uam_flag(p_key text,p_reason text,p_details text) returns void
language plpgsql security definer set search_path=public,pg_temp as $$
begin
 if not public.uam_verified() then raise exception 'Verified registration required'; end if;
 perform 1 from public.uam_profiles where user_id=auth.uid() for update;
 if (select count(*) from public.uam_flags where user_id=auth.uid() and created_at>now()-interval '1 day')>=5 then raise exception 'Daily report limit reached'; end if;
 if not exists(select 1 from public.uam_events where event_key=p_key and approved) then raise exception 'Event is not published'; end if;
 insert into public.uam_flags(event_key,user_id,reason,details) values(p_key,auth.uid(),p_reason,p_details);
end $$;
revoke all on function public.uam_flag(text,text,text) from public,anon;
grant execute on function public.uam_flag(text,text,text) to authenticated;

create function public.uam_resolve_flag(p_id uuid,p_confirmed boolean,p_note text) returns void
language plpgsql security definer set search_path=public,pg_temp as $$
declare f public.uam_flags; owner_id uuid;
begin
 if not public.uam_is_admin() or length(btrim(p_note))<10 then raise exception 'Administrator review and explanation required'; end if;
 select * into strict f from public.uam_flags where id=p_id for update;
 update public.uam_flags set status=case when p_confirmed then 'confirmed' else 'dismissed' end,review_note=p_note where id=p_id;
 if p_confirmed then
  update public.uam_events set approved=false,updated_at=now() where event_key=f.event_key;
  select s.user_id into owner_id from public.uam_submissions s join public.uam_events e on e.submission_id=s.id where e.event_key=f.event_key;
  update public.uam_profiles set suspended=true where user_id=owner_id;
 end if;
end $$;
revoke all on function public.uam_resolve_flag(uuid,boolean,text) from public,anon;
grant execute on function public.uam_resolve_flag(uuid,boolean,text) to authenticated;

create function public.uam_change_admin(p_email text) returns void language plpgsql security definer set search_path=public,pg_temp as $$
begin
 if not public.uam_is_admin() then raise exception 'Administrator access required'; end if;
 if not exists(select 1 from auth.users where lower(email)=lower(btrim(p_email)) and email_confirmed_at is not null) then raise exception 'New administrator must register and verify their email first'; end if;
 insert into public.uam_admins(email) values(lower(btrim(p_email))) on conflict do nothing;
 delete from public.uam_admins where email=(select lower(email) from auth.users where id=auth.uid()) and email<>lower(btrim(p_email));
end $$;
revoke all on function public.uam_change_admin(text) from public,anon;
grant execute on function public.uam_change_admin(text) to authenticated;
create function public.uam_trust_status() returns jsonb language sql stable security definer set search_path=public,pg_temp as $$
 select jsonb_build_object('human_approvals',(select count(*) from public.uam_review_log r join public.uam_submissions s on s.id=r.submission_id where s.user_id=auth.uid() and r.action='approve'),
 'suspended',coalesce((select suspended from public.uam_profiles where user_id=auth.uid()),false),
 'open_reports',(select count(*) from public.uam_flags f join public.uam_events e on e.event_key=f.event_key join public.uam_submissions s on s.id=e.submission_id where s.user_id=auth.uid() and f.status='open')) $$;
revoke all on function public.uam_trust_status() from public,anon;
grant execute on function public.uam_trust_status() to authenticated;

-- Every user-facing table has RLS. Counters, moderation, roles, and publication are never client-writable.
alter table public.uam_admins enable row level security;
alter table public.uam_profiles enable row level security;
alter table public.uam_submissions enable row level security;
alter table public.uam_events enable row level security;
alter table public.uam_review_log enable row level security;
alter table public.uam_alert_locations enable row level security;
alter table public.uam_rsvps enable row level security;
alter table public.uam_flags enable row level security;
alter table public.uam_alert_delivery enable row level security;
create policy uam_profile_read on public.uam_profiles for select to authenticated using(user_id=auth.uid() or public.uam_is_admin());
create policy uam_profile_update on public.uam_profiles for update to authenticated using(user_id=auth.uid()) with check(user_id=auth.uid());
revoke update on public.uam_profiles from authenticated;
grant update(display_name,alerts_enabled,consented_at) on public.uam_profiles to authenticated;
create policy uam_submission_read on public.uam_submissions for select to authenticated using(user_id=auth.uid() or public.uam_is_admin());
create policy uam_event_read on public.uam_events for select to anon,authenticated using(approved or public.uam_is_admin());
create policy uam_reviews_read on public.uam_review_log for select to authenticated using(public.uam_is_admin() or exists(select 1 from public.uam_submissions where id=submission_id and user_id=auth.uid()));
create policy uam_location_owner on public.uam_alert_locations for all to authenticated using(user_id=auth.uid()) with check(user_id=auth.uid() and public.uam_verified());
create policy uam_rsvp_read on public.uam_rsvps for select to authenticated using(user_id=auth.uid());
create policy uam_rsvp_insert on public.uam_rsvps for insert to authenticated with check(user_id=auth.uid() and public.uam_verified() and exists(select 1 from public.uam_events where event_key=uam_rsvps.event_key and approved));
create policy uam_rsvp_update on public.uam_rsvps for update to authenticated using(user_id=auth.uid()) with check(user_id=auth.uid());
create policy uam_rsvp_delete on public.uam_rsvps for delete to authenticated using(user_id=auth.uid());
create policy uam_flag_read on public.uam_flags for select to authenticated using(user_id=auth.uid() or public.uam_is_admin());

insert into storage.buckets(id,name,public,file_size_limit,allowed_mime_types)
values('uam-flyers','uam-flyers',false,6291456,array['image/jpeg','image/png','image/webp']) on conflict(id) do nothing;
create policy uam_flyer_read on storage.objects for select to anon,authenticated using(bucket_id='uam-flyers' and
 ((storage.foldername(name))[1]=auth.uid()::text or public.uam_is_admin() or exists(select 1 from public.uam_events where approved and flyer_path=storage.objects.name)));

grant select on public.uam_events to anon,authenticated;
grant select on public.uam_profiles,public.uam_submissions,public.uam_review_log,public.uam_flags to authenticated;
grant select,insert,update,delete on public.uam_alert_locations,public.uam_rsvps to authenticated;
grant all on public.uam_admins,public.uam_profiles,public.uam_submissions,public.uam_events,public.uam_review_log,public.uam_alert_locations,public.uam_rsvps,public.uam_flags,public.uam_alert_delivery to service_role;
grant usage,select on sequence public.uam_review_log_id_seq to service_role;

create function public.uam_claim_alerts() returns setof jsonb language plpgsql security definer set search_path=public,pg_temp as $$
declare member public.uam_profiles; bid uuid; payload jsonb; email_slots int;
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
  if payload->'events' is not null and payload->'events'<>'null'::jsonb then return next payload; end if;
 end loop;
end $$;
create function public.uam_finish_alerts(p_user uuid,p_keys text[],p_sent boolean) returns void language sql security definer set search_path=public,pg_temp as $$
 update public.uam_alert_delivery set status=case when p_sent then 'sent' else 'pending' end,
 sent_at=case when p_sent then now() else null end,lease_until=null where user_id=p_user and event_key=any(p_keys) and status='sending' $$;
revoke all on function public.uam_claim_alerts(),public.uam_finish_alerts(uuid,text[],boolean) from public,anon,authenticated;
grant execute on function public.uam_claim_alerts(),public.uam_finish_alerts(uuid,text[],boolean) to service_role;
