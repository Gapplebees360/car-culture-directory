(() => {
  const db=globalThis.UAMCommunity?.db;
  if(!db)return;
  const $=id=>document.getElementById(id);
  const check=result=>{if(result.error)throw result.error;return result.data;};
  let generation=0,initialized=false,available=false;
  const status=(text,error=false)=>{const node=$('websiteSubmissionStatus');if(!node)return;node.textContent=text;node.classList.toggle('is-error',error);};
  const inactive=error=>['42P01','42883','PGRST202','PGRST205'].includes(error?.code);
  function failure(error){
    if(inactive(error)){
      available=false;$('submitWebsiteButton').disabled=true;
      status('Website suggestions are not active yet. Event browsing and the existing event form remain available.');
    }else status(error?.message||'The website suggestion could not be saved. Please try again.',true);
  }
  function publicURL(value){
    const url=new URL(String(value).trim());
    const host=url.hostname.toLowerCase();
    if(url.protocol!=='https:'||url.username||url.password||(url.port&&url.port!=='443')||
       !/^[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?\.[a-z]{2,}$/i.test(host)||
       host==='localhost'||/\.(?:localhost|local|internal|test|invalid|example)$/.test(host)){
      throw new Error('Use a public HTTPS website without a login, private address, or custom port.');
    }
    url.hash='';return url.href;
  }
  function externalLink(value){
    try{const url=publicURL(value);const link=document.createElement('a');link.href=url;link.target='_blank';link.rel='noopener noreferrer';link.textContent=url;return link;}catch{return null;}
  }
  const appendText=(parent,tag,text)=>{const node=document.createElement(tag);node.textContent=text;parent.appendChild(node);return node;};
  const count=(report,key,array)=>Number.isInteger(report[key])&&report[key]>=0?report[key]:Array.isArray(report[array])?report[array].length:0;
  function renderSubmission(row){
    const item=document.createElement('li');
    const link=externalLink(row.url);if(link)item.appendChild(link);else appendText(item,'strong','Submitted website');
    const labels={queued:'Waiting for inspection',inspecting:'Inspection in progress',inspected:'Inspection complete',not_automotive:'Not identified as a car-related website',failed:'Inspection could not be completed'};
    appendText(item,'p',labels[row.status]||'Awaiting inspection');
    const report=row.report&&typeof row.report==='object'&&!Array.isArray(row.report)?row.report:{};
    if(!['queued','inspecting'].includes(row.status)){
      appendText(item,'p',`${count(report,'imported_count','events')} imported · ${count(report,'duplicate_count','duplicates')} duplicates skipped · ${count(report,'rejected_count','rejected')} other listings skipped`);
      appendText(item,'p',report.source_enrolled===true?'Added to the recurring crawl list after this inspection.':'Not enrolled for recurring crawls by this inspection.');
      const notes=[...(Array.isArray(report.notes)?report.notes:[]),...(Array.isArray(report.rejected)?report.rejected:[])];
      if(notes.length){const list=document.createElement('ul');for(const entry of notes.slice(0,5)){const text=typeof entry==='string'?entry:typeof entry?.reason==='string'?entry.reason:'';if(text)appendText(list,'li',text.slice(0,500));}item.appendChild(list);}
    }
    return item;
  }
  async function verifiedMember(){
    const result=await db.auth.getUser();if(result.error)throw result.error;
    const user=result.data?.user;
    if(!user?.id||!user.email_confirmed_at)throw new Error('Sign in with a verified email to suggest an event website.');
    return user;
  }
  async function refreshAdmin(ticket){
    const isAdmin=check(await db.rpc('uam_is_admin'));
    if(ticket!==generation)return;
    $('websiteSourcesAdmin').hidden=!isAdmin;$('websiteSourceList').replaceChildren();
    if(!isAdmin)return;
    const rows=[];
    for(let offset=0;offset<2000;offset+=200){
      const batch=check(await db.from('uam_website_sources').select('host,url,enabled,next_check_at,last_checked_at,last_status').order('host').range(offset,offset+199));
      if(ticket!==generation)return;
      rows.push(...batch);if(batch.length<200)break;
      if(offset===1800)throw new Error('There are more website sources than can be shown here. Please contact the site maintainer.');
    }
    if(!rows.length)appendText($('websiteSourceList'),'li','No recurring website sources yet.');
    for(const source of rows){
      const item=document.createElement('li');
      appendText(item,'strong',source.host||'Website source');
      const link=externalLink(source.url);if(link)item.appendChild(link);
      appendText(item,'p',source.enabled?'Recurring inspection enabled':'Recurring inspection paused');
      const button=document.createElement('button');button.type='button';button.textContent=source.enabled?'Pause source':'Re-enable source';
      button.onclick=async()=>{button.disabled=true;try{await verifiedMember();check(await db.rpc('uam_set_website_source',{p_host:source.host,p_enabled:!source.enabled}));status(source.enabled?'Website source paused.':'Website source enabled for another inspection.');await refresh();}catch(error){failure(error);}finally{button.disabled=false;}};
      item.appendChild(button);$('websiteSourceList').appendChild(item);
    }
  }
  async function refresh(){
    const ticket=++generation;
    $('submitWebsiteButton').disabled=true;
    const result=await db.auth.getUser();if(result.error)throw result.error;
    if(ticket!==generation)return;
    const user=result.data?.user;
    $('websiteSubmissions').replaceChildren();$('websiteSourceList').replaceChildren();$('websiteSourcesAdmin').hidden=true;
    if(!user?.id||!user.email_confirmed_at){available=false;status('Sign in with a verified email to suggest an event website.');return;}
    const rows=check(await db.from('uam_website_submissions').select('id,url,status,report,created_at').eq('user_id',user.id).order('created_at',{ascending:false}).limit(50));
    if(ticket!==generation)return;
    available=true;$('submitWebsiteButton').disabled=false;
    if(!rows.length)appendText($('websiteSubmissions'),'li','No website suggestions yet. Your latest 50 suggestions appear here.');
    else{for(const row of rows)$('websiteSubmissions').appendChild(renderSubmission(row));if(rows.length===50)appendText($('websiteSubmissions'),'li','Showing your latest 50 suggestions.');}
    await refreshAdmin(ticket);
  }
  function setup(){
    if(initialized||!$('submitWebsiteForm'))return;initialized=true;
    $('submitWebsiteForm').onsubmit=async event=>{
      event.preventDefault();const form=event.currentTarget;const button=$('submitWebsiteButton');button.disabled=true;
      try{
        await verifiedMember();
        const url=publicURL($('websiteUrl').value);
        status('Adding this website to the inspection queue…');
        const result=check(await db.rpc('uam_submit_website',{p_url:url}));
        if(!result?.id||!['queued','inspecting','inspected','not_automotive','failed'].includes(result.status))throw new Error('The website queue returned an unexpected result. Refresh the list before submitting again.');
        form.reset();status(result.status==='queued'?'Website queued for automatic inspection. Refresh results later to see imported and skipped events.':'This website suggestion is already recorded. Refresh results for its inspection status.');
        try{await refresh();}catch{status('Website saved, but its results could not be refreshed. Use Refresh results later.');}
      }catch(error){failure(error);}finally{button.disabled=!available;}
    };
    $('refreshWebsiteSubmissions').onclick=async()=>{try{await refresh();}catch(error){failure(error);}};
    refresh().catch(failure);
  }
  db.auth.onAuthStateChange(()=>{
    ++generation;available=false;
    if($('websiteSubmissions'))$('websiteSubmissions').replaceChildren();
    if($('websiteSourceList'))$('websiteSourceList').replaceChildren();
    if($('websiteSourcesAdmin'))$('websiteSourcesAdmin').hidden=true;
    if($('submitWebsiteButton'))$('submitWebsiteButton').disabled=true;
    if(initialized)setTimeout(()=>refresh().catch(failure),0);
  });
  document.addEventListener('DOMContentLoaded',setup);
})();
