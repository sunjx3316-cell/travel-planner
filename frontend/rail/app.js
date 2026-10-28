import {Metro} from './metro.js';
import {directServices,connectionServices,prepareServiceIndex} from './services.js';
import {RailMap} from './map.js';
import {fareKey,chooseFare,dateShift,validateFixedLegs} from './router.js';
import {cityIndex,canTransfer,crossTransfers} from './transfers.js';
import {initComparison} from './comparison.js';
import {embedded, bridgeURL, configureTravelBridge, clearTravelSelection, publishTravelSelection, toTravelJourney} from './travel-bridge.js';
const $=id=>document.getElementById(id);
const esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const duration=m=>m<60?`${Math.round(m)}分钟`:`${Math.floor(m/60)}小时${m%60?Math.round(m%60)+'分':''}`;
const durationHTML=m=>m<60?`${Math.round(m)}<em>分钟</em>`:`${Math.floor(m/60)}<em>小时</em>${m%60?Math.round(m%60)+'<em>分</em>':''}`;
const clock=m=>`${String(Math.floor(m/60)%24).padStart(2,'0')}:${String(Math.floor(m%60)).padStart(2,'0')}`;
const clockHTML=m=>clock(m)+(m>=1440?`<small>+${Math.floor(m/1440)}天</small>`:'');
const price=p=>Number.isInteger(p)?String(p):p.toFixed(1);
const fmt=s=>`${s.slice(0,4)}-${s.slice(4,6)}-${s.slice(6,8)}`;
const kinds={fastest:{name:'最快行程',css:'fast',color:'#087e79'},cheapest:{name:'最省钱',css:'cheap',color:'#527aab'},balanced:{name:'综合推荐',css:'balanced',color:'#b67b36'},custom:{name:'自选方案',css:'balanced',color:'#b67b36'}};
let network,cities=[],result,timetable,selected,selectedKind='fastest',ready=false,busy=false,requestId=0,phase='idle';
let journeyExpanded=false;
let comparison,comparisonBackup;
let waypoints=[],pickedLegs=[],manual=false,traceIndex=0,traceTimer,quoteAbort,quotePairs=[],quoteCursor=0,quoteErrors=[];
const fareQuotes={};let currentOptions,travelRiskRules;
configureTravelBridge(() => toTravelJourney(network, selected, currentOptions, fareQuotes, travelRiskRules));
const worker=new Worker('./worker.js',{type:'module'});
const map=new RailMap($('rail-map'),showStation);
const metro=new Metro(minute=>map.setPlayback(minute),i=>showStation(i));
let quotedResult=null,routeLists={},groupOpen={fastest:true,cheapest:false,balanced:false},selectedCity=null,serviceRows=[],serviceLimit=20,previewService=false;
function toast(message){$('toast').textContent=message;$('toast').hidden=false;clearTimeout(toast.timer);toast.timer=setTimeout(()=>$('toast').hidden=true,3000);}
function crossNotice(legs){
  const changes=crossTransfers(legs);if(!changes.length)return '';
  return `<div class="cross-transfer-note"><strong>⚠ 跨站换乘</strong>${changes.map(t=>`<span>${esc(network.stops[t.from][1])} → ${esc(network.stops[t.to][1])} · 间隔 ${duration(t.minutes)}</span>`).join('')}<small>需自行出站、前往另一车站并进站；市内交通时间未核实，费用未计入票价。</small></div>`;
}
function resolve(value){
  value=value.trim();const city=cities.find(c=>c.name===value||value===c.name+'（全部车站）');if(city)return {name:city.name,stations:city.stations};
  const i=network.activeStops.find(i=>network.stops[i][1]===value||network.stops[i][1]+' · 车站'===value||network.stops[i][0]===value.toUpperCase());
  return i===undefined?null:{name:network.stops[i][1],stations:[i]};
}
function setBusy(value){busy=value;$('search').disabled=value||!ready;$('search').querySelector('span').textContent=!ready?'正在装载时刻表':value?'正在展开铁路连接…':manual?'匹配这条路线':'生成推荐方案';}
function stopReplay(){clearInterval(traceTimer);traceTimer=null;$('trace-play').textContent='播放过程';}
function cancelQuote(){quoteAbort?.abort();quoteAbort=null;}
function markDirty({keepPicked=false}={}){
  clearTravelSelection();
  if(!ready)return;cancelQuote();stopReplay();requestId++;phase='idle';setBusy(false);result=null;timetable=null;selected=null;quotedResult=null;previewService=false;metro.clear();
  if(!keepPicked&&pickedLegs.length){pickedLegs=[];toast('条件已更改，请按新条件重新选择车次。');}
  $('transfer-notice').hidden=true;document.querySelector('.visual-workspace').classList.remove('has-cross-transfer');
  $('results').innerHTML='<div class="empty-state"><strong>下一程，由你决定</strong><p>条件已更新，点击查询重新比较路线。</p></div>';
  $('result-count').textContent='条件已更改';$('journey-panel').hidden=true;$('process-panel').hidden=true;$('alternatives').hidden=true;$('more-prices').hidden=true;renderWaypoints();
  $('pricing-status').textContent='按日期、区间和席别查询实际票价。';if(!manual)map.setRoute(null);if(selectedCity)inspectCity(selectedCity,null,false);syncURL();
}
function formOptions(){
  const [h,m]=$('time').value.split(':').map(Number);
  return {origin:resolve($('origin').value)?.stations,destination:resolve($('destination').value)?.stations,date:$('date').value.replaceAll('-',''),earliest:h*60+m,maxTransfers:Number($('transfers').value),minTransfer:30,maxWait:240,maxDuration:2880,valueOfTime:Number($('value-time').value),trainType:$('train-type').value,seatPreference:$('seat-preference').value,waypoints:manual?waypoints:[],fixedLegs:manual?pickedLegs:[],pricingMode:'heuristic'};
}
function syncURL(){
  updateQuerySummary();
  const params=new URLSearchParams({from:$('origin').value,to:$('destination').value,date:$('date').value,time:$('time').value,transfers:$('transfers').value,type:$('train-type').value,value:$('value-time').value,seat:$('seat-preference').value,mode:manual?'manual':'auto'});
  if(waypoints.length)params.set('via',JSON.stringify(waypoints.map(w=>({name:w.name,codes:w.stations.map(i=>network.stops[i][0])}))));
  if(pickedLegs.length){params.set('legs',JSON.stringify(pickedLegs.map(({trip,train,fromIndex,toIndex,serviceDay})=>({trip,train,fromIndex,toIndex,serviceDay}))));params.set('snapshot',network.meta.version);}
  bridgeURL(params);
  history.replaceState(null,'','?'+params);
}
function bindSuggestions(field){
  const input=$(field),list=$(field+'-options');
  const hide=()=>{list.hidden=true;input.setAttribute('aria-expanded','false');};
  const suggest=()=>{
    if(!ready)return;const q=input.value.trim().replace(' · 车站','');
    const cs=cities.filter(c=>!q||c.name.includes(q)).slice(0,4);
    const ss=network.activeStops.filter(i=>!q||network.stops[i][1].includes(q)||network.stops[i][0].toLowerCase().includes(q.toLowerCase())).sort((a,b)=>(network.stops[a][1]===q?-1:network.stops[b][1]===q?1:0)).slice(0,7);
    list.innerHTML=cs.map(c=>`<button type="button" role="option" class="suggestion" data-value="${esc(c.name)}"><span>${esc(c.name)}</span><small>全部 ${c.stations.length} 站</small></button>`).join('')+ss.map(i=>`<button type="button" role="option" class="suggestion" data-value="${esc(network.stops[i][1]+' · 车站')}"><span>${esc(network.stops[i][1])}</span><small>车站 · ${network.stops[i][0]}</small></button>`).join('');
    if(!list.childElementCount)list.innerHTML='<div class="no-suggestion">未找到，试试中文站名或三字母站码。</div>';
    list.hidden=false;input.setAttribute('aria-expanded','true');
    list.querySelectorAll('button').forEach(b=>b.onclick=()=>{input.value=b.dataset.value;hide();if(field!=='via')markDirty();input.focus();hide();});
  };
  input.addEventListener('input',()=>{if(field!=='via')markDirty();suggest();});input.addEventListener('focus',suggest);
  input.addEventListener('keydown',e=>{if(e.key==='Escape')hide();if(e.key==='ArrowDown'){e.preventDefault();suggest();list.querySelector('button')?.focus();}if(field==='via'&&e.key==='Enter'){e.preventDefault();hide();addWaypoint(resolve(input.value));}});
  list.addEventListener('keydown',e=>{if(e.key==='Escape'){input.focus();hide();}if(e.key==='ArrowDown'){e.preventDefault();e.target.nextElementSibling?.focus();}if(e.key==='ArrowUp'){e.preventDefault();e.target.previousElementSibling?.focus();}});
  document.addEventListener('pointerdown',e=>{if(!input.parentElement.contains(e.target))hide();});
}
['origin','destination','via'].forEach(bindSuggestions);
for(const id of ['date','time','transfers','train-type'])$(id).addEventListener('change',markDirty);
$('seat-preference').addEventListener('change',()=>markDirty({keepPicked:true}));
$('swap').onclick=()=>{[$('origin').value,$('destination').value]=[$('destination').value,$('origin').value];waypoints.reverse();renderWaypoints();markDirty();};
$('search-form').onsubmit=e=>{e.preventDefault();search();};
document.querySelectorAll('[data-from]').forEach(b=>b.onclick=()=>{$('origin').value=b.dataset.from;$('destination').value=b.dataset.to;search();});
let preferenceTimer;$('value-time').oninput=()=>{$('value-label').textContent=$('value-time').value;clearTimeout(preferenceTimer);preferenceTimer=setTimeout(()=>{if(ready)search();},450);};
function search(){
  clearTravelSelection();
  if(!ready)return;const o=resolve($('origin').value),d=resolve($('destination').value);
  for(const [key,q] of Object.entries(fareQuotes))if(Date.now()-Date.parse(q.queriedAt)>600000)delete fareQuotes[key];
  if(!o||!d){toast('请从列表选择有效的城市或车站。');return;}
  if(o.stations.some(s=>d.stations.includes(s))){toast('请选择不同的起终点。');return;}
  const date=$('date').value.replaceAll('-',''),[h,m]=$('time').value.split(':').map(Number);
  if(!date||!Number.isFinite(h)||!Number.isFinite(m)){toast('请填写出发日期与时间。');return;}
  if(manual&&waypoints.length>Number($('transfers').value))$('transfers').value=String(waypoints.length);
  try{if(manual)validateFixedLegs(network,pickedLegs,formOptions());}catch(e){toast(e.message);return;}
  cancelQuote();stopReplay();requestId++;phase='timetable';selected=null;result=null;timetable=null;quotedResult=null;previewService=false;metro.clear();quoteCursor=0;quoteErrors=[];setBusy(true);
  $('journey-panel').hidden=true;$('alternatives').hidden=true;$('more-prices').hidden=true;map.setRoute(null);map.setExploration(null,manual?waypoints:[]);
  $('result-count').textContent='正在逐层搜索';$('results').innerHTML='<div class="empty-state"><div class="loading-track"><i></i></div><strong>让每一种连接，都参与比较。</strong><p>从直达到换乘上限，逐层展开可行的车次。</p></div>';
  $('pricing-status').textContent='先搜索时刻，再核对候选区间的真实票价。';
  currentOptions=formOptions();syncURL();document.querySelectorAll('.suggestions').forEach(e=>e.hidden=true);document.querySelectorAll('[role=combobox]').forEach(e=>e.setAttribute('aria-expanded','false'));
  $('scope-note').textContent=`当日出发 · 0–${currentOptions.maxTransfers} 次换乘（含同城跨站）· 总历时 ≤ 48 小时；换乘间隔 30–240 分钟，跨站交通需自行确认。`;
  $('transfer-notice').hidden=true;document.querySelector('.visual-workspace').classList.remove('has-cross-transfer');
  worker.postMessage({type:'plan',id:requestId,options:currentOptions});
}
function annotate(route){
  if(!route)return null;
  const legs=route.legs.map(l=>{
    const q=fareQuotes[fareKey(l.train,network.stops[l.from][0],network.stops[l.to][0],dateShift(currentOptions.date,Math.floor(l.departure/1440)))],f=chooseFare(q?.fares,currentOptions.seatPreference);
    return {...l,cost:f?.amount??null,seatName:f?.seatName,seat:f?.seat,fareVerified:!!f,quotedAt:q?.queriedAt,quoteSource:q?.source};
  });
  const verified=legs.every(l=>l.fareVerified),cost=verified?legs.reduce((s,l)=>s+l.cost,0):null;
  return {...route,legs,verified,cost,crossStationTransfers:crossTransfers(legs).length,score:verified?cost+route.duration/60*currentOptions.valueOfTime+route.transfers*30:null};
}
function collectQuotePairs(r){
  const pairs=new Map();
  const add=l=>{const pair={from:network.stops[l.from][0],to:network.stops[l.to][0],fromName:network.stops[l.from][1],toName:network.stops[l.to][1],date:fmt(dateShift(currentOptions.date,Math.floor(l.departure/1440))),required:[l.train]};const key=[pair.from,pair.to,pair.date].join('|');const previous=pairs.get(key);if(previous){if(!previous.required.includes(l.train)&&previous.required.length<4)previous.required.push(l.train);}else pairs.set(key,pair);};
  // Verify direct and every permitted transfer count before broadening candidates.
  r.fastest?.legs.forEach(add);
  for(const b of r.byTransfers)for(const route of [b.cheapest,b.fastest,b.balanced])route?.legs.forEach(add);
  for(const route of [r.fastest,r.cheapest,r.balanced,...r.candidates])route?.legs.forEach(add);
  return [...pairs.values()];
}
async function fetchMoreQuotes(){
  if(!timetable||phase==='quoting')return;
  const id=requestId;phase='quoting';quoteAbort=new AbortController();$('more-prices').hidden=true;
  const end=Math.min(quoteCursor+16,quotePairs.length);let failedBatches=0;
  for(;quoteCursor<end;){
    if(id!==requestId)return;
    const batch=quotePairs.slice(quoteCursor,Math.min(quoteCursor+2,end));
    $('pricing-status').textContent=`正在核价 ${quoteCursor+1}–${quoteCursor+batch.length} / ${quotePairs.length} 个候选区间…`;
    try{
      const response=await fetch('/api/rail/fares',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({pairs:batch}),signal:AbortSignal.any([quoteAbort.signal,AbortSignal.timeout(35000)])});
      if(!response.ok)throw new Error('票价服务暂不可用。');const payload=await response.json();
      for(const q of payload.results||[]){if(q.error)quoteErrors.push(q.error);for(const row of q.rows||[])fareQuotes[fareKey(row.train,row.from,row.to,row.date.replaceAll('-',''))]=row;}
      if(!(payload.results||[]).some(q=>q.rows?.length))failedBatches++;
    }catch(e){if(e.name==='AbortError'||id!==requestId)return;quoteErrors.push('票价来源暂不可用，请稍后重试。');failedBatches++;}
    if(id!==requestId)return;quoteCursor+=batch.length;
    result.fastest=annotate(timetable.fastest);renderResults(false);
    if(failedBatches>=2)break;
  }
  if(id!==requestId)return;phase='rerank';$('pricing-status').textContent='使用已核对的实际票价重新比较直达与各层换乘…';
  worker.postMessage({type:'plan',id,options:{...currentOptions,pricingMode:'quoted',fareQuotes}});
}
function reason(kind,r){
  if(!r?.verified)return '未获得完整席别票价，<strong>不使用估算金额</strong>。';
  if(kind==='fastest')return '总历时最短，包含中转换乘等待。';
  if(kind==='cheapest')return '<strong>已核价区间组成的可行路线中费用最低</strong>。';
  if(kind==='custom')return '你选择的路线，按实际区间票价合计。';
  return `已核价路线综合比较 · 时间价值 ${currentOptions.valueOfTime} 元 / 小时。`;
}
function renderResults(fit=true){
  if(!result||!timetable)return;
  renderPickedList();
  $('result-count').textContent=`已评估 ${timetable.count.toLocaleString()} 条到达记录 · 每组最多 8 条候选`;
  if(!timetable.count){$('results').innerHTML='<div class="empty-state"><strong>没有找到符合条件的连接</strong><p>试试更早出发、增加换乘次数，或调整城市节点。已加入的车次会保留，可撤回末段再选。</p></div>';if(manual&&pickedLegs.length)renderPickedJourney();return;}
  const all=[...new Map([...timetable.candidates,...(quotedResult?.candidates||[])].map(r=>[r.id,annotate(r)])).values()];
  const verified=all.filter(r=>r.verified),fast=(a,b)=>a.duration-b.duration||a.departure-b.departure;
  routeLists={fastest:all.sort(fast).slice(0,8),cheapest:[...verified].sort((a,b)=>a.cost-b.cost||fast(a,b)).slice(0,8),balanced:[...verified].sort((a,b)=>a.score-b.score||fast(a,b)).slice(0,8)};
  const labels={fastest:['↗','总历时优先'],cheapest:['¥','铁路票价优先 · 市内交通另计'],balanced:['◎','铁路票价、时间与换乘共同比较']};
  $('results').innerHTML=Object.entries(routeLists).map(([kind,rows])=>`<details class="route-group ${kinds[kind].css}" data-group="${kind}" ${groupOpen[kind]?'open':''}><summary><span class="group-icon">${labels[kind][0]}</span><span class="group-title">${kinds[kind].name}<small>${labels[kind][1]}</small></span><span class="group-count">${rows.length} 条</span></summary><div class="route-options">${rows.map((r,i)=>`<button class="route-option ${selected?.id===r.id?'selected':''}" data-kind="${kind}" data-index="${i}" aria-pressed="${selected?.id===r.id}"><div class="option-top"><span>方案 ${String(i+1).padStart(2,'0')}</span><b>${r.transfers?'换乘 '+r.transfers+' 次':'直达'}</b></div><div class="option-middle"><strong>${durationHTML(r.duration)}</strong><span>${r.verified?'¥'+price(r.cost):'<small>待核价</small>'}</span></div><div class="option-bottom"><span>${clock(r.departure)} → ${clockHTML(r.arrival)}</span><span>${r.legs.length} 段车次</span></div><div class="option-trains">${r.legs.map(l=>esc(l.train)).join(' → ')} · ${r.legs.slice(0,-1).map(l=>esc(network.stops[l.to][1])).join(' / ')||'无需换乘'}</div>${crossNotice(r.legs)}</button>`).join('')||'<p class="group-empty">完整票价核对后，这里会列出多条候选。可点击下方继续核价。</p>'}</div></details>`).join('');
  document.querySelectorAll('[data-group]').forEach(d=>d.ontoggle=()=>groupOpen[d.dataset.group]=d.open);
  document.querySelectorAll('.route-option').forEach(b=>b.onclick=()=>{previewService=false;selectRoute(b.dataset.kind,{route:routeLists[b.dataset.kind][Number(b.dataset.index)]});});
  if(previewService)return;
  const preserved=all.find(r=>r.id===selected?.id);
  selectRoute(preserved?selectedKind:'fastest',{fit,route:preserved||routeLists.fastest[0]});
}
function selectRoute(kind,{fit=true,route,riskRules}={}){
  travelRiskRules=riskRules;
  selectedKind=kind;selected=route||result?.[kind];if(!selected)return;
  document.querySelectorAll('.route-option').forEach(b=>{const yes=routeLists[b.dataset.kind]?.[Number(b.dataset.index)]?.id===selected.id;b.classList.toggle('selected',yes);b.setAttribute('aria-pressed',String(yes));});
  map.draftNodes=[];map.setRoute(selected,{fit,color:kinds[selectedKind].color});
  $('view-title').textContent=previewService?'车次预览':manual?'你构建的路线':kinds[selectedKind].name+' · 地图预览';
  $('map-subtitle').textContent=`${network.stops[selected.legs[0].from][1]} → ${network.stops[selected.legs.at(-1).to][1]} · ${fmt(currentOptions.date)}`;
  $('metro-title').textContent=selected.legs.map(l=>l.train).join(' → ');
  const transferHTML=crossNotice(selected.legs);$('transfer-notice').innerHTML=transferHTML;$('transfer-notice').hidden=!transferHTML;document.querySelector('.visual-workspace').classList.toggle('has-cross-transfer',!!transferHTML);
  const panel=$('journey-panel');panel.hidden=false;
  panel.innerHTML=`<span><strong>${duration(selected.duration)}</strong> · ${selected.transfers?'换乘 '+selected.transfers+' 次':'直达'} · ${selected.verified?'铁路票价 ¥'+price(selected.cost):'票价待核对'}</span><div class="journey-actions"><button id="route-detail">全部经停 / 详情 ↗</button></div>`;
  $('route-detail').onclick=showDetail;metro.setRoute(selected,network);
  publishTravelSelection();
}
function showDialog(title,html){$('about-title').textContent=title;$('about-content').innerHTML=html;$('about-dialog').showModal();}
function showAbout(){
  if(!network)return;
  const m=network.meta;
  showDialog('真实票价，也说明比较的边界。',`<div class="data-tags"><span>时刻表 ${fmt(m.version)}</span><span>12306 公开查询票价</span><span>不判断余票与取消</span></div><h3>票价已不再按距离估算</h3><p>报价按上车日期、车次、具体上下车站与席别取得；默认比较二等座或硬座，成人票。缺失报价显示“待核价”，不会当作 0 元，也不会用估算数填补。无座、卧铺不混入默认比较。每张区间票单独取价后合计，不按沿途小段票价累加。</p><p>“最省钱”和“综合推荐”使用已核价区间组成的路线；为控制查询量，先核对一批候选区间，可继续核对更多。未覆盖区间和服务中断可能影响结果，不能宣称为全网实际票价的全局最优。价格时间在行程详情中可查看，报价缓存最长 10 分钟。</p><h3>换乘上限包含更少换乘的路线</h3><p>选择最多 2 次时，同一次查询比较直达、1 次与 2 次；最多支持 3 次换乘，包含同城不同站。当日出发，换乘间隔 30–240 分钟，总历时不超过 48 小时。间隔包含出站、市内交通及重新进站时间；这是搜索范围，并非已核实的跨站用时。跨站路线显著标注两站，市内交通方式与时间需自行确认，额外费用未计入铁路票价和费用排序。手动指定节点要求按顺序在节点内下车，可以从同城其他站接车。</p><h3>寻找过程来自实际计算记录</h3><p>按乘车段数逐轮搜索，以同一登车事件上的出发时间和累计费用标签做支配剪枝，保留更优状态。地图回放各轮实际评估的部分连接，显示真实计数，并非虚构动画。每组最多展示 8 条不同候选；它们来自已探索的状态，不代表穷举全网后的前八名。城市按已收录站名和车站别名分组。每次查询最多处理 50 万登车标签，达到限制时会显式提示；此时最快结果也仅是已探索候选中最优。</p><p>综合成本 = 实际票价 + 总历时（小时）× 时间价值 + 换乘次数 × 30 元。30 元是换乘偏好代价，不是收费。</p><h3>时刻表来源与范围</h3><p>使用 <a href="${m.source}" target="_blank" rel="noopener">${esc(m.publisher)} 的中国铁路 GTFS</a>，CC BY 4.0，${m.stationCount.toLocaleString()} 个车站、${m.tripCount.toLocaleString()} 个车次；坐标源自 OpenStreetMap，边界源自 DataV。时刻仍是静态快照，不代表已核实实际运行。部分缺失轨迹使用虚线示意。算法不读取乘客账户，不购票，不依据余票、临时取消和晚点筛选。</p>`);
}
function showDetail(){
  if(!selected)return;
  showDialog('每一段票价，单独核对。',`<div class="data-tags"><span>${fmt(currentOptions.date)}</span><span>${duration(selected.duration)}</span><span>${selected.verified?'铁路票价 ¥'+price(selected.cost):'全程待核价'}</span></div>${selected.legs.map((l,i)=>`${i?(selected.legs[i-1].to!==l.from?crossNotice([selected.legs[i-1],l]):`<p>在 ${esc(network.stops[l.from][1])} 同站等待 ${duration(l.departure-selected.legs[i-1].arrival)}</p>`):''}<section class="detail-leg"><strong>${i+1}. ${esc(l.train)} · ${esc(network.stops[l.from][1])} → ${esc(network.stops[l.to][1])}</strong><p>${clockHTML(l.departure)} → ${clockHTML(l.arrival)} · ${l.fareVerified?esc(l.seatName)+' ¥'+price(l.cost):'票价待核对'}</p><p class="quote-provenance">${l.fareVerified?'12306 公开查询 · 上车日期 '+fmt(dateShift(currentOptions.date,Math.floor(l.departure/1440)))+' · 查询于 '+new Date(l.quotedAt).toLocaleString('zh-CN',{timeZone:'Asia/Shanghai'}):'未获得此日期与席别的完整报价。'}</p><div class="stop-list">${network.trips[l.trip][2].slice(l.fromIndex,l.toIndex+1).map((i,k)=>{const t=network.trips[l.trip],j=k+l.fromIndex;return `<span>${esc(network.stops[i][1])}<b>${clockHTML(t[3][j]+l.serviceDay*1440)} 到 / ${clockHTML(t[4][j]+l.serviceDay*1440)} 发</b></span>`;}).join('')}</div><a class="official-link" href="https://kyfw.12306.cn/otn/leftTicket/init?linktypeid=dc" target="_blank" rel="noopener">去 12306 自行核对 ↗</a></section>`).join('')}<p>推荐不判断余票或实际运行。费用比较仅覆盖已核价区间。</p><button class="copy-button" id="detail-copy">复制完整行程</button>`);
  $('detail-copy').onclick=copyRoute;
}
async function copyRoute(){
  if(!selected)return;
  const share=new URL(location.href),o=currentOptions;
  const chosen=selected.legs.map(({trip,train,fromIndex,toIndex,serviceDay})=>({trip,train,fromIndex,toIndex,serviceDay}));
  share.search=new URLSearchParams({from:network.stops[selected.legs[0].from][1]+' · 车站',to:network.stops[selected.legs.at(-1).to][1]+' · 车站',date:fmt(o.date),time:clock(o.earliest),transfers:String(o.maxTransfers),type:o.trainType,value:String(o.valueOfTime),seat:o.seatPreference,mode:'manual',snapshot:String(network.meta.version),legs:JSON.stringify(chosen)});
  const lines=[`山海铁道 · ${kinds[selectedKind].name}`,`${fmt(currentOptions.date)} ${network.stops[selected.legs[0].from][1]} → ${network.stops[selected.legs.at(-1).to][1]}`,`历时 ${duration(selected.duration)} · ${selected.verified?'铁路票价 ¥'+price(selected.cost):'票价待核对'}`,...selected.legs.map((l,i)=>`${i&&selected.legs[i-1].to!==l.from?'⚠ 跨站换乘：'+network.stops[selected.legs[i-1].to][1]+' → '+network.stops[l.from][1]+'；间隔 '+duration(l.departure-selected.legs[i-1].arrival)+'；市内交通自行安排，时间未核实、费用另计。\n':''}${i+1}. ${l.train} ${network.stops[l.from][1]} ${clock(l.departure)} (+${Math.floor(l.departure/1440)}天) → ${network.stops[l.to][1]} ${clock(l.arrival)} (+${Math.floor(l.arrival/1440)}天)；${l.fareVerified?l.seatName+' ¥'+price(l.cost):'待核价'}`),'价格按查询时的区间与席别返回；最省钱仅在已核价区间组成的路线中比较。不判断余票、取消或晚点。',location.href];
  lines[lines.length-1]=share.href;
  try{await navigator.clipboard.writeText(lines.join('\n'));toast('完整行程已复制。');}catch{toast('复制未成功，可在详情中选取文字。');}
}
function setMode(value){
  manual=value;document.body.classList.toggle('manual-mode',manual);$('explorer-panel').hidden=!manual;$('city-workbench').hidden=!manual;map.cityMode=manual;map.onCity=inspectCity;map.draftNodes=[];
  $('planner-tab').setAttribute('aria-pressed',String(!manual));$('explore-tab').setAttribute('aria-pressed',String(manual));
  $('draft-return').hidden=!manual;
  if(!manual){selectedCity=null;map.focusCity=null;$('city-inspector').hidden=true;}
  $('map-caption').textContent=manual?'点选城市 · 查看班次 · 添加节点':'拖动探索 · 滚轮缩放';
  $('planner-tab').classList.toggle('active',!manual);$('explore-tab').classList.toggle('active',manual);setBusy(busy);
  stopReplay();$('process-body').hidden=true;$('trace-toggle').textContent='展开';$('trace-toggle').setAttribute('aria-expanded','false');
  map.setExploration(manual&&!$('process-body').hidden?timetable?.trace[traceIndex]:null,manual?waypoints:[]);renderWaypoints();
  if(manual){renderCityList();if(pickedLegs.length)renderPickedJourney();else if(!timetable){map.reset();renderDraft();}}else if(!selected)metro.clear();map.draw();
}
function addWaypoint(node){
  if(!node){toast('请先选择有效的城市或车站。');return;}
  if(waypoints.length>=3){toast('最多添加 3 个换乘节点。');return;}
  const endpoints=[...(resolve($('origin').value)?.stations||[]),...(resolve($('destination').value)?.stations||[])];
  if(node.stations.some(i=>endpoints.includes(i))||waypoints.some(w=>w.stations.some(i=>node.stations.includes(i)))){toast('该节点与起终点或已选节点重复。');return;}
  waypoints.push(node);if(Number($('transfers').value)<waypoints.length)$('transfers').value=String(waypoints.length);
  $('via').value='';$('via-options').hidden=true;$('via').setAttribute('aria-expanded','false');if(!manual)setMode(true);markDirty();toast('已添加 '+node.name+'，点击按节点查询。');
}
function renderWaypoints(){
  renderPickedList();
  $('builder-start').innerHTML=`${esc($('origin').value)}<small>出发</small>`;$('builder-end').innerHTML=`${esc($('destination').value)}<small>到达</small>`;
  $('waypoint-list').innerHTML=waypoints.length?waypoints.map((w,i)=>`<div class="waypoint-chip"><span>${i+1}</span><strong>${esc(w.name)}</strong><button data-move="${i}" data-dir="-1" ${i===0?'disabled':''} aria-label="前移${esc(w.name)}">↑</button><button data-move="${i}" data-dir="1" ${i===waypoints.length-1?'disabled':''} aria-label="后移${esc(w.name)}">↓</button><button data-remove="${i}" aria-label="移除${esc(w.name)}">×</button></div>`).join(''):'<div class="waypoint-empty">在这里添加想经过的城市</div>';
  document.querySelectorAll('[data-remove]').forEach(b=>b.onclick=()=>{waypoints.splice(Number(b.dataset.remove),1);markDirty();});
  document.querySelectorAll('[data-move]').forEach(b=>b.onclick=()=>{const i=Number(b.dataset.move),j=i+Number(b.dataset.dir);[waypoints[i],waypoints[j]]=[waypoints[j],waypoints[i]];markDirty();});
  map.setExploration(null,manual?waypoints:[]);if(manual&&!selected)renderDraft();
}
function draftNodes(){return [resolve($('origin').value),...waypoints,resolve($('destination').value)].filter(Boolean);}
function remainingWaypoints(legs=pickedLegs){let progress=0;for(const l of legs)if(waypoints[progress]?.stations.includes(l.to))progress++;return waypoints.slice(progress);}
function pickedComplete(legs=pickedLegs){return !!legs.length&&!!resolve($('destination').value)?.stations.includes(legs.at(-1).to)&&!remainingWaypoints(legs).length;}
function serviceAddError(l,overrides={}){
  try{
    const legs=validateFixedLegs(network,[...pickedLegs,l],{...formOptions(),maxTransfers:3,...overrides});
    if(resolve($('destination').value)?.stations.includes(l.to)&&remainingWaypoints(legs).length)return '请先经过 '+remainingWaypoints(legs)[0].name+' 节点。';
    if(legs.length===4&&!pickedComplete(legs))return '最多 4 段车次，最后一段须到达目的地。';
    return '';
  }catch(e){return e.message;}
}
function renderPickedList(){
  $('picked-journey').hidden=!pickedLegs.length;if(!pickedLegs.length)return;
  const complete=pickedComplete(),first=pickedLegs[0],last=pickedLegs.at(-1);
  $('picked-legs').innerHTML=pickedLegs.map((l,i)=>`<li>${i?crossNotice([pickedLegs[i-1],l]):''}<div class="picked-leg-title"><span>${i+1}</span><strong>${esc(l.train)}</strong><button data-unpick="${i}" aria-label="撤回第 ${i+1} 段及后续车次">撤回${i<pickedLegs.length-1?'此段起':''}</button></div><div class="picked-leg-stations">${esc(network.stops[l.from][1])} <span>→</span> ${esc(network.stops[l.to][1])}</div><div class="picked-leg-times">${clockHTML(l.departure)} → ${clockHTML(l.arrival)}${i?' · 换乘 '+duration(l.departure-pickedLegs[i-1].arrival):''}</div></li>`).join('');
  $('picked-summary').textContent=`已选 ${pickedLegs.length} 段 · 历时 ${duration(last.arrival-first.departure)} · ${complete?'已到达目的地':'已到达 '+network.stops[last.to][1]+'，可从同城车站继续选车'}`;
  $('continue-picked').hidden=complete;$('complete-picked').textContent=complete?'核对这条行程的票价':'保留已选，推荐后续';
  $('search-via').textContent='保留已选车次，匹配完整行程 →';
  $('picked-legs').querySelectorAll('[data-unpick]').forEach(b=>b.onclick=()=>{
    pickedLegs=pickedLegs.slice(0,Number(b.dataset.unpick));markDirty({keepPicked:true});continuePicked();toast('已撤回，此段及后续车次可重新选择。');
  });
}
function renderPickedJourney(){
  if(!manual||!pickedLegs.length)return;currentOptions=formOptions();const first=pickedLegs[0],last=pickedLegs.at(-1);
  previewService=true;selectRoute('custom',{route:annotate({id:'picked:'+pickedLegs.map(l=>[l.trip,l.fromIndex,l.toIndex,l.serviceDay].join(':')).join('|'),legs:pickedLegs,departure:first.departure,arrival:last.arrival,duration:last.arrival-first.departure,transfers:pickedLegs.length-1})});
  $('view-title').textContent=pickedComplete()?'自选行程 · 已到达目的地':`已加入 ${pickedLegs.length} 段 · 继续选择下一趟`;
  if(!pickedComplete()){
    map.draftNodes=[{name:network.stops[last.to][1],stations:[last.to]},...remainingWaypoints(),resolve($('destination').value)].filter(Boolean);
    map.fit([...pickedLegs.flatMap(l=>[map.stationPoints[l.from],map.stationPoints[l.to]]),...map.draftNodes.map(n=>map.stationPoints[n.stations[0]])]);map.draw();
  }
  renderPickedList();$('segment-checks').innerHTML='';
}
function continuePicked(){
  if(pickedComplete()){$('city-inspector').hidden=true;$('picked-journey').scrollIntoView({block:'nearest'});return;}
  const last=pickedLegs.at(-1),origin=resolve($('origin').value);
  const city=last?(cities.find(c=>c.stations.includes(last.to))||{name:network.stops[last.to][1],stations:[last.to]}):origin;
  inspectCity(city,remainingWaypoints()[0]||resolve($('destination').value));
}
function addService(l){
  const error=serviceAddError(l);if(error){toast(error);return;}
  pickedLegs=validateFixedLegs(network,[...pickedLegs,l],{...formOptions(),maxTransfers:3});
  const required=pickedLegs.length-1+(pickedComplete()?0:1);if(Number($('transfers').value)<required)$('transfers').value=String(required);
  markDirty({keepPicked:true});renderPickedJourney();continuePicked();syncURL();
  toast(`${l.train} 已加入行程${pickedComplete()?'，已到达目的地。':'，继续选择下一段。'}`);
}
$('continue-picked').onclick=()=>{renderPickedJourney();continuePicked();};$('complete-picked').onclick=search;
$('clear-picked').onclick=()=>{pickedLegs=[];markDirty({keepPicked:true});continuePicked();toast('已清空车次，可从出发地重新选择。');};
function renderDraft(){
  if(!manual||!network)return;$('transfer-notice').hidden=true;document.querySelector('.visual-workspace').classList.remove('has-cross-transfer');if(pickedLegs.length){renderPickedJourney();return;}$('search-via').textContent='比较经过这些节点的方案 →';const nodes=draftNodes();map.draftNodes=nodes;map.setRoute(null);map.fit(nodes.map(n=>map.stationPoints[n.stations[0]]));map.draw();metro.draft(nodes);$('metro-title').textContent='我的路线草稿';$('view-title').textContent='自由编辑 · 城市节点';$('map-subtitle').textContent=nodes.map(n=>n.name).join(' → ');$('journey-panel').hidden=true;
  const [h,m]=$('time').value.split(':').map(Number);$('segment-checks').innerHTML=nodes.slice(0,-1).map((n,i)=>{const count=directServices(network,{origin:n.stations,destination:nodes[i+1].stations,date:$('date').value.replaceAll('-',''),earliest:h*60+m,trainType:$('train-type').value}).length;return `<button data-segment="${i}"><span>${esc(n.name)} → ${esc(nodes[i+1].name)}</span><small>${count?count+' 个直达区间':'未找到直达'} ↗</small></button>`;}).join('');document.querySelectorAll('[data-segment]').forEach(b=>b.onclick=()=>{const i=Number(b.dataset.segment);inspectCity(nodes[i],nodes[i+1]);});
}
function renderCityList(){
  const q=$('city-query').value.trim(),rows=cities.filter(c=>!q||c.name.includes(q));
  $('city-count').textContent=cities.length+' 个城市';
  $('city-list').innerHTML=rows.map(c=>`<button data-city="${esc(c.name)}" class="${c.name===selectedCity?.name?'active':''}">${esc(c.name)}</button>`).join('')||'<small>未找到城市，请试试车站搜索。</small>';
  $('city-list').querySelectorAll('button').forEach(b=>b.onclick=()=>inspectCity(cities.find(c=>c.name===b.dataset.city)));
}
function inspectCity(city,target,focus=true){
  if(!city||!manual)return;selectedCity=city;serviceLimit=20;renderCityList();$('city-inspector').hidden=false;
  const continuing=!!pickedLegs.length&&city.stations.some(s=>canTransfer(network,pickedLegs.at(-1).to,s)),routeNodes=draftNodes(),nodeIndex=routeNodes.findIndex(n=>n.name===city.name);const defaultTarget=target||(continuing?remainingWaypoints()[0]:(nodeIndex>=0?routeNodes[nodeIndex+1]:null))||resolve($('destination').value),same=defaultTarget?.stations.some(i=>city.stations.includes(i));
  const dest=same?resolve($('origin').value):defaultTarget;const targets=[...cities];if(dest&&!targets.some(c=>c.name===dest.name))targets.unshift(dest);
  $('city-inspector-content').innerHTML=`<h3 class="city-inspector-title">${esc(city.name)} <small>${city.stations.length} 站</small></h3><p class="city-meta">${city.stations.map(i=>esc(network.stops[i][1])).join(' / ')}</p><div class="city-actions"><button id="city-origin">设为出发</button><button id="city-destination">设为到达</button><button id="city-via">添加节点</button></div><div id="connection-context" class="connection-context" hidden></div><label class="service-filter">${continuing?'下一段到':'查看直达至'} <select id="service-target" aria-label="查看直达车次的目的城市">${targets.filter(c=>c.name!==city.name).map(c=>`<option ${c.name===dest?.name?'selected':''} value="${esc(c.name)}">${esc(c.name)}</option>`).join('')}</select></label><div id="service-count" class="service-count"></div><div id="service-list"></div><button id="more-services" class="more-prices" hidden>展开更多班次</button><p class="city-meta">加入后固定这趟车及上下车站，后续包含同站与同城跨站车次，按间隔 30–240 分钟筛选；跨站交通需自行安排并确认时间，费用另计。可撤回重选，也可保留已选车次推荐后续。</p>`;
  $('city-origin').onclick=()=>{$('origin').value=city.name;renderWaypoints();markDirty();};$('city-destination').onclick=()=>{$('destination').value=city.name;renderWaypoints();markDirty();};$('city-via').onclick=()=>addWaypoint(city);
  const lookup=()=>{
    serviceLimit=20;const dest=resolve($('service-target').value),[h,m]=$('time').value.split(':').map(Number),options={origin:city.stations,destination:dest?.stations,date:$('date').value.replaceAll('-',''),earliest:h*60+m,trainType:$('train-type').value};
    serviceRows=continuing?connectionServices(network,{...options,prefix:pickedLegs}):directServices(network,options);
    const context=$('connection-context'),origin=resolve($('origin').value),otherOrigin=!pickedLegs.length&&!city.stations.some(i=>origin?.stations.includes(i));context.hidden=!pickedLegs.length&&!otherOrigin;
    if(pickedLegs.length){const last=pickedLegs.at(-1);context.innerHTML=continuing?`<strong>接着 ${esc(last.train)} 继续选</strong><span>${esc(network.stops[last.to][1])} ${clockHTML(last.arrival)} 到达 · 已选 ${pickedLegs.length} 段</span><span>班次筛选时间 ${clockHTML(last.arrival+30)}–${clockHTML(last.arrival+240)}</span><span>包含同城其他车站；跨站请核对市内交通与进站时间。</span>`:`<strong>正在浏览其他城市</strong><span>已选行程停在 ${esc(network.stops[last.to][1])}。请从这里继续接车。</span><button id="resume-picked">回到下一段 →</button>`;$('resume-picked')?.addEventListener('click',continuePicked);}
    else if(otherOrigin){context.innerHTML=`<strong>当前出发地：${esc($('origin').value)}</strong><span>正在查看 ${esc(city.name)} 的班次。可在下方将该车的上车站设为出发站并加入，或先从原出发地接到这里。</span><button id="resume-picked">回到 ${esc($('origin').value)} 选首段 →</button>`;$('resume-picked').onclick=continuePicked;}
    renderServices();
  };
  $('service-target').onchange=lookup;$('more-services').onclick=()=>{serviceLimit+=20;renderServices();};lookup();map.focusCity=city;map.draw();if(focus)$('city-inspector').scrollIntoView({block:'nearest'});
}
function renderServices(){
  const continuing=pickedLegs.length&&selectedCity?.stations.some(s=>canTransfer(network,pickedLegs.at(-1).to,s));
  $('service-count').textContent=`${$('date').value} 出发 · ${serviceRows.length} 个${continuing?'候选接续':'直达'}乘车区间`;
  $('service-list').innerHTML=serviceRows.slice(0,serviceLimit).map((l,i)=>{
    const error=serviceAddError(l),originMismatch=!pickedLegs.length&&!resolve($('origin').value)?.stations.includes(l.from),correctedError=originMismatch?serviceAddError(l,{origin:[l.from]}):'';
    const hint=originMismatch?`当前从 ${$('origin').value} 出发；这趟车从 ${network.stops[l.from][1]} 发车。${correctedError}`:error|| (continuing?'换乘间隔 '+duration(l.departure-pickedLegs.at(-1).arrival):'可作为行程第一段');
    const action=originMismatch?`<button data-service-origin="${i}" aria-label="${correctedError?'设为出发站':'设为出发站并加入'} ${esc(l.train)}">${correctedError?'设为出发站':'设为出发并加入'}</button>`:`<button data-add-service="${i}" ${error?'disabled':''} title="${esc(error||'加入此车次到行程')}" aria-label="加入 ${esc(l.train)} 到行程">加入行程 +</button>`;
    return `<article class="service-row"><button class="service-preview" data-service="${i}" aria-label="预览 ${esc(l.train)}"><span><b>${esc(l.train)}</b><strong>${clockHTML(l.departure)} → ${clockHTML(l.arrival)}</strong></span><small>${esc(network.stops[l.from][1])} → ${esc(network.stops[l.to][1])} · ${duration(l.arrival-l.departure)}</small></button>${continuing?crossNotice([pickedLegs.at(-1),l]):''}<div class="service-actions"><small>${esc(hint)}</small>${action}</div></article>`;
  }).join('')||'<p class="city-meta">当前条件下没有可衔接车次。可换一个中转城市，或撤回上一段重新选择。</p>';
  $('more-services').hidden=serviceRows.length<=serviceLimit;
  document.querySelectorAll('[data-service]').forEach(b=>b.onclick=()=>{const l=serviceRows[Number(b.dataset.service)],date=$('date').value.replaceAll('-','');currentOptions={...currentOptions,date,seatPreference:$('seat-preference').value,valueOfTime:Number($('value-time').value)};previewService=true;selectRoute('custom',{route:annotate({id:'service:'+l.trip+':'+l.fromIndex+':'+l.toIndex+':'+date,legs:[l],departure:l.departure,arrival:l.arrival,duration:l.arrival-l.departure,transfers:0})});});
  document.querySelectorAll('[data-add-service]').forEach(b=>b.onclick=()=>addService(serviceRows[Number(b.dataset.addService)]));
  document.querySelectorAll('[data-service-origin]').forEach(b=>b.onclick=()=>{
    if(pickedLegs.length){toast('已有车次，请从实际到达城市继续选车。');return;}
    const l=serviceRows[Number(b.dataset.serviceOrigin)],canAdd=!serviceAddError(l,{origin:[l.from]});
    $('origin').value=network.stops[l.from][1]+' · 车站';markDirty();
    if(canAdd)addService(l);else toast('已更新出发站。'+serviceAddError(l));
  });
}
$('city-query').oninput=renderCityList;
$('draft-return').onclick=()=>{selected=null;clearTravelSelection();previewService=true;renderDraft();};
function renderHubs(){
  const counts=new Map();for(const s of timetable?.trace||[])for(const l of s.links)counts.set(l.to,(counts.get(l.to)||0)+l.count);
  const bridge=new Set((timetable?.candidates||[]).flatMap(r=>r.legs.slice(0,-1).map(l=>l.to)));
  const excluded=new Set([...(currentOptions?.origin||[]),...(currentOptions?.destination||[]),...waypoints.flatMap(w=>w.stations)]);
  for(const i of bridge)if(!counts.has(i))counts.set(i,0);
  const nodes=[...counts].filter(([i])=>!excluded.has(i)).sort((a,b)=>Number(bridge.has(b[0]))-Number(bridge.has(a[0]))||b[1]-a[1]).slice(0,8);
  $('hub-list').innerHTML=nodes.length?nodes.map(([i,count])=>`<button data-hub="${i}" title="添加 ${esc(network.stops[i][1])} 为换乘节点">${esc(network.stops[i][1])}<small>${bridge.has(i)?'方案节点':count}</small></button>`).join(''):'<span class="muted">查询后会展示本次探索到的关键节点。</span>';
  document.querySelectorAll('[data-hub]').forEach(b=>b.onclick=()=>{const i=Number(b.dataset.hub);addWaypoint({name:network.stops[i][1],stations:[i]});});
}
function showStation(i,point){
  if(document.body.classList.contains('comparison-preview')){toast(network.stops[i][1]+' · 可展开行程详情查看经停时刻');return;}
  if(manual){inspectCity(cities.find(c=>c.stations.includes(i))||{name:network.stops[i][1],stations:[i]});return;}
  if(!point)point={x:30,y:30};const popup=$('station-popup'),s=network.stops[i];
  popup.innerHTML=`<strong>${esc(s[1])}</strong><p>车站 ${s[0]}</p><div><button data-set="origin">设为出发</button><button data-set="destination">设为到达</button></div><button id="station-via" class="station-via">经此站换乘 →</button>`;
  popup.style.left=Math.max(10,Math.min(point.x+12,$('rail-map').clientWidth-190))+'px';popup.style.top=Math.max(10,Math.min(point.y+12,$('rail-map').clientHeight-180))+'px';popup.hidden=false;
  popup.querySelectorAll('[data-set]').forEach(b=>b.onclick=()=>{$(b.dataset.set).value=s[1]+' · 车站';popup.hidden=true;markDirty();});$('station-via').onclick=()=>{popup.hidden=true;addWaypoint({name:s[1],stations:[i]});};
}
function renderTrace(){
  $('process-panel').hidden=!timetable?.trace.length;
  $('trace-steps').innerHTML=(timetable?.trace||[]).map((s,i)=>`<button data-step="${i}" class="${i===traceIndex?'active':''}">${s.transfers?s.transfers+' 次换乘':'直达'}</button>`).join('');
  document.querySelectorAll('[data-step]').forEach(b=>b.onclick=()=>{stopReplay();traceIndex=Number(b.dataset.step);renderTrace();});
  const step=timetable?.trace[traceIndex];if(!step)return;
  $('trace-description').textContent=step.transfers===0?'先从出发站登车，比较能直接到达的方案。':`把前一层的到达记录接到下一班车，保留同站或同城跨站、间隔 30–240 分钟的连接。跨站交通需自行确认。此层比较恰好 ${step.transfers} 次换乘。`;
  $('trace-metrics').innerHTML=`<span><strong>${step.evaluated.toLocaleString()}</strong>乘车区间</span><span><strong>${step.reached.toLocaleString()}</strong>到达车站</span><span><strong>${step.found.toLocaleString()}</strong>到达记录</span><span><strong>${step.pruned.toLocaleString()}</strong>被支配状态</span>`;
  const open=!$('process-body').hidden;map.setExploration(open?step:null,manual?waypoints:[]);
}
function renderAlternatives(quoted){
  const rows=quoted.byTransfers||[];$('alternatives').hidden=!rows.length;
  $('alternative-list').innerHTML=rows.map((b,i)=>`<button data-alternative="${i}"><span>${b.transfers?'换乘 '+b.transfers+' 次':'直达'}</span><strong>¥${price(b.cheapest.cost)}</strong><small>${duration(b.cheapest.duration)}</small></button>`).join('');
  document.querySelectorAll('[data-alternative]').forEach(b=>b.onclick=()=>{previewService=false;selectRoute('custom',{route:rows[Number(b.dataset.alternative)].cheapest});});
}
$('add-via').onclick=()=>addWaypoint(resolve($('via').value));$('clear-waypoints').onclick=()=>{waypoints=[];renderWaypoints();markDirty();};$('search-via').onclick=search;
$('planner-tab').onclick=()=>{comparison?.hide();setMode(false);syncURL();if(waypoints.length||pickedLegs.length)search();};$('explore-tab').onclick=()=>{comparison?.hide();setMode(true);syncURL();if(pickedLegs.length)continuePicked();else if(waypoints.length&&currentOptions&&!currentOptions.waypoints?.length)search();};
$('trace-toggle').onclick=()=>{stopReplay();$('process-body').hidden=!$('process-body').hidden;$('trace-toggle').textContent=$('process-body').hidden?'展开':'收起';$('trace-toggle').setAttribute('aria-expanded',String(!$('process-body').hidden));renderTrace();};
$('trace-play').onclick=()=>{
  if(traceTimer){stopReplay();return;}if(!timetable?.trace.length)return;
  $('process-body').hidden=false;$('trace-toggle').textContent='收起';$('trace-toggle').setAttribute('aria-expanded','true');traceIndex=0;renderTrace();$('trace-play').textContent='暂停';
  traceTimer=setInterval(()=>{if(traceIndex>=timetable.trace.length-1){stopReplay();return;}traceIndex++;renderTrace();},1600);
};
$('more-prices').onclick=()=>{if(quoteCursor>=quotePairs.length)quoteCursor=0;fetchMoreQuotes();};
$('rail-map').addEventListener('pointerdown',()=>$('station-popup').hidden=true);
$('rail-map').addEventListener('keydown',e=>{const actions={'+':()=>map.zoom(1.3),'=':()=>map.zoom(1.3),'-':()=>map.zoom(1/1.3),'0':()=>map.reset(),ArrowLeft:()=>{map.tx+=50;map.draw();},ArrowRight:()=>{map.tx-=50;map.draw();},ArrowUp:()=>{map.ty+=50;map.draw();},ArrowDown:()=>{map.ty-=50;map.draw();}};if(actions[e.key]){e.preventDefault();actions[e.key]();}});
$('zoom-in').onclick=()=>map.zoom(1.3);$('zoom-out').onclick=()=>map.zoom(1/1.3);$('reset-map').onclick=()=>map.reset();$('fit-route').onclick=()=>selected?map.setRoute(selected,{color:kinds[selectedKind].color}):map.reset();
document.querySelectorAll('[data-layer]').forEach(e=>e.onchange=()=>{map.filters[e.dataset.layer]=e.checked;map.draw();});
$('about-open').onclick=showAbout;$('about-close').onclick=()=>$('about-dialog').close();
$('about-dialog').addEventListener('click',e=>{if(e.target===$('about-dialog')){const r=e.target.getBoundingClientRect();if(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom)e.target.close();}});
const params=new URLSearchParams(location.search);
for(const [key,id] of [['from','origin'],['to','destination'],['date','date'],['time','time'],['transfers','transfers'],['type','train-type'],['value','value-time'],['seat','seat-preference']])if(params.has(key))$(id).value=params.get(key);
$('value-label').textContent=$('value-time').value;
let resolveNetwork;const networkReady=new Promise(resolve=>resolveNetwork=resolve);
worker.onmessage=({data})=>{
  if(data.type==='ready'){network=data.network;resolveNetwork();return;}
  if(data.id!==requestId)return;
  if(data.type==='error'){setBusy(false);phase='error';$('results').innerHTML=`<div class="error-message">${esc(data.error)}</div>`;if(manual&&pickedLegs.length)renderPickedJourney();return;}
  if(data.type!=='result')return;
  if(data.result.options.pricingMode==='heuristic'){
    timetable=data.result;result={...timetable,fastest:annotate(timetable.fastest),cheapest:null,balanced:null};traceIndex=0;setBusy(false);phase='ready';
    renderResults();renderTrace();renderHubs();quotePairs=collectQuotePairs(timetable);quoteCursor=0;
    if(timetable.truncated)$('scope-note').textContent+=' 已达本次搜索上限，结果仅覆盖已探索候选。';
    if(quotePairs.length)fetchMoreQuotes();else $('pricing-status').textContent='没有可核价的完整路线。';
  }else{
    quotedResult=data.result;phase='ready';result={...timetable,fastest:annotate(timetable.fastest),cheapest:data.result.cheapest,balanced:data.result.balanced};
    renderResults(false);renderAlternatives(data.result);
    const count=Object.keys(fareQuotes).length;
    $('pricing-status').textContent=data.result.count?`已核对 ${quoteCursor} / ${quotePairs.length} 个候选区间，评估 ${data.result.count.toLocaleString()} 条有完整报价的到达记录。费用排序仅覆盖这些区间。`:`未取得当前席别的完整报价，费用推荐暂不生成。${quoteErrors.length?'来源可能暂不可用。':''}`;
    $('more-prices').hidden=quoteCursor>=quotePairs.length&&!quoteErrors.length;$('more-prices').textContent=quoteCursor<quotePairs.length?'继续核对更多候选区间':'重试核价';
  }
};
worker.onerror=()=>{setBusy(false);$('results').innerHTML='<div class="error-message">计算模块加载失败，请刷新重试。</div>';};
worker.postMessage({type:'init'});
async function loadJSON(url){const r=await fetch(url);if(!r.ok)throw new Error('地图数据加载失败，请刷新重试。');return r.json();}
Promise.all([networkReady,loadJSON('./data/map.json'),loadJSON('./data/china.geojson')]).then(([,m,g])=>{
  map.setData(network,m,g);prepareServiceIndex(network);cities=cityIndex(network).cities;map.cities=cities;
  $('station-count').textContent=network.meta.stationCount.toLocaleString();$('train-count').textContent=network.meta.tripCount.toLocaleString();$('snapshot-date').textContent='时刻表 '+fmt(network.meta.version)+' · 实时报价';
  $('date').min=fmt(network.meta.startDate);$('date').max=fmt(network.meta.endDate);
  if(!$('date').value){const today=new Intl.DateTimeFormat('sv-SE',{timeZone:'Asia/Shanghai'}).format(new Date());$('date').value=today>fmt(network.meta.endDate)?fmt(network.meta.endDate):today<fmt(network.meta.startDate)?fmt(network.meta.startDate):today;}
  try{const saved=JSON.parse(params.get('via')||'[]');waypoints=saved.slice(0,3).map(w=>({name:String(w.name),stations:w.codes.map(c=>network.stops.findIndex(s=>s[0]===c)).filter(i=>i>=0)})).filter(w=>w.stations.length);}catch{waypoints=[];}
  try{if(params.has('legs')){if(params.get('snapshot')!==String(network.meta.version))throw new Error('时刻表版本已更新，请重新选择车次。');pickedLegs=validateFixedLegs(network,JSON.parse(params.get('legs')),formOptions());}}catch(e){pickedLegs=[];toast(e.message);}
  ready=true;setMode(params.get('mode')==='manual');setBusy(false);renderWaypoints();renderHubs();
  setupComparison();updateQuerySummary();
  if(manual&&pickedLegs.length){renderPickedJourney();continuePicked();$('results').innerHTML='<div class="empty-state"><strong>已恢复你的自选车次</strong><p>可以继续选下一段，或保留已选车次推荐后续。</p></div>';syncURL();}
  else if (embedded && (!resolve($('origin').value) || !resolve($('destination').value))) {
    document.body.classList.remove('conditions-collapsed');$('toggle-conditions').setAttribute('aria-expanded','true');$('toggle-conditions').textContent='收起出发条件 ▴';
    $('results').innerHTML='<div class="empty-state"><strong>先选好起点和目的地</strong><p>生成铁路方案后，可以直接加入旅行的交通清单。</p></div>';
    $('result-count').textContent='填写出发条件后查询';
  } else search();
}).catch(e=>{$('results').innerHTML=`<div class="error-message">${esc(e.message)}</div>`;});

