// 旅行智规 · 前端逻辑
const $ = (sel) => document.querySelector(sel);

const state = {
  cities: [],
  llmAvailable: false,
  currentCity: null,
  currentSpots: [],
  detail: null,
  cart: [],
};

// ---------- 基础工具 ----------
async function api(path, opts = {}) {
  const resp = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...opts,
  });
  if (!resp.ok) throw new Error(`${path} -> ${resp.status}`);
  return resp.json();
}

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

function stars(r) {
  const n = Math.round(r || 0);
  return "★".repeat(n) + "☆".repeat(Math.max(0, 5 - n));
}

function flash(msg) {
  let t = $("#toast");
  if (!t) {
    t = document.createElement("div");
    t.id = "toast";
    document.body.appendChild(t);
  }
  t.textContent = msg;
  t.classList.add("show");
  clearTimeout(t._timer);
  t._timer = setTimeout(() => t.classList.remove("show"), 1600);
}

function switchTab(name) {
  document.querySelectorAll(".tabs button").forEach((b) =>
    b.classList.toggle("active", b.dataset.tab === name)
  );
  document.querySelectorAll(".tab-pane").forEach((p) =>
    p.classList.toggle("active", p.id === "tab-" + name)
  );
}

// ---------- PWA 安装与离线应用壳 ----------
// 同 Wi-Fi 的 HTTP 访问可以正常使用；要安装到桌面或启用离线壳，需要 HTTPS（localhost 例外）。
let deferredInstallPrompt = null;

function setupPwa() {
  const installButton = $("#install-app");
  window.addEventListener("beforeinstallprompt", (event) => {
    event.preventDefault();
    deferredInstallPrompt = event;
    installButton.hidden = false;
  });
  installButton.addEventListener("click", async () => {
    if (!deferredInstallPrompt) return;
    deferredInstallPrompt.prompt();
    await deferredInstallPrompt.userChoice;
    deferredInstallPrompt = null;
    installButton.hidden = true;
  });
  window.addEventListener("appinstalled", () => {
    deferredInstallPrompt = null;
    installButton.hidden = true;
    flash("旅行智规已安装到桌面");
  });

  const isLocalhost = ["localhost", "127.0.0.1", "[::1]"].includes(location.hostname);
  if ("serviceWorker" in navigator && (location.protocol === "https:" || isLocalhost)) {
    window.addEventListener("load", () => {
      navigator.serviceWorker.register("/service-worker.js").catch((error) => {
        console.warn("PWA 离线缓存注册失败", error);
      });
    });
  }
}

// ---------- 初始化 ----------
async function init() {
  try {
    const [cities, status] = await Promise.all([api("/api/cities"), api("/api/status")]);
    state.cities = cities;
    state.llmAvailable = status.llm_available;
    $("#mode-badge").textContent = state.llmAvailable
      ? "AI 模式: DeepSeek 已连接"
      : "AI 模式: 启发式(mock) · 配置 DEEPSEEK_API_KEY 启用 LLM";
    await loadCart();
    initMap();
    renderCities(null);
  } catch (e) {
    $("#mode-badge").textContent = "后端未启动,请先运行 start.ps1";
    console.error(e);
  }
}

// ---------- 中国地图(两级:全国选省 → 省级选市) ----------
let chart;
let provinceMapIndex = {};
let mapLevel = "china";        // china | province | loop | route
let currentProvince = null;
let currentLoopName = null;
let currentRoutePlan = null;
let provinceSpots = [];
let spotFilter = "全部";
let mapLayer = "all";   // all | spot | food
let lastPlans = [];

const SPOT_CAT_COLOR = { 自然: "#16a34a", 人文: "#ea580c", 综合: "#2563eb" };

const MUNICIPALITY = { "北京市": "北京", "上海市": "上海", "天津市": "天津", "重庆市": "重庆" };

async function initMap() {
  const [china, pmap] = await Promise.all([
    (await fetch("/assets/china.json")).json(),
    (await fetch("/assets/province_map.json")).json(),
  ]);
  echarts.registerMap("china", china);
  provinceMapIndex = pmap;
  chart = echarts.init($("#map"));
  renderChinaMap();
  chart.on("click", onMapClick);
  window.addEventListener("resize", () => chart && chart.resize());
  $("#map-back").addEventListener("click", renderChinaMap);
}

function baseGeoOption() {
  return {
    roam: true,
    itemStyle: { areaColor: "#cfe8e1", borderColor: "#0e7c66", borderWidth: 0.8 },
    emphasis: {
      label: { show: true, color: "#0a5c4c" },
      itemStyle: { areaColor: "#8fd3c2" },
    },
    label: { show: false, fontSize: 9 },
  };
}

function renderChinaMap() {
  mapLevel = "china";
  currentProvince = null;
  $("#map-back").style.display = "none";
  $("#map-filters").style.display = "none";
  $("#map-layers").style.display = "none";
  $("#map-hint").textContent = "点击省份 → 进入该省地图";
  chart.setOption({
    tooltip: {
      trigger: "item",
      formatter: (p) => `${p.name}<br/><span style="font-size:11px">点击进入该省</span>`,
    },
    geo: { map: "china", ...baseGeoOption() },
    series: [{ type: "map", geoIndex: 0, silent: true, data: [] }],
  }, true);
}

async function renderProvinceMap(provinceName) {
  const adcode = provinceMapIndex[provinceName];
  if (!adcode) {
    flash("该省份地图暂不可用");
    return;
  }
  let geo;
  try {
    geo = await (await fetch(`/assets/provinces/${adcode}.json`)).json();
  } catch (e) {
    flash("省份地图加载失败");
    return;
  }
  echarts.registerMap("province", geo);
  mapLevel = "province";
  currentProvince = provinceName;
  $("#map-back").style.display = "block";
  $("#map-filters").style.display = "flex";
  $("#map-layers").style.display = "flex";
  $("#map-hint").textContent = `${provinceName} · 点击景点查看口碑卡`;
  try {
    provinceSpots = await api(`/api/province/${encodeURIComponent(provinceName)}/spots`);
  } catch (e) {
    provinceSpots = [];
  }
  renderProvinceSpots();
}

function setMapLayer(layer) {
  mapLayer = layer;
  document.querySelectorAll(".layer-chip").forEach((b) =>
    b.classList.toggle("active", b.dataset.layer === layer));
  if (mapLevel === "province") renderProvinceSpots();
}

