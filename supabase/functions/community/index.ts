import { createClient } from 'npm:@supabase/supabase-js@2.119.0';
import { validateSubmission, inspectFlyer, digest, eventKey, escapeHtml } from './validation.mjs';

const ORIGIN = 'https://usautomeets.com';
const cors = {'Access-Control-Allow-Origin':ORIGIN,'Access-Control-Allow-Headers':'authorization, apikey, content-type, x-client-info','Access-Control-Allow-Methods':'GET,POST,OPTIONS','Vary':'Origin'};
const json = (data: unknown,status=200) => Response.json(data,{status,headers:{...cors,'Cache-Control':'no-store'}});
const secret = (name: string) => Deno.env.get(name) || '';
const admin = () => createClient(secret('SUPABASE_URL'),secret('SUPABASE_SERVICE_ROLE_KEY'),{auth:{persistSession:false,autoRefreshToken:false}});
const check = (result: any) => {if(result.error) throw new Error(result.error.message); return result.data;};
const pathOf = (req: Request) => new URL(req.url).pathname.split('/community')[1] || '/';
async function user(req: Request, db: any) {
  const token=(req.headers.get('authorization')||'').replace(/^Bearer\s+/i,'');
  const result=await db.auth.getUser(token);
  if(result.error || !result.data.user?.email_confirmed_at) throw new Error('Sign in with a verified email first');
  return result.data.user;
}

async function sync(db: any) {
  const response=await fetch(ORIGIN+'/events.json?catalog='+Date.now(),{headers:{'Cache-Control':'no-cache'}});
  if(!response.ok) throw new Error('Published event feed is unavailable');
  const events=await response.json();
  if(!Array.isArray(events)||events.length>10000) throw new Error('Unexpected event feed');
  const rows=[];
  for(const event of events) {
    if(!event.title || !event.url || !/^\d{4}-\d{2}-\d{2}$/.test(event.date) || event.source==='Community') continue;
    rows.push({event_key:await eventKey(event),event_data:event,approved:true,updated_at:new Date().toISOString()});
  }
  const blocked=check(await db.from('uam_flags').select('event_key').eq('status','confirmed'));
  const hidden=new Set(blocked.map((flag: any)=>flag.event_key));
  for(const row of rows) if(hidden.has(row.event_key)) row.approved=false;
  for(let i=0;i<rows.length;i+=100) check(await db.from('uam_events').upsert(rows.slice(i,i+100),{onConflict:'event_key',ignoreDuplicates:false}));
  return {synced:rows.length};
}

Deno.serve(async(req: Request) => {
  if(req.method==='OPTIONS') return new Response(null,{headers:cors});
  const origin=req.headers.get('origin');
  if(origin && origin!==ORIGIN) return json({error:'Origin not permitted'},403);
  const path=pathOf(req);
  try {
    const db=admin();
    if(path==='/health') {
      const ready=await db.from('uam_profiles').select('user_id',{head:true,count:'exact'});
      return json({accounts:!ready.error,submissions:!ready.error,signup_ready:!ready.error&&secret('AUTH_EMAIL_READY')==='true',alerts_ready:!ready.error&&!!secret('RESEND_API_KEY')&&!!secret('EMAIL_FROM')&&!!secret('ALERT_CRON_SECRET')},ready.error?503:200);
    }
    if(path==='/unsubscribe' && req.method==='POST') {
      const body=await req.json();
      if(typeof body.token!=='string'||!/^[0-9a-f-]{36}$/i.test(body.token)) return json({error:'Invalid unsubscribe link'},400);
      check(await db.from('uam_profiles').update({alerts_enabled:false}).eq('unsubscribe_token',body.token));
      return json({unsubscribed:true});
    }
    if(path==='/sync' && req.method==='POST') {
      // Fixed public source only; a database lease limits refresh to once per hour.
      if(!check(await db.rpc('uam_claim_catalog_refresh'))) return json({cached:true});
      return json(await sync(db));
    }
    if(path==='/submit' && req.method==='POST') {
      const member=await user(req,db);
      if(Number(req.headers.get('content-length')||0)>7*1024*1024) return json({error:'Submission is too large'},413);
      const reader=req.body?.getReader();
      if(!reader)throw new Error('A flyer and event details are required');
      const chunks: Uint8Array[]=[];let length=0;
      while(true){const item=await reader.read();if(item.done)break;length+=item.value.length;if(length>7*1024*1024){await reader.cancel();throw new Error('Submission exceeds the 7 MB request limit');}chunks.push(item.value);}
      const form=await new Response(new Blob(chunks),{headers:{'Content-Type':req.headers.get('Content-Type')||''}}).formData();
      const flyer=form.get('flyer');
      if(!(flyer instanceof File)) throw new Error('An event flyer is required');
      const event=validateSubmission(JSON.parse(String(form.get('event')||'{}')));
      const bytes=new Uint8Array(await flyer.arrayBuffer());
      const image=inspectFlyer(bytes,flyer.type);
      const hash=await digest(bytes);
      const key=member.id+'/'+crypto.randomUUID()+'.'+image.extension;
      check(await db.storage.from('uam-flyers').upload(key,bytes,{contentType:image.type,upsert:false}));
      const result=await db.rpc('uam_submit',{p_user:member.id,p_data:event,p_flyer:key,p_hash:hash});
      if(result.error) {await db.storage.from('uam-flyers').remove([key]); throw new Error(result.error.message);}
      return json(result.data,201);
    }
    if(path==='/alerts/run' && req.method==='POST') {
      // This endpoint is deliberately inert until a sender and scheduler secret are configured.
      if(!secret('RESEND_API_KEY')||!secret('EMAIL_FROM')||!secret('ALERT_CRON_SECRET')) return json({error:'Email delivery is not configured'},503);
      if(req.headers.get('authorization')!=='Bearer '+secret('ALERT_CRON_SECRET')) return json({error:'Not authorized'},401);
      const claimed=check(await db.rpc('uam_claim_alerts'));
      let sent=0,failed=0;
      for(const batch of claimed) {
        const keys=batch.events.map((event: any)=>event.event_key).sort();
        const idempotency='uam-alert-'+batch.batch_id;
        const unsubscribe=ORIGIN+'/community.html?unsubscribe='+encodeURIComponent(batch.unsubscribe_token);
        const items=batch.events.map((event: any)=>'<li><a href="'+escapeHtml(event.event_data.url)+'">'+escapeHtml(event.event_data.title)+'</a> — '+escapeHtml(event.event_data.date)+' · '+escapeHtml(event.event_data.city)+', '+escapeHtml(event.event_data.state)+'</li>').join('');
        const response=await fetch('https://api.resend.com/emails',{method:'POST',headers:{Authorization:'Bearer '+secret('RESEND_API_KEY'),'Content-Type':'application/json','Idempotency-Key':idempotency},body:JSON.stringify({from:secret('EMAIL_FROM'),to:[batch.email],subject:'New car events near you · USA Auto Meets',html:'<h1>Your next meet is out there.</h1><ul>'+items+'</ul><p>You requested these local event alerts. <a href="'+unsubscribe+'">Unsubscribe or change your preferences</a>.</p>'})});
        check(await db.rpc('uam_finish_alerts',{p_user:batch.user_id,p_keys:keys,p_sent:response.ok}));
        if(response.ok) sent++;
        else{failed++;console.error('Alert provider rejected batch',{batch_id:batch.batch_id,status:response.status});}
      }
      return json({sent,failed},failed?502:200);
    }
    return json({error:'Not found'},404);
  } catch(error) {return json({error:error instanceof Error?error.message:'Request failed'},400);}
});
