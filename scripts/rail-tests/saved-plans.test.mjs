import test from 'node:test';
import assert from 'node:assert/strict';
import {savePlanRecord,decodeLibrary,restorePlan,restoreChoice,routeSelection,priceRoute,comparisonKey,rankComparisons} from '../../frontend/rail/saved-plans.js';
import {plan,fareKey} from '../../frontend/rail/router.js';
const trip=(name,stops,times)=>[name,0,stops,times,times,stops.map((_,i)=>i*100),'','G'];
const n={meta:{version:'20261020',startDate:'20261020',endDate:'20261022'},stops:[['T','天津'],['BN','北京南'],['BX','北京西'],['C','重庆北']],services:[['20261020','20261021']],trips:[trip('G1',[0,1],[360,420]),trip('G2',[2,3],[480,900]),trip('G3',[0,3],[400,1000])]};
const options={origin:[0],destination:[3],date:'20261020',earliest:360,maxTransfers:1,trainType:'all',seatPreference:'standard',valueOfTime:40,waypoints:[],fixedLegs:[]};
const fields={from:'天津',to:'重庆',date:'2026-10-20',time:'06:00'};
const make=(name='方案 A',extra={})=>savePlanRecord(n,{name,fields,options,...extra});

test('independent saved plans round-trip without sharing mutable nodes or selected legs',()=>{
  const draft={...options,waypoints:[{name:'北京',stations:[1,2]}]},a=make('A',{options:draft});draft.waypoints[0].stations.push(3);
  const route=plan(n,options).fastest,b=make('B',{route}),c=make('C');route.legs[0].arrival=999;
  const library=decodeLibrary(JSON.stringify({version:1,plans:[a,b,c]}));
  assert.equal(library.length,3);assert.equal(new Set(library.map(p=>p.id)).size,3);
  assert.deepEqual(restorePlan(n,library[0]).options.waypoints[0].stations,[1,2]);
  const fixed=restorePlan(n,library[1]);assert.equal(fixed.route.legs[0].arrival,420);assert.equal(fixed.route.duration,540);assert.equal(fixed.route.legs[1].from,2);
  assert.equal(restorePlan(n,library[2]).route,null);
  const revised=savePlanRecord(n,{name:'B 修改',fields,options},b);assert.equal(revised.id,b.id);assert.equal(b.name,'B');assert.equal(revised.legs.length,0);
});

test('restoration rejects invalid snapshots, station codes, calendars and changed fixed trains',()=>{
  const p=make('完整',{route:plan(n,options).fastest});
  assert.throws(()=>restorePlan(n,{...p,snapshot:'old'}),/时刻表已更新/);
  assert.throws(()=>restorePlan(n,{...p,origin:['missing']}),/未收录/);
  assert.throws(()=>restorePlan(n,{...p,fields:{...p.fields,date:'2026-10-23'}}),/日期超出/);
  assert.throws(()=>restorePlan(n,{...p,fields:{...p.fields,time:'06:90'}}),/出发时间无效/);
  assert.throws(()=>restorePlan(n,{...p,legs:p.legs.map((l,i)=>i===0?{...l,train:'wrong'}:l)}),/不在当前/);
  assert.throws(()=>decodeLibrary('{broken'));
  assert.throws(()=>decodeLibrary(JSON.stringify({version:1,plans:[p,p]})),/不完整/);
});

test('matched choice survives reload while original draft constraints remain editable',()=>{
  const p=make(),route=plan(n,options).fastest,withChoice={...p,choice:routeSelection(route)};
  const restored=restorePlan(n,withChoice);assert.equal(restored.options.fixedLegs.length,0);
  const chosen=restoreChoice(n,withChoice,restored.options);assert.deepEqual(chosen.legs.map(l=>l.train),['G1','G2']);
  const prefix={...options,fixedLegs:[route.legs[0]]};
  assert.throws(()=>restoreChoice(n,{...p,choice:routeSelection(plan(n,{...options,maxTransfers:0}).fastest)},prefix),/固定车次/);
  assert.throws(()=>restoreChoice(n,{...p,choice:[routeSelection(route)[0]]},options),/不完整/);
});

test('only fresh, fully quoted exact train sections enter price ranking',()=>{
  const r=plan(n,options).fastest,now=Date.parse('2026-10-20T04:00:00Z'),q={};
  for(const l of r.legs)q[fareKey(l.train,n.stops[l.from][0],n.stops[l.to][0],options.date)]={fares:{O:100},queriedAt:new Date(now).toISOString(),source:'12306公开查询'};
  const priced=priceRoute(n,r,options,q,now);assert.equal(priced.cost,200);assert.equal(priced.crossStationTransfers,1);
  assert.equal(priceRoute(n,r,options,q,now+600001).cost,null);
  assert.equal(priceRoute(n,r,{...options,seatPreference:'hard'},q,now).cost,null);
  delete q[fareKey('G2','BX','C',options.date)];const partial=priceRoute(n,r,options,q,now);assert.equal(partial.verified,false);assert.equal(partial.cost,null);
  const ranks=rankComparisons([{id:'known',route:priced},{id:'unknown',route:{...partial,duration:400}}]);
  assert.deepEqual(ranks.fastest,['unknown']);assert.deepEqual(ranks.cheapest,['known']);assert.deepEqual(ranks.balanced,['known']);
});

test('comparison groups separate dates, endpoints, earliest times, train types and seats but allow different nodes',()=>{
  const a=make(),b=make('B',{options:{...options,waypoints:[{name:'北京',stations:[1,2]}]}});assert.equal(comparisonKey(a),comparisonKey(b));
  for(const [field,value] of [['date','2026-10-21'],['time','07:00'],['seat','hard'],['type','normal']])assert.notEqual(comparisonKey(a),comparisonKey({...a,fields:{...a.fields,[field]:value}}));
  assert.notEqual(comparisonKey(a),comparisonKey({...a,origin:['BX']}));
  const ranked=rankComparisons([{id:'A',route:{duration:60,cost:100,transfers:0,verified:true}},{id:'B',route:{duration:180,cost:50,transfers:0,verified:true}}],40);
  assert.deepEqual(ranked.fastest,['A']);assert.deepEqual(ranked.cheapest,['B']);assert.deepEqual(ranked.balanced,['A']);
});
