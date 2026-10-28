import {decodeLibrary,restorePlan,routeSelection} from './saved-plans.js';
export const DEFAULT_RISK={same:45,cross:90,caution:30};
export function validateRiskRules(input=DEFAULT_RISK){
  const rules={...DEFAULT_RISK,...input};
  for(const key of ['same','cross'])if(!Number.isInteger(rules[key])||rules[key]<5||rules[key]>240)throw new Error('预留时间请填写 5–240 分钟的整数。');
  rules.caution=30;return rules;
}
export function transferRisk(route,input=DEFAULT_RISK){
  const rules=validateRiskRules(input),changes=route.legs.slice(1).map((l,i)=>{
    const previous=route.legs[i],cross=previous.to!==l.from,gap=l.departure-previous.arrival,required=cross?rules.cross:rules.same,margin=gap-required;
    return {from:previous.to,to:l.from,cross,gap,required,margin,level:margin<0?3:margin<rules.caution?2:1};
  });
  const level=changes.length?Math.max(...changes.map(c=>c.level)):0;
  return {level,label:['无需换乘','余量较充足','需留意','高风险'][level],minimumMargin:changes.length?Math.min(...changes.map(c=>c.margin)):null,changes,rules};
}
export function decisionMetrics(route,rules=DEFAULT_RISK){
  const risk=transferRisk(route,rules),riding=route.legs.reduce((s,l)=>s+l.arrival-l.departure,0),sameWait=risk.changes.filter(c=>!c.cross).reduce((s,c)=>s+c.gap,0),crossWait=risk.changes.filter(c=>c.cross).reduce((s,c)=>s+c.gap,0);
  const elapsed=route.arrival-route.departure;
  if(!route.legs.length||!Number.isFinite(elapsed)||elapsed<=0||route.legs.some(l=>l.arrival<=l.departure)||riding+sameWait+crossWait!==elapsed||risk.changes.some(c=>c.gap<0))throw new Error('行程时间不一致，请重新匹配。');
  return {riding,sameWait,crossWait,duration:elapsed,transfers:risk.changes.length,crossings:risk.changes.filter(c=>c.cross).length,cost:route.verified&&Number.isFinite(route.cost)?route.cost:null,risk};
}
export function decisionRanks(rows,{value=40,avoidHigh=true}={}){
  const best=(list,get)=>{const min=Math.min(...list.map(get));return list.filter(r=>get(r)===min).map(r=>r.id);};
  const priced=rows.filter(r=>r.metrics.cost!==null),eligible=avoidHigh?priced.filter(r=>r.metrics.risk.level<3):priced;
  return {fastest:best(rows,r=>r.metrics.duration),cheapest:best(priced,r=>r.metrics.cost),risk:best(rows,r=>r.metrics.risk.level),balanced:best(eligible,r=>r.metrics.cost+r.metrics.duration/60*value+r.metrics.transfers*30)};
}
export function decodeWorkspace(raw){
  const plans=decodeLibrary(raw),data=raw?JSON.parse(raw):{};
  if(data.finals!==undefined&&!Array.isArray(data.finals))throw new Error('最终行程记录格式无效，原记录未被覆盖。');
  for(const f of data.finals||[]){
    const m=f?.reference?.metrics,it=f?.itinerary;
    if(!f||typeof f.id!=='string'||!f.plan||!Array.isArray(f.plan.legs)||!Number.isFinite(Date.parse(f.savedAt))||!it||typeof it.date!=='string'||!Array.isArray(it.legs)||!it.legs.length||it.legs.some(l=>!l||typeof l.train!=='string'||typeof l.from!=='string'||typeof l.to!=='string'||!Number.isFinite(l.departure)||!Number.isFinite(l.arrival))||!m||!Number.isFinite(m.duration)||!(m.cost===null||Number.isFinite(m.cost))||!m.risk||![0,1,2,3].includes(m.risk.level)||typeof m.risk.label!=='string'||!f.reference.rules)throw new Error('最终行程记录不完整，原记录未被覆盖。');
    validateRiskRules(f.reference.rules);
  }
  if(data.recovery!==undefined&&data.recovery!==null)decodeLibrary(JSON.stringify({version:1,plans:data.recovery.plans}));
  return {version:1,plans,finals:data.finals||[],recovery:data.recovery||null};
}
// One localStorage write commits both the archived decision and the emptied library.
// A quota failure leaves the old value intact; stale tabs must not overwrite it.
export function writeWorkspace(storage,key,expected,next){
  if(storage.getItem(key)!==expected)throw new Error('另一个页面更新了方案，请刷新后再操作，避免覆盖修改。');
  const encoded=JSON.stringify(next);
  try{storage.setItem(key,encoded);}catch{throw new Error('保存未成功，对比库未清空。请检查浏览器存储空间或权限。');}
  return encoded;
}
export function finalizeDecision(network,workspace,p,route,rules=DEFAULT_RISK,now=new Date().toISOString()){
  if(!workspace.plans.some(x=>x.id===p.id))throw new Error('这条方案已不在对比库中，请重新选择。');
  const plan={...structuredClone(p),legs:routeSelection(route),choice:undefined};
  const rebuilt=restorePlan(network,plan).route;if(!rebuilt)throw new Error('请先匹配完整行程，再保存最终方案。');
  // Preserve reference prices as a dated snapshot, never as fresh quotes after reload.
  const metrics=decisionMetrics({...rebuilt,verified:route.verified,cost:route.cost},rules);
  const itinerary={date:plan.fields.date,legs:rebuilt.legs.map(l=>({train:l.train,from:network.stops[l.from][1],to:network.stops[l.to][1],fromCode:network.stops[l.from][0],toCode:network.stops[l.to][0],departure:l.departure,arrival:l.arrival}))};
  const final={id:crypto.randomUUID(),savedAt:now,plan,itinerary,reference:{metrics,fares:route.legs.map(l=>({train:l.train,from:l.from,to:l.to,cost:l.fareVerified?l.cost:null,seatName:l.seatName||null,quotedAt:l.quotedAt||null})),rules:validateRiskRules(rules)}};
  return {version:1,plans:[],finals:[final,...workspace.finals],recovery:{plans:structuredClone(workspace.plans),finalId:final.id,savedAt:now}};
}
export function removeFinalDecision(workspace,id){
  if(!workspace.finals.some(entry=>entry.id===id))throw new Error('这条已定行程已不存在，请刷新后查看。');
  return {...workspace,finals:workspace.finals.filter(entry=>entry.id!==id)};
}
export function recoverComparison(workspace){
  if(!workspace.recovery)throw new Error('没有可恢复的对比库。');
  if(workspace.plans.length)throw new Error('当前对比库已有新方案，请先处理新方案再恢复。');
  return {...workspace,plans:structuredClone(workspace.recovery.plans),recovery:null};
}