function renderProvinceSpots() {
  // 美食街已升级为正式景点(标签含"美食街");图层按标签过滤
  const streets = provinceSpots.filter((s) => (s.tags || []).includes("美食街"));
  const scenic = provinceSpots.filter((s) => !(s.tags || []).includes("美食街"));
  let spotList, foodList;
  if (mapLayer === "food") { spotList = []; foodList = streets; }
  else if (mapLayer === "spot") { spotList = scenic; foodList = []; }
  else { spotList = scenic; foodList = streets; }
  spotList = spotList.filter((s) => spotFilter === "全部" || s.category === spotFilter);
  const series = [{ type: "map", geoIndex: 0, silent: true, data: [] }];
  if (spotList.length) {
    series.push({
      type: "scatter", coordinateSystem: "geo",
      data: spotList.map((s) => ({ name: s.name, value: [s.lng, s.lat, s.id], category: s.category, cityName: s.city_name })),
      symbol: "circle", symbolSize: 9,
      itemStyle: { color: (p) => SPOT_CAT_COLOR[p.data.category] || "#6b7280", borderColor: "#fff", borderWidth: 1 },
      label: { show: spotList.length <= 14, position: "right", fontSize: 9, color: "#0a5c4c", formatter: (p) => p.name },
      labelLayout: { hideOverlap: true },
      emphasis: { itemStyle: { color: "#dc2626" } },
      zlevel: 2,
    });
  }
  if (foodList.length) {
    series.push({
      type: "scatter", coordinateSystem: "geo",
      data: foodList.map((f) => ({ name: f.name, value: [f.lng, f.lat, f.id], cityName: f.city_name, isStreet: true })),
      symbol: "pin", symbolSize: 22,
      itemStyle: { color: "#ea580c", borderColor: "#fff", borderWidth: 1 },
      label: { show: true, position: "top", fontSize: 9, color: "#9a3412", fontWeight: "bold", formatter: (p) => p.name },
      labelLayout: { hideOverlap: true },
      emphasis: { itemStyle: { color: "#dc2626" } },
      zlevel: 3,
    });
  }
  chart.setOption({
    tooltip: {
      trigger: "item",
      formatter: (p) =>
        p.seriesType === "scatter"
          ? p.data.isStreet
            ? `<b>🏮 ${p.name}</b><br/>${esc(p.data.cityName || "")} · 美食街<br/><span style="font-size:11px">点击查看口碑</span>`
            : `<b>${p.name}</b><br/>${esc(p.data.category || "")} · ${esc(p.data.cityName || "")}<br/><span style="font-size:11px">点击查看口碑卡</span>`
          : `${p.name}`,
    },
    geo: { map: "province", ...baseGeoOption() },
    series,
  }, true);
  $("#map-hint").textContent = `${currentProvince} · 🏞景区 ${scenic.length} · 🏮美食街 ${streets.length} · 点击查看详情`;
}

function setSpotFilter(cat) {
  spotFilter = cat;
  document.querySelectorAll(".filter-chip").forEach((b) =>
    b.classList.toggle("active", b.dataset.cat === cat));
  if (mapLevel === "province") renderProvinceSpots();
}

function matchCityByPolygon(polyName, cities) {
  const n = (polyName || "").replace(/市$|地区$|自治州$|盟$/, "");
  let c = cities.find((x) => x.name === n);
  if (c) return c;
  // 前缀匹配:湘西土家族苗族自治州 → 湘西;阿坝藏族羌族自治州 → 阿坝
  c = cities.find((x) => (polyName || "").startsWith(x.name));
  if (c) return c;
  // 反向:城市名以多边形名为前缀(如多边形"凉山"、城市"凉山彝族自治州"场景罕见,兜底)
  return null;
}

// 平替地图对比:主景点 + 各平替 标在地图上
function drawAlternativesMap() {
  const d = state.detail;
  if (!d || !d.alternatives || !d.alternatives.length) return;
  const pts = [];
  if (d.lng != null && d.lat != null) pts.push({ name: `${d.name} (当前)`, lng: d.lng, lat: d.lat, role: "main" });
  d.alternatives.forEach((a) => {
    if (a.alt_lng != null && a.alt_lat != null) pts.push({ name: a.alt_name, lng: a.alt_lng, lat: a.alt_lat, role: "alt" });
  });
  if (!pts.length) { flash("缺少坐标,无法地图对比"); return; }
  const fit = fitGeoFrom(pts);
  mapLevel = "alt";
  currentRoutePlan = null;
  $("#map-back").style.display = "block";
  $("#map-filters").style.display = "none";
  chart.setOption({
    tooltip: {
      trigger: "item",
      formatter: (p) =>
        p.seriesType === "scatter"
          ? `<b>${p.name}</b><br/><span style="font-size:11px">点击查看详情</span>`
          : p.name,
    },
    geo: { map: "china", ...baseGeoOption(), center: fit.center, zoom: fit.zoom },
    series: [
      { type: "map", geoIndex: 0, silent: true, data: [] },
      {
        type: "scatter",
        coordinateSystem: "geo",
        data: pts.map((p) => ({ name: p.name, value: [p.lng, p.lat, p.role === "main" ? "main" : "alt"], role: p.role })),
        symbolSize: (value, params) => (params.data.role === "main" ? 14 : 10),
        itemStyle: {
          color: (p) => (p.data.role === "main" ? "#2563eb" : "#ea580c"),
          borderColor: "#fff", borderWidth: 1,
        },
        label: { show: true, position: "right", fontSize: 10, color: "#0a5c4c", formatter: (p) => p.name },
        labelLayout: { hideOverlap: true },
        emphasis: { itemStyle: { color: "#dc2626" } },
        zlevel: 2,
      },
    ],
  }, true);
  $("#map-hint").textContent = `🔵 当前景点 · 🟠 平替 · 共 ${pts.length} 处`;
}

// 城市美食地图已废弃:美食街已升级为正式景点,直接上图、可加购物车、有口碑卡

function onMapClick(p) {
  if (p.seriesType === "scatter" && p.data && p.data.value && typeof p.data.value[2] === "number") {
    openSpot(p.data.value[2]);   // 景点与美食街(已升级为景点)都可打开口碑卡
    return;
  }
  if (mapLevel === "china") {
    if (p.name) {
      renderCities(p.name);     // 城市 tab 同步切到该省(内部会把地图切到省)
      switchTab("cities");
    }
    return;
  }
  if (mapLevel === "loop" || mapLevel === "route" || mapLevel === "alt" || mapLevel === "food") {
    return; // 环线/路线/平替/美食视图:多边形点击不处理
  }
  // 省级地图:多边形点击按城市名匹配(打开该市景区列表)
  const direct = MUNICIPALITY[currentProvince];
  if (direct) {
    const c = state.cities.find((x) => x.name === direct);
    if (c) openCity(c.id);
    return;
  }
  const c = matchCityByPolygon(p.name, state.cities);
  if (c) {
    openCity(c.id);
  } else {
    flash("该市暂未收录景点,后续持续扩充中");
  }
}

