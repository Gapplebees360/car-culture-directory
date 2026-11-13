export const STATES = 'AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY'.split(' ');
export const CATEGORIES = ['Cars & Coffee','Car Show','Pop-Up Meet','Cruise Night','Track / Drag','Autocross','Road Rally','Rallycross'];
export function validateSubmission(input, now = new Date()) {
  const text = (key, min, max) => {
    if (typeof input[key] !== 'string' || input[key].trim().length < min || input[key].trim().length > max) throw new Error(`Invalid ${key}`);
    return input[key].trim();
  };
  const date = text('date',10,10), end = input.end_date || date;
  for (const value of [date,end]) {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(value) || !Number.isFinite(Date.parse(value+'T12:00:00Z')) || new Date(value+'T12:00:00Z').toISOString().slice(0,10)!==value) throw new Error('Invalid calendar date');
  }
  const today = new Date(now.getTime()-10*3600000).toISOString().slice(0,10);
  const horizon = new Date(now.getTime()+366*86400000).toISOString().slice(0,10);
  if (date < today || date > horizon || end < date || end > horizon) throw new Error('Choose an upcoming event date within one year');
  if (!STATES.includes(input.state) || !CATEGORIES.includes(input.category)) throw new Error('Select a valid state and event type');
  const url = new URL(text('url',10,1000));
  if (url.protocol!=='https:' || url.username || url.password || !/^[a-z0-9.-]+\.[a-z]{2,}$/i.test(url.hostname) || /\.(local|internal|test|invalid|example)$/.test(url.hostname)) throw new Error('Use a public HTTPS organizer or original event link');
  if (input.flyer_permission !== true) throw new Error('Confirm permission to publish the flyer');
  return {title:text('title',5,160),date,end_date:end,state:input.state,city:text('city',2,80),venue:text('venue',3,200),category:input.category,url:url.href,time:text('time',3,100),description:text('description',20,1500),source:'Community',verified_at:now.toISOString().slice(0,10)};
}
export function inspectFlyer(bytes, declaredType) {
  if (!(bytes instanceof Uint8Array) || bytes.length < 32 || bytes.length > 6*1024*1024) throw new Error('Upload a JPG, PNG, or WebP flyer up to 6 MB');
  let type = '';
  if (bytes[0]===255 && bytes[1]===216 && bytes[2]===255 && bytes.at(-2)===255 && bytes.at(-1)===217) type='image/jpeg';
  if ([137,80,78,71,13,10,26,10].every((n,i)=>bytes[i]===n) && new TextDecoder().decode(bytes.slice(12,16))==='IHDR') type='image/png';
  if (new TextDecoder().decode(bytes.slice(0,4))==='RIFF' && new TextDecoder().decode(bytes.slice(8,12))==='WEBP') type='image/webp';
  if (!type || declaredType!==type) throw new Error('The flyer file signature must match JPG, PNG, or WebP, not a renamed document');
  const view=new DataView(bytes.buffer,bytes.byteOffset,bytes.byteLength);
  let width=0,height=0;
  if(type==='image/png'){width=view.getUint32(16);height=view.getUint32(20);}
  if(type==='image/jpeg'){
    for(let position=2;position+9<bytes.length;){
      if(bytes[position]!==255){position++;continue;}
      const marker=bytes[position+1];if(marker===0xda)break;
      if(marker===0xff){position++;continue;}
      const length=view.getUint16(position+2);if(length<2||position+length+2>bytes.length)break;
      if([0xc0,0xc1,0xc2,0xc3,0xc5,0xc6,0xc7,0xc9,0xca,0xcb,0xcd,0xce,0xcf].includes(marker)){height=view.getUint16(position+5);width=view.getUint16(position+7);break;}
      position+=length+2;
    }
  }
  if(type==='image/webp'){
    const chunk=new TextDecoder().decode(bytes.slice(12,16));
    if(view.getUint32(4,true)!==bytes.length-8)throw new Error('Invalid WebP file size');
    if(chunk==='VP8X'){width=1+bytes[24]+(bytes[25]<<8)+(bytes[26]<<16);height=1+bytes[27]+(bytes[28]<<8)+(bytes[29]<<16);}
    if(chunk==='VP8L'&&bytes[20]===0x2f){const packed=view.getUint32(21,true);width=1+(packed&0x3fff);height=1+((packed>>>14)&0x3fff);}
    if(chunk==='VP8 '&&bytes[23]===0x9d&&bytes[24]===1&&bytes[25]===0x2a){width=view.getUint16(26,true)&0x3fff;height=view.getUint16(28,true)&0x3fff;}
  }
  if(width<200||height<200||width>6000||height>6000||width*height>24000000)throw new Error('Use a legible flyer between 200 and 6000 pixels per side, up to 24 megapixels');
  return {type,extension:{'image/jpeg':'jpg','image/png':'png','image/webp':'webp'}[type]};
}
export async function digest(value) {
  const bytes = typeof value==='string' ? new TextEncoder().encode(value) : value;
  return [...new Uint8Array(await crypto.subtle.digest('SHA-256',bytes))].map(n=>n.toString(16).padStart(2,'0')).join('');
}
export async function eventKey(event) {
  return event.event_key || 'imported:' + await digest(JSON.stringify([event.source,event.source_id || event.url,event.date]));
}
export function escapeHtml(value) { return String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); }
