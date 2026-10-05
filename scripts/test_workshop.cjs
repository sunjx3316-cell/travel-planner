/* Offline behavioral checks; never touch user browser storage or the real API. */
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const storage = new Map();
const elements = new Map();
const context = vm.createContext({console, Date, JSON, Number, String, Set,
  state: {cart: [{spot_id: 3, name: '公园', city_name: '北京'}]},
  lastPlans: [], WORKBENCH_STORAGE_KEY: 'library', FINAL_PLAN_STORAGE_KEY: 'final',
  localStorage: {getItem: k => storage.get(k), setItem: (k, v) => storage.set(k, v)},
  clonePlan: p => JSON.parse(JSON.stringify(p)),
  normalizedWorkbenchDays: p => {p.daily.forEach((d,i) => {d.day=i+1; d.items ||= [];});},
  esc: s => String(s ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'),
  $: selector => {if (!elements.has(selector)) elements.set(selector, {}); return elements.get(selector);},
  flash: msg => {context.message=msg;}, renderTrip: () => {context.tripRendered=true;},
  switchTab: tab => {context.activeTab=tab;},
  savedWorkbenchPlans: () => JSON.parse(storage.get('library') || '[]'),
  finalPlan: () => JSON.parse(storage.get('final') || 'null'),
  window: {confirm: () => true, print: () => {context.printed=true;}, addEventListener: () => {}},
  document: {title: 'Travel', body: {appendChild: el => {context.printSheet=el;}}, createElement: () => ({remove(){}})}
});
vm.runInContext(fs.readFileSync('frontend/js/workshop.js','utf8'), context);
const plan = {name:'我的方案', summary:'原始建议', route:[{from:'北京',to:'天津'}], tips:['原交通提醒'],
  daily:[{day:1, stay:{town:'旧住宿'}, foods:{dishes:[{name:'旧餐饮'}]}, next_transport:{to:'天津'}, items:[
    {spot:'故宫',time:'09:00-11:00',why:'预约'}, {spot:'博物馆',time:'10:00-12:00'}]}, {day:2,items:[]}]};
context.beginWorkbench(plan,0);
assert.equal(context.activeTab,'plans');
assert.equal(context.workshopDayIssues(context.state.workbench.plan.daily[0]).issues.length,1);
context.selectWorkbenchItem(0);
assert.match(elements.get('#tab-plans').innerHTML,/安排地点/);
context.transferWorkbenchItem(0,0,1);
assert.equal(context.state.workbench.plan.daily[1].items[0].spot,'故宫');
assert.equal(context.state.workbench.plan.route.length,0);
assert.equal(context.state.workbench.plan.daily[0].stay,undefined);
assert.equal(plan.daily[0].items.length,2); // The AI input is immutable.
context.undoWorkbenchChange();
assert.equal(context.state.workbench.plan.route.length,1);
assert.equal(context.state.workbench.plan.daily[0].stay.town,'旧住宿');
context.removeWorkbenchItem(0,1);
context.restoreWorkbenchDraft();
assert.equal(context.state.workbench.plan.daily[0].items.length,1);
context.selectWorkbenchDay(1);
elements.set('#workbench-cart-item',{value:'3'});
context.addWorkbenchCartItem(1);
context.addWorkbenchCartItem(1);
assert.equal(context.state.workbench.plan.daily[1].items.length,1); // No accidental duplicate add.
context.replaceWorkbenchItem(0,0,'3');
assert.equal(context.state.workbench.plan.daily[0].items[0].spot_id,3);
context.updateWorkbenchItem(0,0,'spot','手动地点');
assert.equal(context.state.workbench.plan.daily[0].items[0].spot_id,undefined);
context.addWorkbenchDay();
assert.equal(context.state.workbench.plan.daily.length,3);
context.removeWorkbenchDay();
assert.equal(context.state.workbench.plan.daily.length,2);
context.setFinalPlan();
assert.equal(context.activeTab,'trip');
assert.equal(context.finalPlan().daily[0].items[0].spot,'手动地点');
const html=context.tripPrintHtml(context.finalPlan());
assert.match(html,/手动地点/);
assert.doesNotMatch(html,/旧住宿|旧餐饮|原交通提醒/);
assert.match(context.tripPrintHtml({name:'<script>alert(1)</script>',daily:[]}),/&lt;script&gt;/);
assert.equal(context.workshopDayIssues({items:[{spot:'A',time:'25:00-26:00'}]}).unspecified,1);
assert.match(context.workshopDayIssues({items:[{spot:'A',time:'12:00-11:00'}]}).issues[0],/结束时间/);
assert.match(context.workshopDayIssues({items:[{spot:'A'},{spot:'A'}]}).issues[0],/重复/);
assert.equal(context.workshopTimeRange('上午'),null);
elements.delete('#trip-print');
context.$ = selector => selector === '#trip-print' ? null : elements.get(selector);
context.printFinalPlan();
assert.equal(context.printed,true);
assert.match(context.printSheet.innerHTML,/手动地点/);
assert.ok(storage.has('travel-planner-workshop-draft-v1'));
console.log('Workshop checks passed: editing, transfer, undo, restoration, replacement, duplicates, derived-data invalidation, final save, print export and escaping.');