// ---------- 环线地图视图 + 路线地图渲染 ----------
function fitGeoFrom(spots) {
  const lngs = spots.map((s) => s.lng).filter((x) => x != null);
  const lats = spots.map((s) => s.lat).filter((x) => x != null);
  if (!lngs.length) return { center: [105, 35], zoom: 4 };
  const minLng = Math.min(...lngs), maxLng = Math.max(...lngs);
  const minLat = Math.min(...lats), maxLat = Math.max(...lats);
  const span = Math.max(maxLng - minLng, maxLat - minLat, 0.5);
  return {
    center: [(minLng + maxLng) / 2, (minLat + maxLat) / 2],
    zoom: Math.min(35, Math.max(1.5, Math.round(45 / span))),
  };
}

async function renderLoopMap(loopName) {
  const loops = state.loopsCache || (state.loopsCache = await api("/api/loops"));
  const lp = loops.find((x) => x.name === loopName);
  if (!lp) return;
  const pts = lp.spots.filter((s) => s.lng != null && s.lat != null);
  mapLevel = "loop";
  currentLoopName = loopName;
  $("#map-back").style.display = "block";
  $("#map-filters").style.display = "none";
  const fit = fitGeoFrom(pts);
  chart.setOption({
    tooltip: {
      trigger: "item",
      formatter: (p) =>
        p.seriesType === "scatter"
          ? `<b>${p.name}</b><br/><span style="font-size:11px">点击查看口碑卡</span>`
          : p.name,
    },
    geo: { map: "china", ...baseGeoOption(), center: fit.center, zoom: fit.zoom },
    series: [
      { type: "map", geoIndex: 0, silent: true, data: [] },
      {
        type: "scatter",
        coordinateSystem: "geo",
        data: pts.map((s) => ({ name: s.name, value: [s.lng, s.lat, s.id], category: s.category })),
        symbolSize: 10,
        itemStyle: { color: (p) => SPOT_CAT_COLOR[p.data.category] || "#f59e0b", borderColor: "#fff", borderWidth: 1 },
        label: { show: pts.length <= 20, position: "right", fontSize: 9, color: "#0a5c4c", formatter: (p) => p.name },
        labelLayout: { hideOverlap: true },   // 标签重叠自动隐藏
        emphasis: { itemStyle: { color: "#dc2626" } },
        zlevel: 2,
      },
    ],
  }, true);
  $("#map-hint").textContent = `${lp.name} · ${lp.spots.length} 个点位 · 点景点看口碑卡`;
}

// 路线地图:折线 + 起终点高亮(闭环时起点=终点只显示一次)
function drawRouteOnMap(plan) {
  if (!plan || !plan.route || !plan.route.length) return;
  const pts = [];
  const first = plan.route[0];
  if (first.from_lng != null) pts.push({ name: first.from, lng: first.from_lng, lat: first.from_lat });
  plan.route.forEach((l) => pts.push({ name: l.to, lng: l.to_lng, lat: l.to_lat }));
  // 闭环:最后一段回到起点,合并起点/终点为同一点
  let closed = false;
  if (pts.length > 1) {
    const a = pts[0], b = pts[pts.length - 1];
    if (Math.abs(a.lng - b.lng) < 1e-6 && Math.abs(a.lat - b.lat) < 1e-6) {
      pts.pop();
      closed = true;
    }
  }
  const coords = pts.map((p) => [p.lng, p.lat]);
  if (closed) coords.push([pts[0].lng, pts[0].lat]); // 折线闭合
  const fit = fitGeoFrom(pts);
  mapLevel = "route";
  currentRoutePlan = plan;
  $("#map-back").style.display = "block";
  $("#map-filters").style.display = "none";
  chart.setOption({
    tooltip: {
      trigger: "item",
      formatter: (p) =>
        p.seriesType === "lines"
          ? `${p.data.fromName} → ${p.data.toName}`
          : `${p.name}<br/><span style="font-size:11px">点击查看口碑卡</span>`,
    },
    geo: { map: "china", ...baseGeoOption(), center: fit.center, zoom: fit.zoom },
    series: [
      { type: "map", geoIndex: 0, silent: true, data: [] },
      {
        type: "lines",
        coordinateSystem: "geo",
        polyline: true,
        data: [{ coords, lineStyle: { width: 3, color: "#0e7c66" } }],
        effect: { show: true, period: 6, trailLength: 0.35, symbol: "arrow", symbolSize: 8, color: "#f59e0b" },
        zlevel: 3,
      },
      {
        type: "scatter",
        coordinateSystem: "geo",
        data: pts.map((p, i) => ({
          name: p.name,
          value: [p.lng, p.lat, i === 0 ? "start" : i === pts.length - 1 ? "end" : "mid"],
        })),
        symbolSize: 12,
        itemStyle: {
          color: (p) =>
            p.data.value[2] === "start" ? "#16a34a" : p.data.value[2] === "end" ? "#dc2626" : "#f59e0b",
          borderColor: "#fff", borderWidth: 1,
        },
        label: { show: true, position: "top", fontSize: 9, color: "#0a5c4c", formatter: (p) => p.name },
        labelLayout: { hideOverlap: true },   // 标签重叠自动隐藏
        emphasis: { itemStyle: { color: "#dc2626" } },
        zlevel: 4,
      },
    ],
  }, true);
  const totalKm = plan.route.reduce((a, l) => a + l.km, 0);
  $("#map-hint").textContent = closed
    ? `${plan.name} · 🔁 闭环环线 起点=终点🟢 · 全长 ${totalKm}km`
    : `${plan.name} · 起点🟢 终点🔴 · 全长 ${totalKm}km`;
}

// ---------- 城市 ----------
function cityCard(c) {
  return `<div class="city-card" onclick="focusCity(${c.id})">
    <h4>${esc(c.name)}</h4>
    <div class="meta">${esc(c.province)} · ${c.spot_count} 个景区</div>
  </div>`;
}

