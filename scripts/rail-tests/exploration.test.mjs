import test from 'node:test';import assert from 'node:assert/strict';
import {directServices} from '../../frontend/rail/services.js';import {plan,fareKey} from '../../frontend/rail/router.js';
const tr=(name,stops,times,kind='G')=>[name,0,stops,times,times,stops.map((_,i)=>i*100),'',kind];
const net=trips=>({meta:{startDate:'20261020',endDate:'20261023'},stops:[['A','甲'],['B','乙'],['C','丙']],services:[['20261020']],trips});
test('city departures use the boarding date and original service calendar across midnight',()=>{
  const n=net([tr('G1',[0,1,2],[1400,1500,1600])]);
  const rows=directServices(n,{origin:[1],destination:[2],date:'20261021',earliest:0});
  assert.equal(rows.length,1);assert.equal(rows[0].departure,60);assert.equal(rows[0].arrival,160);assert.equal(rows[0].serviceDay,-1);
  assert.equal(directServices(n,{origin:[1],destination:[2],date:'20261020'}).length,0);
  assert.equal(directServices(n,{origin:[1],destination:[2],date:'20261021',earliest:61}).length,0);
});
test('city service lookup preserves exact stations, travel direction and train-type filter',()=>{
  const n=net([tr('G1',[0,1,2],[60,90,120]),tr('K1',[1,2],[100,300],'K')]);
  const rows=directServices(n,{origin:[0,1],destination:[2],date:'20261020',trainType:'fast'});
  assert.deepEqual(rows.map(l=>[l.train,l.from,l.to]),[['G1',0,2],['G1',1,2]]);
  assert.equal(directServices(n,{origin:[2],destination:[0,1],date:'20261020'}).length,0);
  assert.equal(directServices(n,{origin:[0,1],destination:[2],date:'20261020',trainType:'normal'}).length,1);
});
test('planner returns bounded distinct alternatives with ordered ranking and no unquoted fares',()=>{
  const n=net(Array.from({length:12},(_,i)=>tr('G'+i,[0,2],[60+i*30,100+i*35]))),opts={origin:[0],destination:[2],date:'20261020',maxTransfers:0};
  const r=plan(n,opts);assert.equal(r.ranked.fastest.length,8);assert.equal(new Set(r.ranked.fastest.map(x=>x.id)).size,8);
  assert.equal(r.ranked.fastest[0].id,r.fastest.id);assert.ok(r.ranked.fastest.every((x,i,a)=>!i||x.duration>=a[i-1].duration));
  const fareQuotes={};for(let i=0;i<4;i++)fareQuotes[fareKey('G'+i,'A','C','20261020')]={fares:{O:100-i*10}};
  const q=plan(n,{...opts,pricingMode:'quoted',fareQuotes});assert.equal(q.ranked.cheapest.length,4);assert.deepEqual(q.ranked.cheapest.map(x=>x.cost),[70,80,90,100]);
});
