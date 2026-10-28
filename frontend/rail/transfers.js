import {cityNames,extraCityStations} from './places.js';
const indexes=new WeakMap();
// Shared city membership for routing and the city inspector. Unknown stations stay independent.
export function cityIndex(network){
  if(indexes.has(network))return indexes.get(network);
  const names=[...new Set(cityNames)],groups=new Map(names.map(name=>[name,{name,stations:[]}])),byStation=new Map();
  const longest=[...names].sort((a,b)=>b.length-a.length);
  for(const i of network.activeStops||network.stops?.map((_,i)=>i)||[]){
    const station=network.stops[i][1],name=names.find(n=>extraCityStations[n]?.includes(station))||longest.find(n=>station.startsWith(n));
    if(name){const group=groups.get(name);group.stations.push(i);byStation.set(i,group);}
  }
  const index={cities:[...groups.values()].filter(c=>c.stations.length),byStation};indexes.set(network,index);return index;
}
export function transferStations(network,station){return cityIndex(network).byStation.get(station)?.stations||[station];}
export function canTransfer(network,from,to){return from===to||transferStations(network,from).includes(to);}
export function crossTransfers(legs){return legs.slice(1).flatMap((l,i)=>legs[i].to===l.from?[]:[{from:legs[i].to,to:l.from,arrival:legs[i].arrival,departure:l.departure,minutes:l.departure-legs[i].arrival}]);}
export function journeyTimeline(legs){
  const nodes=[{station:legs[0].from,minute:legs[0].departure}],links=[];
  legs.forEach((l,i)=>{
    if(i){const previous=legs[i-1];if(previous.to!==l.from){
      links.push({kind:'cross',departure:previous.arrival,arrival:l.departure});nodes.push({station:l.from,minute:l.departure});
    }else nodes.at(-1).wait=l.departure-previous.arrival;}
    links.push({kind:'rail',train:l.train,departure:l.departure,arrival:l.arrival});nodes.push({station:l.to,minute:l.arrival});
  });return {nodes,links};
}