function renderCities(province) {
  const pane = $("#tab-cities");
  if (!province) {
    // 全国省市总览:地图同步回全国
    if (mapLevel !== "china") renderChinaMap();
    // 城市已扩充到 100+,按省浏览 + 城市之旅规划工作台
    const provs = {};
    state.cities.forEach((c) => {
      provs[c.province] = (provs[c.province] || 0) + 1;
    });
    const list = Object.entries(provs).sort((a, b) => a[0].localeCompare(b[0], "zh"));
    pane.innerHTML = `
      ${cityPlanWorkspaceHtml()}
      <h3 style="margin:12px 0 10px">全国省市 · ${list.length} 个</h3>
      <div class="city-grid">${list.map(([p, n]) => `
        <div class="city-card" onclick="renderCities('${esc(p)}')">
          <h4>${esc(p)}</h4>
          <div class="meta">${n} 个城市</div>
        </div>`).join("")}</div>`;
    return;
  }
  const cities = state.cities.filter((c) => c.province === province);
  pane.innerHTML = `
    <div class="back-row"><button class="btn sm" onclick="renderCities(null)">← 全国省市</button></div>
    <h3 style="margin-bottom:10px">${esc(province)}</h3>
    ${cities.length
      ? `<div class="city-grid">${cities.map(cityCard).join("")}</div>`
      : `<div class="empty-hint">该省份暂无收录城市<br/>
         <span style="font-size:11px">正式版接入高德 POI 数据后自动扩充</span></div>`}`;
  // 省级视图:地图同步切到该省(与城市 tab 保持一致)
  if (mapLevel !== "province" || currentProvince !== province) {
    renderProvinceMap(province);
  }
}

async function openCity(cityId) {
  const city = state.cities.find((c) => c.id === cityId);
  state.currentCity = city;
  state.currentSpots = await api(`/api/cities/${cityId}/spots`);
  state.currentFoods = { dishes: [], streets: [] };
  try {
    state.currentFoods = await api(`/api/cities/${cityId}/foods`);
  } catch (e) { /* 无美食数据 */ }
  renderSpots();
  switchTab("spots");
}

function priceText(p) {
  if (p == null) return "";
  return p > 0 ? `门票¥${p}` : "免费";
}

// 商圈徽标:类型(商业/娱乐/混合) + 档次(高端/中高端/中低端)
function commercialText(c) {
  if (!c || !c.type) return "";
  const t = c.type === "商业" ? "商业为主" : c.type === "娱乐" ? "娱乐为主" : "商娱混合";
  return t + (c.tier ? ` · ${c.tier}` : "");
}

function commercialBadge(c) {
  const txt = commercialText(c);
  return txt ? `<span class="commercial-tag">🛍 ${esc(txt)}</span>` : "";
}

function spotRowHtml(s) {
  return `
    <div class="spot-row">
      <div class="info">
        <div class="name">${esc(s.name)}
          ${s.grade ? `<span class="grade-tag">${esc(s.grade)}</span>` : ""}
          ${commercialBadge(s.commercial)}
          ${s.price != null ? `<span class="price-tag">${priceText(s.price)}</span>` : ""}
          <span class="rating">${stars(s.poi_rating)} ${s.poi_rating || ""}</span></div>
        <div class="tags">${(s.tags || []).join(" · ")}</div>
      </div>
      <span class="badge-sm ${s.has_summary ? "" : "pending"}">${s.has_summary ? "已AI分析" : "待分析"}</span>
      <div class="row-btns">
        <button class="btn sm primary" onclick="openSpot(${s.id})">详情</button>
        <button class="btn sm accent" onclick="addToCart(${s.id})">+想去</button>
      </div>
    </div>`;
}

function renderSpots() {
  const pane = $("#tab-spots");
  if (!state.currentCity) {
    pane.innerHTML = `<div class="empty-hint">先从地图上选择一个城市</div>`;
    return;
  }
  const list = state.currentSpots;
  const museums = list.filter((s) => (s.tags || []).includes("博物馆"));
  const commercial = list.filter((s) => (s.tags || []).includes("商圈"));
  const parks = list.filter((s) => (s.tags || []).includes("公园"));
  const streets = list.filter((s) => (s.tags || []).includes("美食街"));
  const scenic = list.filter((s) => !(s.tags || []).some((t) => ["博物馆", "商圈", "公园", "美食街"].includes(t)));
  const foods = state.currentFoods || { dishes: [], streets: [] };
  const foodHtml = (foods.dishes && foods.dishes.length) ? `
    <div class="panel-box food"><h4>🍜 必吃小吃 · ${esc(state.currentCity.name)}</h4>
      ${foods.dishes.map((d) => `
        <div class="food-item"><b>${esc(d.name)}</b>
          <span class="price-tag">¥${d.price_low || ""}-${d.price_high || ""}</span>
          <span class="food-where">${esc(d.where)}</span>
          <br/><span class="food-note">${esc(d.note)}</span></div>`).join("")}
    </div>` : "";
  pane.innerHTML = `
    <div class="back-row"><button class="btn sm" onclick="renderCities(null); switchTab('cities')">← 返回城市</button></div>
    <h3 style="margin-bottom:10px">${esc(state.currentCity.name)} · ${list.length} 个项目</h3>
    ${foodHtml}
    ${museums.length ? `<div class="food-title" style="margin:10px 0 6px">🏛 博物馆</div>${museums.map(spotRowHtml).join("")}` : ""}
    ${commercial.length ? `<div class="food-title" style="margin:10px 0 6px">🛍 商圈/商业街</div>${commercial.map(spotRowHtml).join("")}` : ""}
    ${parks.length ? `<div class="food-title" style="margin:10px 0 6px">🌳 公园</div>${parks.map(spotRowHtml).join("")}` : ""}
    ${streets.length ? `<div class="food-title" style="margin:10px 0 6px">🏮 美食街</div>${streets.map(spotRowHtml).join("")}` : ""}
    ${scenic.length ? `<div class="food-title" style="margin:10px 0 6px">🏞 景区</div>${scenic.map(spotRowHtml).join("")}` : ""}`;
}

// ---------- 景区详情与 AI 口碑卡 ----------
async function openSpot(spotId) {
  state.detail = await api(`/api/spots/${spotId}`);
  renderDetail();
  switchTab("spots");
}

function trustClass(v) {
  return v >= 70 ? "high" : v >= 45 ? "mid" : "low";
}

// 本地采集图片(相对 data/ 的 images/... 路径)转 /media 访问;完整 URL 原样
function mediaUrl(u) {
  if (!u) return u;
  if (u.startsWith("images/")) return "/media/" + u;
  return u;
}

