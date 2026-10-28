import {journeyTimeline} from './transfers.js';
const esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const time=m=>`${String(Math.floor(m/60)%24).padStart(2,'0')}:${String(m%60).padStart(2,'0')}${m>=1440?' +'+Math.floor(m/1440)+'天':''}`;
export class Metro {
  constructor(onProgress,onStation){
    this.onProgress=onProgress;this.onStation=onStation;this.progress=0;
    this.track=document.getElementById('metro-track');this.playButton=document.getElementById('metro-play');this.resetButton=document.getElementById('metro-reset');
    this.status=document.getElementById('metro-status');this.nodes=[];this.links=[];
    this.resizeObserver=new ResizeObserver(()=>this.measureLinks());this.resizeObserver.observe(this.track);
    document.addEventListener('visibilitychange',()=>{if(document.hidden)this.pause();});
    this.playButton.onclick=()=>this.running?this.pause():this.play();
    this.resetButton.onclick=()=>{this.pause();this.progress=0;this.update();};
  }
  pause(){this.running=false;cancelAnimationFrame(this.frame);this.playButton.textContent='播放行程';}
  play(){if(!this.route)return;if(this.progress>=1)this.progress=0;this.running=true;this.playButton.textContent='暂停';this.last=performance.now();
    const step=now=>{if(!this.running)return;if(now-this.last>=32){this.progress=Math.min(1,this.progress+(now-this.last)/24000);this.last=now;this.update();}if(this.progress<1)this.frame=requestAnimationFrame(step);else this.pause();};this.frame=requestAnimationFrame(step);
  }
  setRoute(route,network){
    if(this.route?.id===route.id){this.route=route;return;}
    this.pause();this.route=route;this.progress=0;
    const {nodes,links}=journeyTimeline(route.legs);this.segments=links;
    this.track.innerHTML='<div class="metro-strip">'+nodes.map((n,i)=>{
      const l=links[i-1],minutes=l?l.arrival-l.departure:0;
      return `${i?`<div class="metro-link ${l.kind==='cross'?'cross-station':''}" data-link="${i-1}"><span>${l.kind==='cross'?'跨站换乘 · 间隔 '+minutes+' 分钟':esc(l.train)+' · '+Math.floor(minutes/60)+'h'+minutes%60+'m'}</span>${l.kind==='cross'?'<small>市内交通自行安排</small>':''}<i class="metro-train" hidden>${l.kind==='cross'?'↔':'▰'}</i></div>`:''}<button class="metro-stop" data-station="${n.station}" data-node="${i}" title="查看该站"><strong>${esc(network.stops[n.station][1])}</strong><small>${time(n.minute)}${n.wait?'<br>同站换乘 '+n.wait+' 分钟':''}</small></button>`;
    }).join('')+'</div>';
    this.track.querySelectorAll('[data-station]').forEach(b=>b.onclick=()=>this.onStation(Number(b.dataset.station)));
    this.nodes=[...this.track.querySelectorAll('.metro-stop')];this.links=[...this.track.querySelectorAll('.metro-link')].map(element=>({element,train:element.querySelector('i'),width:0}));this.activeNode=null;this.activeLeg=null;this.lastMinute=null;this.measureLinks();
    this.playButton.disabled=false;this.resetButton.disabled=false;this.update();
    if(!document.body.classList.contains('travel-embedded')&&!matchMedia('(prefers-reduced-motion: reduce)').matches)this.play();
  }
  draft(nodes){
    this.pause();this.route=null;this.onProgress(null);this.playButton.disabled=true;this.resetButton.disabled=true;
    this.track.innerHTML='<div class="metro-strip">'+nodes.map((n,i)=>`${i?'<div class="metro-link draft">待匹配班次</div>':''}<button class="metro-stop" data-draft="${i}"><strong>${esc(n.name)}</strong><small>${i===0?'出发':i===nodes.length-1?'到达':'换乘节点'}</small></button>`).join('')+'</div>';
    this.track.querySelectorAll('[data-draft]').forEach(b=>b.onclick=()=>this.onStation(nodes[Number(b.dataset.draft)].stations[0]));
    document.getElementById('metro-status').textContent='草稿连线 · 尚未验证班次';
  }
  clear(){this.pause();this.route=null;this.onProgress(null);this.playButton.disabled=true;this.resetButton.disabled=true;this.track.innerHTML='<p class="muted">选择一条候选路线，在这里播放沿途行程。</p>';document.getElementById('metro-title').textContent='每一站，都看得见。';document.getElementById('metro-status').textContent='等待选择路线';}
  measureLinks(){for(const l of this.links){l.width=Math.max(0,l.element.clientWidth-16);l.train.style.left='0';}if(this.route)this.update();}
  update(){
    if(!this.route)return;
    const r=this.route,minute=r.departure+this.progress*r.duration;
    let active=this.segments.findIndex(l=>minute<l.arrival);if(active<0)active=this.segments.length-1;
    const node=this.progress===1?this.segments.length:active;
    if(node!==this.activeNode){this.nodes.forEach((n,i)=>n.classList.toggle('current',i===node));this.activeNode=node;}
    if(active!==this.activeLeg){this.links.forEach((n,i)=>n.train.hidden=i!==active);this.activeLeg=active;}
    const l=this.segments[active],p=Math.max(0,Math.min(1,(minute-l.departure)/(l.arrival-l.departure))),link=this.links[active];
    if(link)link.train.style.transform=`translate3d(${p*link.width}px,0,0)`;
    const displayMinute=Math.floor(minute);if(displayMinute!==this.lastMinute){this.status.textContent=`示意 ${time(displayMinute)} · ${l.kind==='cross'?'跨站转移示意':'非实时位置'}`;this.lastMinute=displayMinute;}
    this.onProgress(minute);
  }
}
