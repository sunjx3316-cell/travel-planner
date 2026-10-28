/* Lazy railway integration. Loading the travel home never starts a rail worker. */
(() => {
  const KEY = 'travel-planner-rail-journeys-v1';
  const LIMIT = 12;
  let dialog, frame, session, candidate, trigger, committing = false, commitTimer;
  let targetWorkbench = null;
  const escape = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const text = (value, max = 60) => typeof value === 'string' && value.length > 0 && value.length <= max;
  const minute = value => Number.isInteger(value) && value >= 0 && value <= 10080;
  const clock = value => String(Math.floor(value / 60) % 24).padStart(2, '0') + ':' + String(value % 60).padStart(2, '0') + (value >= 1440 ? ' +' + Math.floor(value / 1440) + '天' : '');
  const duration = value => `${Math.floor(value / 60)}小时${value % 60 ? value % 60 + '分' : ''}`;
  function validate(value) {
    if (!value || !text(value.id, 100) || !text(value.from) || !text(value.to) || !/^\d{4}-\d{2}-\d{2}$/.test(value.date) || !Number.isFinite(Date.parse(value.date)) || !Number.isFinite(Date.parse(value.savedAt))) throw Error('铁路方案格式不完整');
    if (!Array.isArray(value.legs) || value.legs.length < 1 || value.legs.length > 4) throw Error('仅接受完整的 1–4 段车次');
    const legs = value.legs.map(l => {
      if (!l || !text(l.train, 20) || !text(l.from) || !text(l.to) || !text(l.fromCode, 10) || !text(l.toCode, 10) || !minute(l.departure) || !minute(l.arrival) || l.arrival <= l.departure) throw Error('车次数据无效');
      return {train:l.train, from:l.from, to:l.to, fromCode:l.fromCode, toCode:l.toCode, departure:l.departure, arrival:l.arrival};
    });
    if (legs.some((l, i) => i > 0 && l.departure < legs[i-1].arrival) || value.duration !== legs.at(-1).arrival - legs[0].departure || value.duration > 2880 || value.transfers !== legs.length - 1) throw Error('换乘时间不完整');
    if (value.cost !== null && (!Number.isFinite(value.cost) || value.cost <= 0 || value.cost > 100000)) throw Error('票价格式无效');
    return {id:value.id, savedAt:value.savedAt, date:value.date, from:value.from, to:value.to, legs,
      duration:value.duration, transfers:value.transfers, cost:value.cost,
      snapshot:text(value.snapshot, 20) ? value.snapshot : '', risk:text(value.risk, 40) ? value.risk : '待核实'};
  }
  function read() {
    const raw = localStorage.getItem(KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (parsed.version !== 1 || !Array.isArray(parsed.journeys) || parsed.journeys.length > LIMIT) throw Error('交通清单读取失败，原记录已保留');
    return parsed.journeys.map(validate);
  }
  const signature = j => JSON.stringify([j.date, j.legs]);
  function planRows(plan) {
    if (plan.rail_journeys === undefined) return [];
    if (!Array.isArray(plan.rail_journeys) || plan.rail_journeys.length > LIMIT) throw Error('铁路安排无法读取');
    return plan.rail_journeys.map(validate);
  }
  function attach(plan, journey) {
    const rows = planRows(plan), clean = validate(journey);
    const index = rows.findIndex(j => signature(j) === signature(clean));
    if (index >= 0) rows[index] = clean;
    else { if (rows.length >= LIMIT) throw Error('每套方案最多保存 12 程铁路'); rows.push(clean); }
    return rows;
  }
  function editFinal() { openFinalPlanWorkbench(); open({scope:'workbench'}); }
  function useSaved(index) {
    try {
      const wb = state.workbench;
      if (!wb) return;
      const rows = attach(wb.plan, read()[index]);
      mutateWorkshop(draft => { draft.plan.rail_journeys = rows; });
      flash(wb.storageError ? '已加入草稿，但本机保存失败，请勿关闭' : '铁路已加入当前方案，确认行程后生效');
    } catch (error) { flash(error.message); }
  }
  function section(plan = null, scope = 'library') {
    let rows;
    try { rows = plan ? planRows(plan) : read(); } catch { return '<section class="trip-rail"><strong>铁路交通</strong><p>本机交通记录无法读取，原记录未被覆盖。</p></section>'; }
    let saved = [];
    if (scope === 'workbench') { try { saved = read(); } catch {} }
    const action = scope === 'workbench' ? "TravelRail.open({scope:'workbench'})" : scope === 'final' ? 'TravelRail.editFinal()' : 'TravelRail.open()';
    return `<section class="trip-rail"><div class="trip-rail-heading"><strong>铁路交通${rows.length ? ' · ' + rows.length + ' 程' : ''}</strong><button class="btn sm" onclick="${action}">${rows.length ? '添加一程' : '规划铁路交通'} →</button></div>${rows.length ? rows.map(j => `<details class="trip-rail-journey"><summary><span><b>${escape(j.from)} → ${escape(j.to)}</b><small>${escape(j.date)} · ${duration(j.duration)} · ${j.transfers ? j.transfers + ' 次换乘' : '直达'}</small></span><span class="trip-rail-price">${j.cost === null ? '待核价' : '参考 ¥' + j.cost}</span></summary><ol>${j.legs.map(l => `<li><b>${escape(l.train)}</b><span>${escape(l.from)} ${clock(l.departure)}<br>${escape(l.to)} ${clock(l.arrival)}</span></li>`).join('')}</ol><p class="trip-rail-disclaimer">${escape(j.risk)} · 时刻表 ${escape(j.snapshot)}<br>保存于 ${escape(new Date(j.savedAt).toLocaleString())}。仅供参考，余票、运行与换乘需向 12306 核实。</p>${scope !== 'final' ? `<button class="workshop-text-btn" data-remove-rail="${escape(j.id)}" data-rail-scope="${scope}">移除这程</button>` : ''}</details>`).join('') : '<p class="trip-rail-empty">比较车次和换乘，选好后保存在这里。</p>'}${saved.length ? `<details class="trip-rail-saved"><summary>从已存交通清单添加</summary>${saved.map((j,i) => `<button class="btn sm" onclick="TravelRail.useSaved(${i})">${escape(j.date)} ${escape(j.from)} → ${escape(j.to)}</button>`).join('')}</details>` : ''}<p class="trip-rail-local">${plan ? '随本方案保存和导出；铁路日期独立于第几天，请自行留足交通与游玩时间。' : '独立交通清单；可在行程工作坊中选择加入某套方案。'}</p></section>`;
  }
  function printSection(plan) {
    return planRows(plan).map(j => `<section class="trip-print-rail"><h2>铁路 / ${escape(j.from)} → ${escape(j.to)}</h2><p>${escape(j.date)} · ${duration(j.duration)} · ${escape(j.risk)} · ${j.cost === null ? '票价待核实' : '参考 ¥' + j.cost}</p>${j.legs.map(l => `<p><b>${escape(l.train)}</b>　${escape(l.from)} ${clock(l.departure)} → ${escape(l.to)} ${clock(l.arrival)}</p>`).join('')}<small>时刻表 ${escape(j.snapshot)}，价格和运行情况请向 12306 核实。</small></section>`).join('');
  }
  function close() {
    if (!dialog) return;
    clearTimeout(commitTimer);
    // Removing the browsing context also releases its workers, animation loops
    // and requests. Do not keep an invisible rail map alive behind the main map.
    frame?.remove(); frame = null; candidate = null; session = null; committing = false; targetWorkbench = null;
    dialog.close(); dialog.remove(); dialog = null;
    trigger?.focus?.();
  }
  function open(options = {}) {
    if (dialog) return;
    targetWorkbench = options.scope === 'workbench' ? state.workbench : null;
    if (options.scope === 'workbench' && !targetWorkbench) return flash('请先打开一套行程方案');
    trigger = document.activeElement;
    session = crypto.randomUUID();
    let saved;
    try { saved = targetWorkbench?.plan || finalPlan(); } catch { saved = null; }
    const start = document.querySelector('#plan-start')?.value.trim() || saved?.route?.[0]?.from?.replace(/^出发地[:：]/, '') || '';
    const end = saved?.daily?.[0]?.items?.[0]?.city_name || state.cityRec?.order?.[0] || state.cart?.[0]?.city_name || '';
    const url = new URL('/rail/', location.origin);
    url.search = new URLSearchParams({embedded:'1', session, from:start, to:end === start ? '' : end});
    dialog = document.createElement('dialog'); dialog.className = 'rail-workbench';
    dialog.setAttribute('aria-label', '铁路交通工作台');
    dialog.innerHTML = `<div class="rail-workbench-bar"><button class="btn sm" data-rail-close>← 返回旅行</button><strong>铁路交通</strong><span data-rail-status role="status">正在加载…</span><button class="btn sm primary" data-rail-apply disabled>${targetWorkbench ? '加入当前方案' : '加入交通清单'}</button></div><iframe title="铁路推荐、编辑与对比"></iframe>`;
    document.body.appendChild(dialog);
    frame = dialog.querySelector('iframe');
    dialog.querySelector('[data-rail-close]').onclick = close;
    dialog.addEventListener('cancel', event => {event.preventDefault(); close();});
    dialog.querySelector('[data-rail-apply]').onclick = () => {
      if (!candidate || committing) return;
      committing = true;
      dialog.querySelector('[data-rail-apply]').disabled = true;
      frame.contentWindow.postMessage({type:'travel:commit', session}, location.origin);
      commitTimer = setTimeout(() => {if (dialog) {committing = false; candidate = null; dialog.querySelector('[data-rail-status]').textContent = '未收到完整方案，请重新选择';}}, 5000);
    };
    dialog.showModal(); frame.src = url.href;
  }
  window.addEventListener('message', event => {
    if (!dialog || event.origin !== location.origin || event.source !== frame?.contentWindow || event.data?.session !== session) return;
    const type = event.data.type;
    if (!['rail:ready','rail:selection','rail:commit'].includes(type)) return;
    try { candidate = event.data.journey ? validate(event.data.journey) : null; } catch { candidate = null; }
    if (type === 'rail:commit' && committing) {
      clearTimeout(commitTimer); committing = false;
      if (candidate) {
        try {
          if (targetWorkbench) {
            if (state.workbench !== targetWorkbench) throw Error('编辑草稿已变化，请重新打开铁路规划');
            const rows = attach(targetWorkbench.plan, candidate), wb = targetWorkbench;
            mutateWorkshop(draft => { draft.plan.rail_journeys = rows; });
            close(); switchTab('plans');
            flash(wb.storageError ? '已加入草稿，但本机保存失败，请勿关闭' : '已加入当前方案；确认行程后一起保存和导出');
            return;
          }
          const rows = read();
          const index = rows.findIndex(j => signature(j) === signature(candidate));
          if (index >= 0) rows[index] = candidate;
          else {if (rows.length >= LIMIT) throw Error('交通清单已满，请先移除不需要的行程'); rows.push(candidate);}
          localStorage.setItem(KEY, JSON.stringify({version:1, journeys:rows}));
          close(); renderLibrary(); flash('已加入独立交通清单，可在行程工作坊中选用');
          return;
        } catch (error) { flash(error.message || '保存失败，原记录未改动'); }
      }
    }
    dialog.querySelector('[data-rail-apply]').disabled = !candidate || committing;
    dialog.querySelector('[data-rail-status]').textContent = candidate ? `${candidate.from} → ${candidate.to} · ${candidate.risk} · ${candidate.legs.map(l => l.train).join(' / ')}` : '选择一条完整的铁路方案';
  });
  document.addEventListener('click', event => {
    const button = event.target.closest('[data-remove-rail]');
    if (!button) return;
    try {
      if (button.dataset.railScope === 'workbench') {
        if (!state.workbench) return;
        const rows = planRows(state.workbench.plan).filter(j => j.id !== button.dataset.removeRail);
        mutateWorkshop(draft => { draft.plan.rail_journeys = rows; });
        return;
      }
      const rows = read().filter(j => j.id !== button.dataset.removeRail);
      if (!window.confirm('从本机交通清单移除这程？铁路工作台中的对比方案不会删除。')) return;
      localStorage.setItem(KEY, JSON.stringify({version:1, journeys:rows})); renderLibrary();
    } catch { flash('移除失败，原记录未改动'); }
  });
  window.addEventListener('storage', event => {if (event.key === KEY && document.querySelector('#tab-trip.active')) renderTrip();});
  function renderLibrary() {
    switchTab('trip');
    document.querySelector('#tab-trip').innerHTML = `<div class="trip-rail-heading"><h3>独立交通清单</h3><button class="btn sm" onclick="renderTrip()">返回最终行程</button></div>${section()}`;
  }
  window.TravelRail = {open, close, section, read, validate, signature, planRows, attach, editFinal, useSaved, printSection, renderLibrary};
})();
