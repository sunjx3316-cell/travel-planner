import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {plan,estimateFare,dateShift} from '../../frontend/rail/router.js';
import {canTransfer} from '../../frontend/rail/transfers.js';

const trip=(name,stops,arr,dist,kind='K',service=0,dep=arr)=>[name,service,stops,arr,dep,dist,'',kind];
const fixture=(trips,services=[['20261020']])=>({meta:{startDate:'20261019',endDate:'20261023'},services,trips});
const query={origin:[0],destination:[2],date:'20261020',earliest:0,maxTransfers:1};

test('fastest minimizes elapsed journey time, rather than earliest arrival',()=>{
  const n=fixture([trip('early',[0,2],[60,180],[0,200]),trip('fast',[0,2],[600,660],[0,500])]);
  const r=plan(n,query);
  assert.equal(r.fastest.legs[0].train,'fast');
  assert.equal(r.cheapest.legs[0].train,'early');
});

test('through ticket is priced once; split segments do not add minimum fares',()=>{
  const t=trip('local',[0,1,2],[60,80,100],[0,10,20]);
  assert.equal(estimateFare(t,0,2),5);
  const r=plan(fixture([t]),query);
  assert.equal(r.cheapest.cost,5);assert.equal(r.cheapest.transfers,0);
});

test('one-transfer search retains expensive first legs needed to make a connection',()=>{
  const n=fixture([trip('late-cheap',[0,1],[60,180],[0,30]),trip('early-costly',[0,1],[60,100],[0,100]),trip('connection',[1,2],[130,200],[0,50])]);
  const r=plan(n,query);
  assert.deepEqual(r.fastest.legs.map(l=>l.train),['early-costly','connection']);
  assert.equal(r.fastest.duration,140);assert.equal(r.count,1);
});

test('transfer wait has inclusive 30 and 240 minute boundaries',()=>{
  const n=fixture([trip('first',[0,1],[60,100],[0,30]),...[[129,'too-short'],[130,'minimum'],[340,'maximum'],[341,'too-long']].map(([d,name])=>trip(name,[1,2],[d,d+20],[0,30]))]);
  const r=plan(n,query);assert.equal(r.count,2);
  assert.equal(r.fastest.legs[1].train,'minimum');
});

test('boarding after midnight uses the train original departure service date',()=>{
  const n=fixture([trip('overnight',[0,1,2],[1380,1500,1560],[0,100,200])],[['20261019']]);
  const r=plan(n,{...query,origin:[1]});
  assert.equal(r.count,1);assert.equal(r.fastest.departure,60);assert.equal(r.fastest.arrival,120);
  assert.equal(r.fastest.legs[0].serviceDay,-1);
});

test('cross-midnight transfer may board next-day service and cannot board absent service',()=>{
  const a=trip('first',[0,1],[1380,1460],[0,100]);
  const b=trip('second',[1,2],[60,180],[0,100],'K',1);
  const r=plan(fixture([a,b],[['20261020'],['20261021']]),query);
  assert.equal(r.count,1);assert.equal(r.fastest.arrival,1620);
  assert.equal(plan(fixture([a,b],[['20261020'],['20261020']]),query).count,0);
});

test('no inter-station teleport, no transfers when direct-only is requested',()=>{
  const n=fixture([trip('one',[0,1],[60,100],[0,50]),trip('two',[3,2],[140,200],[0,50])]);
  assert.equal(plan(n,query).count,0);
  const m=fixture([trip('one',[0,1],[60,100],[0,50]),trip('two',[1,2],[140,200],[0,50])]);
  assert.equal(plan(m,{...query,maxTransfers:0}).count,0);
});

test('earliest departure, train-type and duration filters are enforced',()=>{
  const n=fixture([trip('G1',[0,2],[60,120],[0,100],'G'),trip('K1',[0,2],[600,800],[0,100])]);
  assert.equal(plan(n,{...query,earliest:300}).fastest.legs[0].train,'K1');
  assert.equal(plan(n,{...query,trainType:'normal'}).fastest.legs[0].train,'K1');
  assert.equal(plan(n,{...query,trainType:'fast'}).cheapest.legs[0].train,'G1');
  assert.equal(plan(fixture([trip('long',[0,2],[60,3000],[0,100])]),query).count,0);
});

