-- DRAFT website submission/inspection queue. Apply only with an approved release.
-- Network/DNS/redirect safety and robots enforcement are performed by the bounded worker,
-- never by database HTTP calls. This proposal does not change flyer submission rules.
create table public.uam_website_submissions(
 id uuid primary key default gen_random_uuid(),user_id uuid not null references public.uam_profiles(user_id),
 url text not null,host text not null,status text not null default 'queued'
 check(status in('queued','inspecting','inspected','not_automotive','failed')),
 report jsonb not null default '{}'::jsonb,created_at timestamptz not null default now(),
 inspected_at timestamptz,lease_token uuid,lease_until timestamptz,attempts integer not null default 0,
 unique(user_id,url));
create table public.uam_website_sources(
 host text primary key,url text not null,submission_id uuid not null references public.uam_website_submissions(id),
 enabled boolean not null default true,suspended boolean not null default false,
 next_check_at timestamptz not null default now(),last_checked_at timestamptz,
 last_status text not null default 'enrolled',created_at timestamptz not null default now());
create table public.uam_website_event_links(
 host text not null references public.uam_website_sources(host),event_key text not null references public.uam_events(event_key) on delete cascade,
 last_seen_at timestamptz not null default now(),primary key(host,event_key));
create index uam_website_queue on public.uam_website_submissions(status,created_at);
create index uam_website_user on public.uam_website_submissions(user_id,created_at);
create index uam_website_due on public.uam_website_sources(next_check_at) where enabled and not suspended;
alter table public.uam_website_submissions enable row level security;
alter table public.uam_website_sources enable row level security;
alter table public.uam_website_event_links enable row level security;
revoke all on public.uam_website_submissions,public.uam_website_sources,public.uam_website_event_links from public,anon,authenticated;
grant select(id,user_id,url,host,status,report,created_at,inspected_at) on public.uam_website_submissions to authenticated;
grant select on public.uam_website_sources to authenticated;
grant all on public.uam_website_submissions,public.uam_website_sources,public.uam_website_event_links to service_role;
create policy uam_website_own_read on public.uam_website_submissions for select to authenticated using(user_id=(select auth.uid()) or (select public.uam_is_admin()));
create policy uam_website_admin_sources on public.uam_website_sources for select to authenticated using((select public.uam_is_admin()));

create function public.uam_website_url(p_url text) returns text language plpgsql immutable security invoker set search_path=public,pg_temp as $$
declare value text; authority text; host text; tail text;
begin
 value:=btrim(p_url);
 if value is null or length(value) not between 12 and 1000 or value~'[[:space:][:cntrl:]]' or position(chr(92) in value)>0 or value!~*'^https://' then raise exception 'Use a public HTTPS website address'; end if;
 value:=split_part(value,'#',1);
 authority:=substring(value from '(?i)^https://([^/?#]+)');
 host:=lower(regexp_replace(authority,':443$',''));
 if host is null or host!~'^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)*\.[a-z]{2,63}$'
  or host~'\.(local|internal|test|invalid|example|localhost|onion)$' or length(host)>253 then raise exception 'Use a public HTTPS domain without credentials or a custom port'; end if;
 tail:=substring(value from length('https://')+length(authority)+1);
 if tail='' then tail:='/'; elsif left(tail,1)='?' then tail:='/'||tail; end if;
 return 'https://'||host||tail;
end $$;
revoke all on function public.uam_website_url(text) from public,anon,authenticated;
grant execute on function public.uam_website_url(text) to service_role;
create function public.uam_website_host(p_url text) returns text language sql immutable security invoker set search_path=public,pg_temp as $$
 select regexp_replace(substring(public.uam_website_url(p_url) from '^https://([^/]+)'),'\Awww\.','') $$;
revoke all on function public.uam_website_host(text) from public,anon,authenticated;
grant execute on function public.uam_website_host(text) to service_role;

create function public.uam_submit_website(p_url text) returns jsonb language plpgsql security definer set search_path=public,pg_temp as $$
declare canonical text; site_host text; existing public.uam_website_submissions;
begin
 if not public.uam_verified() then raise exception 'Sign in with a verified email before submitting a website'; end if;
 perform 1 from public.uam_profiles where user_id=auth.uid() for update;
 if exists(select 1 from public.uam_profiles where user_id=auth.uid() and suspended) then raise exception 'Website submissions are suspended pending review'; end if;
 canonical:=public.uam_website_url(p_url); site_host:=public.uam_website_host(canonical);
 select * into existing from public.uam_website_submissions where user_id=auth.uid() and url=canonical;
 if found and (existing.status in('queued','inspecting') or existing.created_at>now()-interval '1 day') then
  return jsonb_build_object('id',existing.id,'status',existing.status,'url',existing.url);
 end if;
 if (select count(*) from public.uam_website_submissions where user_id=auth.uid() and created_at>now()-interval '1 day')>=3 then raise exception 'Daily website submission limit reached'; end if;
 insert into public.uam_website_submissions(user_id,url,host) values(auth.uid(),canonical,site_host)
 on conflict(user_id,url) do update set status='queued',report='{}'::jsonb,created_at=now(),lease_token=null,lease_until=null,attempts=0
 returning * into existing;
 return jsonb_build_object('id',existing.id,'status',existing.status,'url',existing.url);
