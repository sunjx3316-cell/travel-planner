import {dateShift} from './router.js';
import {transferStations} from './transfers.js';
const indexes=new WeakMap();
export function prepareServiceIndex(network){
  if(indexes.has(network))return indexes.get(network);
  const byStop=new Map();
  network.trips.forEach((t,trip)=>{for(let i=0;i<t[2].length-1;i++){
    const stop=t[2][i];if(!byStop.has(stop))byStop.set(stop,[]);byStop.get(stop).push({trip,i});
  }});
  const index={byStop,calendars:network.services.map(days=>new Set(days)),queries:new Map()};indexes.set(network,index);return index;
}
// A city is a station group, but each returned departure has exact boarding/alighting stations.
export function directServices(network,{origin,destination,date,earliest=0,trainType='all'}){
  if(!origin?.length||!destination?.length)return [];
  if(!/^\d{8}$/.test(date)||date<network.meta.startDate||date>network.meta.endDate)return [];
  const index=prepareServiceIndex(network),key=[origin.join(','),destination.join(','),date,earliest,trainType].join('|');
  if(index.queries.has(key))return index.queries.get(key);
  const to=new Set(destination),rows=[],dates=new Map();
  for(const stop of new Set(origin))for(const {trip,i} of index.byStop.get(stop)||[]){
    const t=network.trips[trip];
    if(trainType==='fast'&&t[7]==='K'||trainType==='normal'&&t[7]!=='K')continue;
      const serviceDay=-Math.floor(t[4][i]/1440),departure=t[4][i]+serviceDay*1440;
      if(!dates.has(serviceDay))dates.set(serviceDay,dateShift(date,serviceDay));
      if(departure<earliest||!index.calendars[t[1]].has(dates.get(serviceDay)))continue;
      for(let j=i+1;j<t[2].length;j++)if(to.has(t[2][j])){
        const arrival=t[3][j]+serviceDay*1440;
        rows.push({trip,train:t[0],kind:t[7],from:t[2][i],to:t[2][j],fromIndex:i,toIndex:j,serviceDay,departure,arrival,cost:null,fareVerified:false});
      }
  }
  rows.sort((a,b)=>a.departure-b.departure||a.arrival-b.arrival||a.train.localeCompare(b.train));
  if(index.queries.size>=64)index.queries.delete(index.queries.keys().next().value);
  index.queries.set(key,rows);return rows;
}

// Return onward departures in the original journey's time coordinate, including midnight.
export function connectionServices(network,{prefix,destination,date,trainType='all',minTransfer=30,maxWait=240,maxDuration=2880}){
  const last=prefix.at(-1);if(!last)return [];
  const low=last.arrival+minTransfer,high=last.arrival+maxWait,rows=[];
  for(let day=Math.floor(low/1440);day<=Math.floor(high/1440);day++){
    const found=directServices(network,{origin:transferStations(network,last.to),destination,date:dateShift(date,day),earliest:Math.max(0,low-day*1440),trainType});
    for(const l of found){const next={...l,departure:l.departure+day*1440,arrival:l.arrival+day*1440,serviceDay:l.serviceDay+day};
      if(next.departure<=high&&next.arrival-prefix[0].departure<=maxDuration&&!(next.trip===last.trip&&next.serviceDay===last.serviceDay))rows.push(next);
    }
  }
  return rows.sort((a,b)=>a.departure-b.departure||a.arrival-b.arrival);
}
