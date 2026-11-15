// Run the real website UI handlers without network, credentials, or hosted writes.
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const root=path.join(__dirname,'..');
const source=fs.readFileSync(path.join(root,'assets/website-submissions.js'),'utf8');
const markup=fs.readFileSync(path.join(root,'community.html'),'utf8');
const verified={id:'member-1',email_confirmed_at:'2026-01-01T00:00:00Z'};
const deferred=()=>{let resolve;return{promise:new Promise(done=>resolve=done),resolve};};
class Element extends EventTarget{
 constructor(tag='div'){super();this.tagName=tag.toUpperCase();this.children=[];this.hidden=false;this.disabled=false;this.value='';this.resetCount=0;this.classes=new Set();this.classList={toggle:(name,on)=>on?this.classes.add(name):this.classes.delete(name)};this._text='';}
 set textContent(value){this._text=String(value);this.children=[];}
 get textContent(){return this._text+this.children.map(child=>child.textContent).join(' ');}
 set innerHTML(value){throw new Error('Unsafe HTML rendering is not allowed in this fixture');}
 appendChild(child){this.children.push(child);return child;}
 replaceChildren(){this.children=[];this._text='';}
 reset(){this.resetCount++;}
 submit(){let work;this.addEventListener('submit',event=>{work=this.onsubmit(event);},{once:true});const event=new Event('submit',{cancelable:true});this.dispatchEvent(event);assert.equal(event.currentTarget,null);return work;}
}
async function settle(){for(let i=0;i<12;i++)await new Promise(resolve=>setImmediate(resolve));}
function fixture({user=verified,rows=[],sources=[],isAdmin=false,missing=false,submitResponse,queryResponse}={}){
 const elements=Object.fromEntries([...markup.matchAll(/\bid="([^"]+)"/g)].map(m=>[m[1],new Element()]));
 const queries=[],calls=[];let init,authCallback,currentUser=user;
 const db={auth:{getUser:async()=>({data:{user:currentUser}}),onAuthStateChange:callback=>{authCallback=callback;}},from:table=>{
  const state={table};queries.push(state);
  const q={select:fields=>{state.fields=fields;return q;},eq:(field,value)=>{state[field]=value;return q;},order:(field,options)=>{state.order={field,options};return q;},limit:value=>{state.limit=value;return q;},range:(start,end)=>{state.range=[start,end];return q;},then:(yes,no)=>Promise.resolve(queryResponse?queryResponse(state):missing?{error:{code:'PGRST205',message:'missing table'}}:{data:table==='uam_website_submissions'?rows:sources.slice(state.range?.[0]||0,(state.range?.[1]??sources.length-1)+1)}).then(yes,no)};return q;
 },rpc:async(name,args)=>{calls.push({name,args});if(name==='uam_is_admin')return{data:isAdmin};if(name==='uam_submit_website')return submitResponse?submitResponse(args):{data:{id:'submission-1',status:'queued'}};if(name==='uam_set_website_source'){const entry=sources.find(s=>s.host===args.p_host);if(entry)entry.enabled=args.p_enabled;return{data:null};}throw new Error('Unexpected RPC '+name);}};
 const context=vm.createContext({UAMCommunity:{db},document:{getElementById:id=>elements[id]||null,createElement:tag=>new Element(tag),addEventListener:(event,callback)=>{if(event==='DOMContentLoaded')init=callback;}},URL,setTimeout:callback=>setImmediate(callback),console});
 vm.runInContext(source,context);init();
 return{elements,queries,calls,logout:()=>{currentUser=null;authCallback('SIGNED_OUT');},setUser:value=>{currentUser=value;authCallback('SIGNED_IN');}};
}
function descendants(element){return[element,...element.children.flatMap(descendants)];}

async function successfulAsyncSubmission(){
 const pending=deferred();
 const ui=fixture({submitResponse:()=>pending.promise});await settle();
 assert.equal(ui.elements.submitWebsiteButton.disabled,false);
 ui.elements.websiteUrl.value='https://Cars.Example.org/events#upcoming';
 const work=ui.elements.submitWebsiteForm.submit();await settle();
 assert.equal(ui.elements.submitWebsiteButton.disabled,true);
 assert.equal(ui.calls.find(call=>call.name==='uam_submit_website').args.p_url,'https://cars.example.org/events');
 pending.resolve({data:{id:'submission-1',status:'queued'}});await work;
 assert.equal(ui.elements.submitWebsiteForm.resetCount,1);
 assert.match(ui.elements.websiteSubmissionStatus.textContent,/queued for automatic inspection/);
 assert.equal(ui.elements.submitWebsiteButton.disabled,false);
 assert.equal(ui.queries[0].user_id,verified.id);
}
async function invalidOrUnverifiedCannotSubmit(){
 for(const url of ['javascript:alert(1)','http://cars.example.org/','https://user:password@cars.example.org/','https://127.0.0.1/','https://localhost/','https://calendar.internal/','https://cars.example.org:8443/events']){
  const ui=fixture();await settle();ui.elements.websiteUrl.value=url;await ui.elements.submitWebsiteForm.submit();
  assert.equal(ui.calls.filter(call=>call.name==='uam_submit_website').length,0,url);
  assert.equal(ui.elements.submitWebsiteForm.resetCount,0);
 }
 const ui=fixture({user:{id:'member-unverified'}});await settle();
 assert.equal(ui.elements.submitWebsiteButton.disabled,true);
 ui.elements.websiteUrl.value='https://cars.example.org/events';await ui.elements.submitWebsiteForm.submit();
 assert.equal(ui.calls.length,0);
 assert.match(ui.elements.websiteSubmissionStatus.textContent,/verified email/);
}
async function unavailableFeatureAndFailuresAreHonest(){
 const ui=fixture({missing:true});await settle();
 assert.equal(ui.elements.submitWebsiteButton.disabled,true);
 assert.match(ui.elements.websiteSubmissionStatus.textContent,/not active yet/);
 const rejected=fixture({submitResponse:()=>({error:{message:'Daily website limit reached'}})});await settle();
 rejected.elements.websiteUrl.value='https://cars.example.org/events';await rejected.elements.submitWebsiteForm.submit();
 assert.equal(rejected.elements.submitWebsiteForm.resetCount,0);
 assert.equal(rejected.elements.websiteSubmissionStatus.textContent,'Daily website limit reached');
 const malformed=fixture({submitResponse:()=>({data:{status:'queued'}})});await settle();
 malformed.elements.websiteUrl.value='https://cars.example.org/events';await malformed.elements.submitWebsiteForm.submit();
 assert.equal(malformed.elements.submitWebsiteForm.resetCount,0);
 assert.match(malformed.elements.websiteSubmissionStatus.textContent,/unexpected result/);
}
async function safeReportRenderingAndCounts(){
 const ui=fixture({rows:[{id:'one',url:'javascript:alert(1)',status:'inspected',report:{imported_count:2,duplicate_count:3,rejected_count:1,source_enrolled:true,notes:['<script>bad()</script>'],rejected:[{reason:'No clear date'}]}},{id:'two',url:'https://cars.example.org/events',status:'failed',report:null}]});await settle();
 assert.match(ui.elements.websiteSubmissions.textContent,/2 imported · 3 duplicates skipped · 1 other listings skipped/);
 assert.match(ui.elements.websiteSubmissions.textContent,/Added to the recurring crawl list/);
 assert.match(ui.elements.websiteSubmissions.textContent,/<script>bad\(\)<\/script>/);
 const links=descendants(ui.elements.websiteSubmissions).filter(node=>node.tagName==='A');
 assert.equal(links.length,1);assert.equal(links[0].href,'https://cars.example.org/events');
 assert.equal(links[0].rel,'noopener noreferrer');
 assert.equal(descendants(ui.elements.websiteSubmissions).some(node=>node.tagName==='SCRIPT'),false);
}
async function staleRefreshCannotRevealPriorAccount(){
 const pending=deferred();
 const ui=fixture({queryResponse:()=>pending.promise});await settle();
 ui.logout();pending.resolve({data:[{url:'https://private.example.org/events',status:'queued'}]});await settle();
 assert.equal(ui.elements.websiteSubmissions.children.length,0);
 assert.equal(ui.elements.submitWebsiteButton.disabled,true);
}
async function adminPauseUsesProtectedRPC(){
 const sources=[{host:'cars.example.org',url:'https://cars.example.org/events',enabled:true}];
 const ui=fixture({isAdmin:true,sources});await settle();
 assert.equal(ui.elements.websiteSourcesAdmin.hidden,false);
 const button=descendants(ui.elements.websiteSourceList).find(node=>node.tagName==='BUTTON');
 assert.equal(button.textContent,'Pause source');await button.onclick();
 const call=ui.calls.find(call=>call.name==='uam_set_website_source');
 assert.equal(call.args.p_host,'cars.example.org');assert.equal(call.args.p_enabled,false);
 assert.match(ui.elements.websiteSourceList.textContent,/Recurring inspection paused/);
}
(async()=>{
 await successfulAsyncSubmission();await invalidOrUnverifiedCannotSubmit();await unavailableFeatureAndFailuresAreHonest();await safeReportRenderingAndCounts();await staleRefreshCannotRevealPriorAccount();await adminPauseUsesProtectedRPC();
 console.log('Website UI checks passed: verified submission, async reset/errors, safe reports/counts, unavailable setup, sign-out privacy, admin source pause.');
})().catch(error=>{console.error(error);process.exitCode=1;});
