import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { stripTypeScriptTypes } from 'node:module';
import { publicCommunityEvents, publicCommunityFlyer } from '../supabase/functions/community/public-community.mjs';

const now=new Date('2026-11-14T05:00:00Z'); // Still November 13 in Hawaii.
const key=n=>'community:00000000-0000-0000-0000-'+String(n).padStart(12,'0');
const base='https://lswnpxeiagureogrlopy.supabase.co/functions/v1/community/';
const event={title:'Tacoma Cars & Coffee',date:'2026-11-13',end_date:'2026-11-13',state:'WA',city:'Tacoma',venue:'Public coffee venue',category:'Cars & Coffee',url:'https://example.org/meet',time:'8–11 AM Pacific',description:'A car meet with coffee, open to all respectful drivers.',source:'Other',verified_at:'2026-11-13'};
const row=(n=1,changes={})=>({event_key:key(n),approved:true,flyer_path:'private-owner/flyer.png',event_data:{...event},...changes});
function png() {
 const bytes=new Uint8Array(40);bytes.set([137,80,78,71,13,10,26,10]);bytes.set(new TextEncoder().encode('IHDR'),12);
 const view=new DataView(bytes.buffer);view.setUint32(16,400);view.setUint32(20,600);
 return new Blob([bytes],{type:'image/png'});
}
function mock(rows,{blob=png(),error=null,bypass=false}={}) {
 const calls=[],downloads=[];
 return {calls,downloads,storage:{from(bucket){assert.equal(bucket,'uam-flyers');return {async download(path){downloads.push(path);return {data:blob,error};}};}},
  from(table){assert.equal(table,'uam_events');let selected=[...rows],pageLimit=Infinity;
   const q={select(value){calls.push(['select',value]);return q;},
    eq(field,value){calls.push(['eq',field,value]);if(!bypass)selected=selected.filter(r=>r[field]===value);return q;},
    like(field,value){calls.push(['like',field,value]);if(!bypass)selected=selected.filter(r=>r[field].startsWith('community:'));return q;},
    or(value){calls.push(['or',value]);if(!bypass){const today=value.match(/gte\.(\d{4}-\d{2}-\d{2})/)[1];selected=selected.filter(r=>(r.event_data.end_date || r.event_data.date)>=today);}return q;},
    order(field,options){calls.push(['order',field,options]);selected.sort((a,b)=>a.event_key.localeCompare(b.event_key));return q;},
    limit(value){calls.push(['limit',value]);pageLimit=value;return q;},
    gt(field,value){calls.push(['gt',field,value]);if(!bypass)selected=selected.filter(r=>r[field]>value);return q;},
    async maybeSingle(){return {data:selected[0] || null,error};},then(resolve,reject){return Promise.resolve({data:selected.slice(0,pageLimit),error}).then(resolve,reject);}};
   return q;}};
}