test('dates outside the snapshot and overlapping station groups are rejected',()=>{
  const n=fixture([trip('one',[0,2],[60,120],[0,100])]);
  assert.throws(()=>plan(n,{...query,date:'20261024'}),/覆盖范围/);
  assert.throws(()=>plan(n,{...query,destination:[0,2]}),/相同车站/);
  assert.equal(dateShift('20261231',1),'20270101');
});

test('zero time-value yields minimum estimated cost, high time-value can favor fastest',()=>{
  const n=fixture([trip('fast',[0,2],[60,120],[0,500],'G'),trip('cheap',[0,2],[60,660],[0,100])]);
  assert.equal(plan(n,{...query,valueOfTime:0}).balanced.legs[0].train,'cheap');
  assert.equal(plan(n,{...query,valueOfTime:120}).balanced.legs[0].train,'fast');
});

test('agrees with an independent brute-force oracle on 25 small randomized timetables',()=>{
  let seed=7331;
  const rand=n=>{seed=(seed*1664525+1013904223)>>>0;return seed%n;};
  for(let example=0;example<25;example++){
    const trips=[];
    for(let i=0;i<16;i++){
      const stops=[...new Set([rand(5),rand(5),rand(5)])];if(stops.length<2)continue;
      const base=rand(1000),arr=stops.map((_,j)=>base+j*(30+rand(50)));
      arr.sort((a,b)=>a-b);
      trips.push(trip('T'+i,stops,arr,stops.map((_,j)=>j*(20+rand(100)))));
      // Monotonic distance is a data invariant of real input.
      trips.at(-1)[5].sort((a,b)=>a-b);
    }
    const candidates=[];
    const record=legs=>{
      const duration=legs.at(-1).arr-legs[0].dep,cost=legs.reduce((a,l)=>a+l.cost,0),transfers=legs.length-1;
      candidates.push({duration,cost,transfers,departure:legs[0].dep,score:cost+duration/60*40+transfers*30});
    };
    for(let a=0;a<trips.length;a++){
      const t=trips[a],i=t[2].indexOf(0);if(i<0)continue;
      for(let j=i+1;j<t[2].length;j++){
        const l={dep:t[4][i],arr:t[3][j],cost:estimateFare(t,i,j)};
        if(t[2][j]===2){record([l]);continue;}
        if(t[2][j]===0)continue;
        for(let b=0;b<trips.length;b++){
          if(a===b)continue;
          const u=trips[b],x=u[2].indexOf(t[2][j]),y=u[2].indexOf(2);
          if(x<0||y<=x)continue;
          const wait=u[4][x]-l.arr;if(wait<30||wait>240)continue;
          record([l,{dep:u[4][x],arr:u[3][y],cost:estimateFare(u,x,y)}]);
        }
      }
    }
    const r=plan(fixture(trips),query);
    // Dominated labels are now merged, so counts describe evaluated arrivals,
    // not every combinatorial path. Objective minima must still match exactly.
    assert.ok(r.count<=candidates.length);
    assert.equal(r.count===0,candidates.length===0);
    if(!candidates.length)continue;
    assert.equal(r.fastest.duration,Math.min(...candidates.map(c=>c.duration)));
    assert.equal(r.cheapest.cost,Math.min(...candidates.map(c=>c.cost)));
    assert.ok(Math.abs(r.balanced.score-Math.min(...candidates.map(c=>c.score)))<1e-8);
  }
});

test('real nationwide snapshot: calendars, cross-day waits and estimate sums remain valid',()=>{
  const n=JSON.parse(fs.readFileSync(new URL('../../frontend/rail/data/network.json',import.meta.url),'utf8'));
  const city=name=>n.activeStops.filter(i=>n.stops[i][1].startsWith(name));
  for(const [a,b] of [['北京','上海'],['广州','长沙'],['南京','杭州'],['昆明','大理']]){
    const r=plan(n,{...query,origin:city(a),destination:city(b),earliest:360});
    assert.ok(r.count>0);
    for(const k of ['fastest','cheapest','balanced']){
      const it=r[k];assert.equal(it.cost,it.legs.reduce((s,l)=>s+l.cost,0));
      assert.equal(it.duration,it.arrival-it.departure);assert.ok(it.duration<=2880);
      for(const l of it.legs){
        assert.ok(n.services[n.trips[l.trip][1]].includes(dateShift('20261020',l.serviceDay)));
        assert.ok(l.arrival>=l.departure);
      }
      if(it.transfers){const [first,second]=it.legs;assert.ok(canTransfer(n,first.to,second.from));assert.ok(second.departure-first.arrival>=30&&second.departure-first.arrival<=240);}
    }
  }
});
