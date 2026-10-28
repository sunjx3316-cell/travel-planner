/* A local-first itinerary editor. AI proposals remain untouched until explicitly saved. */
const WORKSHOP_DRAFT_KEY = 'travel-planner-workshop-draft-v1';

function beginWorkbench(plan, originalIndex) {
  const previous = readWorkbenchDraft();
  if (previous && JSON.stringify(previous.plan) !== JSON.stringify(plan)) {
    try {
      const saved = savedWorkbenchPlans();
      saved.unshift({saved_at: previous.saved_at || new Date().toISOString(), plan: previous.plan});
      localStorage.setItem(WORKBENCH_STORAGE_KEY, JSON.stringify(saved.slice(0, 20)));
    } catch (_) { return flash('无法保留上次草稿，先不要切换方案；请释放本机存储空间'); }
  }
  const copy = clonePlan(plan);
  normalizedWorkbenchDays(copy);
  if (!copy.daily.length) copy.daily.push({day: 1, items: [], note: ''});
  state.workbench = {plan: copy, originalPlan: clonePlan(copy), originalIndex,
    dayIndex: 0, itemIndex: null, undo: []};
  persistWorkbenchDraft();
  renderPlanWorkbench();
  switchTab('plans');
}

function persistWorkbenchDraft() {
  const wb = state.workbench;
  if (!wb) return;
  try {
    localStorage.setItem(WORKSHOP_DRAFT_KEY, JSON.stringify({plan: wb.plan,
      originalPlan: wb.originalPlan, dayIndex: wb.dayIndex, saved_at: new Date().toISOString()}));
    wb.storageError = false;
  } catch (_) { wb.storageError = true; }
  const status = $('#workshop-save-status');
  if (status) status.textContent = wb.storageError ? '本机存储失败，请勿关闭页面' : '草稿已自动保存在本机';
}

function readWorkbenchDraft() {
  try {
    const saved = JSON.parse(localStorage.getItem(WORKSHOP_DRAFT_KEY) || 'null');
    return saved?.plan && Array.isArray(saved.plan.daily) ? saved : null;
  } catch (_) { return null; }
}
function hasWorkbenchDraft() { return !!readWorkbenchDraft(); }
function restoreWorkbenchDraft() {
  const saved = readWorkbenchDraft();
  if (!saved) return flash('没有可恢复的草稿');
  beginWorkbench(saved.plan, null);
  const wb = state.workbench;
  wb.originalPlan = saved.originalPlan || clonePlan(wb.plan);
  wb.dayIndex = Math.max(0, Math.min(Number(saved.dayIndex) || 0, wb.plan.daily.length - 1));
  persistWorkbenchDraft();
  renderPlanWorkbench();
}

function mutateWorkshop(change, affectedDays = [], render = true, editKey = null) {
  const wb = state.workbench;
  if (!wb) return;
  if (!editKey || wb.lastEditKey !== editKey) wb.undo.push({plan: clonePlan(wb.plan), dayIndex: wb.dayIndex, itemIndex: wb.itemIndex});
  wb.lastEditKey = editKey;
  wb.undo = wb.undo.slice(-30);
  change(wb);
  if (affectedDays.length) {
    // Never present the old AI route or stay estimates as if they were recalculated.
    if (!wb.plan.workshop_changed) wb.plan.summary = '根据建议调整后的个人安排';
    wb.plan.workshop_changed = true;
    wb.plan.route = [];
    wb.plan.tips = [];
    wb.plan.daily.forEach(day => {
      delete day.stay; delete day.foods; delete day.next_transport;
      day.items.forEach(item => { delete item.time_reason; });
    });
  }
  normalizedWorkbenchDays(wb.plan);
  wb.dayIndex = Math.max(0, Math.min(wb.dayIndex, wb.plan.daily.length - 1));
  persistWorkbenchDraft();
  if (render) renderPlanWorkbench();
}

