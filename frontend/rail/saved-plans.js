import {validateFixedLegs,fareKey,chooseFare,dateShift} from './router.js';
import {crossTransfers} from './transfers.js';
export const STORAGE_KEY='rail-atlas-plans-v1';
export const MAX_PLANS=20;
const selection=({trip,train,fromIndex,toIndex,serviceDay})=>({trip,train,fromIndex,toIndex,serviceDay});
export const routeSelection=route=>route.legs.map(selection);
export function savePlanRecord(network,{name,fields,options,route},previous){
  if(!options.origin?.length||!options.destination?.length)throw new Error('请先选择有效的出发地和目的地。');
  if(options.origin.some(s=>options.destination.includes(s)))throw new Error('请选择不同的起终点。');
  const fixed=validateFixedLegs(network,route?.legs||options.fixedLegs||[],options);
  const codes=stations=>stations.map(i=>network.stops[i][0]);
  return {id:previous?.id||crypto.randomUUID(),name:String(name||'未命名方案').trim().slice(0,40)||'未命名方案',snapshot:String(network.meta.version),updatedAt:new Date().toISOString(),
    fields:{from:fields.from,to:fields.to,date:fields.date,time:fields.time,transfers:String(options.maxTransfers),type:options.trainType,seat:options.seatPreference,value:String(options.valueOfTime)},
    origin:codes(options.origin),destination:codes(options.destination),waypoints:(options.waypoints||[]).map(w=>({name:w.name,codes:codes(w.stations)})),legs:fixed.map(selection)};
}
export function decodeLibrary(raw){
  if(!raw)return [];
  const data=JSON.parse(raw);if(data.version!==1||!Array.isArray(data.plans))throw new Error('保存的方案格式无法识别，原记录未被覆盖。');
  if(data.plans.length>MAX_PLANS)throw new Error('保存的方案数量超出支持范围，原记录未被覆盖。');
  const ids=new Set();
  for(const p of data.plans){if(!p||typeof p.id!=='string'||ids.has(p.id)||typeof p.name!=='string'||!p.fields||!Array.isArray(p.origin)||!Array.isArray(p.destination)||!Array.isArray(p.waypoints)||!Array.isArray(p.legs))throw new Error('保存的方案记录不完整，原记录未被覆盖。');ids.add(p.id);}
  return data.plans;
}
export function restorePlan(network,p){
  if(p.snapshot!==String(network.meta.version))throw new Error('时刻表已更新，请重新编辑此方案。');
  const byCode=new Map(network.stops.map((s,i)=>[s[0],i]));
  const stops=codes=>{if(!Array.isArray(codes)||!codes.length||codes.some(c=>!byCode.has(c)))throw new Error('方案包含未收录的车站，请重新编辑。');return codes.map(c=>byCode.get(c));};
  const f=p.fields,[h,m]=String(f.time).split(':').map(Number),maxTransfers=Number(f.transfers);
  if(!/^\d{2}:\d{2}$/.test(f.time)||!Number.isInteger(h)||h<0||h>23||!Number.isInteger(m)||m<0||m>59)throw new Error('方案出发时间无效，请重新编辑。');
  if(!Number.isInteger(maxTransfers)||maxTransfers<0||maxTransfers>3||!['all','fast','normal'].includes(f.type)||!['standard','second','hard'].includes(f.seat)||!Number.isFinite(Number(f.value))||Number(f.value)<0||Number(f.value)>120||p.waypoints.length>maxTransfers)throw new Error('方案查询条件无效，请重新编辑。');
  const options={origin:stops(p.origin),destination:stops(p.destination),date:String(f.date).replaceAll('-',''),earliest:h*60+m,maxTransfers,trainType:f.type,seatPreference:f.seat,valueOfTime:Number(f.value),minTransfer:30,maxWait:240,maxDuration:2880,waypoints:p.waypoints.map(w=>({name:String(w.name),stations:stops(w.codes)})),pricingMode:'heuristic'};
  if(options.origin.some(s=>options.destination.includes(s)))throw new Error('方案起终点重复，请重新编辑。');
  options.fixedLegs=validateFixedLegs(network,p.legs,options);
  let progress=0;for(const l of options.fixedLegs)if(options.waypoints[progress]?.stations.includes(l.to))progress++;
  const last=options.fixedLegs.at(-1),complete=!!last&&options.destination.includes(last.to)&&progress===options.waypoints.length;
  if(last&&options.destination.includes(last.to)&&!complete)throw new Error('已选车次未经过全部节点，请重新编辑。');
  const route=complete?{id:options.fixedLegs.map(l=>[l.trip,l.fromIndex,l.toIndex,l.serviceDay].join(':')).join('|'),legs:options.fixedLegs,departure:options.fixedLegs[0].departure,arrival:last.arrival,duration:last.arrival-options.fixedLegs[0].departure,transfers:options.fixedLegs.length-1}:null;
  return {options,route};
}
export function restoreChoice(network,p,options){
  if(!p.choice)return null;
  const copy={...p,legs:p.choice,choice:undefined},restored=restorePlan(network,copy);
  if(!restored.route)throw new Error('已保存的候选不完整，请重新匹配。');
  const fixed=options.fixedLegs||[];
  if(fixed.some((l,i)=>JSON.stringify(selection(l))!==JSON.stringify(selection(restored.route.legs[i]||{}))))throw new Error('候选与固定车次不一致，请重新匹配。');
  return restored.route;
}
export function priceRoute(network,route,options,quotes,now=Date.now()){
  const legs=route.legs.map(l=>{
    const q=quotes[fareKey(l.train,network.stops[l.from][0],network.stops[l.to][0],dateShift(options.date,Math.floor(l.departure/1440)))];
    const fresh=q&&Number.isFinite(Date.parse(q.queriedAt))&&now-Date.parse(q.queriedAt)>=-60000&&now-Date.parse(q.queriedAt)<=600000;
    const f=fresh?chooseFare(q.fares,options.seatPreference):null;
    return {...l,cost:f?.amount??null,fareVerified:!!f,seat:f?.seat,seatName:f?.seatName,quotedAt:f?q.queriedAt:undefined,quoteSource:f?q.source:undefined};
  });
  const verified=legs.every(l=>l.fareVerified),cost=verified?legs.reduce((s,l)=>s+l.cost,0):null;
  return {...route,legs,cost,verified,crossStationTransfers:crossTransfers(legs).length,score:verified?cost+route.duration/60*options.valueOfTime+route.transfers*30:null};
}
export function comparisonKey(plan){const f=plan.fields;return [plan.origin.slice().sort().join(','),plan.destination.slice().sort().join(','),f.date,f.time,f.type,f.seat].join('|');}
export function rankComparisons(rows,valueOfTime=40){
  const matched=rows.filter(r=>r.route),priced=matched.filter(r=>r.route.verified&&Number.isFinite(r.route.cost));
  const best=(list,score)=>{const min=Math.min(...list.map(score));return list.filter(r=>score(r)===min).map(r=>r.id);};
  return {fastest:best(matched,r=>r.route.duration),cheapest:best(priced,r=>r.route.cost),balanced:best(priced,r=>r.route.cost+r.route.duration/60*valueOfTime+r.route.transfers*30)};
}