end $$;
revoke all on function public.uam_submit_website(text) from public,anon;
grant execute on function public.uam_submit_website(text) to authenticated;

create function public.uam_claim_websites(p_limit integer default 3) returns setof jsonb language plpgsql security invoker set search_path=public,pg_temp as $$
declare job public.uam_website_submissions;
begin
 update public.uam_website_submissions set status=case when attempts>=3 then 'failed' else 'queued' end,lease_token=null,lease_until=null
 where status='inspecting' and lease_until<now();
 update public.uam_website_submissions q set status='queued',attempts=0
 from public.uam_website_sources s where s.submission_id=q.id and s.enabled and not s.suspended and s.next_check_at<=now()
 and q.status in('inspected','not_automotive','failed');
 for job in select * from public.uam_website_submissions where status='queued' order by created_at,id limit least(5,greatest(1,coalesce(p_limit,3))) for update skip locked
 loop
  update public.uam_website_submissions set status='inspecting',lease_token=gen_random_uuid(),lease_until=now()+interval '10 minutes',attempts=attempts+1
  where id=job.id returning * into job;
  update public.uam_website_sources set next_check_at=now()+interval '1 day' where submission_id=job.id;
  return next jsonb_build_object('id',job.id,'url',job.url,'site_host',job.host,'lease_token',job.lease_token);
 end loop;
end $$;
revoke all on function public.uam_claim_websites(integer) from public,anon,authenticated;
grant execute on function public.uam_claim_websites(integer) to service_role;

create function public.uam_finish_website(p_id uuid,p_lease uuid,p_report jsonb) returns jsonb language plpgsql security invoker set search_path=public,pg_temp as $$
declare job public.uam_website_submissions; item jsonb; event jsonb; canonical text; source_id text; identity text; k text; d date; finish date;
 source_name text; accepted integer:=0; duplicate_count integer:=0; rejected_count integer:=0;
 automotive boolean; failed boolean; source_enabled boolean; duplicate_key text; title_norm text; city_norm text; venue_norm text; saved_report jsonb;