function undoWorkbenchChange() {
  const wb = state.workbench;
  const prev = wb?.undo.pop();
  if (!prev) return;
  Object.assign(wb, prev);
  wb.lastEditKey = null;
  persistWorkbenchDraft();
  renderPlanWorkbench();
}
function selectWorkbenchDay(index) {
  const wb = state.workbench;
  if (!wb || !wb.plan.daily[index]) return;
  wb.dayIndex = index; wb.itemIndex = null; wb.lastEditKey = null;
  persistWorkbenchDraft(); renderPlanWorkbench();
}
function selectWorkbenchItem(index) {
  if (!state.workbench) return;
  state.workbench.itemIndex = index;
  state.workbench.lastEditKey = null;
  renderPlanWorkbench();
}
function updateWorkbenchMeta(field, value) {
  if (!['name', 'summary'].includes(field)) return;
  mutateWorkshop(wb => {wb.plan[field] = value;}, [], false, 'meta:' + field);
}
function updateWorkbenchDayNote(dayIndex, value) {
  mutateWorkshop(wb => {wb.plan.daily[dayIndex].note = value;}, [], false, 'note:' + dayIndex);
}
function updateWorkbenchItem(dayIndex, itemIndex, field, value, render = true) {
  if (!['spot', 'time', 'why'].includes(field)) return;
  mutateWorkshop(wb => {
    const item = wb.plan.daily[dayIndex].items[itemIndex];
    item[field] = value;
    if (field === 'spot') { delete item.spot_id; delete item.city_name; }
    if (field !== 'why') delete item.time_reason;
  }, field === 'why' ? [] : [dayIndex], render, 'item:' + dayIndex + ':' + itemIndex + ':' + field);
}
function moveWorkbenchItem(dayIndex, itemIndex, direction) {
  const items = state.workbench?.plan.daily[dayIndex]?.items;
  const target = itemIndex + direction;
  if (!items || !items[target]) return;
  mutateWorkshop(wb => {
    [items[itemIndex], items[target]] = [items[target], items[itemIndex]];
    wb.itemIndex = target;
  }, [dayIndex]);
}
function transferWorkbenchItem(dayIndex, itemIndex, targetDay) {
  targetDay = Number(targetDay);
  const wb = state.workbench;
  if (!wb?.plan.daily[targetDay] || targetDay === dayIndex) return;
  mutateWorkshop(wb => {
    const [item] = wb.plan.daily[dayIndex].items.splice(itemIndex, 1);
    wb.plan.daily[targetDay].items.push(item);
    wb.dayIndex = targetDay;
    wb.itemIndex = wb.plan.daily[targetDay].items.length - 1;
  }, [dayIndex, targetDay]);
}
function shiftWorkbenchItemDay(dayIndex, itemIndex, direction) {
  transferWorkbenchItem(dayIndex, itemIndex, dayIndex + direction);
}
function removeWorkbenchItem(dayIndex, itemIndex) {
  mutateWorkshop(wb => {wb.plan.daily[dayIndex].items.splice(itemIndex, 1); wb.itemIndex = null;}, [dayIndex]);
}
function addWorkbenchDay() {
  mutateWorkshop(wb => {
    wb.plan.daily.push({day: wb.plan.daily.length + 1, note: '', items: []});
    wb.dayIndex = wb.plan.daily.length - 1; wb.itemIndex = null;
  }, [state.workbench?.plan.daily.length]);
}
function removeWorkbenchDay() {
  const wb = state.workbench;
  if (!wb || wb.plan.daily.length <= 1) return;
  if (wb.plan.daily[wb.dayIndex].items.length && !window.confirm('移除这一天及其安排？可以通过“撤销”恢复。')) return;
  mutateWorkshop(wb => {wb.plan.daily.splice(wb.dayIndex, 1); wb.itemIndex = null;}, [wb.dayIndex]);
}
function workshopCartEntry(value) {
  return state.cart.find(entry => String(entry.spot_id) === String(value));
}
function workshopCartName(entry) { return entry.name || entry.spot_name || ''; }
function addWorkbenchCartItem(dayIndex) {
  const entry = workshopCartEntry($('#workbench-cart-item')?.value);
  if (!entry) return flash('请先选择清单中的地点');
  const day = state.workbench?.plan.daily[dayIndex];
  if (!day) return;
  if (day.items.some(item => item.spot_id === entry.spot_id || item.spot === workshopCartName(entry))) return flash('当天已经有这个地点');
  mutateWorkshop(wb => {
    day.items.push({spot: workshopCartName(entry), spot_id: entry.spot_id, city_name: entry.city_name, time: '待安排', why: ''});
    wb.itemIndex = day.items.length - 1;
  }, [dayIndex]);
}
function replaceWorkbenchItem(dayIndex, itemIndex, value) {
  const entry = workshopCartEntry(value);
  if (!entry) return;
  mutateWorkshop(wb => {
    const old = wb.plan.daily[dayIndex].items[itemIndex];
    wb.plan.daily[dayIndex].items[itemIndex] = {spot: workshopCartName(entry), spot_id: entry.spot_id,
      city_name: entry.city_name, time: old.time || '待安排', why: ''};
  }, [dayIndex]);
}
function addCustomWorkbenchItem() {
  const index = state.workbench?.dayIndex;
  if (index == null) return;
  mutateWorkshop(wb => {
    const items = wb.plan.daily[index].items;
    items.push({spot: '自由活动 / 休息', time: '待安排', why: ''});
    wb.itemIndex = items.length - 1;
  }, [index]);
}

