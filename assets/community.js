(() => {
  const config=globalThis.UAM_CONFIG;
  if(!config?.supabaseUrl || !globalThis.supabase) return;
  const db=globalThis.supabase.createClient(config.supabaseUrl,config.publishableKey);
  const base=config.supabaseUrl+'/functions/v1/community';
  const $=id=>document.getElementById(id);
  const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const check=result=>{if(result.error)throw new Error(result.error.message);return result.data;};
  const member=async()=> (await db.auth.getUser()).data.user;
  const message=(value,error=false)=>{let box=$('communityMessage');if(!box){box=document.createElement('div');box.id='communityMessage';box.className='community-toast';box.setAttribute('role','status');document.body.appendChild(box);}box.textContent=value;box.classList.toggle('is-error',error);};
  async function eventKey(event) {
    if(event.event_key)return event.event_key;
    const value=JSON.stringify([event.source,event.source_id||event.url,event.date]);
    const hash=[...new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(value)))].map(n=>n.toString(16).padStart(2,'0')).join('');
    return 'imported:'+hash;
  }
  async function invoke(path,body,form=false) {
    const {data:{session}}=await db.auth.getSession();
    const headers={apikey:config.publishableKey};
    if(session)headers.Authorization='Bearer '+session.access_token;
    if(!form)headers['Content-Type']='application/json';
    const response=await fetch(base+path,{method:'POST',headers,body:form?body:JSON.stringify(body)});
    const data=await response.json();
    if(!response.ok)throw new Error(data.error||'The request could not be saved');
    return data;
  }
  async function requireMember(event) {
    const user=await member();
    if(!user){location.href='community.html?event='+encodeURIComponent(await eventKey(event));return null;}
    if(!user.email_confirmed_at)throw new Error('Verify your email before continuing');
    return user;
  }
  async function save(event,status) {
    const user=await requireMember(event);if(!user)return;
    await invoke('/sync',{});
    check(await db.from('uam_rsvps').upsert({user_id:user.id,event_key:await eventKey(event),status}));
    message(status==='going'?'RSVP saved here. Follow the organizer link for official entry or tickets.':'Event saved to your account.');
  }
  async function report(event) {
    if(!await requireMember(event))return;
    const dialog=$('reportDialog')||document.createElement('dialog');
    dialog.id='reportDialog';dialog.className='community-dialog';
    dialog.innerHTML='<form id="reportEventForm"><h2>Report this event</h2><p>Reports go to a moderator. A report alone does not remove an event.</p><label>Reason<select name="reason"><option value="wrong_date">Wrong date or location</option><option value="cancelled">Cancelled</option><option value="not_real">Event may not be real</option><option value="spam">Spam or duplicate</option><option value="unsafe">Safety concern</option><option value="other">Other</option></select></label><label>What should we check?<textarea name="details" minlength="10" maxlength="1000" required></textarea></label><div class="community-actions"><button class="button" type="submit">Send for review</button><button type="button" data-close>Cancel</button></div><p role="status" data-status></p></form>';
    if(!dialog.isConnected)document.body.appendChild(dialog);
    dialog.querySelector('[data-close]').onclick=()=>dialog.close();
    dialog.querySelector('form').onsubmit=async e=>{e.preventDefault();const form=e.currentTarget;const button=form.querySelector('button[type=submit]');button.disabled=true;try{check(await db.rpc('uam_flag',{p_key:await eventKey(event),p_reason:form.reason.value,p_details:form.details.value}));dialog.close();message('Report received. A moderator will review it.');}catch(error){form.querySelector('[data-status]').textContent=error.message;}finally{button.disabled=false;}};
    dialog.showModal();
  }
  function decorateCard(card,event) {
    const actions=document.createElement('div');actions.className='community-card-actions';
    for(const [label,fn] of [['Save',()=>save(event,'saved')],['RSVP',()=>save(event,'going')],['Report',()=>report(event)]]){
      const button=document.createElement('button');button.type='button';button.textContent=label;
      button.onclick=()=>Promise.resolve(fn()).catch(error=>message(error.message,true));actions.appendChild(button);
    }
    card.querySelector('.card-footer').appendChild(actions);
  }
  async function loadPublicEvents() {
    const rows=check(await db.from('uam_events').select('event_key,event_data,flyer_path').eq('approved',true).like('event_key','community:%').limit(500));
    const paths=rows.map(row=>row.flyer_path).filter(Boolean);
    const signed=paths.length?check(await db.storage.from('uam-flyers').createSignedUrls(paths,3600)):[];
    const images=new Map(signed.filter(row=>row.signedUrl).map(row=>[row.path,row.signedUrl]));
    return rows.map(row=>({...row.event_data,event_key:row.event_key,...(images.has(row.flyer_path)?{image:images.get(row.flyer_path),image_kind:'source_artwork'}:{})}));
  }
  globalThis.UAMCommunity={db,eventKey,decorateCard,loadPublicEvents,save,report};
  globalThis.UAMCommunity.syncDirectory=async records=>{
    const [community,hidden]=await Promise.all([loadPublicEvents(),db.rpc('uam_hidden_event_keys').then(check)]);
    const excluded=new Set(hidden);
    const filtered=await Promise.all(records.map(async event=>excluded.has(await eventKey(event))?null:event));
    return [...filtered.filter(Boolean),...community];
  };

  async function refreshAccount() {
    const user=await member();
    $('signedOut').hidden=!!user;$('signedIn').hidden=!user;
    if(!user)return;
    $('accountEmail').textContent=user.email;
    const profile=check(await db.from('uam_profiles').select('*').eq('user_id',user.id).single());
    $('alertsEnabled').checked=profile.alerts_enabled;
    const health=await fetch(base+'/health').then(r=>r.json()).catch(()=>({}));
    $('alertsEnabled').disabled=!health.alerts_ready;
    $('emailReadiness').textContent=health.alerts_ready?'Choose where to hear about newly listed events.':'Email sending is being activated. You can save locations now; email alerts remain off until delivery is ready.';
    const locations=check(await db.from('uam_alert_locations').select('*').eq('user_id',user.id));
    $('alertLocations').replaceChildren();
    for(const loc of locations){const row=document.createElement('li');row.textContent=(loc.city?loc.city+', ':'All cities in ')+loc.state+' ';const button=document.createElement('button');button.textContent='Remove';button.onclick=async()=>{check(await db.from('uam_alert_locations').delete().eq('id',loc.id));await refreshAccount();};row.appendChild(button);$('alertLocations').appendChild(row);}
    const submissions=check(await db.from('uam_submissions').select('id,event_data,status,review_note,review_kind').eq('user_id',user.id).order('created_at',{ascending:false}));
    const trust=check(await db.rpc('uam_trust_status'));
    $('trustStatus').textContent=trust.suspended?'Publishing is suspended. Contact the moderator for review.':`${Math.min(4,trust.human_approvals)} of 4 manual approvals completed. ${trust.open_reports?'New events require review while reports are open.':trust.human_approvals>=4?'Automatic publishing is available after validation.':'New submissions are reviewed before publication.'}`;
    $('mySubmissions').innerHTML=submissions.length?submissions.map(row=>'<li><strong>'+esc(row.event_data.title)+'</strong> — '+esc(row.status)+(row.review_note?'<p>'+esc(row.review_note)+'</p>':'')+'</li>').join(''):'<li>No submissions yet. Your first four approved events require a moderator.</li>';
    const saved=check(await db.from('uam_rsvps').select('event_key,status,uam_events(event_data,approved)').eq('user_id',user.id));
    $('myEvents').replaceChildren();
    for(const entry of saved){const row=document.createElement('li');const event=entry.uam_events?.event_data;row.textContent=(event?event.title+' · '+event.date:'Event withdrawn or unavailable')+' — '+entry.status+' ';if(event){const a=document.createElement('a');a.href=event.url;a.target='_blank';a.rel='noopener noreferrer';a.textContent='Organizer / tickets ↗';row.appendChild(a);}const remove=document.createElement('button');remove.textContent='Remove';remove.onclick=async()=>{check(await db.from('uam_rsvps').delete().eq('event_key',entry.event_key).eq('user_id',user.id));await refreshAccount();};row.appendChild(remove);$('myEvents').appendChild(row);}
    const selected=new URLSearchParams(location.search).get('event');
    if(selected){const rows=check(await db.from('uam_events').select('event_data,event_key').eq('event_key',selected).eq('approved',true));if(rows[0]){const event={...rows[0].event_data,event_key:selected};$('selectedEvent').hidden=false;$('selectedEventName').textContent=event.title;$('saveSelected').onclick=()=>save(event,'saved').then(refreshAccount).catch(error=>message(error.message,true));$('rsvpSelected').onclick=()=>save(event,'going').then(refreshAccount).catch(error=>message(error.message,true));}}
    const isAdmin=check(await db.rpc('uam_is_admin'));
    $('adminPanel').hidden=!isAdmin;
    if(isAdmin)await refreshAdmin();
  }
  async function refreshAdmin() {
    const pending=check(await db.from('uam_submissions').select('*').eq('status','pending').order('created_at'));
    $('reviewQueue').replaceChildren();
    for(const row of pending){const card=document.createElement('article');card.className='review-card';const signed=check(await db.storage.from('uam-flyers').createSignedUrl(row.flyer_path,600));card.innerHTML='<h3>'+esc(row.event_data.title)+'</h3><img class="review-flyer" src="'+esc(signed.signedUrl)+'" alt="Submitted event flyer"><p>'+esc(row.event_data.date)+' · '+esc(row.event_data.city)+', '+esc(row.event_data.state)+' · '+esc(row.event_data.venue)+'</p><p>'+esc(row.event_data.description)+'</p><p><a target="_blank" rel="noopener noreferrer" href="'+esc(row.event_data.url)+'">Check organizer evidence ↗</a></p><label class="check-label"><input type="checkbox" data-checked> I compared the flyer, date, venue, and organizer evidence.</label><label>Review note<textarea data-note minlength="10" required></textarea></label><div class="community-actions"><button data-approve>Approve</button><button data-reject>Reject</button></div>';
      for(const [selector,action] of [['[data-approve]','approve'],['[data-reject]','reject']])card.querySelector(selector).onclick=async()=>{try{check(await db.rpc('uam_review',{p_id:row.id,p_action:action,p_note:card.querySelector('[data-note]').value,p_checked:card.querySelector('[data-checked]').checked}));await refreshAdmin();}catch(error){message(error.message,true);}};
      $('reviewQueue').appendChild(card);
    }
    if(!pending.length)$('reviewQueue').textContent='No submissions waiting for review.';
    const flags=check(await db.from('uam_flags').select('*,uam_events(event_data)').eq('status','open').order('created_at'));
    $('flagQueue').replaceChildren();
    for(const flag of flags){const card=document.createElement('article');card.className='review-card';card.innerHTML='<h3>'+esc(flag.uam_events?.event_data?.title||flag.event_key)+'</h3><p>'+esc(flag.reason)+': '+esc(flag.details)+'</p><label>Review finding<textarea data-note minlength="10"></textarea></label><div class="community-actions"><button data-confirm>Confirm / hide event</button><button data-dismiss>Dismiss report</button></div>';
      for(const [selector,confirmed] of [['[data-confirm]',true],['[data-dismiss]',false]])card.querySelector(selector).onclick=async()=>{try{check(await db.rpc('uam_resolve_flag',{p_id:flag.id,p_confirmed:confirmed,p_note:card.querySelector('[data-note]').value}));await refreshAdmin();}catch(error){message(error.message,true);}};
      $('flagQueue').appendChild(card);
    }
    if(!flags.length)$('flagQueue').textContent='No open event reports.';
  }
  async function setupPage() {
    if(!$('signedOut'))return;
    const states='AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY'.split(' ');
    for(const id of ['alertState','submitState'])for(const state of states){const opt=document.createElement('option');opt.value=opt.textContent=state;$(id).appendChild(opt);}
    const readiness=await fetch(base+'/health').then(response=>response.json()).catch(()=>({}));
    if(!readiness.accounts){document.querySelectorAll('form button').forEach(button=>button.disabled=true);message('Community accounts are awaiting activation. Event browsing remains available.');return;}
    $('signInForm').onsubmit=async e=>{e.preventDefault();try{check(await db.auth.signInWithPassword({email:$('loginEmail').value.trim(),password:$('loginPassword').value}));message('Signed in.');await refreshAccount();}catch(error){message(error.message,true);}};
    $('signUpForm').onsubmit=async e=>{e.preventDefault();try{check(await db.auth.signUp({email:$('registerEmail').value.trim(),password:$('registerPassword').value,options:{emailRedirectTo:location.origin+'/community.html'}}));message('If registration is available for this address, check your email and confirm it before signing in.');}catch(error){message(error.message,true);}};
    $('signOut').onclick=async()=>{await db.auth.signOut();await refreshAccount();};
    $('forgotPassword').onclick=async()=>{try{const email=$('loginEmail').value.trim();if(!email)throw new Error('Enter your account email first');check(await db.auth.resetPasswordForEmail(email,{redirectTo:location.origin+'/community.html'}));message('If this account exists, check your email for a password reset link.');}catch(error){message(error.message,true);}};
    $('resetPasswordForm').onsubmit=async e=>{e.preventDefault();try{check(await db.auth.updateUser({password:$('newPassword').value}));$('passwordRecovery').hidden=true;message('Password updated.');}catch(error){message(error.message,true);}};
    $('addAlertLocation').onsubmit=async e=>{e.preventDefault();try{const user=await member();check(await db.from('uam_alert_locations').insert({user_id:user.id,state:$('alertState').value,city:$('alertCity').value.trim()||null}));message('Alert location saved.');await refreshAccount();}catch(error){message(error.message,true);}};
    $('saveAlertConsent').onclick=async()=>{try{const user=await member();check(await db.from('uam_profiles').update({alerts_enabled:$('alertsEnabled').checked,consented_at:$('alertsEnabled').checked?new Date().toISOString():null}).eq('user_id',user.id));message($('alertsEnabled').checked?'Email alerts enabled for your saved locations.':'Email alerts are off.');}catch(error){message(error.message,true);}};
    $('submitEventForm').onsubmit=async e=>{e.preventDefault();const button=$('submitEventButton');button.disabled=true;try{const fields=new FormData(e.currentTarget);const flyer=fields.get('flyer');if(!flyer?.size)throw new Error('An event flyer is required');const event=Object.fromEntries(fields.entries());delete event.flyer;event.flyer_permission=$('flyerPermission').checked;const body=new FormData();body.append('flyer',flyer);body.append('event',JSON.stringify(event));const result=await invoke('/submit',body,true);message(result.status==='approved'?'Event published after the automated checks.':'Event received with its flyer and queued for moderator approval.');e.currentTarget.reset();await refreshAccount();}catch(error){message(error.message,true);}finally{button.disabled=false;}};
    $('changeAdminForm').onsubmit=async e=>{e.preventDefault();if(!confirm('Transfer site moderation to this verified account?'))return;try{check(await db.rpc('uam_change_admin',{p_email:$('newAdminEmail').value.trim()}));message('Administrator changed.');await refreshAccount();}catch(error){message(error.message,true);}};
    const unsubscribe=new URLSearchParams(location.search).get('unsubscribe');
    if(unsubscribe){$('unsubscribePanel').hidden=false;$('confirmUnsubscribe').onclick=async()=>{try{await invoke('/unsubscribe',{token:unsubscribe});message('Email alerts have been turned off.');$('unsubscribePanel').hidden=true;}catch(error){message(error.message,true);}};}
    await refreshAccount();
    db.auth.onAuthStateChange(event=>{if(event==='PASSWORD_RECOVERY')$('passwordRecovery').hidden=false;setTimeout(()=>refreshAccount().catch(error=>message(error.message,true)),0);});
  }
  document.addEventListener('DOMContentLoaded',()=>setupPage().catch(error=>message(error.message,true)));
})();
