// Exercise the actual UI handlers with asynchronous network responses and real
// EventTarget dispatch semantics, without contacting production services.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { webcrypto } = require('node:crypto');

const root = path.join(__dirname, '..');
const script = fs.readFileSync(path.join(root, 'assets/community.js'), 'utf8');
const markup = fs.readFileSync(path.join(root, 'community.html'), 'utf8');

function deferred() {
  let resolve;
  const promise = new Promise(done => { resolve = done; });
  return { promise, resolve };
}

class Element extends EventTarget {
  constructor(id = '') {
    super();
    this.id = id;
    this.hidden = true;
    this.value = '';
    this.checked = false;
    this.disabled = false;
    this.children = [];
    this.resetCount = 0;
    this.fields = new Map();
    this.classes = new Set();
    this.classList = { toggle: (name, enabled) => enabled ? this.classes.add(name) : this.classes.delete(name) };
  }
  appendChild(child) { this.children.push(child); }
  querySelector() { return this.button ||= new Element(); }
  reset() { this.resetCount++; }
  setAttribute() {}
  replaceChildren() { this.children = []; }
  submit() {
    let finished;
    const listener = event => { finished = this.onsubmit(event); };
    this.addEventListener('submit', listener, { once: true });
    const event = new Event('submit', { cancelable: true });
    this.dispatchEvent(event);
    assert.equal(event.currentTarget, null, 'dispatch must clear currentTarget before async work resumes');
    return finished;
  }
}

class FormDataFixture {
  constructor(form) { this.fields = new Map(form?.fields || []); }
  get(name) { return this.fields.get(name); }
  entries() { return this.fields.entries(); }
  append(name, value) { this.fields.set(name, value); }
}