function workshopTimeRange(text) {
  const value = String(text || '').replace(/：/g, ':');
  const match = value.match(/^(\d{1,2}):(\d{2})\s*[-–—~～至]\s*(\d{1,2}):(\d{2})$/);
  if (!match) return null;
  const [, h1, m1, h2, m2] = match.map(Number);
  if (h1 > 23 || h2 > 23 || m1 > 59 || m2 > 59) return null;
  return [h1 * 60 + m1, h2 * 60 + m2];
}
function workshopPeriod(item) {
  const text = String(item.time || '').trim();
  if (/全天|待安排|晚上|夜|傍晚/.test(text)) return 'other';
  if (/上午|早|中午/.test(text)) return 'morning';
  if (/下午/.test(text)) return 'afternoon';
  const range = workshopTimeRange(text);
  return range ? (range[0] < 720 ? 'morning' : range[0] < 1080 ? 'afternoon' : 'other') : 'other';
}
function selectWorkshopCard(dayIndex, itemIndex) {
  if (state.workbench?.suppressClick) return;
  state.workbench.dayIndex = dayIndex;
  selectWorkbenchItem(itemIndex);
  document.querySelector('.workshop-inspector')?.scrollIntoView({behavior: 'smooth', block: 'nearest'});
}
function moveWorkshopCard(fromDay, fromIndex, toDay, period, beforeIndex = null) {
  const wb = state.workbench;
  const item = wb?.plan.daily[fromDay]?.items[fromIndex];
  if (!item || !wb.plan.daily[toDay] || !['morning', 'afternoon', 'other'].includes(period)) return;
  if (fromDay === toDay && beforeIndex === fromIndex) return;
  const changePeriod = workshopPeriod(item) !== period;
  mutateWorkshop(wb => {
    const source = wb.plan.daily[fromDay].items;
    const target = wb.plan.daily[toDay].items;
    source.splice(fromIndex, 1);
    if (changePeriod) item.time = {morning: '上午', afternoon: '下午', other: '待安排'}[period];
    let insertAt;
    if (beforeIndex != null && Number.isInteger(beforeIndex)) {
      insertAt = beforeIndex - (fromDay === toDay && fromIndex < beforeIndex ? 1 : 0);
    } else {
      const last = target.reduce((found, entry, i) => workshopPeriod(entry) === period ? i : found, -1);
      insertAt = last >= 0 ? last + 1 : period === 'morning' ? 0 : target.length;
    }
    insertAt = Math.max(0, Math.min(insertAt, target.length));
    target.splice(insertAt, 0, item);
    wb.dayIndex = toDay; wb.itemIndex = null;
  }, [fromDay, toDay]);
  flash(changePeriod ? '已移动，时间改为' + item.time + '；可点卡片填写具体时间' : '安排已移动，可撤销');
}
let workshopDrag = null;
function startWorkshopDrag(event, dayIndex, itemIndex) {
  if (event.button !== 0 || !event.isPrimary) return;
  workshopDrag = {dayIndex, itemIndex, x: event.clientX, y: event.clientY, pointerId: event.pointerId,
    card: event.currentTarget, active: false};
}
function clearWorkshopDrag() {
  if (!workshopDrag) return;
  workshopDrag.ghost?.remove();
  workshopDrag.card.classList.remove('dragging');
  document.querySelectorAll('.workshop-drop.hovered').forEach(el => el.classList.remove('hovered'));
  workshopDrag = null;
}
document.addEventListener('pointermove', event => {
  const drag = workshopDrag;
  if (!drag || event.pointerId !== drag.pointerId) return;
  if (!drag.active && Math.hypot(event.clientX - drag.x, event.clientY - drag.y) < 7) return;
  if (!drag.active) {
    drag.active = true;
    state.workbench.suppressClick = true;
    drag.card.classList.add('dragging');
    drag.ghost = drag.card.cloneNode(true);
    drag.ghost.className = 'workshop-card workshop-drag-ghost';
    drag.ghost.style.width = drag.card.getBoundingClientRect().width + 'px';
    document.body.appendChild(drag.ghost);
  }
  event.preventDefault();
  drag.ghost.style.left = (event.clientX + 12) + 'px';
  drag.ghost.style.top = (event.clientY + 12) + 'px';
  const zone = document.elementFromPoint(event.clientX, event.clientY)?.closest('.workshop-drop');
  document.querySelectorAll('.workshop-drop.hovered').forEach(el => el.classList.remove('hovered'));
  zone?.classList.add('hovered');
  const pane = document.getElementById('tab-plans');
  const rect = pane?.getBoundingClientRect();
  if (rect && event.clientY > rect.bottom - 55) pane.scrollTop += 14;
  if (rect && event.clientY < rect.top + 55) pane.scrollTop -= 14;
}, {passive: false});
document.addEventListener('pointerup', event => {
  const drag = workshopDrag;
  if (!drag || event.pointerId !== drag.pointerId) return;
  const zone = document.elementFromPoint(event.clientX, event.clientY)?.closest('.workshop-drop');
  const before = document.elementFromPoint(event.clientX, event.clientY)?.closest('.workshop-card');
  const active = drag.active;
  clearWorkshopDrag();
  if (active && zone) moveWorkshopCard(drag.dayIndex, drag.itemIndex, Number(zone.dataset.day), zone.dataset.period,
    before ? Number(before.dataset.item) : null);
  if (active) setTimeout(() => {if (state.workbench) state.workbench.suppressClick = false;}, 0);
});
document.addEventListener('pointercancel', () => {
  clearWorkshopDrag();
  if (state.workbench) state.workbench.suppressClick = false;
});
function workshopBoardHtml(plan, selectedDay) {
  const periods = [['morning', '上午'], ['afternoon', '下午']];
  return `<div class="workshop-board">${plan.daily.map((day, di) => {
    const slots = day.items.some(item => workshopPeriod(item) === 'other') ? [...periods, ['other', '全天 / 晚间 / 待安排']] : periods;
    return `<section class="workshop-day ${di === selectedDay ? 'selected' : ''}" aria-label="第 ${di + 1} 天"><div class="workshop-column-head"><button class="workshop-text-btn" onclick="selectWorkbenchDay(${di})">第 ${di + 1} 天</button><small>${day.items.length} 个安排</small><button class="workshop-text-btn" aria-label="第 ${di + 1} 天添加安排" onclick="selectWorkbenchDay(${di});addCustomWorkbenchItem()">＋</button></div>${slots.map(([period, label]) => `<div class="workshop-drop" data-day="${di}" data-period="${period}" aria-label="第 ${di + 1} 天${label}"><div class="workshop-slot-title">${label}</div>${day.items.map((item, i) => workshopPeriod(item) === period ? `<button type="button" class="workshop-card ${di === selectedDay && i === state.workbench.itemIndex ? 'selected' : ''}" data-item="${i}" onpointerdown="startWorkshopDrag(event,${di},${i})" onclick="selectWorkshopCard(${di},${i})" aria-label="编辑 ${esc(item.spot || '未命名安排')}"><span class="workshop-grip" aria-hidden="true">⠿</span><span><b>${esc(item.spot || '未命名安排')}</b><small>${esc(item.time || '待安排')}${item.city_name ? ' · ' + esc(item.city_name) : ''}</small></span></button>` : '').join('')}<div class="workshop-drop-hint">拖到这里</div></div>`).join('')}</section>`;
  }).join('')}</div>`;
}
function workshopDayIssues(day) {
  const issues = [], names = new Set(), ranges = [];
  let unspecified = 0;
  day.items.forEach((item, i) => {
    const name = String(item.spot || '').trim();
    if (!name) issues.push('第 ' + (i + 1) + ' 个安排没有名称');
    if (name && names.has(name)) issues.push(name + ' 在当天重复出现');
    names.add(name);
    const range = workshopTimeRange(item.time);
    if (!range) { unspecified++; return; }
    if (range[1] <= range[0]) { issues.push(name + ' 的结束时间不晚于开始时间，请核对跨夜或时间填写'); return; }
    if (ranges.some(prev => range[0] < prev.end && range[1] > prev.start)) issues.push(name + ' 与当天其他安排时间重叠');
    if (ranges.length && range[0] < ranges[ranges.length - 1].start) issues.push(name + ' 的时间与排列顺序不一致');
    ranges.push({start: range[0], end: range[1]});
  });
  if (day.items.length > 5) issues.push('当天有 ' + day.items.length + ' 个安排，建议留出休息和交通时间');
  return {issues: [...new Set(issues)], unspecified};
}