function summaryHtml(s) {
  return `
    <div class="panel-box"><h4>✨ AI 攻略整合(亮点)</h4>
      <ul>${(s.highlights || []).map((h) => `<li>${esc(h)}</li>`).join("") || "<li>暂无</li>"}</ul></div>
    <div class="panel-box"><h4>🎯 典型玩法</h4>
      <ul>${(s.play_style || []).map((h) => `<li>${esc(h)}</li>`).join("") || "<li>暂无</li>"}</ul></div>
    ${s.cost_range ? `<div class="panel-box"><h4>💰 花费参考</h4><div style="font-size:13px">${esc(s.cost_range)}</div></div>` : ""}
    ${(s.ad_ratio || 0) > 0 ? `
      <div class="panel-box"><h4>📢 暗广检测 · 嫌疑笔记占比 ${Math.round(s.ad_ratio * 100)}%</h4>
        <ul>${(s.ad_signals || []).map((x) => `<li>${esc(x)}</li>`).join("") || "<li>暂无信号</li>"}</ul></div>` : ""}
    <div class="panel-box avoid"><h4>⚠️ 真实下限 · 避雷共识</h4>
      ${(s.consensus_issues || []).map((c) =>
        `<div class="avoid-item"><span class="consensus-tag">多账号共识</span>${esc(c)}</div>`).join("") || ""}
      ${(s.avoid_points || []).filter((p) => !p.consensus).map((p) => `
        <div class="avoid-item">${esc(p.point)}
          <div class="ev">来源: ${esc(p.evidence)} · 具体性 ${p.specificity}/5 · 可验证性 ${p.verifiable}/5</div>
        </div>`).join("") || `<div style="font-size:12px;color:var(--muted)">暂无有效负面信息</div>`}
    </div>
    <div class="panel-box"><h4>🛡 口碑信任度</h4>
      <div class="trust-row">
        <div class="trust-badge ${trustClass(s.trust_score || 0)}">${s.trust_score ?? "-"}</div>
        <div>
          <div class="source-line">${esc(s.source || "")} · ${s.note_count || 0} 篇笔记</div>
          <div class="source-line">综合暗广占比、差评具体性与共识度得出</div>
        </div>
      </div>
    </div>`;
}

function sampleNotesHtml(notes) {
  return `<div class="sample-notes"><details>
    <summary>查看原始笔记(${notes.length} 篇 · 当前为示例数据,正式数据来自小红书)</summary>
    ${notes.map((n) => `
      <div class="note-item">
        <span class="t">${esc(n.title)}</span>
        <span class="note-type ${esc(n.note_type || "guide")}">${esc(n.note_type || "guide")}</span>
        <div class="c">${esc((n.content || "").slice(0, 120))}${(n.content || "").length > 120 ? "..." : ""}</div>
      </div>`).join("")}
  </details></div>`;
}

function altHtml(d) {
  if (!d.alternatives || !d.alternatives.length) return "";
  return `
    <div class="panel-box alt"><h4>💰 平替推荐 · 更省钱的选择
      <button class="btn sm" style="float:right" onclick="drawAlternativesMap()">🗺 地图对比</button></h4>
      ${d.alternatives.map((a) => `
        <div class="alt-item">
          <div class="alt-head">
            <b>${esc(a.alt_name)}</b>
            <span class="days-tag">${esc(a.alt_city)}${a.alt_grade ? " · " + esc(a.alt_grade) : ""}</span>
            <span class="price-tag">原门票: ${esc(a.price_note)}</span>
          </div>
          <div class="alt-note">${esc(a.note)}</div>
          <div class="alt-downs"><b>缺点:</b> ${(a.downsides || []).map((x) => esc(x)).join("；")}</div>
          <div style="display:flex;gap:8px;margin-top:6px">
            <button class="btn sm" onclick="openSpot(${a.alt_id})">查看</button>
            <button class="btn sm accent" onclick="addToCart(${a.alt_id})">＋ 改选平替</button>
          </div>
        </div>`).join("")}
    </div>`;
}

function renderDetail() {
  const d = state.detail;
  const pane = $("#tab-spots");
  const imgHtml = (d.images && d.images.length)
    ? `<img class="spot-img" src="${esc(mediaUrl(d.images[0]))}" alt="${esc(d.name)}">`
    : `<div class="img-placeholder"><div class="emoji">🏞️</div><div>${esc(d.name)}</div>
       <div class="note">图片将在小红书采集后展示</div></div>`;
  pane.innerHTML = `
    <div class="detail-card">
      <div class="back-row"><button class="btn sm" onclick="renderSpots()">← 返回景区列表</button></div>
      <div class="detail-head">
        <div>
          <h2>${esc(d.name)}
            ${d.grade ? `<span class="grade-tag">${esc(d.grade)}</span>` : ""}
            ${commercialBadge(d.commercial)}
            <span class="rating">${stars(d.poi_rating)} ${d.poi_rating || ""}</span></h2>
          <div class="detail-meta">${esc(d.city_name)} · ${esc(d.address || "")} · ${(d.tags || []).join(" / ")}
            ${d.price != null ? ` · <b>${priceText(d.price)}</b>` : ""}</div>
        </div>
      </div>
      ${imgHtml}
      ${d.summary ? summaryHtml(d.summary) : `
        <div class="panel-box"><h4>🤖 暂无 AI 口碑分析</h4>
          <div style="font-size:12px;color:var(--muted);margin-bottom:8px">
            当前为示例数据阶段,可运行 AI 加工管线(攻略整合 / 暗广过滤 / 避雷共识)生成口碑卡。</div>
          <button class="btn primary sm" id="analyze-btn" onclick="reAnalyze(${d.id})">开始 AI 分析</button>
        </div>`}
      ${altHtml(d)}
      ${d.notes && d.notes.length ? sampleNotesHtml(d.notes) : ""}
      <div style="margin-top:10px">
        <button class="btn primary" onclick="addToCart(${d.id})">+ 加入想去清单</button>
        ${d.summary ? `<button class="btn" style="margin-left:8px" onclick="reAnalyze(${d.id})">↻ 重新 AI 分析</button>` : ""}
      </div>
    </div>`;
}

async function reAnalyze(spotId) {
  const btn = $("#analyze-btn");
  if (btn) {
    btn.disabled = true;
    btn.textContent = "AI 分析中...";
  }
  try {
    const card = await api(`/api/spots/${spotId}/summarize`, { method: "POST" });
    state.detail.summary = card;
    state.detail.notes = state.detail.notes || [];
    renderDetail();
    // 同步景区列表的已分析标记
    const sp = state.currentSpots.find((x) => x.id === spotId);
    if (sp) sp.has_summary = true;
  } catch (e) {
    flash("分析失败: " + e.message);
    if (btn) { btn.disabled = false; btn.textContent = "开始 AI 分析"; }
  }
}

