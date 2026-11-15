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

await pg.exec(await readFile(new URL('../supabase/proposals/community-completion.sql',import.meta.url),'utf8'));
await pg.exec(await readFile(new URL('../supabase/proposals/alert-retry-window.sql',import.meta.url),'utf8'));
const owner=randomUUID(),moderator=randomUUID(),recipient=randomUUID();
for(const [id,email] of [[owner,'owner@example.test'],[moderator,'mod@example.test'],[recipient,'recipient@example.test']])await pg.query('insert into auth.users(id,email,email_confirmed_at) values($1,$2,now())',[id,email]);
await pg.query('insert into public.uam_admins(email) values($1)',['mod@example.test']);
const claim=async(id,role='authenticated')=>{await pg.exec('reset role');await pg.query("select set_config('request.jwt.claim.sub',$1,false)",[id||'']);await pg.exec('set role '+role);};
const reset=()=>pg.exec('reset role');
const date=(await pg.query("select (current_date+2)::text as date")).rows[0].date;
const key=id=>'imported:'+createHash('sha256').update(id).digest('hex');
const data=id=>({title:'Dated car meet '+id,date,end_date:date,city:'Tacoma',state:'WA',venue:'Test venue',category:'Cars & Coffee',url:'https://example.test/event/'+id,description:'A public test meet with an explicit date and venue',source:'Fixture'});
const row=id=>({event_key:key(id),event_data:data(id)});
const reconcile=items=>pg.query('select public.uam_reconcile_catalog($1::jsonb) as result',[JSON.stringify(items)]);
// Failure keeps a one-minute cooldown; a successful claim still holds the hour.
await claim('', 'service_role');
assert.equal((await pg.query('select public.uam_claim_catalog_refresh() as yes')).rows[0].yes,true);
await pg.query('select public.uam_fail_catalog_refresh()');
assert.equal((await pg.query('select public.uam_claim_catalog_refresh() as yes')).rows[0].yes,false);
await reset();await pg.exec("update public.uam_job_locks set last_run=last_run-interval '61 seconds' where name='catalog'");
await claim('', 'service_role');
assert.equal((await pg.query('select public.uam_claim_catalog_refresh() as yes')).rows[0].yes,true);
assert.equal((await pg.query('select public.uam_claim_catalog_refresh() as yes')).rows[0].yes,false);
await reset();await pg.exec("update public.uam_job_locks set last_run=now()-interval '59 minutes' where name='catalog'");
await claim('', 'service_role');assert.equal((await pg.query('select public.uam_claim_catalog_refresh() as yes')).rows[0].yes,false);
await reset();await pg.exec("update public.uam_job_locks set last_run=now()-interval '61 minutes' where name='catalog'");
await claim('', 'service_role');assert.equal((await pg.query('select public.uam_claim_catalog_refresh() as yes')).rows[0].yes,true);
// The RPC is unavailable to browsers, including registered members.
await claim('', 'anon');await assert.rejects(()=>reconcile([]),/permission denied/);
await assert.rejects(()=>pg.query('select public.uam_fail_catalog_refresh()'),/permission denied/);
await claim(owner);await assert.rejects(()=>reconcile([]),/permission denied/);
await assert.rejects(()=>pg.query('select public.uam_fail_catalog_refresh()'),/permission denied/);
await claim('', 'service_role');await reconcile([row('A'),row('B')]);await reset();
await claim(recipient);await pg.query('select public.uam_flag($1,$2,$3)',[key('A'),'cancelled','The organizer says this date was cancelled.']);
await claim(moderator);let flag=(await pg.query('select id from public.uam_flags where event_key=$1',[key('A')])).rows[0];
await pg.query('select public.uam_resolve_flag($1,$2,$3)',[flag.id,true,'Confirmed cancellation against the organizer source']);
await reset();const result=(await reconcile([row('A')])).rows[0].result;
assert.equal(result.retired,1);
assert.equal((await pg.query('select approved from public.uam_events where event_key=$1',[key('A')])).rows[0].approved,false);
assert.equal((await pg.query('select approved from public.uam_events where event_key=$1',[key('B')])).rows[0].approved,false);
const hidden=(await pg.query('select public.uam_hidden_event_keys() as key')).rows.map(r=>r.key);
assert.deepEqual(hidden,[key('A')]);
await reconcile([row('A'),row('B')]);
assert.equal((await pg.query('select approved from public.uam_events where event_key=$1',[key('B')])).rows[0].approved,true);
assert.equal((await pg.query('select approved from public.uam_events where event_key=$1',[key('A')])).rows[0].approved,false);
await assert.rejects(()=>reconcile([row('C'),{event_key:'invalid',event_data:data('invalid')}]),/Invalid catalog/);
await assert.rejects(()=>pg.query('select public.uam_reconcile_catalog($1::jsonb)',[null]),/bounded catalog/);
assert.equal((await pg.query('select * from public.uam_events where event_key=$1',[key('C')])).rows.length,0);
assert.equal((await pg.query('select approved from public.uam_events where event_key=$1',[key('B')])).rows[0].approved,true);
// Reporting an approved community submission must align its owner-visible status.
const submission=randomUUID(),communityKey='community:'+submission;
await pg.query("insert into public.uam_submissions(id,user_id,event_data,flyer_path,flyer_hash,event_date,status) values($1,$2,$3,'fixture.png','fixturehash',$4,'approved')",[submission,owner,JSON.stringify(data('community')),date]);
await pg.query('insert into public.uam_events(event_key,event_data,submission_id,approved) values($1,$2,$3,true)',[communityKey,JSON.stringify(data('community')),submission]);
await claim(recipient);await pg.query('select public.uam_flag($1,$2,$3)',[communityKey,'not_real','The flyer does not match the stated venue.']);
await claim(moderator);flag=(await pg.query('select id from public.uam_flags where event_key=$1',[communityKey])).rows[0];
await pg.query('select public.uam_resolve_flag($1,$2,$3)',[flag.id,true,'Confirmed venue mismatch after reviewing flyer']);
await reset();assert.equal((await pg.query('select status from public.uam_submissions where id=$1',[submission])).rows[0].status,'hidden');
await reconcile([]);assert.equal((await pg.query('select * from public.uam_events where event_key=$1',[communityKey])).rows.length,1);
assert.equal((await pg.query("select count(*)::int as count from public.uam_events where approved and event_key like 'imported:%'")).rows[0].count,0);
// New-only alert matching, stable exact retries, and conservative changed-payload suppression.
await claim(recipient);await pg.query("insert into public.uam_alert_locations(user_id,state,city) values($1,'WA','Tacoma')",[recipient]);
await pg.query('update public.uam_profiles set alerts_enabled=true,consented_at=now() where user_id=$1',[recipient]);
await reset();
async function addAlertEvent(id){await pg.query("insert into public.uam_events(event_key,event_data,approved,first_seen_at) values($1,$2,true,now()+interval '1 second')",[key(id),JSON.stringify(data(id))]);}
async function batches(){return (await pg.query('select * from public.uam_claim_alerts() as payload')).rows.map(r=>r.payload);}
async function expire(){await pg.exec("update public.uam_alert_delivery set lease_until=now()-interval '1 minute' where status='sending'");}
await addAlertEvent('retry-1');await addAlertEvent('retry-2');
let first=(await batches())[0];assert.equal(first.events.length,2);await expire();
// Non-rendered scrape metadata does not invalidate an otherwise identical retry.
await pg.query("update public.uam_events set event_data=event_data||jsonb_build_object('verified_at','2099-01-01') where event_key=$1",[key('retry-1')]);
let retry=(await batches())[0];assert.equal(retry.batch_id,first.batch_id);assert.equal(retry.events.length,2);
await expire();await pg.query('update public.uam_events set approved=false where event_key=$1',[key('retry-1')]);
assert.deepEqual(await batches(),[]);
assert.deepEqual((await pg.query('select distinct status from public.uam_alert_delivery where batch_id=$1',[first.batch_id])).rows.map(r=>r.status),['suppressed']);
await addAlertEvent('recipient-change');first=(await batches())[0];await expire();
await pg.query('update auth.users set email=$1 where id=$2',['updated@example.test',recipient]);
assert.deepEqual(await batches(),[]);
assert.equal((await pg.query('select status from public.uam_alert_delivery where batch_id=$1',[first.batch_id])).rows[0].status,'suppressed');
// Retrying after an uncertain delivery cannot outlive provider duplicate protection.
await addAlertEvent('retry-window');first=(await batches())[0];
assert.ok(Number.isFinite(Date.parse(first.retry_before)));
assert.deepEqual(await batches(),[]); // Active lease blocks concurrent sends.
await expire();retry=(await batches())[0];
assert.equal(retry.batch_id,first.batch_id);assert.equal(retry.retry_before,first.retry_before);
await pg.exec("update public.uam_alert_delivery set first_attempt_at=now()-interval '23 hours',lease_until=now()-interval '1 minute' where status='sending'");
assert.deepEqual(await batches(),[]);
assert.equal((await pg.query('select status from public.uam_alert_delivery where batch_id=$1',[first.batch_id])).rows[0].status,'suppressed');
await addAlertEvent('provider-failed');first=(await batches())[0];
await pg.query('select public.uam_finish_alerts($1,$2,false)',[recipient,[key('provider-failed')]]);
retry=(await batches())[0];assert.equal(retry.batch_id,first.batch_id);assert.equal(retry.retry_before,first.retry_before);
await pg.query('select public.uam_finish_alerts($1,$2,true)',[recipient,[key('provider-failed')]]);
assert.deepEqual(await batches(),[]); // Recorded successful sends never replay.
await addAlertEvent('unknown-attempt');first=(await batches())[0];
await pg.query('update public.uam_alert_delivery set first_attempt_at=null where batch_id=$1',[first.batch_id]);await expire();
assert.deepEqual(await batches(),[]);
await claim(recipient);assert.deepEqual((await pg.query('select payload_fingerprint from public.uam_alert_delivery')).rows,[]);
await pg.close();
// Execute the actual Edge sync routine with fake network/DB boundaries. Invalid
// snapshots must fail before the service RPC, not silently retire omitted rows.
const {stripTypeScriptTypes}=await import('node:module');
const edge=await readFile(new URL('../supabase/functions/community/index.ts',import.meta.url),'utf8');
const syncSource=stripTypeScriptTypes(edge.slice(edge.indexOf('async function sync(db: any)'),edge.indexOf('\nDeno.serve')));
let feed=[data('edge')],calls=[];
const sync=new Function('fetch','eventKey','check','ORIGIN',syncSource+';return sync;')(
 async()=>({ok:true,json:async()=>feed}),async()=>key('edge'),result=>{if(result.error)throw result.error;return result.data;},'https://usautomeets.com');
