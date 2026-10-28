import test from 'node:test';import assert from 'node:assert/strict';import {plan,estimateFare} from '../../frontend/rail/router.js';
const t=(name,stops,times,dist)=>[name,0,stops,times,times,dist,'','K'];
const network=trips=>({meta:{startDate:'20261020',endDate:'20261021'},services:[['20261020']],trips});
const opts={origin:[0],destination:[4],date:'20261020',earliest:0};
test('upper bounds include direct and every lower transfer count; two transfers can be cheapest',()=>{
  const n=network([t('direct',[0,4],[60,120],[0,1000]),t('a',[0,1],[60,90],[0,10]),t('b',[1,2],[120,150],[0,10]),t('c',[2,4],[180,210],[0,10])]);
  const r=plan(n,{...opts,maxTransfers:2});assert.equal(r.fastest.transfers,0);assert.equal(r.cheapest.transfers,2);assert.equal(r.cheapest.cost,15);
  assert.deepEqual(r.byTransfers.map(b=>b.transfers),[0,2]);
  assert.equal(plan(n,{...opts,maxTransfers:1}).cheapest.transfers,0);
});
test('three-transfer paths are searched and ordered mandatory nodes require a real alight',()=>{
  const n=network([t('a',[0,1],[60,90],[0,10]),t('b',[1,2],[120,150],[0,10]),t('c',[2,3],[180,210],[0,10]),t('d',[3,4],[240,270],[0,10])]);
  assert.equal(plan(n,{...opts,maxTransfers:2}).count,0);
  const r=plan(n,{...opts,maxTransfers:3,waypoints:[{stations:[1]},{stations:[2]},{stations:[3]}]});assert.equal(r.cheapest.transfers,3);assert.equal(r.trace.length,4);
  assert.equal(plan(n,{...opts,maxTransfers:3,waypoints:[{stations:[2]},{stations:[1]}]}).count,0);
});
test('an earlier arrival cannot incorrectly dominate a later one under maximum wait',()=>{
  const n=network([t('early',[0,1],[0,20],[0,10]),t('late',[0,1],[200,220],[0,10]),t('onward',[1,4],[300,330],[0,10])]);
  const r=plan(n,{...opts,maxTransfers:1,maxWait:100});assert.deepEqual(r.fastest.legs.map(l=>l.train),['late','onward']);
});
test('multi-round objective values match independent enumeration on random small networks',()=>{
  let seed=919;const rand=n=>{seed=(seed*1664525+1013904223)>>>0;return seed%n;};
  for(let ex=0;ex<20;ex++){
    const trips=[];for(let i=0;i<13;i++){const a=rand(5),b=rand(5);if(a===b)continue;const d=rand(600);trips.push(t('T'+i,[a,b],[d,d+20+rand(50)],[0,20+rand(250)]));}
    for(let cap=0;cap<=3;cap++){
      const all=[];
      function walk(stop,arrival,first,cost,legs,last){
        for(let i=0;i<trips.length;i++){
          const tr=trips[i];if(i===last||tr[2][0]!==stop)continue;
          if(!legs){if(tr[4][0]>=1440)continue;}else{const wait=tr[4][0]-arrival;if(wait<30||wait>240)continue;}
          const start=legs?first:tr[4][0],fare=cost+estimateFare(tr,0,1),next=tr[2][1],ar=tr[3][1],count=legs+1;
          if(next===4){all.push({duration:ar-start,cost:fare,score:fare+(ar-start)/60*40+(count-1)*30});continue;}
          if(count<=cap&&next!==0)walk(next,ar,start,fare,count,i);
        }
      }
      walk(0,0,0,0,0,-1);const r=plan(network(trips),{...opts,maxTransfers:cap});
      assert.equal(r.count===0,all.length===0);if(!all.length)continue;
      assert.equal(r.fastest.duration,Math.min(...all.map(a=>a.duration)));assert.equal(r.cheapest.cost,Math.min(...all.map(a=>a.cost)));
      assert.ok(Math.abs(r.balanced.score-Math.min(...all.map(a=>a.score)))<1e-8);
    }
  }
});
