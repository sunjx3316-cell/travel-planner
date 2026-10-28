const colors={G:'#7aafa7',D:'#97b4c4',K:'#c5a480'};
export const project=([lon,lat])=>[(lon-73)*22,(54-lat)*27];
const major=['北京','上海','天津','重庆','广州','深圳','成都','杭州','南京','武汉','西安','郑州','长沙','济南','青岛','福州','厦门','南昌','合肥','昆明','贵阳','南宁','海口','沈阳','大连','长春','哈尔滨','太原','石家庄','呼和浩特','兰州','西宁','银川','乌鲁木齐','拉萨'];

export class RailMap {
  constructor(canvas,onStation){
    this.canvas=canvas;this.ctx=canvas.getContext('2d');this.onStation=onStation;
    this.sceneCanvas=document.createElement('canvas');this.sceneCtx=this.sceneCanvas.getContext('2d');
    this.sceneDirty=true;this.sceneMargin=100;this.geometryCache=new Map();this.stats={fullRedraws:0,frames:0};
    this.filters={G:true,D:true,K:true};this.scale=1;this.tx=0;this.ty=0;this.route=null;this.labels=[];
    this.resizeObserver=new ResizeObserver(()=>this.resize());this.resizeObserver.observe(canvas.parentElement);
    let drag=null,moved=false;
    canvas.addEventListener('pointerdown',e=>{drag={x:e.clientX,y:e.clientY,tx:this.tx,ty:this.ty};moved=false;canvas.setPointerCapture(e.pointerId);canvas.classList.add('dragging');});
    canvas.addEventListener('pointermove',e=>{
      if(!drag)return;
      if(Math.hypot(e.clientX-drag.x,e.clientY-drag.y)>4)moved=true;
      this.tx=drag.tx+e.clientX-drag.x;this.ty=drag.ty+e.clientY-drag.y;this.viewChanged();
    });
    canvas.addEventListener('pointerup',e=>{
      if(!moved){const r=canvas.getBoundingClientRect();this.pick(e.clientX-r.left,e.clientY-r.top);}
      drag=null;canvas.classList.remove('dragging');if(moved)this.finishInteraction();
    });
    canvas.addEventListener('pointercancel',()=>{drag=null;canvas.classList.remove('dragging');this.finishInteraction();});
    canvas.addEventListener('wheel',e=>{e.preventDefault();const r=canvas.getBoundingClientRect();this.zoom(Math.exp(-e.deltaY*.001),e.clientX-r.left,e.clientY-r.top);},{passive:false});
  }
  resize(){
    const r=this.canvas.parentElement.getBoundingClientRect();this.w=r.width;this.h=r.height;
    const dpr=Math.min(devicePixelRatio||1,2);this.canvas.width=this.w*dpr;this.canvas.height=this.h*dpr;this.dpr=dpr;
    this.sceneCanvas.width=(this.w+2*this.sceneMargin)*dpr;this.sceneCanvas.height=(this.h+2*this.sceneMargin)*dpr;
    if(!this.initialized){this.reset();this.initialized=true;}
    else if(this.route)this.setRoute(this.route,{color:this.routeColor});
    else if(this.draftNodes?.length){this.fit(this.draftNodes.map(n=>this.stationPoints[n.stations[0]]));this.draw();}
    else this.reset();
  }
  setData(network,mapData,borders){
    this.network=network;this.data=mapData;this.borders=borders;
    this.geometryCache.clear();
    this.stationPoints=network.stops.map(s=>project(s.slice(2)));
    this.paths={G:new Path2D(),D:new Path2D(),K:new Path2D()};
    this.schematicPaths={G:new Path2D(),D:new Path2D(),K:new Path2D()};
    const seen=new Set(),trackEdges={G:new Set(),D:new Set(),K:new Set()};
    const schematicEdges=new Set();
    for(const t of network.trips){
      if(!t[6]||!mapData.shapes[t[6]]){
        for(let i=1;i<t[2].length;i++){
          const a=t[2][i-1],b=t[2][i],key=[Math.min(a,b),Math.max(a,b),t[7]].join(':');
          if(schematicEdges.has(key))continue;schematicEdges.add(key);
          this.schematicPaths[t[7]].moveTo(...this.stationPoints[a]);this.schematicPaths[t[7]].lineTo(...this.stationPoints[b]);
        }
        continue;
      }
      if(seen.has(t[6]))continue;
      seen.add(t[6]);const path=this.paths[t[7]];
      const points=mapData.shapes[t[6]];
      // Many trains share the same track. Stroke each segment once per layer.
      for(let i=1;i<points.length;i++){
        const a=points[i-1].join(','),b=points[i].join(','),key=a<b?a+'|'+b:b+'|'+a;
        if(trackEdges[t[7]].has(key))continue;trackEdges[t[7]].add(key);
        path.moveTo(...project(points[i-1]));path.lineTo(...project(points[i]));
      }
    }
    this.fallback=new Path2D();
    for(const [a,b] of mapData.edges){const p=this.stationPoints[a],q=this.stationPoints[b];this.fallback.moveTo(...p);this.fallback.lineTo(...q);}
    this.provincePaths=(borders?.features||[]).map(f=>{
      const path=new Path2D();const polygons=f.geometry.type==='Polygon'?[f.geometry.coordinates]:f.geometry.coordinates;
      for(const polygon of polygons)for(const ring of polygon){ring.forEach((p,i)=>{const q=project(p);i?path.lineTo(...q):path.moveTo(...q);});path.closePath();}
      return {path,properties:f.properties};
    });
    this.labels=major.map(name=>{
      let idx=network.stops.findIndex(s=>s[1]===name);
      if(idx<0)idx=network.stops.findIndex(s=>s[1].startsWith(name));
      return {name,idx};
    }).filter(s=>s.idx>=0);
    this.reset();
  }
  reset(){
    if(!this.w||!this.h)return;
    this.fit([[0,0],[1386,972]],70);this.draw();
  }
  fit(points,padding=90){
    if(!points.length)return;
    const xs=points.map(p=>p[0]),ys=points.map(p=>p[1]);
    const minX=Math.min(...xs),maxX=Math.max(...xs),minY=Math.min(...ys),maxY=Math.max(...ys);
    const px=Math.min(padding,this.w*.17),py=Math.min(55,this.h*.16);
    this.scale=Math.max(.12,Math.min(3.8,(this.w-px*2)/Math.max(140,maxX-minX),(this.h-py*2)/Math.max(180,maxY-minY)));
    this.tx=this.w/2-(minX+maxX)/2*this.scale;
    this.ty=this.h/2-(minY+maxY)/2*this.scale;
  }
  zoom(factor,x=this.w/2,y=this.h/2){
    const next=Math.max(.12,Math.min(10,this.scale*factor));factor=next/this.scale;
    this.tx=x-(x-this.tx)*factor;this.ty=y-(y-this.ty)*factor;this.scale=next;this.viewChanged();
  }
  panBy(x,y){this.tx+=x;this.ty+=y;this.viewChanged();}
  viewChanged(){clearTimeout(this.settleTimer);this.requestPaint();this.settleTimer=setTimeout(()=>this.finishInteraction(),120);}
  finishInteraction(){clearTimeout(this.settleTimer);this.draw();}
  setRoute(route,{fit=true,color='#087e79'}={}){
    const changed=this.route?.id!==route?.id||this.routeColor!==color;
    if(this.route?.id!==route?.id){this.playbackMinute=null;this.geometryCache.clear();}
    this.route=route;this.routeColor=color;
    if(route&&fit)this.fit(route.legs.flatMap(l=>this.network.trips[l.trip][2].slice(l.fromIndex,l.toIndex+1).map(i=>this.stationPoints[i])),85);
    if(changed||fit)this.draw();
  }
  setExploration(step,nodes=[]){this.exploration=step;this.explorationNodes=nodes;this.draw();}
  setPlayback(minute){this.playbackMinute=minute;this.requestPaint();}
  routeGeometry(leg){
    const key=[leg.trip,leg.fromIndex,leg.toIndex].join(':');
    if(this.geometryCache.has(key))return this.geometryCache.get(key);
    const geometry=this.routePoints(leg),path=new Path2D(),cumulative=[0];
    geometry.points.forEach((p,i)=>{if(i){path.lineTo(...p);const a=geometry.points[i-1];cumulative.push(cumulative.at(-1)+Math.hypot(p[0]-a[0],p[1]-a[1]));}else path.moveTo(...p);});
    Object.assign(geometry,{path,cumulative,total:cumulative.at(-1)});this.geometryCache.set(key,geometry);return geometry;
  }
  routePoints(leg){
    const trip=this.network.trips[leg.trip],shape=this.data.shapes[trip[6]];
    if(shape?.length){
      const from=this.network.stops[leg.from].slice(2),to=this.network.stops[leg.to].slice(2);
      const near=p=>{let at=0,best=Infinity;shape.forEach((q,i)=>{const d=(p[0]-q[0])**2+(p[1]-q[1])**2;if(d<best){best=d;at=i;}});return at;};
      const a=near(from),b=near(to);
      // Fall back to calling points when a shape does not cover both endpoints.
      if(a!==b && Math.hypot(shape[a][0]-from[0],shape[a][1]-from[1])<.2 && Math.hypot(shape[b][0]-to[0],shape[b][1]-to[1])<.2){
        const pts=a<b?shape.slice(a,b+1):shape.slice(b,a+1).reverse();
        return {points:[project(from),...pts.map(project),project(to)],schematic:false};
      }
    }
    return {points:trip[2].slice(leg.fromIndex,leg.toIndex+1).map(i=>this.stationPoints[i]),schematic:true};
  }
  pick(x,y){
    if(!this.network)return;
    if(this.cityMode){
      if(this.sceneView){const ratio=this.scale/this.sceneView.scale;x=(x-this.tx+this.sceneView.tx*ratio)/ratio;y=(y-this.ty+this.sceneView.ty*ratio)/ratio;}
      const hit=(this.cityHitboxes||[]).find(b=>x>=b.x-10&&x<=b.x+b.width&&y>=b.y-15&&y<=b.y+12);
      if(hit)this.onCity?.(hit.city);return;
    }
    let best=12,idx=-1;
    for(const i of this.network.activeStops){const p=this.stationPoints[i],d=Math.hypot(p[0]*this.scale+this.tx-x,p[1]*this.scale+this.ty-y);if(d<best){best=d;idx=i;}}
    if(idx>=0)this.onStation(idx,{x,y});
  }
  draw(){
    this.sceneDirty=true;this.requestPaint();
  }
  requestPaint(){
    if(this.paintFrame)return;
    this.paintFrame=requestAnimationFrame(()=>{this.paintFrame=0;this.paint();});
  }
  paint(){
    if(!this.w)return;
    if(this.sceneDirty){this.drawScene();this.sceneView={scale:this.scale,tx:this.tx,ty:this.ty};this.sceneDirty=false;this.stats.fullRedraws++;}
    const c=this.ctx,s=this.scale;
    const ratio=s/this.sceneView.scale,margin=this.sceneMargin;
    c.setTransform(this.dpr,0,0,this.dpr,0,0);c.fillStyle='#eaf0ed';c.fillRect(0,0,this.w,this.h);
    c.drawImage(this.sceneCanvas,this.tx-this.sceneView.tx*ratio-margin*ratio,this.ty-this.sceneView.ty*ratio-margin*ratio,(this.w+2*margin)*ratio,(this.h+2*margin)*ratio);
    if(this.route&&this.playbackMinute!=null){
      const legs=this.route.legs,minute=this.playbackMinute,leg=legs.find(l=>minute<l.arrival)||legs.at(-1),previous=legs[legs.indexOf(leg)-1],cross=previous&&previous.to!==leg.from&&minute<leg.departure;
      const {points,cumulative,total}=this.routeGeometry(leg),p=Math.max(0,Math.min(1,(minute-leg.departure)/(leg.arrival-leg.departure))),d=p*total;
      let low=1,high=points.length-1;while(low<high){const mid=(low+high)>>>1;if(cumulative[mid]<d)low=mid+1;else high=mid;}
      const i=Math.min(low,points.length-1),a=points[Math.max(0,i-1)],b=points[i],length=cumulative[i]-cumulative[Math.max(0,i-1)],f=length?(d-cumulative[i-1])/length:0;
      let point=[a[0]+(b[0]-a[0])*f,a[1]+(b[1]-a[1])*f];
      if(cross){const from=this.stationPoints[previous.to],to=this.stationPoints[leg.from],fraction=Math.max(0,Math.min(1,(minute-previous.arrival)/(leg.departure-previous.arrival)));point=[from[0]+(to[0]-from[0])*fraction,from[1]+(to[1]-from[1])*fraction];}
      c.save();c.translate(this.tx,this.ty);c.scale(s,s);
      c.beginPath();c.arc(...point,8/s,0,Math.PI*2);c.fillStyle=cross?'#b65a17':'#193c35';c.fill();c.strokeStyle='#fff';c.lineWidth=3/s;c.stroke();
      c.beginPath();c.arc(...point,14/s,0,Math.PI*2);c.strokeStyle='#193c3535';c.lineWidth=3/s;c.stroke();c.restore();
    }
    c.font='10px ui-monospace,monospace';c.fillStyle='#8b9e92';c.textBaseline='alphabetic';c.fillText('73°E',18,this.h-19);c.fillText('WGS 84',this.w-70,this.h-19);
    this.stats.frames++;
  }
  drawScene(){
    if(!this.w)return;
    const c=this.sceneCtx,s=this.scale,m=this.sceneMargin;c.setTransform(this.dpr,0,0,this.dpr,this.dpr*m,this.dpr*m);c.clearRect(-m,-m,this.w+2*m,this.h+2*m);
    c.fillStyle='#eaf0ed';c.fillRect(-m,-m,this.w+2*m,this.h+2*m);
    c.save();c.translate(this.tx,this.ty);c.scale(s,s);
    // Subtle graticule keeps the map readable without external tiles.
    c.strokeStyle='#dce5df';c.lineWidth=.6/s;
    for(let lon=75;lon<=135;lon+=5){const x=project([lon,40])[0];c.beginPath();c.moveTo(x,-150);c.lineTo(x,1300);c.stroke();}
    for(let lat=15;lat<=55;lat+=5){const y=project([100,lat])[1];c.beginPath();c.moveTo(-100,y);c.lineTo(1500,y);c.stroke();}
    this.provincePaths?.forEach(({path,properties},i)=>{
      c.fillStyle=i%3===0?'#f4f5e9':i%3===1?'#f0f2e5':'#f6f6eb';c.fill(path);
      c.strokeStyle='#d0d9c9';c.lineWidth=.8/s;c.stroke(path);
    });
    if(this.paths){
      for(const k of ['K','D','G'])if(this.filters[k]){
        c.globalAlpha=this.route?.legs.length ? .45 : .7;c.strokeStyle=colors[k];c.lineWidth=(k==='G'?1.05:.65)/Math.sqrt(s);c.stroke(this.paths[k]);
        c.globalAlpha=this.route?.legs.length ? .2 : .35;c.setLineDash([2/s,3/s]);c.lineWidth=.65/s;c.stroke(this.schematicPaths[k]);c.setLineDash([]);
      }
      c.globalAlpha=1;
      if(s>1.8){c.fillStyle='#92a89d';for(const i of this.network.activeStops){const [x,y]=this.stationPoints[i];c.beginPath();c.arc(x,y,1.4/s,0,Math.PI*2);c.fill();}}
    }
    if(this.exploration){
      c.strokeStyle='#789cb5';c.globalAlpha=.4;c.lineWidth=1.3/s;c.setLineDash([3/s,4/s]);
      for(const link of this.exploration.links||[]){const a=this.stationPoints[link.from],b=this.stationPoints[link.to];c.beginPath();c.moveTo(...a);c.lineTo(...b);c.stroke();}
      c.setLineDash([]);c.globalAlpha=1;
      for(const idx of this.exploration.stations||[]){const [x,y]=this.stationPoints[idx];c.fillStyle='#78a1b4';c.beginPath();c.arc(x,y,2/s,0,Math.PI*2);c.fill();}
    }
    if(this.draftNodes?.length){
      c.strokeStyle='#c49a63';c.lineWidth=2.5/s;c.setLineDash([7/s,6/s]);c.beginPath();
      this.draftNodes.forEach((n,i)=>{const p=this.stationPoints[n.stations[0]];i?c.lineTo(...p):c.moveTo(...p);});c.stroke();c.setLineDash([]);
    }
    if(this.route){
      for(const leg of this.route.legs){
        const {path,schematic}=this.routeGeometry(leg);
        c.lineCap='round';c.lineJoin='round';c.strokeStyle='#fff';c.lineWidth=7/s;c.stroke(path);
        c.strokeStyle=this.routeColor;c.lineWidth=3.5/s;c.setLineDash(schematic?[7/s,4/s]:[]);c.stroke(path);c.setLineDash([]);
      }
      this.route.legs.slice(1).forEach((leg,i)=>{const previous=this.route.legs[i];if(previous.to===leg.from)return;
        const a=this.stationPoints[previous.to],b=this.stationPoints[leg.from];c.beginPath();c.moveTo(...a);c.lineTo(...b);c.strokeStyle='#fff';c.lineWidth=6/s;c.stroke();c.strokeStyle='#b65a17';c.lineWidth=3/s;c.setLineDash([5/s,4/s]);c.stroke();c.setLineDash([]);
        c.font=`600 ${11/s}px "Microsoft YaHei",sans-serif`;c.strokeStyle='#fff8e9';c.lineWidth=4/s;const x=(a[0]+b[0])/2,y=(a[1]+b[1])/2+17/s;c.strokeText('跨站换乘 · 示意',x,y);c.fillStyle='#a44e10';c.fillText('跨站换乘 · 示意',x,y);
      });
    }
    const selected=new Set(this.route?.legs.flatMap(l=>[l.from,l.to])||[]);
    c.textBaseline='middle';
    for(const {name,idx} of this.labels){
      if(this.cityMode)continue;
      if(selected.has(idx))continue;
      const [x,y]=this.stationPoints[idx];
      c.fillStyle='#53685b';c.beginPath();c.arc(x,y,2.3/s,0,Math.PI*2);c.fill();
      c.font=`${name==='北京'||name==='上海'?600:400} ${11/s}px "Microsoft YaHei",sans-serif`;
      c.lineWidth=3/s;c.strokeStyle='#f3f5ec';c.strokeText(name,x+7/s,y-7/s);c.fillText(name,x+7/s,y-7/s);
    }
    for(const idx of selected){
      const [x,y]=this.stationPoints[idx],name=this.network.stops[idx][1];
      c.fillStyle='#fff';c.strokeStyle=this.routeColor;c.lineWidth=3/s;c.beginPath();c.arc(x,y,5/s,0,Math.PI*2);c.fill();c.stroke();
      c.font=`600 ${13/s}px "Microsoft YaHei",sans-serif`;c.lineWidth=5/s;c.strokeStyle='#f6f7ef';c.strokeText(name,x+11/s,y-12/s);c.fillStyle='#183d38';c.fillText(name,x+11/s,y-12/s);
    }
    for(let i=0;i<(this.explorationNodes||[]).length;i++){
      const node=this.explorationNodes[i],idx=node.stations?.[0];if(idx===undefined)continue;const [x,y]=this.stationPoints[idx];
      c.fillStyle='#bd8748';c.strokeStyle='#fff';c.lineWidth=2/s;c.beginPath();c.arc(x,y,9/s,0,Math.PI*2);c.fill();c.stroke();
      c.font=`600 ${10/s}px sans-serif`;c.fillStyle='#fff';c.textAlign='center';c.fillText(String(i+1),x,y);c.textAlign='left';
      c.font=`600 ${11/s}px sans-serif`;c.strokeStyle='#f5f5e9';c.lineWidth=4/s;c.strokeText(node.name,x+13/s,y+10/s);c.fillStyle='#8e622f';c.fillText(node.name,x+13/s,y+10/s);
    }
    if(this.cityMode){
      this.cityHitboxes=[];const used=[],dots=[];
      const important=new Set([...(this.draftNodes||[]).map(n=>n.name),this.focusCity?.name]);
      const cities=[...(this.cities||[])].sort((a,b)=>Number(important.has(b.name))-Number(important.has(a.name)));
      for(const city of cities){
        const [x,y]=this.stationPoints[city.stations[0]],sx=x*s+this.tx,sy=y*s+this.ty;
        if(sx<-m||sy<-m||sx>this.w+m||sy>this.h+m)continue;
        if(!important.has(city.name)&&dots.some(p=>Math.hypot(p.x-sx,p.y-sy)<16))continue;
        dots.push({x:sx,y:sy});
        const width=city.name.length*12+17;
        const collision=used.some(p=>Math.abs(sy-p.y)<22&&sx<p.x+p.width&&sx+width>p.x);
        c.beginPath();c.arc(x,y,(important.has(city.name)?6:3.5)/s,0,Math.PI*2);c.fillStyle=important.has(city.name)?'#b4894c':'#fafff9';c.strokeStyle='#648d7b';c.lineWidth=1.5/s;c.fill();c.stroke();
        this.cityHitboxes.push({city,x:sx,y:sy,width:collision?8:width});
        if(collision&&!important.has(city.name))continue;
        used.push({x:sx,y:sy,width});c.font=`500 ${11/s}px "Microsoft YaHei",sans-serif`;c.strokeStyle='#f3f6ec';c.lineWidth=4/s;c.strokeText(city.name,x+9/s,y-5/s);c.fillStyle='#42654f';c.fillText(city.name,x+9/s,y-5/s);
      }
    }
    c.restore();
    if(!this.network){c.font='14px sans-serif';c.fillStyle='#5f766b';c.fillText('正在铺开中国铁路地图…',this.w/2-90,this.h/2);}
  }
}