function renderPlanWorkbench() {
  const wb = state.workbench;
  if (!wb) return;
  const plan = wb.plan;
  normalizedWorkbenchDays(plan);
  const di = wb.dayIndex || 0, day = plan.daily[di];
  if (!day) return;
  const item = day.items[wb.itemIndex];
  const check = workshopDayIssues(day);
  const allIssues = plan.daily.reduce((n, d) => n + workshopDayIssues(d).issues.length, 0);
  const options = '<option value="">选择清单地点</option>' + state.cart.map(entry =>
    `<option value="${Number(entry.spot_id)}">${esc(entry.city_name)} · ${esc(workshopCartName(entry))}</option>`).join('');
  $('#tab-plans').innerHTML = `<div class="workshop">
    <div class="workshop-header"><button class="workshop-back" onclick="closePlanWorkbench()" aria-label="返回方案">←</button><div><div class="eyebrow">行程工作坊</div><h3>${esc(plan.name || '我的行程')}</h3><small id="workshop-save-status" role="status">${wb.storageError ? '本机存储失败，请勿关闭页面' : '草稿已自动保存在本机'}</small></div><button class="btn sm accent" onclick="setFinalPlan()">确认行程</button></div>
    <div class="workshop-overview"><span>${plan.daily.length} 天 · ${plan.daily.reduce((n, d) => n + d.items.length, 0)} 个安排${allIssues ? ' · ' + allIssues + ' 项待核对' : ''}</span><button class="btn sm" onclick="undoWorkbenchChange()" ${wb.undo.length ? '' : 'disabled'}>撤销</button></div>
    <p class="workshop-subtle workshop-board-help">拖动卡片，调整日期或上午 / 下午；点击卡片编辑。改时段时，原具体时间会改为新时段。</p>
    ${workshopBoardHtml(plan, di)}
    ${window.TravelRail?.section(plan, 'workbench') || ''}
    <div class="workshop-day-head"><h4>第 ${di + 1} 天 · ${item ? '编辑安排' : '添加与设置'}</h4><button class="workshop-text-btn" onclick="addCustomWorkbenchItem()">＋ 自由安排</button></div>
    ${item ? `<label class="workshop-period-control">时段<select aria-label="安排时段" onchange="moveWorkshopCard(${di},${wb.itemIndex},${di},this.value)">${[['morning','上午'],['afternoon','下午'],['other','全天 / 晚间 / 待安排']].map(([value,label]) => `<option value="${value}" ${workshopPeriod(item) === value ? 'selected' : ''}>${label}</option>`).join('')}</select></label>` : ''}
    ${item ? `<section class="workshop-inspector" aria-label="编辑当前安排"><div class="workshop-editor-title">编辑安排<button class="workshop-text-btn" onclick="selectWorkbenchItem(null)">完成</button></div><label>地点<input aria-label="安排地点" value="${esc(item.spot || '')}" oninput="updateWorkbenchItem(${di},${wb.itemIndex},'spot',this.value,false)"></label><label>时间<input aria-label="安排时间" placeholder="如 09:00-11:00，或上午" value="${esc(item.time || '')}" oninput="updateWorkbenchItem(${di},${wb.itemIndex},'time',this.value,false)"></label><label>备注<input aria-label="安排备注" value="${esc(item.why || '')}" placeholder="预约、同行人偏好等" oninput="updateWorkbenchItem(${di},${wb.itemIndex},'why',this.value,false)"></label><div class="workshop-editor-tools"><button class="btn sm" onclick="moveWorkbenchItem(${di},${wb.itemIndex},-1)" ${wb.itemIndex === 0 ? 'disabled' : ''}>上移</button><button class="btn sm" onclick="moveWorkbenchItem(${di},${wb.itemIndex},1)" ${wb.itemIndex === day.items.length - 1 ? 'disabled' : ''}>下移</button><label>移至<select aria-label="移至其他日期" onchange="transferWorkbenchItem(${di},${wb.itemIndex},this.value)">${plan.daily.map((d, i) => `<option value="${i}" ${i === di ? 'selected' : ''}>第 ${i + 1} 天</option>`).join('')}</select></label><button class="workshop-text-btn danger" onclick="removeWorkbenchItem(${di},${wb.itemIndex})">移除</button></div>${state.cart.length ? `<details><summary>用清单中的地点替换</summary><select aria-label="替换安排地点" onchange="replaceWorkbenchItem(${di},${wb.itemIndex},this.value)">${options}</select></details>` : ''}</section>` : '<p class="workshop-subtle">点击一项安排，即可调整时间、顺序或日期。</p>'}
    ${state.cart.length ? `<div class="workshop-add"><select id="workbench-cart-item" aria-label="从清单选择地点">${options}</select><button class="btn sm" onclick="addWorkbenchCartItem(${di})">加入当天</button></div>` : ''}
    <details class="workshop-checks" ${check.issues.length ? 'open' : ''}><summary>${check.issues.length ? check.issues.length + ' 项安排待核对' : '安排检查'}${check.unspecified ? ' · ' + check.unspecified + ' 项未填写具体时间' : ''}</summary>${check.issues.map(issue => `<p>${esc(issue)}</p>`).join('')}<small>本地规则检查，不重新调用 AI。只检查明确时间段；开放时间、交通耗时和预约需另行确认。</small></details>
    <details class="workshop-settings"><summary>更多设置与当天备注</summary><label>行程名称<input aria-label="行程名称" value="${esc(plan.name || '')}" oninput="updateWorkbenchMeta('name',this.value)"></label><label>行程说明<input value="${esc(plan.summary || '')}" onchange="updateWorkbenchMeta('summary',this.value)"></label><label>当天备注<textarea aria-label="当天备注" oninput="updateWorkbenchDayNote(${di},this.value)">${esc(day.note || '')}</textarea></label><div class="workshop-editor-tools"><button class="btn sm" onclick="addWorkbenchDay()">增加一天</button><button class="btn sm" onclick="removeWorkbenchDay()" ${plan.daily.length <= 1 ? 'disabled' : ''}>移除当天</button><button class="btn sm" onclick="savePlanWorkbench()">另存本机版本</button></div>${plan.workshop_changed ? '<p class="workshop-subtle">安排已修改，旧路线和受影响日期的住宿、餐饮、交通推算已撤下。备注保留作参考，请重新核对。</p>' : ''}</details>
  </div>`;
}