function harness({ health, submit, profile, alertsReady = true, publicRows = [], serverPageLimit, profileWrite, alertLocations=[] } = {}) {
  const elements = Object.fromEntries([...markup.matchAll(/\bid="([^"]+)"/g)].map(match => [match[1], new Element(match[1])]));
  let initialize, authCallback;
  const requests = [];
  const timers = [];
  const updates = [], queries = [], signedBatches = [];
  const user = profile ? { id: 'fixture-user', email: 'member@example.org', email_confirmed_at: '2026-01-01T00:00:00Z' } : null;
  function query(table) {
    const state = { table, orders: [] };
    queries.push(state);
    const result = () => {
      if (table === 'uam_profiles') {
        assert.ok(profile, 'profile queries require a signed-in fixture');
        if(state.update&&profileWrite)return profileWrite.promise.then(result=>{if(result.error)return result;updates.push({...state.update});Object.assign(profile,state.update);return {data:[{...profile}]};});
        if (state.update) { updates.push({ ...state.update }); Object.assign(profile, state.update); }
        return { data: state.single ? { ...profile } : [{ ...profile }] };
      }
      if(table==='uam_alert_locations'){
        if(state.insert)alertLocations.push({id:'fixture-location-'+alertLocations.length,...state.insert});
        return {data:alertLocations.map(row=>({...row}))};
      }
      if (table !== 'uam_events') return { data: [] };
      let rows = publicRows.slice();
      if (state.upcoming) {
        assert.match(state.upcoming, /^event_data->>end_date\.gte\.\d{4}-\d{2}-\d{2},and\(event_data->>end_date\.is\.null,event_data->>date\.gte\.\d{4}-\d{2}-\d{2}\)$/);
        const today = state.upcoming.match(/gte\.(\d{4}-\d{2}-\d{2})/)[1];
        rows = rows.filter(row => (row.event_data.end_date || row.event_data.date) >= today);
      }
      for (const [column, options] of state.orders.slice().reverse()) {
        rows.sort((a, b) => String(column === 'event_key' ? a.event_key : a.event_data.date).localeCompare(String(column === 'event_key' ? b.event_key : b.event_data.date)) * (options.ascending ? 1 : -1));
      }
      const count = rows.length;
      if (state.range) rows = rows.slice(state.range[0], state.range[1] + 1);
      if (state.limit) rows = rows.slice(0, state.limit);
      if (serverPageLimit) rows = rows.slice(0, serverPageLimit);
      return { data: rows, count };
    };
    const builder = {
      select: fields => { state.select = fields; return builder; },
      eq: (field, value) => { state[field] = value; return builder; },
      like: (field, value) => { state[field] = value; return builder; },
      or: value => { state.upcoming = value; return builder; },
      order: (field, options) => { state.orders.push([field, options]); return builder; },
      range: (from, to) => { state.range = [from, to]; return builder; },
      limit: count => { state.limit = count; return builder; },
      single: () => { state.single = true; return Promise.resolve(result()); },
      update: value => { state.update = value; return builder; },
      insert: value => { state.insert = value; return builder; },
      then: (resolve, reject) => Promise.resolve().then(result).then(resolve, reject),
    };
    return builder;
  }
  const db = {
    auth: {
      getUser: async () => ({ data: { user } }),
      getSession: async () => ({ data: { session: null } }),
      onAuthStateChange: callback => { authCallback = callback; return { data: { subscription: { unsubscribe() {} } } }; },
    },
    from: query,
    rpc: async name => ({ data: name === 'uam_trust_status' ? { suspended: false, human_approvals: 0, open_reports: 0 } : false }),
    storage: { from: () => ({ createSignedUrls: async paths => {
      signedBatches.push(paths);
      return { data: paths.map(path => ({ path, signedUrl: 'https://example.org/flyers/' + path })) };
    } }) },
  };
  const context = vm.createContext({
    UAM_CONFIG: { supabaseUrl: 'https://example.supabase.co', publishableKey: 'public-fixture-key' },
    supabase: { createClient: () => db },
    document: {
      getElementById: id => elements[id] || null,
      createElement: () => new Element(),
      querySelectorAll: () => [],
      addEventListener: (name, callback) => { if (name === 'DOMContentLoaded') initialize = callback; },
      body: new Element(),
    },
    fetch: async (url, options) => {
      requests.push({ url, options });
      if (url.endsWith('/health')) return health ? health.promise : { json: async () => ({ accounts: true, signup_ready: true, alerts_ready: alertsReady }) };
      if (url.endsWith('/submit')) return submit.promise;
      throw new Error('Unexpected network request: ' + url);
    },
    location: { origin: 'https://usautomeets.com', search: '' },
    setTimeout: callback => { timers.push(callback); },
    FormData: FormDataFixture, URLSearchParams, TextEncoder, crypto: webcrypto, console,
  });
  vm.runInContext(script, context);
  return { elements, requests, timers, updates, queries, signedBatches, community: context.UAMCommunity, initialize: () => initialize(), authEvent: event => {
    assert.equal(typeof authCallback, 'function', 'auth listener must exist before page readiness requests');
    authCallback(event);
  } };
}

async function successfulSubmission() {
  const submit = deferred();
  const ui = harness({ submit });
  await ui.initialize();
  const form = ui.elements.submitEventForm;
  form.fields = new Map([['title', 'Fixture car meet'], ['flyer', { size: 100 }]]);
  ui.elements.flyerPermission.checked = true;
  const finished = form.submit();
  await Promise.resolve();
  assert.equal(ui.elements.submitEventButton.disabled, true);
  submit.resolve({ ok: true, json: async () => ({ status: 'pending' }) });
  await finished;
  assert.equal(form.resetCount, 1, 'successful async submission must reset its captured form');
  assert.match(ui.elements.communityMessage.textContent, /queued for moderator approval/);
  assert.equal(ui.elements.communityMessage.classes.has('is-error'), false);
  assert.equal(ui.elements.submitEventButton.disabled, false);
  assert.equal(ui.requests.filter(request => request.url.endsWith('/submit')).length, 1);
}

async function failedSubmissionRetainsFields() {
  const submit = deferred();
  const ui = harness({ submit });
  await ui.initialize();
  ui.elements.submitEventForm.fields = new Map([['flyer', { size: 100 }]]);
  const finished = ui.elements.submitEventForm.submit();
  submit.resolve({ ok: false, json: async () => ({ error: 'The flyer could not be stored' }) });
  await finished;
  assert.equal(ui.elements.submitEventForm.resetCount, 0);
  assert.equal(ui.elements.communityMessage.textContent, 'The flyer could not be stored');
  assert.equal(ui.elements.communityMessage.classes.has('is-error'), true);
  assert.equal(ui.elements.submitEventButton.disabled, false);
}

async function earlyRecoveryEvent() {
  const health = deferred();
  const ui = harness({ health });
  // Supabase starts URL-session initialization as soon as the client is created.
  // Recovery must work even before DOMContentLoaded/readiness finishes.
  ui.authEvent('PASSWORD_RECOVERY');
  assert.equal(ui.elements.passwordRecovery.hidden, false);
  const initialized = ui.initialize();
  assert.equal(ui.requests.filter(request => request.url.endsWith('/health')).length, 1);
  assert.equal(ui.elements.passwordRecovery.hidden, false);
  health.resolve({ json: async () => ({ accounts: true, signup_ready: true }) });
  await initialized;
  assert.equal(ui.elements.passwordRecovery.hidden, false);
}

async function unchangedAlertConsentKeepsOriginalCutoff() {
  const original = '2026-01-01T00:00:00Z';
  const profile = { alerts_enabled: true, consented_at: original };
  const ui = harness({ profile });
  await ui.initialize();
  await ui.elements.saveAlertConsent.onclick();
  await ui.elements.saveAlertConsent.onclick();
  assert.equal(profile.consented_at, original);
  assert.equal(ui.updates.length, 0, 'unchanged enabled preference must not rewrite consent and suppress queued events');
  assert.equal(ui.elements.communityMessage.classes.has('is-error'), false);
}

async function outageStillAllowsOptOutButNotNewOptIn() {
  const profile = { alerts_enabled: true, consented_at: '2026-01-01T00:00:00Z' };
  const ui = harness({ profile, alertsReady: false });
  await ui.initialize();
  assert.equal(ui.elements.alertsEnabled.disabled, false, 'existing consent can always be revoked');
  ui.elements.alertsEnabled.checked = false;
  await ui.elements.saveAlertConsent.onclick();
  assert.equal(profile.alerts_enabled, false);
  assert.equal(profile.consented_at, null);
  assert.equal(ui.elements.alertsEnabled.disabled, true);
  // A synthetic toggle or stale page must not bypass the readiness check.
  ui.elements.alertsEnabled.checked = true;
  await ui.elements.saveAlertConsent.onclick();
  assert.equal(profile.alerts_enabled, false);
  assert.equal(ui.updates.length, 1);
  assert.match(ui.elements.communityMessage.textContent, /Email delivery is not ready/);
}

async function newOptInSetsFreshConsentWhenReady() {
  const profile = { alerts_enabled: false, consented_at: null };
  const ui = harness({ profile });
  await ui.initialize();
  ui.elements.alertsEnabled.checked = true;
  await ui.elements.saveAlertConsent.onclick();
  assert.equal(profile.alerts_enabled, true);
  assert.match(profile.consented_at, /^\d{4}-\d{2}-\d{2}T/);
  const consented = profile.consented_at;
  await ui.elements.saveAlertConsent.onclick();
  assert.equal(profile.consented_at, consented);
  assert.equal(ui.updates.length, 1);
}

async function preferenceFeedbackStaysNextToTheButton() {
  const profile={alerts_enabled:false,consented_at:null};
  const locations=[];
  const ui=harness({profile,alertsReady:false,alertLocations:locations});await ui.initialize();
  ui.elements.alertState.value='WA';ui.elements.alertCity.value='Tacoma';
  await ui.elements.saveAlertConsent.onclick();
  assert.equal(locations.length,1);assert.equal(locations[0].state,'WA');assert.equal(locations[0].city,'Tacoma');
  assert.match(ui.elements.alertPreferencesStatus.textContent,/Location and email preferences saved/);
  assert.match(ui.elements.alertPreferencesStatus.textContent,/not activated yet/);
  assert.equal(profile.alerts_enabled,false);
  await ui.elements.saveAlertConsent.onclick();assert.equal(locations.length,1,'re-saving a selected location must not duplicate it');
}

async function preferenceSaveHasBusyStateAndInlineErrors() {
  const profile={alerts_enabled:false,consented_at:null};const write=deferred();
  const ui=harness({profile,profileWrite:write});await ui.initialize();
  ui.elements.alertsEnabled.checked=true;
  const saved=ui.elements.saveAlertConsent.onclick();
  assert.equal(ui.elements.saveAlertConsent.disabled,true);assert.equal(ui.elements.saveAlertConsent.textContent,'Saving…');
  assert.match(ui.elements.alertPreferencesStatus.textContent,/Saving email preferences/);
  const again=ui.elements.saveAlertConsent.onclick();await again;
  write.resolve({error:{message:'Could not store preferences'}});await saved;
  assert.equal(ui.elements.saveAlertConsent.disabled,false);
  assert.equal(ui.elements.alertPreferencesStatus.textContent,'Could not store preferences');
  assert.equal(ui.elements.alertPreferencesStatus.classes.has('is-error'),true);
  assert.equal(ui.updates.length,0);
}

async function invalidLocationIsExplainedLocally() {
  const ui=harness({profile:{alerts_enabled:false,consented_at:null}});await ui.initialize();
  ui.elements.alertCity.value='Tacoma';await ui.elements.saveAlertConsent.onclick();
  assert.match(ui.elements.alertPreferencesStatus.textContent,/Choose a state/);
  assert.equal(ui.elements.alertPreferencesStatus.classes.has('is-error'),true);
  assert.equal(ui.elements.saveAlertConsent.disabled,false);
}

function publicEvent(number, date, endDate, flyer = false) {
  return { event_key: 'community:' + String(number).padStart(5, '0'), event_data: {
    title: 'Fixture event ' + number, date, ...(endDate ? { end_date: endDate } : {}),
  }, flyer_path: flyer ? 'fixture/flyer-' + number + '.jpg' : null };
}

async function upcomingCommunityEventsAreFilteredBeforePagination() {
  const expired = Array.from({ length: 700 }, (_, i) => publicEvent(i, '2000-01-01', '2000-01-01'));
  const upcoming = Array.from({ length: 501 }, (_, i) => publicEvent(1000 + i, '2099-01-01', '2099-01-01', true));
  const ongoing = publicEvent(900, '2000-01-01', '2099-01-01');
  const ui = harness({ publicRows: [...expired, ...upcoming, ongoing] });
  const events = await ui.community.loadPublicEvents();
  assert.equal(events.length, 502, 'historical rows must not crowd out upcoming or ongoing listings');
  assert.ok(events.some(event => event.event_key === ongoing.event_key));
  assert.ok(events.some(event => event.event_key === upcoming.at(-1).event_key));
  assert.ok(!events.some(event => event.event_key === expired[0].event_key));
  assert.deepEqual(ui.queries.map(query => query.range), [[0, 249], [250, 499], [500, 749]]);
  for (const query of ui.queries) {
    assert.ok(query.upcoming, 'date filter belongs on every database page request');
    assert.deepEqual(JSON.parse(JSON.stringify(query.orders)), [['event_data->>date', { ascending: true }], ['event_key', { ascending: true }]]);
  }
  assert.deepEqual(ui.signedBatches.map(batch => batch.length), [250, 250, 1]);
  assert.equal(events.find(event => event.event_key === upcoming.at(-1).event_key).image_kind, 'source_artwork');
}

async function oversizedOrTruncatedCalendarIsExplicitlyReported() {
  const records = Array.from({ length: 10001 }, (_, i) => publicEvent(i, '2099-01-01', '2099-01-01'));
  const ui = harness({ publicRows: records });
  await assert.rejects(() => ui.community.loadPublicEvents(), /too large to load completely/);
  assert.equal(ui.queries.length, 41, 'requests must stay bounded even for an oversized calendar');
  assert.equal(ui.signedBatches.length, 0);
  assert.equal(ui.elements.communityMessage.classes.has('is-error'), true);
  const limited = harness({ publicRows: records.slice(0, 200), serverPageLimit: 100 });
  await assert.rejects(() => limited.community.loadPublicEvents(), /could not be loaded/);
  assert.equal(limited.queries.length, 1, 'an unexpectedly truncated server response must not silently return a partial calendar');
}

(async () => {
  await successfulSubmission();
  await failedSubmissionRetainsFields();
  await earlyRecoveryEvent();
  await unchangedAlertConsentKeepsOriginalCutoff();
  await outageStillAllowsOptOutButNotNewOptIn();
  await newOptInSetsFreshConsentWhenReady();
  await preferenceFeedbackStaysNextToTheButton();
  await preferenceSaveHasBusyStateAndInlineErrors();
  await invalidLocationIsExplainedLocally();
  await upcomingCommunityEventsAreFilteredBeforePagination();
  await oversizedOrTruncatedCalendarIsExplicitlyReported();
  console.log('Community UI checks passed: async submission, recovery, consent preservation/opt-out/readiness, and complete upcoming-event pagination.');
})().catch(error => { console.error(error); process.exitCode = 1; });