// ---------- 环线 ----------
async function renderLoops() {
  const pane = $("#tab-loops");
  try {
    const loops = await api("/api/loops");
    state.loopsCache = loops;
    if (!loops.length) {
      pane.innerHTML = `<div class="empty-hint">暂无环线数据</div>`;
      return;
    }
    pane.innerHTML = `
      <h3 style="margin-bottom:6px">精选自驾环线 (${loops.length})</h3>
      <div class="loop-note">🗺 点「地图查看」→ 切到该区域地图 → 整条加入清单 → 清单自驾模式生成路线并画在地图上</div>
      ${loops.map((lp) => `
        <div class="plan-card">
          <h4>🏔 ${esc(lp.name)} <span class="days-tag">${esc(lp.days)}</span></h4>
          <div class="summary">${esc(lp.desc)}</div>
          <div class="loop-spots">${lp.spots.map((s) => `
            <span class="chip">${esc(s.city_name)} · ${esc(s.name)}${s.grade ? ` <b>${esc(s.grade)}</b>` : ""}</span>`).join("")}
          </div>
          <div style="display:flex;gap:8px;flex-wrap:wrap">
            <button class="btn primary sm" onclick="renderLoopMap('${esc(lp.name)}')">🗺 地图查看</button>
            <button class="btn sm" onclick="addLoopToCart('${esc(lp.name)}')">＋ 整条加入清单 (${lp.spots.length})</button>
          </div>
        </div>`).join("")}`;
  } catch (e) {
    pane.innerHTML = `<div class="empty-hint">环线加载失败: ${esc(e.message)}</div>`;
  }
}

async function addLoopToCart(loopName) {
  try {
    const loops = await api("/api/loops");
    const lp = loops.find((x) => x.name === loopName);
    if (!lp) return;
    for (const s of lp.spots) {
      await api(`/api/cart/${s.id}`, { method: "POST" });
    }
    await loadCart();
    flash(`已加入 ${lp.spots.length} 个点位 ✓ 切到清单→自驾模式生成路线`);
  } catch (e) {
    flash("加入失败: " + e.message);
  }
}

// ---------- 购物车 ----------
async function loadCart() {
  state.cart = await api("/api/cart");
  $("#cart-count").textContent = state.cart.length;
}

async function addToCart(spotId) {
  await api(`/api/cart/${spotId}`, { method: "POST" });
  await loadCart();
  flash("已加入清单 ✓");
}

async function clearCart() {
  await api("/api/cart", { method: "DELETE" });
  await loadCart();
  renderCart();
  flash("清单已清空");
}

async function removeFromCart(spotId) {
  await api(`/api/cart/${spotId}`, { method: "DELETE" });
  await loadCart();
  renderCart();
}

// 清单生成模式:city=单城市 / roadtrip=自驾多城
let planMode = "city";

function setPlanMode(m) {
  planMode = m;
  renderCart();
}

function renderCart() {
  const pane = $("#tab-cart");
  if (!state.cart.length) {
    pane.innerHTML = `<div class="empty-hint">清单还是空的 🗺️<br/>去地图上点几个想去的地方吧</div>`;
    return;
  }
  const daysSel = `<label>天数</label><select id="days" onchange="syncPlanDays('cart')">${
    [1, 2, 3, 4, 5, 6, 7, 8, 9, 10].map((d) => `<option value="${d}" ${d === +($("#plan-days") ? $("#plan-days").value : 3) ? "selected" : ""}>${d} 天</option>`).join("")}</select>`;
  const styleSel = `<label>风格</label><select id="style">
    <option>轻松</option><option>紧凑</option><option>亲子</option></select>`;
  const modeToggle = `
    <div class="mode-toggle">
      <button class="btn sm ${planMode === "city" ? "primary" : ""}" onclick="setPlanMode('city')">🏙 城市模式</button>
      <button class="btn sm ${planMode === "roadtrip" ? "primary" : ""}" onclick="setPlanMode('roadtrip')">🚗 自驾模式</button>
    </div>`;

  if (planMode === "city") {
    const byCity = {};
    state.cart.forEach((it) => {
      (byCity[it.city_name] = byCity[it.city_name] || []).push(it);
    });
    pane.innerHTML = `
      <h3 style="margin-bottom:8px">想去清单 (${state.cart.length})
        <button class="btn sm danger" style="float:right" onclick="clearCart()">清空</button>
      </h3>
      ${modeToggle}
      <div class="cart-actions">${daysSel}${styleSel}
        <div class="city-group-title" style="margin-top:6px">🏙 城市模式:先选城市 → 每城选玩几天 → 加想玩的 → 生成(含时段规划与跨城交通)</div>
      </div>
      ${Object.entries(byCity).map(([city, items]) => `
        <div class="city-group-title">🏙 ${esc(city)} (${items.length})
          <span style="float:right;font-weight:400;font-size:12px">玩 <select id="city-days-${esc(city)}" style="padding:2px 6px;border:1px solid var(--border);border-radius:6px">
            ${[1, 2, 3].map((d) => `<option value="${d}" ${d === Math.min(3, Math.max(1, Math.ceil(items.length / 3))) ? "selected" : ""}>${d}天</option>`).join("")}
          </select></span>
        </div>
        ${items.map((it) => `
          <div class="cart-row">
            <div class="info"><div class="name">${esc(it.name)}</div></div>
            <button class="btn sm danger" onclick="removeFromCart(${it.spot_id})">移除</button>
          </div>`).join("")}
      `).join("")}
      <button class="btn primary" style="margin-top:10px" onclick="generateCityTour()">
        🏙 生成城市之旅(${Object.keys(byCity).length} 城)</button>`;
    return;
  }
  if (planMode === "roadtrip") {
    const byCity = {};
    state.cart.forEach((it) => {
      (byCity[it.city_name] = byCity[it.city_name] || []).push(it);
    });
    pane.innerHTML = `
      <h3 style="margin-bottom:8px">想去清单 (${state.cart.length})
        <button class="btn sm danger" style="float:right" onclick="clearCart()">清空</button>
      </h3>
      ${modeToggle}
      <div class="cart-actions">${daysSel}${styleSel}
        <label style="display:block;margin-top:6px"><input type="checkbox" id="close-loop" checked> 🔁 闭合环线(终点返回起点)</label>
        <label style="display:block;margin-top:6px">🚩 出发地
          <input id="start-city" list="city-list" placeholder="如:兰州" style="width:120px;padding:5px 8px;border:1px solid var(--border);border-radius:8px">
          <datalist id="city-list">${state.cities.map((c) => `<option value="${esc(c.name)}">`).join("")}</datalist>
        </label>
      </div>
      <div class="city-group-title">🚗 自驾模式:将全部地点串联成一条路线(跨城市)</div>
      ${Object.entries(byCity).map(([city, items]) => `
        <div class="city-group-title">🏙 ${esc(city)} (${items.length})</div>
        ${items.map((it) => `
          <div class="cart-row">
            <div class="info"><div class="name">${esc(it.name)}</div></div>
            <button class="btn sm danger" onclick="removeFromCart(${it.spot_id})">移除</button>
          </div>`).join("")}
      `).join("")}
      <button class="btn primary" style="margin-top:10px" onclick="generateRoadtrip()">
        🚗 生成自驾路线</button>`;
    return;
  }
}

