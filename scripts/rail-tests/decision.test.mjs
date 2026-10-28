import test from 'node:test';
import assert from 'node:assert/strict';
import {transferRisk,decisionMetrics,decisionRanks,decodeWorkspace,writeWorkspace,finalizeDecision,recoverComparison,validateRiskRules} from '../../frontend/rail/decision-model.js';
import {savePlanRecord,restorePlan,priceRoute,routeSelection} from '../../frontend/rail/saved-plans.js';
import {finalText} from '../../frontend/rail/decision-view.js';
import {plan,fareKey} from '../../frontend/rail/router.js';

const trip=(name,stops,times)=>[name,0,stops,times,times,stops.map((_,i)=>i*100),'','G'];
const network={meta:{version:'20261020',startDate:'20261020',endDate:'20261022'},stops:[['T','天津'],['BN','北京南'],['BX','北京西'],['C','重庆北']],services:[['20261020','20261021']],trips:[trip('G1',[0,1],[360,420]),trip('G2',[2,3],[480,900]),trip('G3',[0,3],[400,1000])]};
const options={origin:[0],destination:[3],date:'20261020',earliest:360,maxTransfers:1,trainType:'all',seatPreference:'standard',valueOfTime:40,waypoints:[],fixedLegs:[]};
const fields={from:'天津',to:'重庆',date:'2026-10-20',time:'06:00'};
const make=(name='A')=>savePlanRecord(network,{name,fields,options});
const route=(gap,cross=false,start=360)=>({departure:start,arrival:start+120+gap,verified:true,cost:100,legs:[{from:0,to:1,departure:start,arrival:start+60},{from:cross?2:1,to:3,departure:start+60+gap,arrival:start+120+gap}]});

test('transfer risk boundaries use worst margin and distinguish cross-station from same-station',()=>{
  for(const [gap,level] of [[44,3],[45,2],[74,2],[75,1]])assert.equal(transferRisk(route(gap)).level,level);
  for(const [gap,level] of [[33,3],[89,3],[90,2],[119,2],[120,1]])assert.equal(transferRisk(route(gap,true)).level,level);
  const cross=transferRisk(route(33,true));assert.equal(cross.minimumMargin,-57);assert.equal(cross.changes[0].required,90);
  assert.equal(transferRisk(route(33,true),{cross:30}).level,2);
  const mixed=route(120,true);mixed.legs.push({from:3,to:4,departure:mixed.arrival+40,arrival:mixed.arrival+100});
  assert.equal(transferRisk(mixed).level,3);assert.equal(transferRisk(mixed).minimumMargin,-5);
  assert.throws(()=>validateRiskRules({same:0}),/5–240/);assert.throws(()=>validateRiskRules({cross:NaN}),/5–240/);
});

test('time composition sums to elapsed duration through midnight; direct is no transfer',()=>{
  const m=decisionMetrics(route(90,true,1380));assert.equal(m.duration,210);assert.equal(m.riding+m.sameWait+m.crossWait,m.duration);assert.equal(m.crossWait,90);
  const direct={departure:1380,arrival:1500,verified:false,cost:900,legs:[{from:0,to:3,departure:1380,arrival:1500}]};
  const d=decisionMetrics(direct);assert.equal(d.risk.level,0);assert.equal(d.risk.minimumMargin,null);assert.equal(d.cost,null);assert.equal(d.transfers,0);
  assert.throws(()=>decisionMetrics({...direct,arrival:1490}),/时间不一致/);
  assert.throws(()=>decisionMetrics(route(-2)),/时间不一致/);
});

test('risk preference changes balanced winner without hiding high risk or inventing unknown fares',()=>{
  const rows=[{id:'cross',metrics:decisionMetrics(route(33,true))},{id:'same',metrics:decisionMetrics({...route(90),cost:150})},{id:'unknown',metrics:decisionMetrics({...route(30),verified:false,cost:0})}];
  const rank=decisionRanks(rows);assert.deepEqual(rank.fastest,['unknown']);assert.deepEqual(rank.cheapest,['cross']);assert.deepEqual(rank.balanced,['same']);
  assert.deepEqual(decisionRanks(rows,{avoidHigh:false,value:40}).balanced,['cross']);
  assert.deepEqual(decisionRanks([rows[0]]).balanced,[]);assert.deepEqual(decisionRanks([rows[2]]).cheapest,[]);
});

