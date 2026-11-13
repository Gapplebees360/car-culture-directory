import test from 'node:test';
import assert from 'node:assert/strict';
import { validateSubmission, inspectFlyer, eventKey, escapeHtml } from '../supabase/functions/community/validation.mjs';
const now=new Date('2026-11-13T18:00:00Z');
const fixture={title:'Tacoma Cars & Coffee',date:'2026-11-21',state:'WA',city:'Tacoma',venue:'Public coffee venue',category:'Cars & Coffee',url:'https://example.org/meet',time:'8–11 AM Pacific',description:'A car meet with coffee, open to all respectful drivers.',flyer_permission:true};
test('requires flyer permission, valid date, geography, and public proof URL',()=>{
 assert.equal(validateSubmission(fixture,now).date,'2026-11-21');
 for(const changes of [{flyer_permission:false},{date:'2026-02-30'},{state:'XX'},{url:'javascript:alert(1)'},{url:'https://localhost/test'},{date:'2026-01-01'},{category:'Unknown'},{description:''}])assert.throws(()=>validateSubmission({...fixture,...changes},now));
});
test('rejects renamed documents, oversized files, and MIME mismatches',()=>{
 assert.throws(()=>inspectFlyer(new TextEncoder().encode('<svg onload="alert(1)"></svg>'),'image/png'));
 assert.throws(()=>inspectFlyer(new Uint8Array(7*1024*1024),'image/jpeg'));
 const png=new Uint8Array(40);png.set([137,80,78,71,13,10,26,10]);png.set(new TextEncoder().encode('IHDR'),12);
 const view=new DataView(png.buffer);view.setUint32(16,400);view.setUint32(20,600);
 assert.equal(inspectFlyer(png,'image/png').extension,'png');assert.throws(()=>inspectFlyer(png,'image/jpeg'));
});
test('event identity is stable and includes the occurrence date',async()=>{
 const event={source:'Calendar',source_id:'123',date:'2026-11-21'};
 assert.equal(await eventKey(event),await eventKey({...event}));assert.notEqual(await eventKey(event),await eventKey({...event,date:'2026-11-22'}));
});
test('email content escapes event text',()=>assert.equal(escapeHtml('<script>&"'), '&lt;script&gt;&amp;&quot;'));