function setFinalPlan() {
  const draft = state.workbench?.plan;
  if (!draft) return;
  if (!draft.daily.some(day => day.items.length)) return flash('请至少添加一项安排');
  normalizedWorkbenchDays(draft);
  try { localStorage.setItem(FINAL_PLAN_STORAGE_KEY, JSON.stringify(clonePlan(draft))); }
  catch (_) { return flash('保存失败：本机存储不可用或已满，请勿关闭草稿'); }
  persistWorkbenchDraft();
  flash('已确认最终行程，可继续编辑或导出 PDF');
  renderTrip(); switchTab('trip');
}

function savePlanWorkbench() {
  const wb = state.workbench;
  if (!wb) return;
  const saved = savedWorkbenchPlans();
  saved.unshift({saved_at: new Date().toISOString(), plan: clonePlan(wb.plan)});
  try { localStorage.setItem(WORKBENCH_STORAGE_KEY, JSON.stringify(saved.slice(0, 20))); }
  catch (_) { return flash('本机存储不可用，未能另存版本'); }
  if (Number.isInteger(wb.originalIndex) && lastPlans[wb.originalIndex]) lastPlans[wb.originalIndex] = clonePlan(wb.plan);
  persistWorkbenchDraft();
  flash('已另存为本机版本');
}

