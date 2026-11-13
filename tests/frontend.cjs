// Dependency-free script smoke checks; these do not replace visual browser QA.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const html = fs.readFileSync(path.join(__dirname, '..', 'index.html'), 'utf8');
const script = html.match(/<script>([\s\S]*?)<\/script>/)[1]
  .replace(/let eventsData = (\[[\s\S]*?\]);/, 'let eventsData = [];')
  + fs.readFileSync(path.join(__dirname, '..', 'assets', 'app.js'), 'utf8');
class Element {
  constructor() { this.value = ''; this.children = []; this.listeners = {}; }
  set innerHTML(value) { this.markup = value; this.children = []; this.value = ''; }
  get innerHTML() { return this.markup; }
  appendChild(child) { this.children.push(child); }
  addEventListener(name, handler) { this.listeners[name] = handler; }
}
const ids = ['eventsGrid', 'eventCount', 'searchInput', 'stateFilter', 'cityFilter', 'categoryFilter', 'coverageSummary', 'dateFilter', 'loadMore', 'resetFilters', 'totalEvents', 'totalStates', 'totalSources'];
const elements = Object.fromEntries(ids.map(id => [id, new Element()]));
let initialize;
const context = vm.createContext({URL, Date, document: {
  getElementById: id => elements[id],
  createElement: () => new Element(),
  addEventListener: (name, fn) => { if (name === 'DOMContentLoaded') initialize = fn; }
}});
vm.runInContext(script, context);
initialize();
assert.equal(elements.stateFilter.children.length, 50);
assert.match(elements.eventsGrid.innerHTML, /No verified upcoming listings/);
const fixture = {title: '<img src=x onerror=alert(1)>', city: 'Kent', state: 'WA',
  category: 'Track / Drag', date: '2099-01-01', venue: 'Test Track',
  description: '<script>alert(1)</script>', url: 'javascript:alert(1)', image: 'javascript:alert(1)'};
context.fixture = fixture;
vm.runInContext('eventsData = [fixture]; renderEvents(eventsData)', context);
let card = elements.eventsGrid.children[0].innerHTML;
assert.ok(!card.includes('<script>'));
assert.ok(!card.includes('javascript:'));
assert.ok(card.includes('&lt;img'));
elements.stateFilter.value = 'CA';
elements.stateFilter.listeners.change();
assert.match(elements.eventsGrid.innerHTML, /Try adjusting your filters/);
elements.stateFilter.value = 'WA';
elements.stateFilter.listeners.change();
assert.equal(elements.eventsGrid.children.length, 1);
elements.searchInput.value = 'missing keyword';
elements.searchInput.listeners.input();
assert.equal(elements.eventCount.textContent, 'Showing 0 upcoming events');
context.fixture.url = 'https://example.org/event?id=1&other=2';
vm.runInContext('renderEvents([fixture])', context);
assert.match(elements.eventsGrid.children[0].innerHTML, /href="https:\/\/example.org\/event\?id=1&amp;other=2"/);
vm.runInContext('eventsData = [{...fixture, date: "2000-01-01"}, {...fixture, date: "2099-01-01"}]', context);
initialize();
assert.equal(elements.eventsGrid.children.length, 1);
assert.ok(!html.includes('example_sitekey'));
assert.ok(!html.includes('Successfully subscribed'));
console.log('Frontend smoke checks passed: initialization, safe rendering, filters, expired dates, empty state.');