test('feed whitelists fields, forces Community, and publishes only stable flyer URLs',async()=>{
 const db=mock([row(1,{user_id:'secret',submission_id:'private',event_data:{...event,image:'https://bad/signed?token=secret',user_id:'private',review_notes:'hidden'}})]);
 const response=await publicCommunityEvents(db,base+'public-events',now), body=await response.json();
 assert.equal(response.status,200);assert.equal(response.headers.get('cache-control'),'no-store');
 assert.equal(body.next_cursor,null);assert.equal(body.events[0].source,'Community');
 assert.equal(body.events[0].image,base+'public-flyer?event='+encodeURIComponent(key(1)));
 for(const forbidden of ['token=','signed','flyer_path','private-owner','user_id','submission_id','review_notes'])assert.ok(!JSON.stringify(body).includes(forbidden));
 assert.equal(body.events[0].event_key,key(1));assert.deepEqual(db.downloads,[]);
});
test('pending, hidden, expired events are excluded even if returned unexpectedly; ongoing survives',async()=>{
 const rows=[row(1,{approved:false}),row(2,{approved:false}),row(3,{event_data:{...event,date:'2026-11-11',end_date:'2026-11-12'}}),row(4,{event_data:{...event,date:'2026-11-10',end_date:'2026-11-14'}})];
 const result=await (await publicCommunityEvents(mock(rows,{bypass:true}),base+'public-events',now)).json();
 assert.deepEqual(result.events.map(e=>e.event_key),[key(4)]);
 assert.equal((await (await publicCommunityEvents(mock([row()]),base+'public-events',new Date('2026-11-14T10:00:00Z'))).json()).events.length,0);
});
test('cursor is bounded and ordered; malformed/injected cursors never reach database',async()=>{
 for(const cursor of ['x','community:%','community:'+ 'a'.repeat(10000),key(1).toUpperCase()]) {
  const db=mock([]);assert.equal((await publicCommunityEvents(db,base+'public-events?cursor='+encodeURIComponent(cursor),now)).status,400);assert.deepEqual(db.calls,[]);
 }
 const rows=Array.from({length:251},(_,i)=>row(i+1));
 const db=mock(rows);const first=await (await publicCommunityEvents(db,base+'public-events?limit=999999',now)).json();
 assert.equal(first.events.length,250);assert.equal(first.next_cursor,key(250));assert.ok(db.calls.some(c=>c[0]==='limit'&&c[1]===250));
 const second=await (await publicCommunityEvents(mock(rows),base+'public-events?cursor='+encodeURIComponent(first.next_cursor),now)).json();
 assert.deepEqual(second.events.map(e=>e.event_key),[key(251)]);assert.equal(second.next_cursor,null);
 assert.equal((await publicCommunityEvents(mock([]),base+'public-events?cursor='+key(1)+'&cursor='+key(2),now)).status,400);
});
test('invalid approved public fields fail closed, database errors do not leak details',async()=>{
 for(const changes of [{url:'javascript:alert(1)'},{state:'XX'},{category:'Unknown'},{title:''},{verified_at:'2026-02-30'}]) {
  const response=await publicCommunityEvents(mock([row(1,{event_data:{...event,...changes}})]),base+'public-events',now);assert.equal(response.status,503);
 }
 const response=await publicCommunityEvents(mock([],{error:{message:'secret database details'}}),base+'public-events',now);assert.equal(response.status,503);assert.ok(!(await response.text()).includes('secret'));
});
test('flyer returns validated raster with no-store and nosniff',async()=>{
 const db=mock([row()]);const response=await publicCommunityFlyer(db,base+'public-flyer?event='+key(1),now);
 assert.equal(response.status,200);assert.equal(response.headers.get('content-type'),'image/png');assert.equal(response.headers.get('cache-control'),'no-store');assert.equal(response.headers.get('x-content-type-options'),'nosniff');assert.equal((await response.arrayBuffer()).byteLength,40);assert.deepEqual(db.downloads,['private-owner/flyer.png']);
});
test('flyer authorization is checked on every request and rejects pending/hidden/expired/missing',async()=>{
 const record=row();const db=mock([record]);assert.equal((await publicCommunityFlyer(db,base+'public-flyer?event='+key(1),now)).status,200);
 record.approved=false;assert.equal((await publicCommunityFlyer(db,base+'public-flyer?event='+key(1),now)).status,404);assert.equal(db.downloads.length,1);
 for(const record of [row(1,{approved:false}),row(1,{event_data:{...event,date:'2026-11-01',end_date:'2026-11-02'}}),row(1,{flyer_path:null})]) {
  const db=mock([record],{bypass:true});assert.equal((await publicCommunityFlyer(db,base+'public-flyer?event='+key(1),now)).status,404);assert.equal(db.downloads.length,0);
 }
 assert.equal((await publicCommunityFlyer(mock([]),base+'public-flyer?event='+key(1),now)).status,404);
});
test('flyer rejects document MIME, signature mismatch, oversize, storage failure, and bad keys',async()=>{
 for(const options of [{blob:new Blob(['<svg></svg>'],{type:'image/svg+xml'})},{blob:new Blob([await png().arrayBuffer()],{type:'image/jpeg'})},{blob:new Blob([new Uint8Array(6*1024*1024+1)],{type:'image/png'})},{error:{message:'private storage failure'}}]) {
  const response=await publicCommunityFlyer(mock([row()],options),base+'public-flyer?event='+key(1),now);assert.equal(response.status,404);assert.ok(!(await response.text()).includes('private'));
 }
 const db=mock([row()]);assert.equal((await publicCommunityFlyer(db,base+'public-flyer?event=../private',now)).status,404);assert.deepEqual(db.calls,[]);
});

test('actual Edge routes retain CORS and moderation-safe response headers',async()=>{
 const edge=await readFile(new URL('../supabase/functions/community/index.ts',import.meta.url),'utf8');
 let handler;
 const origin='https://usautomeets.com',cors={'Access-Control-Allow-Origin':origin,'Vary':'Origin'};
 new Function('Deno','ORIGIN','cors','json','admin','pathOf','publicCommunityEvents','publicCommunityFlyer',stripTypeScriptTypes(edge.slice(edge.indexOf('Deno.serve('))))(
  {serve:fn=>{handler=fn;}},origin,cors,(value,status=200)=>Response.json(value,{status}),()=>mock([row()]),req=>new URL(req.url).pathname.split('/community')[1],
  (db,url)=>publicCommunityEvents(db,url,now),(db,url)=>publicCommunityFlyer(db,url,now));
 for(const route of ['public-events','public-flyer?event='+key(1)]) {
  const response=await handler(new Request(base+route));assert.equal(response.status,200);
  assert.equal(response.headers.get('access-control-allow-origin'),origin);assert.equal(response.headers.get('cache-control'),'no-store');assert.equal(response.headers.get('x-content-type-options'),'nosniff');
 }
 const forbidden=await handler(new Request(base+'public-events',{headers:{Origin:'https://unrelated.example'}}));assert.equal(forbidden.status,403);
});