async function generateCityTour() {
  const ids = state.cart.map((it) => it.spot_id);
  if (!ids.length) {
    flash("清单为空,请先加入想去的地方");
    return;
  }
  // 城市模式:每城天数可调;无闭环/出发点(那是自驾模式的)
  // 若已有推荐结果(state.cityRec),直接按推荐生成
  const rec = state.cityRec;
  let cityDays = rec ? rec.city_days : {};
  if (!rec) {
    // 只收集清单里真实存在的城市(避免残留的旧下拉污染每城天数)
    document.querySelectorAll("[id^='city-days-']").forEach((sel) => {
      const cn = sel.id.replace("city-days-", "");
      if (state.cart.some((it) => it.city_name === cn)) {
        cityDays[cn] = +sel.value;
      }
    });
  }
  const startCity = ($("#plan-start") && $("#plan-start").value.trim()) || (rec ? rec.start_city : "");
  // 总天数:优先工作台 #plan-days(始终存在),再退到清单 #days(需打开过清单才渲染)
  const days = rec
    ? Object.values(rec.city_days).reduce((a, b) => a + b, 0)
    : +($("#plan-days") ? $("#plan-days").value : ($("#days") ? $("#days").value : 3));
  const body = {
    spot_ids: ids,
    days,
    style: $("#style") ? $("#style").value : "轻松",
    close_loop: false,
    city_days: Object.keys(cityDays).length ? cityDays : null,
    start_city: startCity,
  };
  try {
    const resp = await api("/api/plans/citytour", { method: "POST", body: JSON.stringify(body) });
    const plans = resp.map((r) => r.plan);
    renderPlans("城市之旅", plans);
    if (plans[0]) drawRouteOnMap(plans[0]);
  } catch (e) {
    flash("生成失败: " + e.message);
  }
}

// ---------- 城市之旅规划工作台(城市 tab) ----------
function cityPlanWorkspaceHtml() {
  const byCity = {};
  state.cart.forEach((it) => {
    (byCity[it.city_name] = byCity[it.city_name] || []).push(it);
  });
  const chips = Object.keys(byCity).map((cn) => {
    const c = state.cities.find((x) => x.name === cn);
    const id = c ? c.id : 0;
    return `<span class="chip city-chip" onclick="focusCity(${id})" title="点击定位到 ${esc(cn)}">
      📍 ${esc(cn)} × ${byCity[cn].length}
      <b class="chip-x" onclick="event.stopPropagation(); removeCityFromCart('${esc(cn)}')" title="移除该城">✕</b>
    </span>`;
  }).join(" ");
  return `
  <div class="panel-box plan-box">
    <h4>🏙 城市之旅规划
      <button class="btn sm primary" style="float:right" onclick="generateCityTour()">生成城市之旅</button>
    </h4>
    <div style="font-size:12px;color:var(--muted);margin:4px 0 8px">
      已选城市: ${chips || '<span style="color:var(--muted)">(先去地图/城市页加入想玩的地方)</span>'}
      <br>点击城市标签 → 地图自动切到该省并定位,同时列出有啥玩的;点 ✕ 移除该城;
      加购物车后点「获取推荐」由算法分配每城天数与起始城市。
    </div>
    <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">
      <label style="font-size:12px">🚩 出发地
        <input id="plan-start" list="plan-city-list" placeholder="如:兰州" style="width:120px;padding:4px 8px;border:1px solid var(--border);border-radius:8px">
        <datalist id="plan-city-list">${state.cities.map((c) => `<option value="${esc(c.name)}">`).join("")}</datalist>
      </label>
      <label style="font-size:12px">📅 总天数
        <select id="plan-days" onchange="syncPlanDays('ws')" style="padding:4px 8px;border:1px solid var(--border);border-radius:8px">
          ${[1, 2, 3, 4, 5, 6, 7, 8, 9, 10].map((d) => `<option value="${d}" ${d === +($("#days") ? $("#days").value : 3) ? "selected" : ""}>${d} 天</option>`).join("")}
        </select>
      </label>
      <button class="btn sm" onclick="getCityRecommend()">🤖 获取推荐(每城几天 · 从哪开始)</button>
    </div>
    <div id="city-rec" style="margin-top:8px"></div>
  </div>`;
}

// 清单 tab「天数」与工作台「总天数」双向同步,避免两个入口天数打架
function syncPlanDays(from) {
  const cart = $("#days");
  const ws = $("#plan-days");
  if (!cart || !ws) return;
  const v = from === "cart" ? cart.value : ws.value;
  cart.value = v;
  ws.value = v;
}

async function getCityRecommend() {
  const ids = state.cart.map((it) => it.spot_id);
  if (!ids.length) {
    flash("清单为空,先加入想去的地方");
    return;
  }
  const startCity = ($("#plan-start") && $("#plan-start").value.trim()) || "";
  const total = +($("#plan-days") ? $("#plan-days").value : 4);
  try {
    const rec = await api("/api/plans/cityplan-recommend", {
      method: "POST",
      body: JSON.stringify({ spot_ids: ids, total_days: total, start_city: startCity }),
    });
    state.cityRec = rec;
    const daysHtml = Object.entries(rec.city_days)
      .map(([c, d]) => `<span class="chip city-chip">${esc(c)} ${d}天</span>`)
      .join(" ");
    $("#city-rec").innerHTML = `
      <div class="rec-box">
        ${rec.warn ? `<div class="rec-warn">${esc(rec.warn)}</div>` : ""}
        <div><b>🚩 起始城市:</b> ${esc(rec.start_city)} — ${esc(rec.start_reason)}</div>
        <div style="margin-top:4px"><b>🗺 游玩顺序:</b> ${rec.order.map((c) => esc(c)).join(" → ")}</div>
        <div style="margin-top:4px"><b>📅 每城天数:</b> ${daysHtml}</div>
        <div class="rec-reasons" style="margin-top:4px;font-size:12px;color:var(--muted)">
          ${Object.entries(rec.reasons.days || {}).map(([c, r]) => `· ${esc(c)}: ${esc(r)}`).join("<br>")}
        </div>
        <button class="btn sm primary" style="margin-top:8px" onclick="generateCityTour()">✅ 按推荐生成城市之旅</button>
      </div>`;
  } catch (e) {
    flash("获取推荐失败: " + e.message);
  }
}

