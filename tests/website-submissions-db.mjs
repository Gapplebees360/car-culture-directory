import { PGlite } from '@electric-sql/pglite';
import { readFile } from 'node:fs/promises';
import assert from 'node:assert/strict';
import { randomUUID, createHash } from 'node:crypto';
const pg=new PGlite();
await pg.exec(`
 create role anon; create role authenticated; create role service_role bypassrls;
 create schema auth; create schema storage;
 create table auth.users(id uuid primary key,email text,email_confirmed_at timestamptz);
 create function auth.uid() returns uuid language sql stable as $$ select nullif(current_setting('request.jwt.claim.sub',true),'')::uuid $$;
 create table storage.buckets(id text primary key,name text,public boolean,file_size_limit bigint,allowed_mime_types text[]);
 create table storage.objects(id uuid default gen_random_uuid(),bucket_id text,name text);
 alter table storage.objects enable row level security;
 create function storage.foldername(text) returns text[] language sql immutable as $$ select string_to_array($1,'/') $$;
 grant usage on schema public,auth,storage to anon,authenticated,service_role;
 grant select on storage.objects to anon,authenticated;
 alter default privileges in schema public grant all on tables to anon,authenticated;
`);
await pg.exec(await readFile(new URL('../supabase/migrations/20261113_community.sql',import.meta.url),'utf8'));
await pg.exec(await readFile(new URL('../supabase/proposals/website-submissions.sql',import.meta.url),'utf8'));
const owner=randomUUID(),other=randomUUID(),unverified=randomUUID(),moderator=randomUUID();
for(const [id,email,confirmed] of [[owner,'owner@example.test',true],[other,'other@example.test',true],[unverified,'pending@example.test',false],[moderator,'mod@example.test',true]]){
 await pg.query('insert into auth.users(id,email,email_confirmed_at) values($1,$2,case when $3 then now() else null end)',[id,email,confirmed]);
}
await pg.query('insert into public.uam_admins(email) values($1)',['mod@example.test']);
const claim=async(id,role='authenticated')=>{await pg.exec('reset role');await pg.query("select set_config('request.jwt.claim.sub',$1,false)",[id||'']);await pg.exec('set role '+role);};
const reset=()=>pg.exec('reset role');
const submit=async url=>(await pg.query('select public.uam_submit_website($1) as result',[url])).rows[0].result;
const jobs=async(limit=3)=>(await pg.query('select public.uam_claim_websites($1) as result',[limit])).rows.map(r=>r.result);
const finish=async(job,report)=>(await pg.query('select public.uam_finish_website($1,$2,$3::jsonb) as result',[job.id,job.lease_token,JSON.stringify(report)])).rows[0].result;
const date=(await pg.query('select (current_date+2)::text as d')).rows[0].d;
const event=(n,changes={})=>{
 const e={title:'Regional Car Show '+n,date,end_date:date,city:'Tacoma',state:'WA',venue:'Garage Hall',category:'Car Show',
 url:'https://events.example.com/event/'+n,description:'An automotive car show with published details.',...changes};
 e.source_id=e.url+'|'+createHash('sha256').update(JSON.stringify([e.title,e.city,e.state,e.venue])).digest('hex').slice(0,16);
 return e;
};
const report=events=>({automotive:true,events,duplicates:[],rejected:[],notes:[]});
await claim('', 'anon');await assert.rejects(()=>submit('https://events.example.com/'),/permission denied/);
await claim(unverified);await assert.rejects(()=>submit('https://events.example.com/'),/verified email/);
await claim(owner);
for(const url of ['http://events.example.com/','https://127.0.0.1/','https://localhost/','https://private.local/','https://user:pass@events.example.com/','https://events.example.com:444/','https://[::1]/'])await assert.rejects(()=>submit(url),/public HTTPS/);
const first=await submit('HTTPS://EVENTS.EXAMPLE.COM:443/calendar#section');
assert.equal(first.url,'https://events.example.com/calendar');
assert.equal((await submit(first.url)).id,first.id);
await assert.rejects(()=>pg.query('select public.uam_claim_websites(3)'),/permission denied/);
await assert.rejects(()=>pg.query('select lease_token from public.uam_website_submissions'),/permission denied/);
await claim(other);assert.equal((await pg.query('select id from public.uam_website_submissions')).rows.length,0);
const otherSubmission=await submit(first.url);assert.notEqual(otherSubmission.id,first.id);
await claim('', 'service_role');let batch=await jobs(1);assert.equal(batch.length,1);let job=batch[0];
await assert.rejects(()=>pg.query('select public.uam_finish_website($1,$2,$3)',[job.id,randomUUID(),JSON.stringify(report([]))]),/lease/);
// Existing higher-priority listing is never overwritten by the submitted site.
const existingKey='imported:'+'a'.repeat(64);
await pg.query('insert into public.uam_events(event_key,event_data,approved) values($1,$2,true)',[existingKey,JSON.stringify(event(1,{source:'SCCA',url:'https://original.example.com/one'}))]);
let result=await finish(job,report([event(1),event(2)]));assert.equal(result.accepted,1);assert.equal(result.duplicates,1);assert.equal(result.source_enrolled,true);
const imported=(await pg.query("select event_key,event_data from public.uam_events where event_data->>'source' like 'Website:%'")).rows[0];
assert.equal(imported.event_data.source,'Website: events.example.com');
const expected='imported:'+createHash('sha256').update(JSON.stringify([imported.event_data.source,imported.event_data.source_id,date])).digest('hex');
assert.equal(imported.event_key,expected);assert.equal(imported.event_data.event_key,expected);
assert.equal((await pg.query('select event_data from public.uam_events where event_key=$1',[existingKey])).rows[0].event_data.source,'SCCA');
assert.equal((await pg.query('select public.uam_export_website_events() as event')).rows.length,1);
await claim(owner);const own=(await pg.query('select status,report from public.uam_website_submissions where id=$1',[first.id])).rows[0];
assert.equal(own.status,'inspected');assert.equal(own.report.imported_count,1);
assert.equal((await pg.query('select * from public.uam_website_sources')).rows.length,0);
await assert.rejects(()=>pg.query('select public.uam_set_website_source($1,false)',['events.example.com']),/Administrator/);
// Recurring checks are due-driven; same-date distinct events sharing an index URL survive.
await claim('', 'service_role');batch=await jobs();job=batch.find(j=>j.id===otherSubmission.id);assert.ok(job);
result=await finish(job,report([event(3,{url:'https://events.example.com/calendar',time:'8 AM'}),event(4,{url:'https://events.example.com/calendar',time:'2 PM'})]));
assert.equal(result.accepted,2);
await reset();await pg.query("update public.uam_website_sources set next_check_at=now()-interval '1 minute'");
await claim('', 'service_role');batch=await jobs();assert.equal(batch.length,1);job=batch[0];
result=await finish(job,report([event(2)]));assert.equal(result.accepted,0);assert.equal(result.duplicates,1);
// Safe parser failures retain the accepted source and its prior listings.
await reset();await pg.query("update public.uam_website_sources set next_check_at=now()-interval '1 minute'");
await claim('', 'service_role');job=(await jobs())[0];
await finish(job,{automotive:false,events:[],safety_failure:true,error:'robots denied',notes:['No bypass attempted.']});
assert.equal((await pg.query('select public.uam_export_website_events()')).rows.length,3);
// Another submitter cannot disable an accepted site by submitting its unrelated contact page.
await claim(other);const contact=await submit('https://events.example.com/contact');
await claim('', 'service_role');job=(await jobs()).find(j=>j.id===contact.id);assert.ok(job);
await finish(job,{automotive:false,events:[],notes:['No automotive evidence on this page.']});
assert.equal((await pg.query('select enabled from public.uam_website_sources where host=$1',['events.example.com'])).rows[0].enabled,true);
assert.equal((await pg.query('select public.uam_export_website_events()')).rows.length,3);
// Confirmed flags cannot be bypassed by reinspection.
await claim(other);await pg.query('select public.uam_flag($1,$2,$3)',[expected,'cancelled','The organizer confirms this date is cancelled.']);
await claim(moderator);const flag=(await pg.query('select id from public.uam_flags where event_key=$1',[expected])).rows[0];
await pg.query('select public.uam_resolve_flag($1,true,$2)',[flag.id,'Confirmed cancellation against the event page']);
await reset();await pg.query("update public.uam_website_sources set next_check_at=now()-interval '1 minute'");await claim('', 'service_role');job=(await jobs())[0];
result=await finish(job,report([event(2)]));assert.equal(result.accepted,0);assert.equal((await pg.query('select approved from public.uam_events where event_key=$1',[expected])).rows[0].approved,false);
// Administrators can suspend a discovered source; users cannot re-enable it by inspection.
await claim(moderator);await pg.query('select public.uam_set_website_source($1,false)',['events.example.com']);
await claim('', 'service_role');assert.equal((await pg.query('select public.uam_export_website_events()')).rows.length,0);
await reset();await pg.query("update public.uam_website_submissions set status='queued',attempts=0 where id=$1",[otherSubmission.id]);await claim('', 'service_role');job=(await jobs())[0];
result=await finish(job,report([event(9)]));assert.equal(result.source_enrolled,false);assert.equal(result.accepted,0);
// Daily submission limit and bounded worker claims.
await claim(owner);await submit('https://second.example.com/');await submit('https://third.example.com/');await assert.rejects(()=>submit('https://fourth.example.com/'),/Daily/);
await claim('', 'service_role');batch=await jobs(999);assert.ok(batch.length<=5);
await reset();await pg.exec("update public.uam_website_submissions set lease_until=now()-interval '1 minute',attempts=3 where status='inspecting'");await claim('', 'service_role');await jobs();
assert.equal((await pg.query("select count(*)::int as n from public.uam_website_submissions where status='inspecting' and attempts>3")).rows[0].n,0);
await claim(owner);await assert.rejects(()=>pg.query('select public.uam_finish_website($1,$2,$3)',[first.id,randomUUID(),'{}']),/permission denied/);
await pg.close();
console.log('Website submission database checks passed: verified ownership, private leases, rate limits, worker leases, safe import/deduplication, stable identity, recurring sources, moderation preservation, suspension and export.');