function tripPrintHtml(plan) {
  const groups = [];
  const periodOf = item => /全天/.test(item.time || '') ? 'all_day' : workshopPeriod(item) !== 'other' ? workshopPeriod(item)
    : /晚上|夜|傍晚|^(18|19|2[0-3])[:：]/.test(item.time || '') ? 'evening' : 'flexible';
  const slots = [['all_day','ALL DAY / 全天'],['morning','AM / 上午'],['afternoon','PM / 下午'],['evening','NIGHT / 晚间'],['flexible','FLEX / 时间待定']];
  for (let start = 0; start < plan.daily.length; start += 3) {
    const days = plan.daily.slice(start, start + 3);
    const cards = days.map(day => {
      const items = day.items || [];
      const sections = slots.map(([period,label]) => {
        const entries = items.filter(item => periodOf(item) === period);
        if (!entries.length && (!['morning','afternoon'].includes(period) || items.some(item => periodOf(item) === 'all_day'))) return '';
        return `<h3 class="trip-period">${label}</h3>${entries.map(item => `<div class="trip-calendar-card"><small>${esc(item.time || '时间待定')}</small><b>${esc(item.spot || '未命名安排')}</b>${item.why ? `<p>${esc(item.why)}</p>` : ''}${item.time_reason && !plan.workshop_changed ? `<small>${esc(item.time_reason)}</small>` : ''}</div>`).join('') || '<small>留白时间 · 自由安排</small>'}`;
      }).join('');
      const notes = [day.note ? `<p>${esc(day.note)}</p>` : '',
        !plan.workshop_changed && day.stay ? `<p>住 / ${esc(day.stay.area_label || day.stay.town || '')} ${esc(day.stay.price || '')}</p>` : '',
        !plan.workshop_changed && day.next_transport ? `<p>次日行 / ${esc(day.next_transport.to || '')} ${esc(day.next_transport.rail || day.next_transport.recommend || '')}</p>` : '',
        !plan.workshop_changed && day.foods?.dishes?.length ? `<p>食 / ${day.foods.dishes.map(dish => esc(dish.name)).join('、')}</p>` : ''].join('');
      return `<td>${sections}${notes ? `<div class="trip-memo"><h3 class="trip-period">MEMO / 当天备忘</h3>${notes}</div>` : ''}</td>`;
    });
    groups.push(`<table class="trip-calendar"><thead><tr>${days.map((day,i) => `<th><span class="trip-day-number">${String(start+i+1).padStart(2,'0')}</span> / 第 ${start+i+1} 天<small>${(day.items || []).length} 个安排</small></th>`).join('')}</tr></thead><tbody><tr>${cards.join('')}</tr></tbody></table>`);
  }
  groups.push(window.TravelRail?.printSection(plan) || '');
  return `<header><div>旅行智规 · 日历式行程表</div><h1>${esc(plan.name || '我的行程')}</h1><p>${esc(plan.summary || '')}</p><small>${plan.daily.length} 天 · 导出日期 ${new Date().toLocaleDateString('zh-CN', {timeZone: 'Asia/Shanghai'})}</small></header>${plan.workshop_changed ? '<p class="trip-print-note">本行程已手动调整，交通、住宿及预约请出发前核实。</p>' : ''}${groups.join('')}${plan.tips?.length && !plan.workshop_changed ? `<section><h2>出行参考提醒</h2>${plan.tips.map(tip => `<p>${esc(tip)}</p>`).join('')}</section>` : ''}<footer>以最终确认的安排为准，开放时间、预约和交通信息需出发前核实。</footer>`;
}
async function exportFinalPlanPdf() {
  const plan = finalPlan();
  if (!plan) return flash('请先确认最终行程');
  if (exportFinalPlanPdf.busy) return;
  exportFinalPlanPdf.busy = true;
  try {
    const response = await fetch('/api/plans/export-pdf', {method: 'POST',
      headers: {'Content-Type': 'application/json'}, body: JSON.stringify(plan)});
    if (!response.ok) {
      const error = await response.json().catch(() => ({}));
      throw new Error(typeof error.detail === 'string' ? error.detail : 'PDF 导出失败，请检查日程内容或稍后重试');
    }
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url; link.download = (plan.name || '我的行程').replace(/[\\/:*?"<>|]/g, '-') + '-日程安排.pdf';
    document.body.appendChild(link); link.click(); link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 60000);
    flash('PDF 已生成，正在下载');
  } catch (error) { flash(error.message + '；也可使用“打印另存”'); }
  finally { exportFinalPlanPdf.busy = false; }
}
function printFinalPlan() {
  const plan = finalPlan();
  if (!plan) return flash('请先确认最终行程');
  normalizedWorkbenchDays(plan);
  $('#trip-print')?.remove();
  const sheet = document.createElement('article');
  sheet.id = 'trip-print'; sheet.innerHTML = tripPrintHtml(plan);
  document.body.appendChild(sheet);
  const title = document.title;
  document.title = (plan.name || '我的行程') + '-日程安排';
  const cleanup = () => { document.title = title; sheet.remove(); };
  window.addEventListener('afterprint', cleanup, {once: true});
  flash('在打印窗口选择“另存为 PDF”；如内置浏览器无响应，请在系统浏览器打开本页面');
  try { window.print(); } catch (_) { cleanup(); flash('请在系统浏览器中打开本页面，再导出 PDF'); }
}
