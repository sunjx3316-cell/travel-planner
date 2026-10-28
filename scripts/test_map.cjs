const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const nodes = new Map();
const context = vm.createContext({document: {
  querySelector: key => {if (!nodes.has(key)) nodes.set(key, {style: {}, textContent: ''}); return nodes.get(key);},
  querySelectorAll: () => [],
}});
const source = fs.readFileSync('frontend/js/app.js', 'utf8').split('// ---------- 事件绑定 ----------')[0];
vm.runInContext(source, context);
vm.runInContext(`
let testOption = {geo: [{map: 'province', zoom: 22, center: [110,25]}], series: []};
chart = {getOption: () => testOption, setOption: (option, replace) => {
  testOption = replace ? {...option, geo: [option.geo]} : {...testOption, ...option, geo: [{...testOption.geo[0], ...option.geo}]};
}, getWidth: () => 800, getHeight: () => 500, convertToPixel: (_, p) => [p[0]*100,p[1]*100]};
mapLevel = 'province'; currentProvince = '广西壮族自治区';
state.cart = [{spot_id: 2}, {spot_id: 1}];
provinceSpots = [{id: 1, name: '<测试景点>', lng: 110, lat: 25, category: '自然', tags: []},
  {id: 2, name: '美食街', lng: 111, lat: 25.1, category: '人文', tags: ['美食街']},
  {id: 3, name: '未加入清单', lng: 110, lat: 25.2, category: '综合', tags: []}];
renderProvinceSpots();
`, context);
const run = code => vm.runInContext(code, context);
assert.equal(run('testOption.geo[0].zoom'), 22, 'refresh must preserve map zoom');
assert.equal(run('testOption.series.filter(s => s.type === "scatter").flatMap(s => s.data).length'), 2);
assert.equal(run('testOption.series[1].data[0].markerNo'), 2);
assert.equal(run('testOption.series[1].symbol'), 'circle');
assert.equal(run('testOption.series[1].emphasis.scale'), false);
assert.match(run('testOption.tooltip.formatter({seriesType:"scatter",name:"<测试景点>", data:{}})'), /&lt;测试景点&gt;/);
run('setMapLayer("food")');
assert.equal(run('testOption.series[1].data[0].name'), '美食街');
run('state.cart = []; renderProvinceSpots()');
assert.equal(run('testOption.series.length'), 1, 'removed pins must disappear');
run('fitMapPoints()');
assert.equal(run('testOption.geo[0].zoom'), 1);
run('zoomMap(1000)');
assert.equal(run('testOption.geo[0].zoom'), 80);
run('zoomMap(.00001)');
assert.equal(run('testOption.geo[0].zoom'), .6);
run(`drawRouteOnMap({name: '天津至桂林', route: [
  {from:'天津', from_lng:117.2, from_lat:39.1, to:'桂林', to_lng:110.3, to_lat:25.3, km:1800},
  {from:'桂林', from_lng:110.3, from_lat:25.3, to:'天津', to_lng:117.2, to_lat:39.1, km:1800}
]})`);
assert.equal(run('testOption.animation'), false);
assert.equal(run('testOption.series[2].symbol'), 'circle');
assert.equal(run('testOption.series[2].emphasis.scale'), false);
assert.equal(run('testOption.series[2].data.length'), 2, 'closed route must not duplicate start pin');
assert.equal(run('testOption.series[2].data[1].markerNo'), 2);
assert.equal(run('testOption.series[1].data[0].coords.length'), 3, 'closed route retains the return leg');
assert.equal(run('testOption.series[1].effect'), undefined, 'no animated arrow on route');
assert.equal(run('testOption.tooltip.formatter({seriesType:"map", name:"山西省", dataIndex:3})'), '山西省');
run(`state.detail = {name:'主景点', lng:110, lat:25,
  alternatives:[{alt_name:'平替景点', alt_lng:111, alt_lat:26}]}; drawAlternativesMap()`);
assert.equal(run('testOption.animation'), false);
assert.equal(run('testOption.series[1].symbol'), 'circle');
assert.equal(run('testOption.series[1].animation'), false);
assert.equal(run('testOption.series[1].emphasis.scale'), false);
run(`state.loopsCache = [{name:'测试环线', spots:[{id:1, name:'景点', lng:110,lat:25, category:'自然'}]}];
  renderLoopMap('测试环线')`);
assert.equal(run('testOption.series[1].symbol'), 'circle');
assert.equal(run('testOption.animation'), false);
assert.equal(run('testOption.series[1].emphasis.scale'), false);
assert.doesNotMatch(source, /chart\.on\(["'](?:finished|georoam)["']/);
assert.doesNotMatch(source, /scheduleMapPinLayout|arrangeMapPins|pin-leaders|image:\/\/data:image/);
console.log('Map checks passed: native non-animated pins in province/route/loop/alternative views; cart sync, zoom, numbering and no roam repaint callbacks.');