test('legacy libraries migrate without losing plans and corrupt archives cannot be overwritten',()=>{
  const a=make(),old=JSON.stringify({version:1,plans:[a]}),ws=decodeWorkspace(old);
  assert.deepEqual(ws,{version:1,plans:[a],finals:[],recovery:null});
  assert.throws(()=>decodeWorkspace(JSON.stringify({...ws,finals:[{id:'x',plan:a,savedAt:'now'}]})),/不完整/);
  assert.throws(()=>decodeWorkspace(JSON.stringify({...ws,recovery:{plans:[a,a]}})),/不完整/);
});

test('final save preserves exact selected route, reference fares and all cleared groups in one write',()=>{
  const a=make(),b=make('B');b.fields.date='2026-10-21';const ws={version:1,plans:[a,b],finals:[],recovery:null};
  const route=plan(network,options).fastest,now=Date.parse('2026-10-20T00:00:00Z'),quotes={};
  for(const l of route.legs)quotes[fareKey(l.train,network.stops[l.from][0],network.stops[l.to][0],options.date)]={fares:{O:100},queriedAt:new Date(now).toISOString(),source:'12306公开查询'};
  const priced=priceRoute(network,route,options,quotes,now),next=finalizeDecision(network,ws,a,priced,undefined,new Date(now).toISOString());
  assert.equal(ws.plans.length,2);assert.equal(next.plans.length,0);assert.equal(next.finals.length,1);assert.deepEqual(next.finals[0].plan.legs,routeSelection(route));
  assert.equal(next.finals[0].itinerary.legs[1].from,'北京西');assert.equal(next.finals[0].reference.metrics.cost,200);assert.equal(next.finals[0].reference.metrics.risk.level,3);
  assert.equal(next.recovery.plans.length,2);assert.equal(decodeWorkspace(JSON.stringify(next)).finals[0].id,next.finals[0].id);
  const restored=restorePlan(network,next.finals[0].plan);assert.equal(priceRoute(network,restored.route,restored.options,{},now).cost,null);
  const copied=finalText(next.finals[0]);assert.match(copied,/北京南 → 北京西，间隔 60 分钟/);assert.match(copied,/历史参考/);assert.match(copied,/高风险/);
  let raw=JSON.stringify(ws),writes=0;const storage={getItem:()=>raw,setItem:(_,v)=>{raw=v;writes++;}};
  writeWorkspace(storage,'key',raw,next);assert.equal(writes,1);assert.equal(JSON.parse(raw).plans.length,0);assert.equal(JSON.parse(raw).finals.length,1);
  const recovered=recoverComparison(next);assert.deepEqual(recovered.plans,ws.plans);assert.equal(recovered.finals.length,1);assert.equal(recovered.recovery,null);
  assert.throws(()=>recoverComparison({...next,plans:[a]}),/已有新方案/);
});

test('failed storage or stale tabs leave the original comparison library intact',()=>{
  const a=make(),ws={version:1,plans:[a],finals:[],recovery:null},raw=JSON.stringify(ws);
  const next=finalizeDecision(network,ws,a,plan(network,options).fastest);
  let stored=raw;const storage={getItem:()=>stored,setItem:()=>{throw new Error('QuotaExceeded');}};
  assert.throws(()=>writeWorkspace(storage,'key',raw,next),/对比库未清空/);assert.equal(stored,raw);assert.equal(ws.plans.length,1);
  assert.throws(()=>writeWorkspace(storage,'key','stale',next),/另一个页面/);assert.equal(stored,raw);
  assert.throws(()=>finalizeDecision(network,ws,{...a,snapshot:'old'},plan(network,options).fastest),/时刻表已更新/);
  const incomplete={...plan(network,options).fastest,legs:plan(network,options).fastest.legs.slice(0,1)};
  assert.throws(()=>finalizeDecision(network,ws,a,incomplete),/完整行程/);
  assert.equal(next.finals[0].reference.metrics.cost,null);
});
