import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { stripTypeScriptTypes } from 'node:module';
const edge=await readFile(new URL('../supabase/functions/community/index.ts',import.meta.url),'utf8');
const handlerSource=stripTypeScriptTypes(edge.slice(edge.indexOf('Deno.serve(')));
const batch={user_id:'fixture-user',batch_id:'fixture-batch',email:'recipient@example.test',unsubscribe_token:'fixture-token',events:[{event_key:'fixture-key',event_data:{url:'https://example.org/car-meet',title:'Cars & Coffee',date:'2026-12-01',city:'Tacoma',state:'WA'}}]};
async function invoke(retryBefore,{reject=false,throwNetwork=false,finishError=false}={}) {
 let handler,requests=[],finished=[];
 const db={rpc:async(name,args)=>name==='uam_claim_alerts'?{data:[{...batch,retry_before:retryBefore}]}:(finished.push(args),finishError?{error:new Error('Fixture DB error')}:{data:null})};
 const check=result=>{if(result.error)throw result.error;return result.data;};
 const factory=new Function('Deno','admin','pathOf','cors','json','secret','check','ORIGIN','escapeHtml','fetch','console',handlerSource);
 factory({serve:fn=>{handler=fn;}},()=>db,()=>'/alerts/run',{},(body,status=200)=>Response.json(body,{status}),()=> 'fixture-only',check,'https://example.org',value=>value,
  async(url,options)=>{requests.push({url,options});if(throwNetwork)throw new Error('Fixture network failure');return {ok:!reject,status:reject?429:200};},{error:()=>{}});
 const response=await handler(new Request('https://example.org/community/alerts/run',{method:'POST',headers:{Authorization:'Bearer fixture-only'}}));
 return {response,body:await response.json(),requests,finished};
}
for(const deadline of [undefined,'bad-date',new Date(Date.now()-1000).toISOString(),new Date(Date.now()+5000).toISOString()]) {
 const result=await invoke(deadline);assert.equal(result.response.status,502);assert.equal(result.requests.length,0);assert.equal(result.finished.length,0);
}
const deadline=new Date(Date.now()+3600000).toISOString();
let result=await invoke(deadline);
assert.equal(result.response.status,200);assert.equal(result.body.sent,1);assert.equal(result.finished[0].p_sent,true);
assert.equal(result.requests[0].url,'https://api.resend.com/emails');assert.ok(result.requests[0].options.signal instanceof AbortSignal);
assert.equal(result.requests[0].options.headers['Idempotency-Key'],'uam-alert-fixture-batch');
result=await invoke(deadline,{reject:true});assert.equal(result.response.status,502);assert.equal(result.finished[0].p_sent,false);
result=await invoke(deadline,{throwNetwork:true});assert.equal(result.response.status,400);assert.equal(result.finished.length,0);
result=await invoke(deadline,{finishError:true});assert.equal(result.response.status,400);assert.equal(result.requests.length,1);
const retry=await invoke(deadline);
assert.equal(retry.requests[0].options.headers['Idempotency-Key'],result.requests[0].options.headers['Idempotency-Key']);
assert.equal(retry.requests[0].options.body,result.requests[0].options.body);
console.log('Alert delivery local boundaries passed: retry cutoff, bounded request, provider rejection, uncertain network/DB completion, stable payload/key. No network requests made.');