begin
 select * into strict job from public.uam_website_submissions where id=p_id for update;
 if job.status<>'inspecting' or job.lease_token is distinct from p_lease or job.lease_until<now() then raise exception 'Inspection lease expired or does not match'; end if;
 if p_report is null or jsonb_typeof(p_report)<>'object' or octet_length(p_report::text)>2000000
  or jsonb_typeof(p_report->'automotive') is distinct from 'boolean' or jsonb_typeof(p_report->'events') is distinct from 'array'
  or jsonb_array_length(p_report->'events')>100 then raise exception 'Invalid bounded inspection report'; end if;
 automotive:=(p_report->>'automotive')::boolean;
 failed:=coalesce(p_report->>'safety_failure','false')<>'false' or coalesce(p_report->>'error','')<>'';
 if failed or not automotive then
  saved_report:=jsonb_build_object('automotive',false,'source_enrolled',false,'imported_count',0,'duplicate_count',0,'rejected_count',jsonb_array_length(p_report->'events'),
   'error',left(coalesce(p_report->>'error',''),500),'notes',case when jsonb_typeof(p_report->'notes')='array' then (select coalesce(jsonb_agg(v),'[]'::jsonb) from (select left(value#>>'{}',300) v from jsonb_array_elements(p_report->'notes') limit 20) n) else '[]'::jsonb end);
  update public.uam_website_submissions set status=case when failed then 'failed' else 'not_automotive' end,report=saved_report,inspected_at=now(),lease_token=null,lease_until=null where id=job.id;
  update public.uam_website_sources set last_checked_at=now(),last_status=case when failed then 'failed' else 'not_automotive' end,next_check_at=now()+interval '7 days',enabled=case when failed then enabled else false end where host=job.host and submission_id=job.id;
  if not failed and exists(select 1 from public.uam_website_sources where host=job.host and submission_id=job.id) then update public.uam_events e set approved=false,updated_at=now() from public.uam_website_event_links l where l.host=job.host and e.event_key=l.event_key; end if;
  return jsonb_build_object('accepted',0,'duplicates',0,'source_enrolled',false,'status',case when failed then 'failed' else 'not_automotive' end);
 end if;
 perform pg_advisory_xact_lock(hashtext('uam-website-import'));
 insert into public.uam_website_sources(host,url,submission_id,next_check_at,last_checked_at,last_status)
 values(job.host,job.url,job.id,now()+interval '1 day',now(),'inspected')
 on conflict(host) do update set
  url=case when not public.uam_website_sources.enabled and not public.uam_website_sources.suspended then excluded.url else public.uam_website_sources.url end,
  submission_id=case when not public.uam_website_sources.enabled and not public.uam_website_sources.suspended then excluded.submission_id else public.uam_website_sources.submission_id end,
  enabled=not public.uam_website_sources.suspended,next_check_at=now()+interval '1 day',last_checked_at=now(),last_status='inspected';
 select enabled and not suspended into source_enabled from public.uam_website_sources where host=job.host;
 if source_enabled then
 for item in select value from jsonb_array_elements(p_report->'events')
 loop
  if jsonb_typeof(item)<>'object' or length(btrim(item->>'title')) not between 5 and 160 or length(btrim(item->>'city')) not between 2 and 80
   or length(btrim(item->>'venue')) not between 3 and 200 or jsonb_typeof(item->'title') is distinct from 'string'
   or jsonb_typeof(item->'city') is distinct from 'string' or jsonb_typeof(item->'venue') is distinct from 'string'
   or coalesce(item->>'state','')<>all(string_to_array('AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY',' '))
   or coalesce(item->>'category','') not in('Cars & Coffee','Car Show','Pop-Up Meet','Cruise Night','Track / Drag','Autocross','Road Rally','Rallycross')
   or coalesce(item->>'date','')!~'^\d{4}-\d{2}-\d{2}$'
   or concat(item->>'title',' ',item->>'description')!~*'\m(car|cars|automotive|autocross|rallycross|drag racing|track day|hot rods?|cruise.?in|truck show|cars? (&|and) coffee|caffeine (&|and) gasoline)\M'
   then raise exception 'Invalid automotive event in inspection report'; end if;
  d:=(item->>'date')::date; finish:=coalesce(nullif(item->>'end_date',''),item->>'date')::date;
  if finish<d or finish<current_date-1 or d>current_date+366 or finish>current_date+366 then raise exception 'Invalid upcoming event date'; end if;
  canonical:=public.uam_website_url(item->>'url');
  if public.uam_website_host(canonical)<>job.host then raise exception 'Event evidence must belong to the inspected website'; end if;
  source_id:=item->>'source_id';
  if source_id is null or length(source_id)>1500 or left(source_id,length(canonical)+1)<>canonical||'|'
   or substring(source_id from length(canonical)+2)!~'^[a-f0-9]{8,64}$' then raise exception 'Stable event identity is required'; end if;
  source_name:='Website: '||job.host;
  identity:='['||to_json(source_name)::text||','||to_json(source_id)::text||','||to_json(item->>'date')::text||']';
  k:='imported:'||encode(sha256(convert_to(identity,'UTF8')),'hex');
  event:=jsonb_build_object('title',btrim(item->>'title'),'date',d::text,'end_date',finish::text,'city',btrim(item->>'city'),'state',item->>'state','venue',btrim(item->>'venue'),
   'category',item->>'category','url',canonical,'source',source_name,'source_id',source_id,'event_key',k,'verified_at',current_date::text,
   'description',left(coalesce(item->>'description','Listed on the original event website. Confirm current details before attending.'),1500),'time',left(coalesce(item->>'time','See organizer for schedule'),100));
  if coalesce(item->>'image','')<>'' then event:=event||jsonb_build_object('image',public.uam_website_url(item->>'image'),'image_kind','source_artwork','image_source',canonical); end if;
  title_norm:=regexp_replace(lower(item->>'title'),'[^a-z0-9]+','','g'); city_norm:=regexp_replace(lower(item->>'city'),'[^a-z0-9]+','','g'); venue_norm:=regexp_replace(lower(item->>'venue'),'[^a-z0-9]+','','g');
  select e.event_key into duplicate_key from public.uam_events e where e.event_key<>k and (e.approved or exists(select 1 from public.uam_flags f where f.event_key=e.event_key and f.status='confirmed'))
   and e.event_data->>'date'=d::text and e.event_data->>'state'=item->>'state'
   and regexp_replace(lower(e.event_data->>'city'),'[^a-z0-9]+','','g')=city_norm
   and (regexp_replace(lower(e.event_data->>'title'),'[^a-z0-9]+','','g')=title_norm or
    (split_part(e.event_data->>'url','#',1)=canonical and regexp_replace(lower(e.event_data->>'venue'),'[^a-z0-9]+','','g')=venue_norm
     and (position(title_norm in regexp_replace(lower(e.event_data->>'title'),'[^a-z0-9]+','','g'))>0 or position(regexp_replace(lower(e.event_data->>'title'),'[^a-z0-9]+','','g') in title_norm)>0)))
   limit 1;
  if duplicate_key is not null or exists(select 1 from public.uam_flags where event_key=k and status='confirmed') then duplicate_count:=duplicate_count+1; continue; end if;
  if exists(select 1 from public.uam_events e where e.event_key=k and (e.event_data->>'source'<>source_name or e.event_data->>'source_id'<>source_id
    or regexp_replace(lower(e.event_data->>'title'),'[^a-z0-9]+','','g')<>title_norm
    or regexp_replace(lower(e.event_data->>'city'),'[^a-z0-9]+','','g')<>city_norm or e.event_data->>'state'<>item->>'state')) then
   rejected_count:=rejected_count+1; continue;
  end if;
  if exists(select 1 from public.uam_events where event_key=k) then
   update public.uam_events set event_data=event,approved=true,updated_at=now() where event_key=k;
   duplicate_count:=duplicate_count+1;
  else
   insert into public.uam_events(event_key,event_data,approved) values(k,event,true); accepted:=accepted+1;
  end if;
  insert into public.uam_website_event_links(host,event_key) values(job.host,k) on conflict(host,event_key) do update set last_seen_at=now();
 end loop;
 end if;
 rejected_count:=rejected_count+case when jsonb_typeof(p_report->'rejected')='array' then jsonb_array_length(p_report->'rejected') else 0 end;
 duplicate_count:=duplicate_count+case when jsonb_typeof(p_report->'duplicates')='array' then jsonb_array_length(p_report->'duplicates') else 0 end;
 saved_report:=jsonb_build_object('automotive',true,'source_enrolled',source_enabled,'imported_count',accepted,'duplicate_count',duplicate_count,'rejected_count',rejected_count,
  'notes',case when jsonb_typeof(p_report->'notes')='array' then (select coalesce(jsonb_agg(v),'[]'::jsonb) from (select left(value#>>'{}',300) v from jsonb_array_elements(p_report->'notes') limit 20) n) else '[]'::jsonb end,
  'rejected',case when jsonb_typeof(p_report->'rejected')='array' then (select coalesce(jsonb_agg(jsonb_build_object('reason',left(coalesce(value->>'reason','Not imported'),300),'title',left(coalesce(value->>'title',''),160))),'[]'::jsonb) from (select value from jsonb_array_elements(p_report->'rejected') limit 20) n) else '[]'::jsonb end);
 update public.uam_website_submissions set status='inspected',report=saved_report,inspected_at=now(),lease_token=null,lease_until=null where id=job.id;
 return jsonb_build_object('accepted',accepted,'duplicates',duplicate_count,'source_enrolled',source_enabled,'status','inspected');
end $$;
revoke all on function public.uam_finish_website(uuid,uuid,jsonb) from public,anon,authenticated;
grant execute on function public.uam_finish_website(uuid,uuid,jsonb) to service_role;

create function public.uam_export_website_events() returns setof jsonb language sql stable security invoker set search_path=public,pg_temp as $$
 select e.event_data from public.uam_events e join public.uam_website_event_links l on l.event_key=e.event_key
 join public.uam_website_sources s on s.host=l.host where s.enabled and not s.suspended and e.approved
 and coalesce(e.event_data->>'end_date',e.event_data->>'date')::date>=current_date-1 order by e.event_data->>'date',e.event_key $$;
revoke all on function public.uam_export_website_events() from public,anon,authenticated;
grant execute on function public.uam_export_website_events() to service_role;
create function public.uam_set_website_source(p_host text,p_enabled boolean) returns void language plpgsql security definer set search_path=public,pg_temp as $$
begin
 if not public.uam_is_admin() then raise exception 'Administrator access required'; end if;
 if p_enabled is null then raise exception 'Choose enabled or suspended'; end if;
 update public.uam_website_sources set enabled=p_enabled,suspended=not p_enabled,next_check_at=case when p_enabled then now() else next_check_at end where host=lower(p_host);
 if not found then raise exception 'Website source not found'; end if;
 if not p_enabled then update public.uam_events e set approved=false,updated_at=now() from public.uam_website_event_links l where l.host=lower(p_host) and e.event_key=l.event_key; end if;
end $$;
revoke all on function public.uam_set_website_source(text,boolean) from public,anon;
grant execute on function public.uam_set_website_source(text,boolean) to authenticated;
