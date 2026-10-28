import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {plan,validateFixedLegs,fareKey} from '../../frontend/rail/router.js';
import {directServices,connectionServices} from '../../frontend/rail/services.js';
import {canTransfer} from '../../frontend/rail/transfers.js';

const trip=(name,stops,times,service=0)=>[name,service,stops,times,times,stops.map((_,i)=>i*100),'','G'];
const fixture=(trips,services=[['20261020']])=>({meta:{startDate:'20261019',endDate:'20261023'},services,trips,stops:Array.from({length:5},(_,i)=>['S'+i,'Station '+i])});
const options={origin:[0],destination:[2],date:'20261020',earliest:0,maxTransfers:2};
const selection=(trip,serviceDay=0,fromIndex=0,toIndex=1)=>({trip,serviceDay,fromIndex,toIndex});

test('continuation preserves the exact selected train, station and departure in every recommendation',()=>{
  const n=fixture([trip('chosen',[0,1],[60,100]),trip('faster-first',[0,1],[90,100]),trip('next-fast',[1,2],[130,200]),trip('next-later',[1,2],[140,250]),trip('direct',[0,2],[100,110])]);
  const r=plan(n,{...options,fixedLegs:[selection(0)]});
  assert.equal(r.count,2);
  for(const route of r.candidates){assert.equal(route.legs[0].train,'chosen');assert.equal(route.departure,60);assert.equal(route.transfers,1);}
  assert.equal(r.fastest.duration,140);assert.equal(r.trace[0].transfers,1);
  assert.equal(plan(n,{...options,fixedLegs:[selection(0)],maxTransfers:0}).count,0);
});

test('saved selections are rebuilt from timetable; invalid records and connection gaps are rejected',()=>{
  const n=fixture([trip('first',[0,1],[60,100]),trip('short',[1,2],[129,200]),trip('min',[1,2],[130,200]),trip('max',[1,2],[340,400]),trip('late',[1,2],[341,400]),trip('other-station',[3,2],[140,200])]);
  const l=validateFixedLegs(n,[{...selection(0),departure:999,arrival:1000,from:4,cost:1}],options)[0];
  assert.equal(l.departure,60);assert.equal(l.arrival,100);assert.equal(l.from,0);assert.equal(l.cost,null);
  for(const second of [1,4])assert.throws(()=>validateFixedLegs(n,[selection(0),selection(second)],options),/30–240/);
  for(const second of [2,3])assert.equal(validateFixedLegs(n,[selection(0),selection(second)],options).length,2);
  assert.throws(()=>validateFixedLegs(n,[selection(0),selection(5)],options),/不同城市/);
  for(const bad of [null,selection(99),selection(0,0,0,50),{...selection(0),train:'changed'}])assert.throws(()=>validateFixedLegs(n,[bad],options));
  assert.throws(()=>validateFixedLegs(n,[selection(0)],{...options,earliest:61}),/最早出发/);
});

test('same through train cannot be split into a transfer or extended after reaching the destination',()=>{
  const through=['through',0,[0,1,2],[60,100,200],[60,140,200],[0,100,200],'','G'];
  const n=fixture([through,trip('back',[2,3],[250,300])]);
  assert.throws(()=>validateFixedLegs(n,[selection(0),selection(0,0,1,2)],options),/同一趟/);
  assert.throws(()=>validateFixedLegs(n,[selection(0,0,0,2),selection(1)],options),/已经到达/);
});

test('onward service list crosses midnight and uses the actual station and inclusive wait window',()=>{
  const n=fixture([trip('first',[0,1],[1380,1420]),trip('short',[1,2],[9,100],1),trip('min',[1,2],[10,100],1),trip('max',[1,2],[220,300],1),trip('late',[1,2],[221,300],1),trip('wrong-station',[3,2],[30,100],1)],[['20261020'],['20261021']]);
  const prefix=validateFixedLegs(n,[selection(0)],options);
  const rows=connectionServices(n,{prefix,destination:[2],date:options.date});
  assert.deepEqual(rows.map(l=>l.train),['min','max']);assert.equal(rows[0].departure,1450);assert.equal(rows[0].serviceDay,1);
  const r=plan(n,{...options,fixedLegs:prefix});assert.equal(r.fastest.arrival,1540);assert.equal(r.fastest.duration,160);
  assert.deepEqual(validateFixedLegs(n,[...prefix,rows[0]],options).map(l=>l.departure),[1380,1450]);
});

test('quoted continuation requires real fares for the selected prefix as well as the remaining legs',()=>{
  const n=fixture([trip('first',[0,1],[60,100]),trip('next',[1,2],[130,200])]);
  const fareQuotes={[fareKey('next','S1','S2',options.date)]:{fares:{O:80}}};
  const opts={...options,fixedLegs:[selection(0)],pricingMode:'quoted',fareQuotes};
  assert.equal(plan(n,opts).count,0);
  fareQuotes[fareKey('first','S0','S1',options.date)]={fares:{O:30}};
  const r=plan(n,opts);assert.equal(r.cheapest.cost,110);assert.equal(r.cheapest.duration,140);
  const completed=plan(n,{...opts,fixedLegs:[selection(0),selection(1)]});
  assert.equal(completed.count,1);assert.equal(completed.cheapest.cost,110);
});

test('selected prefix advances mandatory waypoint order and retains whole-journey duration bounds',()=>{
  const n=fixture([trip('first',[0,1],[60,100]),trip('next',[1,3],[130,170]),trip('last',[3,2],[200,250])]);
  const opts={...options,fixedLegs:[selection(0)],waypoints:[{stations:[1]},{stations:[3]}]};
  assert.equal(plan(n,opts).count,1);
  assert.equal(plan(n,{...opts,waypoints:[{stations:[3]},{stations:[1]}]}).count,0);
  assert.equal(plan(n,{...opts,maxDuration:189}).count,0);
  assert.equal(plan(n,{...opts,maxDuration:190}).fastest.duration,190);
});

test('real Tianjin to Zhengzhou selection can be joined to Chongqing without replacing the chosen train',()=>{
  const n=JSON.parse(fs.readFileSync(new URL('../../frontend/rail/data/network.json',import.meta.url),'utf8'));
  const byName=name=>n.stops.findIndex(s=>s[1]===name);
  const opts={origin:[byName('天津西')],destination:[byName('重庆北')],date:'20261023',earliest:360,maxTransfers:2};
  const chosen=directServices(n,{...opts,destination:[byName('郑州东')]}).find(l=>l.train==='G1739');
  assert.ok(chosen);const onward=connectionServices(n,{prefix:[chosen],destination:opts.destination,date:opts.date});
  assert.ok(onward.length);assert.ok(onward.every(l=>canTransfer(n,chosen.to,l.from)&&l.departure>=chosen.arrival+30));
  const r=plan(n,{...opts,fixedLegs:[chosen]});assert.ok(r.count);
  assert.ok(r.candidates.every(r=>r.legs[0].train==='G1739'&&r.legs[0].to===chosen.to&&r.departure===chosen.departure));
});
