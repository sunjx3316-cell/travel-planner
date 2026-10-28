import test from 'node:test';
import assert from 'node:assert/strict';
import {plan,validateFixedLegs,fareKey} from '../../frontend/rail/router.js';
import {directServices,connectionServices} from '../../frontend/rail/services.js';
import {canTransfer,cityIndex,crossTransfers,journeyTimeline} from '../../frontend/rail/transfers.js';
const trip=(name,stops,times,service=0)=>[name,service,stops,times,times,stops.map((_,i)=>i*100),'','G'];
const fixture=trips=>({meta:{startDate:'20261020',endDate:'20261022'},stops:[['T','天津'],['BN','北京南'],['BX','北京西'],['C','重庆北'],['S','上海虹桥']],services:[['20261020','20261021']],trips});
const opts={origin:[0],destination:[3],date:'20261020',maxTransfers:1};
const selected=trip=>({trip,fromIndex:0,toIndex:1,serviceDay:0});

test('same-city transfer is included in recommendations and fixed itineraries; another city is rejected',()=>{
  const n=fixture([trip('first',[0,1],[360,420]),trip('cross',[2,3],[480,900]),trip('same',[1,3],[480,950]),trip('foreign',[4,3],[480,800])]);
  const r=plan(n,opts);assert.equal(r.count,2);assert.deepEqual(r.fastest.legs.map(l=>l.train),['first','cross']);assert.equal(r.fastest.crossStationTransfers,1);assert.equal(r.fastest.duration,540);
  assert.equal(plan(n,{...opts,maxTransfers:0}).count,0);
  const prefix=validateFixedLegs(n,[selected(0)],opts),rows=connectionServices(n,{prefix,destination:[3],date:opts.date});
  assert.deepEqual(rows.map(l=>l.train).sort(),['cross','same']);
  assert.equal(validateFixedLegs(n,[selected(0),selected(1)],opts).length,2);
  assert.throws(()=>validateFixedLegs(n,[selected(0),selected(3)],opts),/不同城市/);
  const continued=plan(n,{...opts,fixedLegs:prefix});assert.equal(continued.fastest.legs[1].train,'cross');
  assert.equal(plan(n,{...opts,fixedLegs:[selected(0),selected(1)]}).fastest.duration,540);
});

test('cross-station connections respect inclusive wait bounds across midnight',()=>{
  const n=fixture([trip('first',[0,1],[1380,1420]),...[[9,'early'],[10,'min'],[220,'max'],[221,'late']].map(([m,name])=>trip(name,[2,3],[m,m+60]))]);
  const prefix=validateFixedLegs(n,[selected(0)],opts),rows=connectionServices(n,{prefix,destination:[3],date:opts.date});
  assert.deepEqual(rows.map(l=>l.train),['min','max']);assert.equal(rows[0].serviceDay,1);
  for(const l of rows)assert.equal(validateFixedLegs(n,[...prefix,l],opts).length,2);
  assert.equal(plan(n,{...opts,fixedLegs:prefix}).count,2);
});

test('cross-station quoted routing still requires both railway fares and retains exact ticket pairs',()=>{
  const n=fixture([trip('first',[0,1],[360,420]),trip('cross',[2,3],[480,900])]);
  const fareQuotes={[fareKey('first','T','BN',opts.date)]:{fares:{O:60}},[fareKey('cross','BX','C',opts.date)]:{fares:{O:500}}};
  const r=plan(n,{...opts,pricingMode:'quoted',fareQuotes});assert.equal(r.cheapest.cost,560);assert.equal(r.cheapest.crossStationTransfers,1);assert.equal(r.cheapest.transfers,1);
  delete fareQuotes[fareKey('cross','BX','C',opts.date)];assert.equal(plan(n,{...opts,pricingMode:'quoted',fareQuotes}).count,0);
});

test('city nodes advance at alighting while a specific different station is not silently visited',()=>{
  const n=fixture([trip('first',[0,1],[360,420]),trip('cross',[2,3],[480,900])]);
  assert.equal(plan(n,{...opts,waypoints:[{stations:[1,2]}]}).count,1);
  assert.equal(plan(n,{...opts,waypoints:[{stations:[2]}]}).count,0);
});

test('city aliases share the inspector and router grouping; unidentified stations stay separate',()=>{
  const n={stops:[['A','汉口'],['B','武昌'],['C','武汉'],['D','北京西'],['E','未知甲'],['F','未知乙']]};
  assert.equal(canTransfer(n,0,1),true);assert.equal(canTransfer(n,1,2),true);assert.equal(canTransfer(n,0,3),false);assert.equal(canTransfer(n,4,5),false);
  assert.deepEqual(cityIndex(n).cities.find(c=>c.name==='武汉').stations,[0,1,2]);
});

test('timeline renders both transfer stations with a distinct surface-transfer interval',()=>{
  const n=fixture([trip('first',[0,1],[360,420]),trip('cross',[2,3],[480,900])]);
  const legs=validateFixedLegs(n,[selected(0),selected(1)],opts),timeline=journeyTimeline(legs);
  assert.deepEqual(timeline.nodes.map(n=>n.station),[0,1,2,3]);assert.deepEqual(timeline.links.map(l=>l.kind),['rail','cross','rail']);
  assert.deepEqual(timeline.links[1],{kind:'cross',departure:420,arrival:480});assert.equal(crossTransfers(legs)[0].minutes,60);
  const same=journeyTimeline([legs[0],{...legs[1],from:1}]);assert.equal(same.nodes.length,3);assert.equal(same.nodes[1].wait,60);assert.equal(same.links.length,2);
});
