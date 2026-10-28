import assert from 'node:assert/strict';
globalThis.location = new URL('http://localhost/rail/');
globalThis.window = {};
globalThis.parent = window;
const {toTravelJourney} = await import('../frontend/rail/travel-bridge.js');
const {plan, fareKey} = await import('../frontend/rail/router.js');
const trip = (name, stops, times) => [name, 0, stops, times, times, stops.map((_,i)=>i*100), '', 'G'];
const network = {meta:{version:'20261020',startDate:'20261020',endDate:'20261022'},
  stops:[['VNP','北京南'],['TJP','天津'],['JGK','济南西']], services:[['20261020','20261021']],
  trips:[trip('G1',[0,1],[1380,1440]),trip('G2',[1,2],[60,180])]};
const options = {origin:[0],destination:[2],date:'20261020',earliest:1320,maxTransfers:1,
  trainType:'all',seatPreference:'standard',valueOfTime:40,waypoints:[],fixedLegs:[],minTransfer:30,maxWait:240,maxDuration:2880,pricingMode:'heuristic'};
const route = plan(network, options).fastest;
assert.ok(route);
const result = toTravelJourney(network, route, options, {});
assert.equal(result.from, '北京南');
assert.equal(result.to, '济南西');
assert.equal(result.cost, null);
assert.equal(result.risk, '需留意');
assert.equal(toTravelJourney(network, route, options, {}, {same:5,cross:90}).risk, '余量较充足', 'retain the user-selected transfer rules');
assert.equal(result.legs.length, 2);
assert.equal(result.legs[1].departure, 1500, 'cross-midnight day offset survives handoff');
assert.equal(toTravelJourney(network, {...route, legs:route.legs.slice(0,1)}, options, {}), null, 'reject partial route');
const quotes = {};
for (const l of route.legs) quotes[fareKey(l.train, network.stops[l.from][0], network.stops[l.to][0], l.train==='G1'?'20261020':'20261021')] = {fares:{O:50},queriedAt:new Date().toISOString()};
assert.equal(toTravelJourney(network, route, options, quotes).cost, 100);
for (const q of Object.values(quotes)) q.queriedAt = new Date(Date.now()-610000).toISOString();
assert.equal(toTravelJourney(network, route, options, quotes).cost, null, 'expired quote must not become reference price');
console.log('Rail bridge checks passed: complete-route validation, actual core algorithm, cross-midnight handoff and fresh-only price snapshots.');
