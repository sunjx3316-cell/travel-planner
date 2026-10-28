/* One shared workspace, two explicit planning modes. No keys in browser storage. */
window.TravelMode = (() => {
  let settings = null;
  let selected = 'local';
  let busy = false;
  let first = false;
  const local = ['localhost', '127.0.0.1', '[::1]'].includes(location.hostname);
  const badge = document.querySelector('#mode-badge');
  const dialog = document.createElement('dialog');
  dialog.className = 'mode-dialog';
  dialog.setAttribute('aria-labelledby', 'mode-title');
  dialog.innerHTML = `
    <div class="mode-heading"><div><span class="mode-eyebrow">TRAVEL YOUR WAY</span>
      <h2 id="mode-title">先选一种旅行规划方式</h2>
      <p>同一份资料，同一个工作坊。按你的需要出发。</p></div>
      <button type="button" class="mode-close" aria-label="关闭模式设置">×</button></div>
    <div class="mode-options" role="radiogroup" aria-label="规划模式">
      <button type="button" class="mode-option" role="radio" data-mode="local" aria-checked="true">
        <span class="mode-option-top"><span class="mode-symbol">⌁</span><span class="mode-tag">推荐先体验</span></span>
        <strong>本地规划</strong><span class="mode-caption">不需要 Key · 无 AI 调用费用</span>
        <span class="mode-feature">用内置景点、评价和图片选目的地</span>
        <span class="mode-feature">按距离、游玩与驾驶时间生成多套安排</span>
        <span class="mode-feature">拖动微调、保存行程、导出日历 PDF</span>
        <span class="mode-bottom">不向 AI 服务发送你的行程</span>
      </button>
      <button type="button" class="mode-option" role="radio" data-mode="ai" aria-checked="false">
        <span class="mode-option-top"><span class="mode-symbol">✧</span><span class="mode-tag">自带 API</span></span>
        <strong>AI 增强</strong><span class="mode-caption">需要联网 · 费用由你的 API 账户承担</span>
        <span class="mode-feature">包含本地规划的所有功能</span>
        <span class="mode-feature">DeepSeek 补充方案说明与每日提醒</span>
        <span class="mode-feature">调用失败时，自动保留本地推荐</span>
        <span class="mode-bottom">发送本次规划所需的地点与偏好</span>
      </button>
    </div>
    <section class="mode-api" hidden aria-label="DeepSeek 配置">
      <div class="mode-api-label"><label for="mode-key">DeepSeek API Key</label><span id="mode-key-state"></span></div>
      <input id="mode-key" type="password" autocomplete="off" spellcheck="false" maxlength="512" placeholder="粘贴你自己的 Key" aria-describedby="mode-key-help">
      <p id="mode-key-help">仅保存在这台电脑的私有配置文件，不上传到项目仓库或放入安装包。当前支持 DeepSeek 官方接口。</p>
      <div class="mode-api-actions"><button type="button" class="mode-test">测试连接（少量 Token）</button><button type="button" class="mode-forget">移除已保存 Key</button></div>
      <p class="mode-test-result" aria-live="polite"></p>
    </section>
    <details class="mode-details"><summary>使用边界与隐私说明</summary>
      <p>本地规划不调用 AI，内置资料、地图、工作坊与 PDF 可在本机服务运行时使用。外部来源链接、高德资料更新、在线票价核验仍需要网络；本地时刻表不保证实时开行或余票。</p>
      <p>当前 AI 主要增强城市／自驾方案的说明与提醒，路线和时间仍由本地算法估算；已有评价库不会自动全部发送给 AI，也不代表 AI 已核验全部评论。请自行确认开放时间、预约及交通。</p>
      <p>Key 不会回传给页面，当前以本机文件保存，请勿分享 data/private 或 .env。局域网访客不能修改 Key，但启用 AI 后，访问这台服务的人可能消耗你的额度；请勿直接暴露公网。切换模式不改变已保存的行程，也不能撤回已经发出的请求。</p>
    </details>
    <p class="mode-feedback" role="status"></p>
    <div class="mode-footer"><span>以后可以随时从顶部切换</span><button type="button" class="mode-enter">进入本地规划 →</button></div>`;
  document.body.appendChild(dialog);
  const q = s => dialog.querySelector(s);

  function apply(data) {
    settings = data;
    const state = data.connection?.state;
    badge.textContent = data.mode === 'local' ? '本地规划 · 切换' :
      state === 'failed' ? 'AI 增强 · 上次请求失败' :
      state === 'success' ? 'AI 增强 · 上次请求成功' : 'AI 增强 · 待测试';
    badge.title = '查看模式说明与 API 设置';
    if (dialog.open) render();
  }
  function render() {
    dialog.querySelectorAll('[data-mode]').forEach(b => {
      b.setAttribute('aria-checked', String(b.dataset.mode === selected));
    });
    q('.mode-api').hidden = selected !== 'ai';
    q('.mode-close').hidden = first;
    q('#mode-key').disabled = !local || busy;
    q('#mode-key-state').textContent = settings?.configured ? '已有 Key · 不显示明文' : '未配置';
    q('#mode-key').placeholder = settings?.configured ? '留空保留原 Key，输入可替换' : '粘贴你自己的 Key';
    q('.mode-forget').hidden = !settings?.configured;
    dialog.querySelectorAll('button').forEach(b => b.disabled = busy || (!local && !b.classList.contains('mode-close')));
    q('.mode-enter').textContent = busy ? '处理中…' : selected === 'local' ? '进入本地规划 →' : '保存并进入 AI 模式 →';
  }
  async function request(path, data) {
    const response = await fetch('/api/ai/' + path, {
      method: 'POST', headers: {'Content-Type': 'application/json', 'X-Travel-Settings': '1'},
      body: JSON.stringify(data || {}), cache: 'no-store',
    });
    const body = await response.json();
    if (!response.ok) throw new Error(typeof body.detail === 'string' ? body.detail : '操作失败，请稍后重试');
    apply(body);
    return body;
  }
  async function refresh() {
    try {
      const response = await fetch('/api/status', {cache: 'no-store'});
      if (response.ok) apply((await response.json()).ai);
    } catch (_) { /* retain the last known mode, never claim connection success */ }
  }
  function open(isFirst = false) {
    if (!settings) return;
    first = isFirst;
    selected = settings.mode;
    q('#mode-key').value = '';
    q('.mode-feedback').textContent = local ? '' : '请在运行程序的电脑上打开 127.0.0.1 管理模式与 API。';
    q('.mode-test-result').textContent = settings.connection?.message || '';
    q('#mode-title').textContent = first ? '先选一种旅行规划方式' : '选择你的规划模式';
    render();
    if (!dialog.open) dialog.showModal();
  }
  async function perform(action) {
    if (busy) return;
    busy = true;
    q('.mode-feedback').textContent = '';
    render();
    try { await action(); }
    catch (error) { q('.mode-feedback').textContent = error.message; }
    finally { busy = false; render(); }
  }
  q('.mode-enter').onclick = () => perform(async () => {
    const key = q('#mode-key').value.trim();
    await request('settings', {mode: selected, ...(selected === 'ai' && key ? {api_key: key} : {})});
    q('#mode-key').value = '';
    first = false;
    dialog.close();
  });
  q('.mode-test').onclick = () => perform(async () => {
    const key = q('#mode-key').value.trim();
    if (key) {
      await request('settings', {mode: settings.mode, api_key: key});
      q('#mode-key').value = '';
    }
    q('.mode-test-result').textContent = '正在发送一次小额测试请求…';
    const result = await request('test');
    q('.mode-test-result').textContent = result.connection.message || '未能完成测试';
  });
  q('.mode-forget').onclick = () => perform(async () => {
    if (!window.confirm('移除本应用保存的 Key 并切回本地规划？不会注销你在 DeepSeek 的 Key。')) return;
    await request('settings', {mode: 'local', clear_key: true});
    selected = 'local';
    q('#mode-key').value = '';
    q('.mode-feedback').textContent = '已移除，后续规划不调用 AI。';
  });
  dialog.querySelectorAll('[data-mode]').forEach(b => b.onclick = () => {
    selected = b.dataset.mode;
    q('.mode-feedback').textContent = '';
    render();
  });
  q('.mode-close').onclick = () => dialog.close();
  dialog.addEventListener('cancel', event => { if (first || busy) event.preventDefault(); });
  dialog.addEventListener('close', () => { q('#mode-key').value = ''; badge.focus(); });
  badge.onclick = () => { open(); refresh(); };
  return {apply, refresh, open, isAI: () => settings?.enabled === true,
    init(data) { apply(data); if (!data.onboarded && local) open(true); }};
})();
