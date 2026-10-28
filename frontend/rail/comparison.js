import {STORAGE_KEY,MAX_PLANS,savePlanRecord,restorePlan,restoreChoice,routeSelection,priceRoute,comparisonKey} from './saved-plans.js';
import {fareKey,dateShift} from './router.js';
import {crossTransfers} from './transfers.js';
import {DEFAULT_RISK,validateRiskRules,transferRisk,decisionMetrics,decisionRanks,decodeWorkspace,writeWorkspace,finalizeDecision,recoverComparison} from './decision-model.js';
import {renderDecision,renderFinals,finalText} from './decision-view.js';
const $=id=>document.getElementById(id);
const esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const time=m=>`${String(Math.floor(m/60)%24).padStart(2,'0')}:${String(m%60).padStart(2,'0')}${m>=1440?' +'+Math.floor(m/1440)+'天':''}`;
const duration=m=>m<60?`${m}分钟`:`${Math.floor(m/60)}小时${m%60?m%60+'分':''}`;
const date=s=>`${s.slice(0,4)}-${s.slice(4,6)}-${s.slice(6,8)}`;

export function initComparison({network,readEditor,loadEditor,newEditor,preview,enter,leave,toast,quotes,onFinal}){
  let plans=[],states=new Map(),activeId=null,open=false,previewing=false,running=false,generation=0,matcher,abort,pending,readError='',removed,lastStored;
  let finals=[],recovery=null,view='library',analysisGroup='',decisionSelected=null,rules={...DEFAULT_RISK},avoidHigh=true,lastPricingState='';
  try{lastStored=localStorage.getItem(STORAGE_KEY);({plans,finals,recovery}=decodeWorkspace(lastStored));if(!plans.length&&finals.length)view='finals';}catch(e){readError=e.message||'浏览器无法读取本地方案。';}
  const workspace=()=>({version:1,plans,finals,recovery});
  function commit(next,nextView=view){
    if(readError)throw new Error(readError);
    lastStored=writeWorkspace(localStorage,STORAGE_KEY,lastStored,next);
    ({plans,finals,recovery}=next);view=nextView;render();
  }
  function persist(next){
    commit({...workspace(),plans:next});
  }
  function state(p){
    if(!states.has(p.id)){try{const restored=restorePlan(network,p),route=restoreChoice(network,p,restored.options)||restored.route;states.set(p.id,{...restored,routes:route?[route]:[],status:route?'已恢复车次 · 可重新核价':'待匹配',selected:0});}catch(e){states.set(p.id,{routes:[],status:e.message,error:true});}}
    return states.get(p.id);
  }
  function current(p){const s=state(p);return s.routes[s.selected||0]?priceRoute(network,s.routes[s.selected||0],s.options,quotes):null;}
  const pricingState=()=>JSON.stringify(plans.map(p=>{const r=current(p);return [p.id,r?.verified,r?.cost];}));
  function showPreview(route,options,name){
    previewing=true;document.body.classList.remove('comparison-mode');document.body.classList.add('comparison-preview');$('comparison-page').hidden=true;
    $('comparison-return').textContent='← 返回'+(view==='analysis'?'可视化对比':view==='finals'?'已定行程':'对比库');preview(route,options,name,rules);
  }
  function startAnalysis(id){
    const p=plans.find(p=>p.id===id);analysisGroup=p?comparisonKey(p):$('compare-group').value;
    const available=plans.filter(p=>comparisonKey(p)===analysisGroup&&current(p));if(!available.length){toast('请先匹配至少一条完整行程。');return;}
    decisionSelected=id||available[0].id;view='analysis';render();$('comparison-page').scrollTop=0;$('decision-content').querySelector('h2')?.focus({preventScroll:true});
  }
  function saveFinal(id){
    try{const p=plans.find(p=>p.id===id),route=p&&current(p);if(!route)throw new Error('请先选择完整行程。');
      const options=state(p).options;
      const next=finalizeDecision(network,workspace(),p,route,rules);commit(next,'finals');states.clear();activeId=null;removed=null;$('undo-plan').hidden=true;
      onFinal?.(route,options,rules);
      $('plan-name').value=nextName();$('save-plan').textContent='加入对比库';$('comparison-page').scrollTop=0;toast('最终行程已保存，对比库已清空。');
    }catch(e){toast(e.message);}
  }
  function renderDecisionStep(){
    const rows=plans.filter(p=>comparisonKey(p)===analysisGroup).map(p=>({id:p.id,name:p.name,plan:p,route:current(p)})).filter(r=>r.route);
    renderDecision($('decision-content'),{network,rows,selectedId:decisionSelected,rules,value:Number($('compare-value').value),avoidHigh,totalPlans:plans.length,groupCount:plans.filter(p=>comparisonKey(p)===analysisGroup).length,
      onSelect:id=>{decisionSelected=id;render();$('decision-content').querySelector('.decision-plan-tabs [aria-pressed="true"]')?.focus({preventScroll:true});},
      onRules:(next,key)=>{try{rules=validateRiskRules(next);}catch(e){toast(e.message);}render();$('risk-'+key)?.focus({preventScroll:true});},onValue:value=>{$('compare-value').value=String(value);render();$('decision-value')?.focus({preventScroll:true});},onAvoid:value=>{avoidHigh=value;render();$('avoid-high-risk')?.focus({preventScroll:true});},
      onBack:()=>{view='library';render();},onPreview:id=>{const p=plans.find(p=>p.id===id);showPreview(current(p),state(p).options,p.name);},onSave:saveFinal});
  }
  function renderFinalStep(){
    renderFinals($('final-content'),{finals,recovery,planCount:plans.length,network,
      onLibrary:()=>{view='library';render();},onRecover:()=>{try{commit(recoverComparison(workspace()),'library');toast('已恢复对比库，最终行程仍保留。');}catch(e){toast(e.message);}},
      onPreview:id=>{try{const f=finals.find(f=>f.id===id),r=restorePlan(network,f.plan);showPreview(priceRoute(network,r.route,r.options,quotes),r.options,f.plan.name+' · 已定行程');}catch(e){toast(e.message);}},
      onCopy:async id=>{try{await navigator.clipboard.writeText(finalText(finals.find(f=>f.id===id)));toast('最终行程已复制。');}catch{toast('复制失败，可以使用导出文本。');}},
      onExport:id=>{const f=finals.find(f=>f.id===id),url=URL.createObjectURL(new Blob([finalText(f)],{type:'text/plain;charset=utf-8'})),a=document.createElement('a');a.href=url;a.download='山海铁道-'+f.itinerary.date+'.txt';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}});
  }
  function nextName(){let i=0;while(plans.some(p=>p.name==='方案 '+String.fromCharCode(65+i)))i++;return '方案 '+String.fromCharCode(65+i);}
  function updateCount(){$('compare-tab').textContent=`03 方案对比${plans.length?' · '+plans.length:''}`;$('open-comparison').textContent=`统一匹配 / 对比（${plans.length}）`;$('saved-count').textContent=`${plans.length} / ${MAX_PLANS} · 保存在当前浏览器`;}
  function save(andNew=false){
    try{
      const old=plans.find(p=>p.id===activeId);if(!old&&plans.length>=MAX_PLANS)throw new Error(`最多保存 ${MAX_PLANS} 个方案，可移除不需要的方案。`);
      const data=readEditor(),p=savePlanRecord(network,{...data,name:$('plan-name').value},old);restorePlan(network,p);
      const next=old?plans.map(x=>x.id===p.id?p:x):[...plans,p];states.delete(p.id);commit({...workspace(),plans:next},'library');activeId=p.id;
      toast(`已保存「${p.name}」${andNew?'，可以制作下一个方案。':'，可到方案对比中统一匹配。'}`);
      if(andNew){activeId=null;$('plan-name').value=nextName();$('save-plan').textContent='加入对比库';newEditor();}else $('save-plan').textContent='更新对比方案';
    }catch(e){toast(e.message);}
  }
  function show(){if(open&&!previewing)return;enter();open=true;previewing=false;document.body.classList.remove('comparison-preview','map-focus');document.body.classList.add('comparison-mode');$('comparison-page').hidden=false;$('compare-tab').classList.add('active');$('planner-tab').classList.remove('active');$('explore-tab').classList.remove('active');render();}
  function hide(){if(!open)return;stop(false);open=false;previewing=false;document.body.classList.remove('comparison-mode','comparison-preview');$('comparison-page').hidden=true;$('compare-tab').classList.remove('active');leave();}
  function edit(p){try{const s=restorePlan(network,p);hide();activeId=p.id;$('plan-name').value=p.name;$('save-plan').textContent='更新对比方案';loadEditor(p,s.options);toast(`正在编辑「${p.name}」，加入对比库后更新此方案。`);}catch(e){toast(e.message);}}
  function create(){hide();view='library';activeId=null;$('plan-name').value=nextName();$('save-plan').textContent='加入对比库';newEditor();}
  function stop(notify=true){
    generation++;abort?.abort();matcher?.terminate();matcher=null;pending?.reject(new DOMException('Stopped','AbortError'));pending=null;
    for(const s of states.values())if(s.busy){s.busy=false;s.status=s.routes.length?'已停止，保留已匹配车次':'已停止，可重新匹配';}
    running=false;if(notify)render();
  }
  function getWorker(){
    return new Promise((resolve,reject)=>{
      if(matcher){resolve();return;}matcher=new Worker('./worker.js',{type:'module'});pending={resolve,reject};
      matcher.onmessage=({data})=>{if(!pending)return;const task=pending;pending=null;data.type==='error'?task.reject(new Error(data.error)):task.resolve(data.result);};
      matcher.onerror=()=>{pending?.reject(new Error('匹配模块加载失败，请重试。'));pending=null;};matcher.postMessage({type:'init'});
    });
  }
  async function solve(options){await getWorker();return new Promise((resolve,reject)=>{pending={resolve,reject};matcher.postMessage({type:'plan',id:1,options});});}
  function quotePairs(routes,options){
    const pairs=new Map();for(const r of routes)for(const l of r.legs){
      const pair={from:network.stops[l.from][0],to:network.stops[l.to][0],fromName:network.stops[l.from][1],toName:network.stops[l.to][1],date:date(dateShift(options.date,Math.floor(l.departure/1440))),required:[l.train]},key=[pair.from,pair.to,pair.date].join('|');
      const old=pairs.get(key);if(old){if(!old.required.includes(l.train)&&old.required.length<4)old.required.push(l.train);}else pairs.set(key,pair);
    }return [...pairs.values()].slice(0,12);
  }
  async function match(ids){
    if(running)return;const targets=plans.filter(p=>ids.includes(p.id));if(!targets.length)return;
    running=true;const token=++generation;abort=new AbortController();render();
    try{
      for(let i=0;i<targets.length;i++){
        if(token!==generation)return;const p=targets[i],s=state(p);s.busy=true;s.error=false;s.status=`正在匹配 ${i+1} / ${targets.length}`;render();
        try{
          const restored=restorePlan(network,p);s.options=restored.options;
          let found;if(restored.route){s.routes=[restored.route];s.limited=false;}else{
            found=await solve(s.options);if(token!==generation)return;
            s.routes=[...new Map([found.fastest,found.cheapest,found.balanced,...found.candidates].filter(Boolean).map(r=>[r.id,r])).values()].slice(0,24);s.limited=found.truncated;
          }
          s.selected=0;s.status=s.routes.length?'已匹配，正在核对铁路票价':'未找到路线，请编辑节点或条件';render();
          let failed=0;const pairs=quotePairs(s.routes,s.options);
          for(let j=0;j<pairs.length;j+=2){
            if(token!==generation)return;s.status=`核对票价 ${j+1}–${Math.min(j+2,pairs.length)} / ${pairs.length}`;render();
            try{
              const response=await fetch('/api/rail/fares',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({pairs:pairs.slice(j,j+2)}),signal:AbortSignal.any([abort.signal,AbortSignal.timeout(35000)])});
              if(!response.ok)throw new Error('票价服务暂不可用');const payload=await response.json();
              if(token!==generation)return;
              for(const q of payload.results||[])for(const row of q.rows||[])quotes[fareKey(row.train,row.from,row.to,row.date.replaceAll('-',''))]=row;
              if(!(payload.results||[]).some(q=>q.rows?.length))failed++;
            }catch(e){if(token!==generation)return;failed++;}
            if(failed>=2)break;
          }
          if(found&&pairs.length){
            const quoted=await solve({...s.options,pricingMode:'quoted',fareQuotes:quotes});if(token!==generation)return;
            s.routes=[...new Map([...s.routes,...quoted.candidates].map(r=>[r.id,r])).values()];s.limited ||= quoted.truncated;
          }
          s.routes.sort((a,b)=>a.duration-b.duration||a.departure-b.departure);s.selected=0;
          s.status=s.routes.length?(failed?'已匹配 · 部分票价暂不可用':'匹配完成'):'未找到路线，请编辑节点或条件';
          persist(plans.map(x=>x.id===p.id?{...x,choice:s.routes[0]?routeSelection(s.routes[0]):undefined}:x));
        }catch(e){if(token!==generation)return;s.status=e.message;s.error=true;}
        s.busy=false;render();
      }
    }finally{if(token===generation){running=false;matcher?.terminate();matcher=null;render();}}
  }
  function render(){
    updateCount();if(!open)return;if(view!=='finals')lastPricingState=pricingState();
    $('comparison-library').hidden=view!=='library';$('decision-content').hidden=view!=='analysis';$('final-content').hidden=view!=='finals';
    $('library-view').classList.toggle('active',view==='library');$('finals-view').classList.toggle('active',view==='finals');$('finals-view').textContent=`已定行程${finals.length?' · '+finals.length:''}`;
    $('start-visual').hidden=view!=='library';
    if(view==='analysis'){renderDecisionStep();return;}if(view==='finals'){renderFinalStep();return;}
    const groupSelect=$('compare-group'),old=groupSelect.value,groups=new Map();for(const p of plans)if(!groups.has(comparisonKey(p)))groups.set(comparisonKey(p),p);
    groupSelect.innerHTML=[...groups].map(([key,p])=>`<option value="${esc(key)}">${esc(p.fields.from)} → ${esc(p.fields.to)} · ${esc(p.fields.date)} · ${esc(p.fields.time)} · ${p.fields.type==='fast'?'高铁/动车':p.fields.type==='normal'?'普速':'全部列车'} · ${p.fields.seat==='hard'?'硬座':p.fields.seat==='second'?'二等座':'二等座/硬座'}</option>`).join('');
    if(groups.has(old))groupSelect.value=old;
    const rows=plans.filter(p=>comparisonKey(p)===groupSelect.value),value=Number($('compare-value').value),rank=decisionRanks(rows.map(p=>({id:p.id,route:current(p)})).filter(r=>r.route).map(r=>({...r,metrics:decisionMetrics(r.route,rules)})),{value,avoidHigh});
    $('comparison-page').querySelector('.comparison-footnote').textContent=`仅比较本组当前选择的候选，不代表全网最优。当前风险预留：同站 ${rules.same} 分钟，跨站 ${rules.cross} 分钟；综合优选${avoidHigh?'优先排除高风险':'未排除高风险'}。可在可视化对比中调整。刷新后需重新核价。`;
    $('start-visual').disabled=running||!rows.some(p=>current(p));
    $('compare-caption').textContent=readError||`${plans.length} 个已保存方案 · 当前组 ${rows.length} 个 · 同起终点、日期、出发时段、车型与席别放在一起比较`;
    $('match-all').disabled=running||!rows.length;$('match-all').textContent=running?'正在逐个匹配…':'统一匹配本组方案';$('stop-matching').hidden=!running;
    $('compare-progress').textContent=running?'后台逐个计算，可随时停止；已完成的结果会保留。':'比较当前各方案选中的候选。铁路票价仅比较完整报价；市内交通费用另计，换乘间隔需自行确认。';
    $('comparison-grid').innerHTML=rows.map((p,i)=>{
      const s=state(p),r=current(p),badges=Object.entries(rank).filter(([key,ids])=>key!=='risk'&&ids.includes(p.id)).map(([key])=>`<span class="comparison-badge ${key}">${{fastest:'本组最快',cheapest:'本组铁路票价最低',balanced:'本组综合优选'}[key]}</span>`).join('');
      const routeLabel=r?`${network.stops[r.legs[0].from][1]} → ${network.stops[r.legs.at(-1).to][1]}`:[p.fields.from,...p.waypoints.map(w=>w.name),p.fields.to].join(' → ');
      const cross=r?crossTransfers(r.legs):[],risk=r?transferRisk(r,rules):null;
      const options=s.routes.map((raw,k)=>{const route=priceRoute(network,raw,s.options,quotes);return `<option value="${k}" ${k===(s.selected||0)?'selected':''}>${k+1}. ${route.legs.map(l=>l.train).join(' → ')} · ${duration(route.duration)} · ${route.verified?'¥'+route.cost:'待核价'}</option>`;}).join('');
      return `<article class="comparison-card" data-plan="${esc(p.id)}"><div class="comparison-card-top"><span class="plan-number">${String(i+1).padStart(2,'0')}</span><input class="plan-title" aria-label="方案名称 ${i+1}" maxlength="40" value="${esc(p.name)}" ${running?'disabled':''}><button data-remove-plan="${esc(p.id)}" aria-label="移除 ${esc(p.name)}" ${running?'disabled':''}>×</button></div><p class="comparison-route">${esc(routeLabel)}</p><div class="comparison-badges">${badges||'<span class="neutral-badge">'+(r?'已选完整行程':'路线草稿')+'</span>'}</div>
        ${r?`<div class="comparison-metrics"><div><small>总历时</small><strong>${duration(r.duration)}</strong></div><div><small>铁路票价</small><strong>${r.verified?'¥'+r.cost:'待核价'}</strong></div><div><small>换乘</small><strong>${r.transfers} 次 <em>${cross.length?'含 '+cross.length+' 次跨站':''}</em></strong></div></div><p class="comparison-clock">${time(r.departure)} 出发 <span>→</span> ${time(r.arrival)} 到达</p>`:'<div class="unmatched-plan"><strong>先存想法，再匹配车次。</strong><p>'+esc(p.waypoints.length?'途经 '+p.waypoints.map(w=>w.name).join(' → '):'按已保存的条件搜索')+`<br>已固定 ${p.legs.length} 段车次 · 最多 ${p.fields.transfers} 次换乘</p></div>`}
        ${cross.length?`<div class="comparison-cross"><strong>⚠ 同城跨站换乘</strong>${cross.map(t=>`<span>${esc(network.stops[t.from][1])} → ${esc(network.stops[t.to][1])} · 间隔 ${duration(t.minutes)}</span>`).join('')}<small>需自行安排出站、市内交通及进站，交通费另计。</small></div>`:''}
        ${r?`${s.routes.length>1?`<label class="candidate-picker">选择匹配结果 · ${s.routes.length} 条候选<select data-candidate="${esc(p.id)}" ${running?'disabled':''}>${options}</select></label>`:`<p class="single-candidate">${r.legs.map(l=>esc(l.train)).join(' → ')}</p>`}<details class="comparison-legs"><summary>展开 ${r.legs.length} 段车次</summary>${r.legs.map(l=>`<p><b>${esc(l.train)}</b> ${esc(network.stops[l.from][1])} → ${esc(network.stops[l.to][1])}<small>${time(l.departure)} → ${time(l.arrival)} · ${l.fareVerified?l.seatName+' ¥'+l.cost:'待核价'}</small></p>`).join('')}</details>`:''}
        ${risk?`<p class="library-risk"><span class="risk-badge risk-${risk.level}">${risk.label}</span>${risk.minimumMargin===null?'无需中转':'最紧换乘：'+(risk.minimumMargin<0?'不足 '+(-risk.minimumMargin):'余 '+risk.minimumMargin)+' 分钟'}</p>`:''}<p class="plan-status ${s.error?'error':''}" role="status">${esc(s.status)}${s.limited?' · 已达搜索上限，仅比较已探索候选':''}</p><div class="comparison-card-actions"><button data-analyze-plan="${esc(p.id)}" ${!r||running?'disabled':''}>开始对比 →</button><button data-preview-plan="${esc(p.id)}" ${!r||running?'disabled':''}>地图 / 线路</button></div><details class="plan-more"><summary>编辑与更多操作</summary><div class="comparison-card-secondary"><button data-edit-plan="${esc(p.id)}" ${running?'disabled':''}>继续编辑</button><button data-match-plan="${esc(p.id)}" ${running?'disabled':''}>${r?'重新匹配 / 核价':'匹配这条方案'}</button><button data-copy-plan="${esc(p.id)}" ${running?'disabled':''}>复制为新方案</button></div></details></article>`;
    }).join('')||'<div class="comparison-empty"><span>01 / 02 / 03…</span><h2>给不同的走法，各留一个位置。</h2><p>将自由编辑或智能推荐的路线加入对比库，<br>匹配后开始可视化对比。</p><button id="empty-new-plan">开始制作第一个方案 →</button></div>';
    $('empty-new-plan')?.addEventListener('click',create);
    $('comparison-grid').querySelectorAll('[data-plan]').forEach(card=>{const p=plans.find(p=>p.id===card.dataset.plan);card.querySelector('.plan-title').onchange=e=>{try{persist(plans.map(x=>x.id===p.id?{...x,name:e.target.value.trim().slice(0,40)||p.name}:x));if(activeId===p.id)$('plan-name').value=plans.find(x=>x.id===p.id).name;}catch(e){toast(e.message);}};});
    const bind=(attr,fn)=>$('comparison-grid').querySelectorAll('['+attr+']').forEach(b=>b.onclick=()=>fn(plans.find(p=>p.id===b.getAttribute(attr))));
    bind('data-edit-plan',edit);bind('data-match-plan',p=>match([p.id]));bind('data-analyze-plan',p=>startAnalysis(p.id));
    bind('data-preview-plan',p=>{const r=current(p);if(r)showPreview(r,state(p).options,p.name);});
    bind('data-copy-plan',p=>{try{if(plans.length>=MAX_PLANS)throw new Error(`最多保存 ${MAX_PLANS} 个方案。`);persist([...plans,{...structuredClone(p),id:crypto.randomUUID(),name:(p.name+' · 副本').slice(0,40)}]);}catch(e){toast(e.message);}});
    bind('data-remove-plan',p=>{try{const index=plans.indexOf(p);persist(plans.filter(x=>x.id!==p.id));removed={p,index};$('undo-plan').hidden=false;if(activeId===p.id){activeId=null;$('plan-name').value=nextName();$('save-plan').textContent='加入对比库';}}catch(e){toast(e.message);}});
    $('comparison-grid').querySelectorAll('[data-candidate]').forEach(el=>el.onchange=()=>{const p=plans.find(p=>p.id===el.dataset.candidate),s=state(p);s.selected=Number(el.value);try{persist(plans.map(x=>x.id===p.id?{...x,choice:routeSelection(s.routes[s.selected])}:x));}catch(e){toast(e.message);render();}});
  }
  $('save-plan').onclick=()=>save();$('save-new-plan').onclick=()=>save(true);$('open-comparison').onclick=show;$('compare-tab').onclick=show;
  $('start-visual').onclick=()=>startAnalysis();$('library-view').onclick=()=>{view='library';render();};$('finals-view').onclick=()=>{stop(false);view='finals';render();};
  $('compare-back').onclick=hide;$('comparison-return').onclick=()=>{enter();previewing=false;document.body.classList.remove('comparison-preview');document.body.classList.add('comparison-mode');$('comparison-page').hidden=false;render();};
  $('compare-new').onclick=create;$('compare-group').onchange=render;$('compare-value').onchange=render;
  $('match-all').onclick=()=>match(plans.filter(p=>comparisonKey(p)=== $('compare-group').value).map(p=>p.id));$('stop-matching').onclick=()=>stop();
  $('undo-plan').onclick=()=>{if(!removed)return;try{const next=[...plans];next.splice(removed.index,0,removed.p);persist(next);removed=null;$('undo-plan').hidden=true;}catch(e){toast(e.message);}};
  for(const id of ['save-plan','save-new-plan','open-comparison','compare-tab'])$(id).disabled=false;
  $('plan-name').value=nextName();render();
  // Expired quotes lose ranking eligibility even when the comparison page is left open.
  setInterval(()=>{if(open&&view!=='finals'&&!running&&!previewing&&!['INPUT','SELECT'].includes(document.activeElement?.tagName)&&pricingState()!==lastPricingState)render();},60000);
  return {hide,isOpen:()=>open};
}
