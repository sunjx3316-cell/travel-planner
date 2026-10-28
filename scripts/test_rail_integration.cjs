const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const storage = new Map();
const listeners = {};
const context = vm.createContext({window: {addEventListener: (name, fn) => listeners[name] = fn},
  document: {addEventListener() {}},
  localStorage: {getItem: k => storage.get(k), setItem: (k,v) => storage.set(k,v)}});
const source = fs.readFileSync('frontend/js/rail.js', 'utf8');
vm.runInContext(source, context);
const host = context.window.TravelRail;
const journey = {id:'test', savedAt:'2026-10-28T03:00:00Z', snapshot:'20261020', date:'2026-10-29',
  from:'北京', to:'天津', duration:30, transfers:0, cost:null, risk:'无需换乘',
  legs:[{train:'C1', from:'北京南', to:'天津', fromCode:'VNP',toCode:'TJP',departure:540,arrival:570}]};
assert.equal(host.validate(journey).cost, null);
const plan = {rail_journeys: host.attach({}, journey)};
assert.equal(host.attach(plan, {...journey,id:'new'}).length, 1);
assert.equal(host.planRows(plan)[0].legs[0].train, 'C1');
assert.match(host.section(plan, 'final'), /北京/);
assert.match(host.printSection(plan), /C1/);
for (const value of [{...journey, cost:0}, {...journey, cost:NaN}, {...journey, duration:90}, {...journey, transfers:2}, {...journey, legs:[]}]) assert.throws(() => host.validate(value));
const html = host.section();
assert.match(html, /规划铁路交通/);
assert.doesNotMatch(html, /iframe/);
storage.set('travel-planner-rail-journeys-v1', JSON.stringify({version:1, journeys:[{...journey, from:'<script>bad</script>'}]}));
assert.match(host.section(), /&lt;script&gt;/);
assert.match(host.section(), /待核价/);
assert.doesNotMatch(host.section(), /<script>/);
assert.equal(host.signature(journey), host.signature({...journey, id:'different',savedAt:'2026-10-28T04:00:00Z'}));
storage.set('travel-planner-rail-journeys-v1', 'broken');
assert.throws(host.read);
assert.match(host.section(), /原记录未被覆盖/);
assert.equal(storage.get('travel-planner-rail-journeys-v1'), 'broken');
assert.match(source, /event\.origin !== location\.origin/);
assert.match(source, /event\.source !== frame\?\.contentWindow/);
assert.match(source, /frame\?\.remove\(\)/);
assert.doesNotMatch(fs.readFileSync('frontend/index.html','utf8'), /<iframe/);
console.log('Rail integration checks passed: lazy loading, bounded validated storage, unknown prices, deduplication, escaping, same-origin/source/session gates and iframe teardown.');
