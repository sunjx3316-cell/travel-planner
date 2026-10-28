import {canTransfer,transferStations,crossTransfers} from './transfers.js';
/* At the SAME boarding event and round, a later origin departure with lower
   cost dominates another label. Safe with a maximum transfer wait because all
   future choices begin at that identical event. Estimates discover candidates
   only; quoted mode NEVER imputes a fare. */
export function estimateFare(t,i,j){const rate=t[7]==='G'?.46:t[7]==='D'?.34:.14;return Math.max(5,Math.round((t[5][j]-t[5][i])*rate*2)/2);}
export function dateShift(date,days){const d=new Date(`${date.slice(0,4)}-${date.slice(4,6)}-${date.slice(6,8)}T00:00:00Z`);d.setUTCDate(d.getUTCDate()+days);return d.toISOString().slice(0,10).replaceAll('-','');}
export function fareKey(train,from,to,date){return [date,from,to,train].join('|');}
export function chooseFare(fares,preference='standard'){
  const allowed=preference==='second'?['O']:preference==='hard'?['1']:['O','1'];
  for(const seat of allowed)if(Number.isFinite(fares?.[seat])&&fares[seat]>0)return {amount:fares[seat],seat,seatName:seat==='O'?'二等座':'硬座'};
  return null;
}
function lowerBound(list,target){let l=0,r=list.length;while(l<r){const m=(l+r)>>>1;if(list[m].dep<target)l=m+1;else r=m;}return l;}
// Rebuild selected legs from the timetable; never trust saved times or prices.
export function validateFixedLegs(network,selections,{origin,destination=[],date,earliest=0,maxTransfers=3,minTransfer=30,maxWait=240,maxDuration=2880,trainType='all'}){
  if(!Array.isArray(selections)||selections.length>maxTransfers+1)throw new Error('已选车次超过换乘上限。');
  if(!/^\d{8}$/.test(date)||date<network.meta.startDate||date>network.meta.endDate)throw new Error('日期超出时刻表覆盖范围，请更新日期。');
  if(!Number.isFinite(earliest)||earliest<0||earliest>=1440)throw new Error('请填写有效的最早出发时间。');
  const legs=[];
  for(const s of selections){
    if(!s||typeof s!=='object')throw new Error('已选车次记录无效，请重新选择。');
    const t=network.trips[s.trip],i=s.fromIndex,j=s.toIndex,day=s.serviceDay;
    if(!Number.isInteger(s.trip)||!t||!Number.isInteger(i)||!Number.isInteger(j)||i<0||j<=i||j>=t[2].length||!Number.isInteger(day)||Math.abs(day)>5||s.train&&s.train!==t[0])throw new Error('已选车次不在当前时刻表中，请重新选择。');
    if(!network.services[t[1]].includes(dateShift(date,day)))throw new Error('该日期没有这趟车，请重新选择。');
    if(trainType==='fast'&&t[7]==='K'||trainType==='normal'&&t[7]!=='K')throw new Error('已选车次不符合车型条件。');
    const l={trip:s.trip,train:t[0],kind:t[7],from:t[2][i],to:t[2][j],fromIndex:i,toIndex:j,serviceDay:day,departure:t[4][i]+day*1440,arrival:t[3][j]+day*1440,cost:null,fareVerified:false};
    const last=legs.at(-1);
    if(!last){if(!origin?.includes(l.from))throw new Error('首段请从上方设置的出发地选车。');if(l.departure<earliest||l.departure>=1440)throw new Error('首段车次不符合出发日期或最早出发时间。');}
    else{
      if(destination.includes(last.to))throw new Error('已经到达目的地。');
      if(!canTransfer(network,last.to,l.from))throw new Error('请从上一段到达的城市继续选车；不同城市须先添加乘车区间。');
      if(last.trip===l.trip&&last.serviceDay===l.serviceDay)throw new Error('这是同一趟车，请重选上一段的下车站。');
      if(l.departure-last.arrival<minTransfer||l.departure-last.arrival>maxWait)throw new Error(`换乘须预留 ${minTransfer}–${maxWait} 分钟。`);
    }
    if(l.arrival<=l.departure||l.arrival-(legs[0]?.departure??l.departure)>maxDuration)throw new Error('行程总历时不能超过 48 小时。');
    legs.push(l);
  }
  return legs;
}
export function plan(network,options){
  const {origin,destination,date,earliest=0,maxTransfers=1,minTransfer=30,maxWait=240,maxDuration=2880,valueOfTime=40,trainType='all',waypoints=[],fixedLegs=[],fareQuotes={},pricingMode='heuristic',seatPreference='standard',maxBoardLabels=500000}=options;
  if(!/^\d{8}$/.test(date)||date<network.meta.startDate||date>network.meta.endDate)throw new Error('日期超出时刻表覆盖范围，请更新日期。');
  if(!origin?.length||!destination?.length)throw new Error('请选择有效的出发地和目的地。');
  if(origin.some(s=>destination.includes(s)))throw new Error('出发地与目的地包含相同车站。');
  if(!Number.isInteger(maxTransfers)||maxTransfers<0||maxTransfers>3)throw new Error('支持直达至最多 3 次换乘。');
  if(waypoints.length>maxTransfers)throw new Error('指定换乘节点数不能超过换乘上限。');
  if(waypoints.some(w=>!w.stations?.length))throw new Error('换乘节点无有效车站。');
  const start=new Set(origin),dest=new Set(destination),via=waypoints.map(w=>new Set(w.stations));
  const hasQuotes=Object.keys(fareQuotes).length>0;
  const prefix=validateFixedLegs(network,fixedLegs,{origin,destination,date,earliest,maxTransfers,minTransfer,maxWait,maxDuration,trainType}).map(l=>{
    const q=fareQuotes[fareKey(l.train,network.stops?.[l.from]?.[0]??l.from,network.stops?.[l.to]?.[0]??l.to,dateShift(date,Math.floor(l.departure/1440)))],f=chooseFare(q?.fares,seatPreference);
    return {...l,cost:f?.amount??estimateFare(network.trips[l.trip],l.fromIndex,l.toIndex),fareVerified:!!f,seat:f?.seat,seatName:f?.seatName,quotedAt:q?.queriedAt,quoteSource:q?.source};
  });
  const serviceSets=network.services.map(s=>new Set(s));
  const maxOffset=Math.ceil(Math.max(...network.trips.map(t=>t[4].at(-1)))/1440),horizon=1440+maxDuration;
  const offsets=[];for(let day=-maxOffset;day<=Math.ceil(horizon/1440);day++)offsets.push({day,date:dateShift(date,day)});
  const departures=new Map(),occurrences=[];
  const eligible=t=>trainType==='all'||(trainType==='fast'?t[7]!=='K':t[7]==='K');
  for(let ti=0;ti<network.trips.length;ti++){
    const t=network.trips[ti];if(!eligible(t))continue;
    for(const {day,date:serviceDate} of offsets){
      if(!serviceSets[t[1]].has(serviceDate))continue;
      const base=day*1440;if(t[3].at(-1)+base<earliest||t[4][0]+base>horizon)continue;
      const occurrence=occurrences.length;occurrences.push({ti,day});
      for(let i=0;i<t[2].length-1;i++){
        const dep=t[4][i]+base;if(dep<earliest||dep>horizon)continue;
        const station=t[2][i];if(!departures.has(station))departures.set(station,[]);
        departures.get(station).push({occurrence,ti,day,i,dep,key:`${occurrence}:${i}`});
      }
    }
  }
  for(const list of departures.values())list.sort((a,b)=>a.dep-b.dep);
  const transferDepartures=new Map();
  function onward(station){
    const stops=transferStations(network,station),key=stops[0];
    if(!transferDepartures.has(key))transferDepartures.set(key,stops.flatMap(s=>departures.get(s)||[]).sort((a,b)=>a.dep-b.dep));
    return transferDepartures.get(key);
  }
  let bestFast=null,bestCheap=null,bestBalanced=null,count=0,pruned=0,truncated=false,totalLabels=0;
  const byTransfers=[],trace=[],shortlist=new Map(),frontier=[];
  const compareFast=(a,b)=>a.duration-b.duration||a.cost-b.cost||a.transfers-b.transfers||a.departure-b.departure;
  const compareCheap=(a,b)=>a.cost-b.cost||compareFast(a,b);
  const compareBalanced=(a,b)=>a.score-b.score||compareFast(a,b);
  const ranked={fastest:[],cheapest:[],balanced:[]};
  function accept(legs){
    const departure=legs[0].departure,arrival=legs.at(-1).arrival,duration=arrival-departure;
    if(duration<=0||duration>maxDuration)return;
    const cost=legs.reduce((s,l)=>s+l.cost,0),transfers=legs.length-1;
    const item={id:legs.map(l=>`${l.trip}:${l.fromIndex}:${l.toIndex}:${l.serviceDay}`).join('|'),legs,departure,arrival,duration,cost,transfers,
      score:cost+duration/60*valueOfTime+transfers*30,verified:pricingMode==='quoted',crossStationTransfers:crossTransfers(legs).length};
    count++;
    // Bounded, distinct alternatives among explored labels, not an exhaustive K-shortest guarantee.
    for(const [key,cmp] of [['fastest',compareFast],['cheapest',compareCheap],['balanced',compareBalanced]]){
      const list=ranked[key];
      if(!list.some(r=>r.id===item.id)&&(list.length<8||cmp(item,list.at(-1))<0)){
        list.push(item);list.sort(cmp);if(list.length>8)list.pop();
      }
    }
    if(!bestFast||compareFast(item,bestFast)<0)bestFast=item;
    if(!bestCheap||compareCheap(item,bestCheap)<0)bestCheap=item;
    if(!bestBalanced||compareBalanced(item,bestBalanced)<0)bestBalanced=item;
    const b=byTransfers[transfers]||={transfers,count:0,fastest:null,cheapest:null,balanced:null};b.count++;
    for(const [key,cmp] of [['fastest',compareFast],['cheapest',compareCheap],['balanced',compareBalanced]])if(!b[key]||cmp(item,b[key])<0)b[key]=item;
    if(!frontier.some(p=>p.duration<=duration&&p.cost<=cost&&p.transfers<=transfers)){
      for(let i=frontier.length-1;i>=0;i--)if(duration<=frontier[i].duration&&cost<=frontier[i].cost&&transfers<=frontier[i].transfers)frontier.splice(i,1);
      frontier.push(item);
    }
  }
  let boards=new Map();
  if(prefix.length){
    let progress=0;for(const l of prefix)if(via[progress]?.has(l.to))progress++;
    const last=prefix.at(-1),priced=pricingMode!=='quoted'||prefix.every(l=>l.fareVerified);
    if(priced&&dest.has(last.to)){if(progress===via.length)accept(prefix);}
    else if(priced){for(const e of onward(last.to))if(e.dep>=last.arrival+minTransfer&&e.dep<=last.arrival+maxWait&&!(e.ti===last.trip&&e.day===last.serviceDay))boards.set(e.key+':'+progress,{event:e,progress,labels:[{first:prefix[0].departure,cost:prefix.reduce((s,l)=>s+l.cost,0),legs:prefix}]});}
  }else for(const stop of origin)for(const e of departures.get(stop)||[])if(e.dep<1440)boards.set(e.key+':0',{event:e,progress:0,labels:[{first:e.dep,cost:0,legs:[]}]});
  for(let round=prefix.length;round<=maxTransfers&&boards.size;round++){
    const nextBoards=new Map(),reached=new Set(),links=new Map();let evaluated=0,roundLabels=0,roundPruned=0,foundBefore=count,queued=0,halt=false;
    for(const group of boards.values()){
      const {event:e,progress}=group,t=network.trips[e.ti];
      for(const label of group.labels){
        roundLabels++;totalLabels++;if(totalLabels>maxBoardLabels){truncated=true;halt=true;break;}
        for(let j=e.i+1;j<t[2].length;j++){
          const stop=t[2][j],arr=t[3][j]+e.day*1440;if(arr-label.first>maxDuration)break;
          const quote=hasQuotes?fareQuotes[fareKey(t[0],network.stops?.[t[2][e.i]]?.[0]??t[2][e.i],network.stops?.[stop]?.[0]??stop,dateShift(date,Math.floor(e.dep/1440)))]:undefined;
          const selectedFare=chooseFare(quote?.fares,seatPreference);if(pricingMode==='quoted'&&!selectedFare)continue;
          const cost=selectedFare?.amount??estimateFare(t,e.i,j);
          const leg={trip:e.ti,train:t[0],kind:t[7],from:t[2][e.i],to:stop,fromIndex:e.i,toIndex:j,departure:e.dep,arrival:arr,
            serviceDay:e.day,cost,distance:Math.round(t[5][j]-t[5][e.i]),seat:selectedFare?.seat,seatName:selectedFare?.seatName,
            fareVerified:!!selectedFare,quotedAt:quote?.queriedAt,quoteSource:quote?.source};
          evaluated++;reached.add(stop);
          const linkKey=`${leg.from}:${stop}`,link=links.get(linkKey)||{from:leg.from,to:stop,count:0};link.count++;links.set(linkKey,link);
          const p=progress<via.length&&via[progress].has(stop)?progress+1:progress,legs=[...label.legs,leg];
          if(dest.has(stop)){if(p===via.length)accept(legs);continue;}
          if(round===maxTransfers||start.has(stop))continue;
          const ds=onward(stop);if(!ds.length)continue;
          for(let k=lowerBound(ds,arr+minTransfer);k<ds.length&&ds[k].dep<=arr+maxWait;k++){
            const outgoing=ds[k];if(outgoing.occurrence===e.occurrence)continue;
            const key=outgoing.key+':'+p;let next=nextBoards.get(key);
            if(!next){if(queued>=Math.floor(maxBoardLabels/2)){truncated=true;continue;}next={event:outgoing,progress:p,labels:[]};nextBoards.set(key,next);}
            const newCost=label.cost+cost;
            if(next.labels.some(l=>l.first>=label.first&&l.cost<=newCost)){roundPruned++;continue;}
            if(queued>=Math.floor(maxBoardLabels/2)){truncated=true;continue;}
            const before=next.labels.length;next.labels=next.labels.filter(l=>!(label.first>=l.first&&newCost<=l.cost));next.labels.push({first:label.first,cost:newCost,legs});queued+=next.labels.length-before;
          }
        }
      }
      if(halt)break;
    }
    pruned+=roundPruned;
    trace.push({round,transfers:round,boardingEvents:boards.size,labels:roundLabels,evaluated,reached:reached.size,pruned:roundPruned,found:count-foundBefore,
      links:[...links.values()].sort((a,b)=>b.count-a.count).slice(0,100),stations:[...reached].slice(0,160)});
    boards=nextBoards;if(halt)break;
  }
  for(const r of [bestFast,bestCheap,bestBalanced,...Object.values(ranked).flat(),...byTransfers.flatMap(b=>b?[b.fastest,b.cheapest,b.balanced]:[]),...frontier])if(r)shortlist.set(r.id,r);
  return {fastest:bestFast,cheapest:bestCheap,balanced:bestBalanced,ranked,count,frontier:frontier.sort(compareFast),candidates:[...shortlist.values()],byTransfers:byTransfers.filter(Boolean),trace,pruned,totalLabels,truncated,
    options:{...options,fareQuotes:undefined,earliest,maxTransfers,minTransfer,maxWait,maxDuration,valueOfTime,trainType,waypoints,seatPreference,pricingMode}};
}
