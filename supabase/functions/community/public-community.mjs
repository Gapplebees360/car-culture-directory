import { STATES, CATEGORIES, inspectFlyer } from './validation.mjs';

const KEY = /^community:[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
const FLYER = 'https://lswnpxeiagureogrlopy.supabase.co/functions/v1/community/public-flyer';
const HEADERS = {'Cache-Control':'no-store','X-Content-Type-Options':'nosniff'};
const PAGE_SIZE = 250;
const json = (value, status=200) => Response.json(value,{status,headers:HEADERS});
const day = now => new Date(now.getTime()-10*3600000).toISOString().slice(0,10);
const validDate = value => typeof value==='string' && /^\d{4}-\d{2}-\d{2}$/.test(value)
  && Number.isFinite(Date.parse(value+'T12:00:00Z')) && new Date(value+'T12:00:00Z').toISOString().slice(0,10)===value;
const current = (row,today) => row?.approved===true && KEY.test(row.event_key)
  && validDate(row.event_data?.date) && validDate(row.event_data.end_date || row.event_data.date)
  && (row.event_data.end_date || row.event_data.date)>=row.event_data.date
  && (row.event_data.end_date || row.event_data.date)>=today;
const futureFilter = today => `event_data->>end_date.gte.${today},and(event_data->>end_date.is.null,event_data->>date.gte.${today})`;

function publicEvent(row) {
  const input=row.event_data, event={};
  for(const [key,min,max] of [['title',5,160],['city',2,80],['venue',3,200],['time',3,100],['description',20,1500]]) {
    if(typeof input[key]!=='string' || input[key].trim().length<min || input[key].trim().length>max) throw new Error('Invalid public event');
    event[key]=input[key].trim();
  }
  if(!STATES.includes(input.state) || !CATEGORIES.includes(input.category)
    || !validDate(input.verified_at) || typeof input.url!=='string' || input.url.length>1000) throw new Error('Invalid public event');
  const url=new URL(input.url);
  if(url.protocol!=='https:' || url.username || url.password || !/^[a-z0-9.-]+\.[a-z]{2,}$/i.test(url.hostname)
    || /\.(local|internal|test|invalid|example)$/i.test(url.hostname)) throw new Error('Invalid public URL');
  Object.assign(event,{event_key:row.event_key,date:input.date,end_date:input.end_date || input.date,
    state:input.state,category:input.category,url:url.href,verified_at:input.verified_at,source:'Community'});
  if(row.flyer_path) Object.assign(event,{image:FLYER+'?event='+encodeURIComponent(row.event_key),image_kind:'source_artwork'});
  return event;
}

// The public snapshot is deliberately independent of the imported catalog feed.
export async function publicCommunityEvents(db,requestUrl,now=new Date()) {
  const url=new URL(requestUrl), cursor=url.searchParams.get('cursor');
  if(url.searchParams.getAll('cursor').length>1 || (cursor!==null && !KEY.test(cursor))) return json({error:'Invalid cursor'},400);
  const today=day(now);
  try {
    let query=db.from('uam_events').select('event_key,event_data,flyer_path,approved')
      .eq('approved',true).like('event_key','community:%').or(futureFilter(today))
      .order('event_key',{ascending:true}).limit(PAGE_SIZE);
    if(cursor) query=query.gt('event_key',cursor);
    const {data,error}=await query;
    if(error || !Array.isArray(data) || data.length>PAGE_SIZE) throw new Error('Public events unavailable');
    let previous=cursor || '';
    const events=[];
    for(const row of data) {
      if(!KEY.test(row.event_key) || row.event_key<=previous) throw new Error('Invalid public event order');
      previous=row.event_key;
      if(!current(row,today)) continue;
      events.push(publicEvent(row));
    }
    return json({events,next_cursor:data.length===PAGE_SIZE ? previous : null});
  } catch {return json({error:'Public events unavailable'},503);}
}

export async function publicCommunityFlyer(db,requestUrl,now=new Date()) {
  const url=new URL(requestUrl), key=url.searchParams.get('event');
  const missing=()=>json({error:'Not found'},404);
  if(url.searchParams.getAll('event').length!==1 || !KEY.test(key || '')) return missing();
  try {
    const {data:row,error}=await db.from('uam_events').select('event_key,event_data,flyer_path,approved')
      .eq('event_key',key).eq('approved',true).or(futureFilter(day(now))).maybeSingle();
    if(error || !row || row.event_key!==key || !current(row,day(now)) || typeof row.flyer_path!=='string' || !row.flyer_path) return missing();
    // Only this fixed private bucket is consulted; never accept a path from a URL.
    const {data:blob,error:downloadError}=await db.storage.from('uam-flyers').download(row.flyer_path);
    if(downloadError || !blob || blob.size>6*1024*1024 || blob.size<32) return missing();
    const bytes=new Uint8Array(await blob.arrayBuffer());
    const {type}=inspectFlyer(bytes,blob.type);
    return new Response(bytes,{headers:{...HEADERS,'Content-Type':type,'Content-Length':String(bytes.length)}});
  } catch {return missing();}
}
