import test from 'node:test';import assert from 'node:assert/strict';
import {RailMap,project} from '../../frontend/rail/map.js';

function fixture(){
  const frames=[];
  const context=()=>new Proxy({arcs:[],arc(...args){this.arcs.push(args);}},{get:(o,k)=>k in o?o[k]:(()=>{})});
  const canvas=()=>({width:0,height:0,parentElement:{getBoundingClientRect:()=>({width:900,height:550})},getContext(){return this.ctx??=context();},addEventListener(){},classList:{add(){},remove(){}}});
  globalThis.document={createElement:canvas};globalThis.devicePixelRatio=1;
  globalThis.Path2D=class{moveTo(){}lineTo(){}closePath(){}};
  globalThis.ResizeObserver=class{observe(){}};
  globalThis.requestAnimationFrame=fn=>{frames.push(fn);return frames.length;};
  const network={stops:[['A','甲',116,40],['B','乙',117,39]],activeStops:[0,1],trips:[['G1',0,[0,1],[0,60],[0,60],[0,100],'line','G']]};
  const route={id:'a',legs:[{trip:0,from:0,to:1,fromIndex:0,toIndex:1,departure:0,arrival:60}]};
  const map=new RailMap(canvas(),()=>{});map.resize();map.setData(network,{shapes:{line:[[116,40],[117,39]]},edges:[[0,1]]},{features:[]});map.setRoute(route);
  const flush=()=>{const pending=frames.splice(0);pending.forEach(fn=>fn());};flush();return {map,flush,frames,route};
}

test('playback moves the train without redrawing the national rail network or recomputing geometry',()=>{
  const {map,flush,route}=fixture(),redraws=map.stats.fullRedraws;
  // The expensive scene/geometry routines must never be used by ordinary playback.
  const drawScene=map.drawScene,routePoints=map.routePoints;
  map.drawScene=()=>{throw new Error('playback rebuilt scene');};map.routePoints=()=>{throw new Error('playback rebuilt geometry');};
  for(let minute=0;minute<=60;minute++){map.setPlayback(minute);flush();}
  assert.equal(map.stats.fullRedraws,redraws);
  assert.deepEqual(map.ctx.arcs.at(-1).slice(0,2),project([117,39]));
  map.setPlayback(30);flush();const point=map.ctx.arcs.at(-1);assert.deepEqual(point.slice(0,2),project([116.5,39.5]));
  map.drawScene=drawScene;map.routePoints=routePoints;
  map.setRoute({...route,id:'b'},{color:'#abc'});flush();assert.equal(map.stats.fullRedraws,redraws+1);
  map.setRoute(null);flush();assert.equal(map.route,null);
});

test('rapid map input coalesces to one frame and view/layer changes invalidate the cache',()=>{
  const {map,flush,frames}=fixture(),redraws=map.stats.fullRedraws;
  for(let i=0;i<100;i++){map.tx++;map.draw();}
  assert.equal(frames.length,1);flush();assert.equal(map.stats.fullRedraws,redraws+1);
  map.filters.G=false;map.draw();flush();assert.equal(map.stats.fullRedraws,redraws+2);
  map.zoom(1.2);flush();assert.equal(map.stats.fullRedraws,redraws+2);
  map.finishInteraction();flush();assert.equal(map.stats.fullRedraws,redraws+3);
});

test('cross-station animation travels between the two station points during the gap without redrawing',()=>{
  const {map,flush,route}=fixture();
  const second={...route.legs[0],from:0,to:1,departure:120,arrival:180};
  map.setRoute({id:'cross',legs:[route.legs[0],second]});flush();
  const redraws=map.stats.fullRedraws;
  map.drawScene=()=>{throw new Error('transfer playback rebuilt scene');};
  map.setPlayback(60);flush();assert.deepEqual(map.ctx.arcs.at(-1).slice(0,2),map.stationPoints[1]);
  map.setPlayback(90);flush();
  const expected=map.stationPoints[0].map((p,i)=>(p+map.stationPoints[1][i])/2);
  assert.deepEqual(map.ctx.arcs.at(-1).slice(0,2),expected);
  map.setPlayback(120);flush();assert.deepEqual(map.ctx.arcs.at(-1).slice(0,2),map.stationPoints[0]);
  assert.equal(map.stats.fullRedraws,redraws);
});

test('city picking follows the cached image while panning and zooming before the final redraw',()=>{
  const {map,flush}=fixture();map.cityMode=true;map.cities=[{name:'甲',stations:[0]}];map.draw();flush();
  const hit=map.cityHitboxes[0];assert.ok(hit);const view={...map.sceneView};let picked;
  map.onCity=city=>picked=city.name;
  map.panBy(35,20);map.zoom(1.1);flush();
  const ratio=map.scale/view.scale;
  map.pick(hit.x*ratio+map.tx-view.tx*ratio,hit.y*ratio+map.ty-view.ty*ratio);
  assert.equal(picked,'甲');map.finishInteraction();flush();
});