async function removeCityFromCart(cityName) {
  const items = state.cart.filter((it) => it.city_name === cityName);
  for (const it of items) {
    try {
      await api(`/api/cart/${it.spot_id}`, { method: "DELETE" });
    } catch (e) { /* 单项删除失败继续 */ }
  }
  await loadCart();
  renderCities(null);   // 刷新工作台 chips
  flash(`已移除 ${cityName} 的 ${items.length} 项`);
}

async function focusCity(cityId) {
  const city = state.cities.find((c) => c.id === cityId);
  if (!city) return;
  // 地图自动切到该省份
  if (mapLevel !== "province" || currentProvince !== city.province) {
    await renderProvinceMap(city.province);
  }
  // 定位到城市并放大
  chart.setOption({ geo: { center: [city.lng, city.lat], zoom: 22 } });
  // 切到该城市页,列出有啥玩的
  await openCity(cityId);
  switchTab("spots");
}

function drawRoute(i) {
  if (lastPlans[i]) drawRouteOnMap(lastPlans[i]);
}

async function generateRoadtrip() {
  const ids = state.cart.map((it) => it.spot_id);
  if (ids.length < 2) {
    flash("自驾模式至少需要 2 个景区");
    return;
  }
  const closeLoop = $("#close-loop") ? $("#close-loop").checked : true;
  const startCity = $("#start-city") ? $("#start-city").value.trim() : "";
  const body = {
    spot_ids: ids,
    days: +($("#days") ? $("#days").value : 5),
    style: $("#style") ? $("#style").value : "轻松",
    close_loop: closeLoop,
    start_city: startCity,
  };
  try {
    const resp = await api("/api/plans/roadtrip", { method: "POST", body: JSON.stringify(body) });
    const plans = resp.map((r) => r.plan);
    renderPlans("自驾路线", plans);
    if (plans[0]) drawRouteOnMap(plans[0]);   // 生成后自动画在地图上
  } catch (e) {
    flash("生成失败: " + e.message);
  }
}

// ---------- 行程方案 ----------
async function generatePlans(cityName) {
  const items = state.cart.filter((it) => it.city_name === cityName);
  const city = state.cities.find((c) => c.name === cityName);
  if (!city) return;
  const body = {
    city_id: city.id,
    days: +$("#days").value,
    style: $("#style").value,
    spot_ids: items.map((it) => it.spot_id),
  };
  try {
    const resp = await api("/api/plans/generate", { method: "POST", body: JSON.stringify(body) });
    renderPlans(cityName, resp.map((r) => r.plan));
  } catch (e) {
    flash("生成失败: " + e.message);
  }
}

function renderPlans(cityName, plans) {
  lastPlans = plans;
  const pane = $("#tab-plans");
  pane.innerHTML = `
    <h3 style="margin-bottom:8px">${esc(cityName)} · 行程方案(${plans.length} 套可选)</h3>
    ${plans.map((p, i) => `
      <div class="plan-card">
        <h4>${esc(p.name)}</h4>
        <div class="summary">${p.source ? `来源: ${esc(p.source)} · ` : ""}${esc(p.summary)}</div>
        ${p.route && p.route.length ? `
          <div class="route-strip">${p.route.map((l) => {
            const tr = l.transport || {};
            const trTxt = tr.recommend ? ` · ${tr.recommend}` : "";
            return `<div><span>${esc(l.from_city)} <b>${esc(l.from)}</b></span> → <span><b>${esc(l.to)}</b> <em>${l.km}km/${l.hours}h</em></span>
              <div class="route-tr">🚄 ${esc(tr.rail || "自驾")}${trTxt}</div></div>`;
          }).join("")}</div>
          <button class="btn sm primary" onclick="drawRoute(${i})">🗺 在地图查看此路线</button>` : ""}
        ${(p.daily || []).map((day) => `
          <div class="day-block">
            <div class="day-title">第 ${day.day} 天</div>
            ${day.note ? `<div class="day-note">${esc(day.note)}</div>` : ""}
            ${(day.items || []).map((it) =>
              `<div class="item">${it.time ? `<span class="time-chip">🕐${esc(it.time)}</span> ` : ""}${esc(it.spot)} <span class="why">— ${esc(it.why)}</span>
                ${it.time_reason ? `<br/><span class="time-note">${esc(it.time_reason)}</span>` : ""}</div>`).join("")}
            ${day.next_transport ? `
              <div class="stay-line tr">🚄 前往下一城 <b>${esc(day.next_transport.to)}</b>:
                ${esc(day.next_transport.rail || `自驾 ${day.next_transport.km}km`)} · 建议:${esc(day.next_transport.recommend || "高铁")}</div>` : ""}
            ${day.stay ? `
              <div class="stay-line">🏨 住: <b>${esc(day.stay.area_label || day.stay.town)}</b> · ${esc(day.stay.price)} · 距当日终点 ${day.stay.km_from_last}km
                <br/><span class="stay-note">${esc(day.stay.fit_note || day.stay.note)}</span></div>` : ""}
            ${day.foods && day.foods.dishes && day.foods.dishes.length ? `
              <div class="day-food">🍜 必吃: ${day.foods.dishes.map((d) => `${esc(d.name)} ¥${d.price_low || ""}-${d.price_high || ""}`).join("、")}
              ${day.foods.streets && day.foods.streets.length ? `<br/>🏮 美食街: ${day.foods.streets.map((s) => esc(s.name)).join("、")}` : ""}</div>` : ""}
          </div>`).join("")}
        ${(p.tips || []).length ? `<div class="tips"><b>💡 提示</b><br/>${p.tips.map((t) => esc(t)).join("<br/>")}</div>` : ""}
      </div>`).join("")}
    <div style="text-align:center;margin-top:6px">
      <button class="btn sm" onclick="renderCart(); switchTab('cart')">← 返回清单调整</button>
    </div>`;
  switchTab("plans");
}

// ---------- 事件绑定 ----------
document.querySelectorAll(".tabs button").forEach((b) => {
  b.addEventListener("click", () => {
    switchTab(b.dataset.tab);
    if (b.dataset.tab === "cart") renderCart();
    if (b.dataset.tab === "loops") renderLoops();
    if (b.dataset.tab === "spots" && !state.currentSpots.length && !state.detail) renderSpots();
  });
});

setupPwa();
init();
