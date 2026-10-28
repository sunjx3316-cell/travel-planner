const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const nodes = new Map();
const context = vm.createContext({document: {
  querySelector: key => {
    if (!nodes.has(key)) nodes.set(key, {style: {}, textContent: '', classList: {contains: () => false}});
    return nodes.get(key);
  }, querySelectorAll: () => [],
}});
vm.runInContext(fs.readFileSync('frontend/js/app.js', 'utf8').split('// ---------- 事件绑定 ----------')[0], context);
const run = code => vm.runInContext(code, context);
run(`state.cart=[{spot_id:1, name:'景点', city_name:'桂林'}]; state.planDays=7;
  state.planStyle='亲子'; state.roadStartCity='兰州'; state.cityStartCity='桂林';
  state.cityDays={'桂林':2}; state.closeLoop=false; setPlanMode('roadtrip');`);
for (let i=0; i<2; i++) {
  assert.match(nodes.get('#tab-cart').innerHTML, /value="兰州"/);
  assert.match(nodes.get('#tab-cart').innerHTML, /selected>亲子/);
  assert.doesNotMatch(nodes.get('#tab-cart').innerHTML, /id="close-loop" checked/);
  run(`setPlanMode('city')`);
  assert.match(nodes.get('#tab-cart').innerHTML, /value="2" selected>2天/);
  assert.match(run('cityPlanWorkspaceHtml()'), /value="桂林"/);
  run(`setPlanMode('roadtrip')`);
}
run(`$('#days').value='1'`);
run(`state.cityRec={city_days:{'桂林':2}};syncPlanDays('cart')`);
assert.equal(run('state.cityDays["桂林"]'),0);
assert.equal(run('state.cityRec'),null);
assert.equal(run('state.planDays'),1);
console.log('Planning preference checks passed: mode/tab rerenders preserve departure, style, loop and city days; smaller budgets clear stale allocations.');