function updateQuerySummary(){
  $('query-summary-text').textContent=`${$('origin').value} → ${$('destination').value}  ·  ${$('date').value}  ·  ${$('time').value} 后出发  ·  ${$('transfers').selectedOptions[0]?.textContent||''}`;
}
$('toggle-conditions').onclick=()=>{
  const collapsed=document.body.classList.toggle('conditions-collapsed');$('toggle-conditions').textContent=collapsed?'修改出发条件 ▾':'收起出发条件 ▴';$('toggle-conditions').setAttribute('aria-expanded',String(!collapsed));
};
$('toggle-metro').onclick=()=>{const expanded=document.body.classList.toggle('metro-expanded');$('toggle-metro').textContent=expanded?'收起线路 ▾':'展开线路 ▴';$('toggle-metro').setAttribute('aria-expanded',String(expanded));};
$('map-focus').onclick=()=>{const focus=document.body.classList.toggle('map-focus');$('map-focus').textContent=focus?'退出专注地图 ⛶':'专注地图 ⛶';$('map-focus').setAttribute('aria-pressed',String(focus));};
function setupComparison(){
  comparison=initComparison({network,quotes:fareQuotes,toast,
    onFinal:(route,options,rules)=>{selected=route;currentOptions=options;travelRiskRules=rules;publishTravelSelection();},
    readEditor:()=>{
      const options=formOptions(),complete=selected&&options.destination?.includes(selected.legs.at(-1).to)&&(!previewService||pickedComplete());
      return {options,route:complete?selected:null,fields:{from:$('origin').value,to:$('destination').value,date:$('date').value,time:$('time').value}};
    },
    newEditor:()=>{waypoints=[];pickedLegs=[];selectedCity=null;$('city-inspector').hidden=true;setMode(true);markDirty();renderDraft();},
    loadEditor:(p,options)=>{
      for(const [key,id] of [['from','origin'],['to','destination'],['date','date'],['time','time'],['transfers','transfers'],['type','train-type'],['value','value-time'],['seat','seat-preference']])$(id).value=p.fields[key];
      $('value-label').textContent=$('value-time').value;waypoints=structuredClone(options.waypoints);pickedLegs=structuredClone(options.fixedLegs);selectedCity=null;$('city-inspector').hidden=true;
      setMode(true);markDirty({keepPicked:true});if(pickedLegs.length)continuePicked();
    },
    enter:()=>{
      clearTravelSelection();
      if(!comparisonBackup)comparisonBackup={selected,selectedKind,currentOptions,previewService};
      $('map-focus').textContent='专注地图 ⛶';$('map-focus').setAttribute('aria-pressed','false');
      clearTimeout(preferenceTimer);cancelQuote();stopReplay();requestId++;phase='idle';setBusy(false);metro.pause();
    },
    leave:()=>{
      const backup=comparisonBackup;comparisonBackup=null;setMode(manual);
      if(backup){({currentOptions,previewService}=backup);if(backup.selected)selectRoute(backup.selectedKind,{route:backup.selected});else if(manual)renderDraft();else{selected=null;map.setRoute(null);metro.clear();$('journey-panel').hidden=true;$('transfer-notice').hidden=true;}}
    },
    preview:(route,options,name,rules)=>{currentOptions=options;previewService=true;map.cityMode=false;map.focusCity=null;map.setExploration(null,[]);selectRoute('custom',{route,riskRules:rules});$('view-title').textContent=name+' · 方案预览';}
  });
}