const boundary={rpc:async(name,args)=>{calls.push({name,args});return{data:{synced:args.p_rows.length,retired:0}};}};
await sync(boundary);assert.equal(calls.length,1);assert.equal(calls[0].name,'uam_reconcile_catalog');
calls=[];feed=[data('edge'),{...data('invalid-date'),date:'2026-02-30'}];
await assert.rejects(()=>sync(boundary),/Invalid published catalog snapshot/);assert.equal(calls.length,0);
feed=[];await sync(boundary);assert.deepEqual(calls[0].args.p_rows,[]);
const originalFailure=new Error('Fixed feed unavailable');let refreshCalls=[],refreshLogs=[];
const refresh=new Function('fetch','eventKey','check','ORIGIN','console',syncSource+';return refreshCatalog;')(
 async()=>{throw originalFailure;},async()=>key('edge'),result=>{if(result.error)throw result.error;return result.data;},'https://usautomeets.com',{error:message=>refreshLogs.push(message)});
await assert.rejects(()=>refresh({rpc:async name=>{refreshCalls.push(name);return name==='uam_claim_catalog_refresh'?{data:true}:{error:new Error('Cooldown update failed')};}}),error=>error===originalFailure);
assert.deepEqual(refreshCalls,['uam_claim_catalog_refresh','uam_fail_catalog_refresh']);
assert.deepEqual(refreshLogs,['Could not shorten failed catalog refresh cooldown']);
console.log('Completion proposal PostgreSQL regressions passed: atomic retirement/reappearance, confirmed suppressions, hidden submission status, stable retry fingerprint, changed-batch suppression, service-only RPC and private payloads.');
