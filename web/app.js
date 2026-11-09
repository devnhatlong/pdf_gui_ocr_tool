// === app.js === Giao diện OfflineOCR Studio - gọi xuống Python qua window.pywebview.api
'use strict';
const $ = id => document.getElementById(id);
const S = {
  boot: null, settings: {}, docs: {}, thumbs: {}, page: 'overview',
  ocrDoc: '', ocrUid: '', ocrResult: null, img: null, zoom: 1, showBoxes: false, regionMode: false, quality: 'fast',
  savedRange: null, splitDoc: '', groups: [], scores: {}, sel: new Set(), anchor: null, cur: null,
  selGroup: 0, groupNames: {}, namesByDoc: {}, groupFields: {}, fieldsByDoc: {}, pageImgs: new Map(), viewKey: null, splitZoom: 1, dragUids: null, batchFiles: [], batchJob: null, jobs: {}, handled: new Set(), pollVersion: 0,
  system: null, cancelRequests: new Set(),
};
const GROUP_COLORS = ['#2164eb', '#0b9d70', '#f3a933', '#e75b67', '#8b5cf6', '#06b6d4', '#d946ef', '#84cc16'];
const BLOCK_LABELS = {
  text: 'Đoạn văn', paragraph_title: 'Tiêu đề đoạn', doc_title: 'Tiêu đề văn bản', table: 'Bảng',
  header: 'Đầu trang', footer: 'Chân trang', image: 'Hình ảnh', figure_title: 'Chú thích', number: 'Số trang',
  seal: 'Con dấu', formula: 'Công thức', abstract: 'Tóm tắt', content: 'Mục lục', reference: 'Tham khảo',
  aside_text: 'Ghi chú lề', chart: 'Biểu đồ', footnote: 'Chú thích cuối', vision_footnote: 'Chú thích hình',
  header_image: 'Ảnh đầu trang', footer_image: 'Ảnh chân trang', algorithm: 'Thuật toán', formula_number: 'Số công thức'
};
const PAGE_NAMES = {
  overview: 'Tổng quan', ocr: 'OCR tài liệu', split: 'Tách & ghép PDF', batch: 'Xử lý hàng loạt',
  history: 'Lịch sử', models: 'Quản lý mô hình', settings: 'Cài đặt'
};

// ---------------------------------------------------------------- tiện ích
async function call(name, ...args) {
  const r = await window.pywebview.api[name](...args);
  if (r && typeof r === 'object' && !Array.isArray(r) && r.error) throw new Error(r.error);
  return r;
}
function esc(s) { return String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c])); }
function debounce(fn, ms) { return (...a) => { clearTimeout(fn._t); fn._t = setTimeout(() => fn(...a), ms); }; }
function fmtTime(ts) {
  const d = new Date(ts * 1000), now = new Date();
  const hm = d.toLocaleTimeString('vi-VN', { hour: '2-digit', minute: '2-digit' });
  if (d.toDateString() === now.toDateString()) return 'Hôm nay ' + hm;
  const y = new Date(now - 864e5);
  if (d.toDateString() === y.toDateString()) return 'Hôm qua ' + hm;
  return d.toLocaleDateString('vi-VN') + ' ' + hm;
}
function baseName(p) { return String(p || '').split(/[\\/]/).pop(); }
// Icon Lucide nhúng sẵn (web/vendor/lucide/icons.js) - chạy offline
function ic(name, cls = '') {
  const p = (window.LUCIDE_ICONS || {})[name];
  return p ? `<svg class="ic ${cls}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${p}</svg>` : '';
}
function renderIcons(root = document) {
  root.querySelectorAll('i[data-ic]').forEach(el => { el.outerHTML = ic(el.dataset.ic, el.className); });
}
document.addEventListener('DOMContentLoaded', () => renderIcons());
const TOAST_ICONS = { ok: 'circle-check', warn: 'triangle-alert', info: 'info' };
function toast(msg, actions = [], ms = 4200, kind = 'info') {
  const el = $('toast');
  el.innerHTML = ic(TOAST_ICONS[kind] || 'info', 'tic') + esc(msg) + actions.map((a, i) => `<a data-i="${i}">${esc(a.label)}</a>`).join('');
  el.querySelectorAll('a').forEach(a => a.onclick = () => { actions[a.dataset.i].fn(); el.classList.remove('show'); });
  el.classList.add('show');
  clearTimeout(window.toastTimer);
  window.toastTimer = setTimeout(() => el.classList.remove('show'), actions.length ? ms + 3000 : ms);
}
function fail(e) { console.error(e); toast(e.message || String(e), [], 5000, 'warn'); }
function fileActions(path) {
  return [{ label: 'Mở file', fn: () => call('open_path', path).catch(fail) },
  { label: 'Mở thư mục', fn: () => call('reveal', path).catch(fail) }];
}
async function copyText(text) {
  try { await navigator.clipboard.writeText(text); } catch { await call('copy_text', text); }
  toast('Đã copy vào clipboard');
}

// ---------------------------------------------------------------- modal
let modalLocked = false;
function openModal(html, opts = {}) {
  $('modal').className = 'modal' + (opts.wide ? ' wide' : '');
  $('modal').innerHTML = html;
  modalLocked = !!opts.locked;
  $('modalShade').classList.add('show');
}
function closeModal() { if (!modalLocked) $('modalShade').classList.remove('show'); }
$('modalShade').addEventListener('click', e => { if (e.target === $('modalShade')) closeModal(); });
function confirmBox(title, text, okLabel = 'Đồng ý', extra = '') {
  return new Promise(res => {
    openModal(`<h2>${esc(title)}</h2><p class="sub">${esc(text)}</p>${extra}<div class="row between mt"><button class="btn" id="cNo">Hủy</button><button class="btn primary" id="cYes">${esc(okLabel)}</button></div>`);
    $('cNo').onclick = () => { closeModal(); res(false); };
    $('cYes').onclick = () => { const v = extra ? $('modal') : true; res(v); closeModal(); };
  });
}

// ---------------------------------------------------------------- khởi động
window.addEventListener('pywebviewready', init);
async function init() {
  try {
    S.boot = await call('bootstrap');
  } catch (e) { return fail(e); }
  S.settings = S.boot.settings;
  applyTheme(S.settings.theme);
  $('sbVersion').textContent = `Phiên bản ${S.boot.app.version}`;
  setThemeBusy(false);
  $('ocrEngine').innerHTML = S.boot.engines.map(e => `<option value="${e.key}">${esc(e.key === 'auto' ? 'Tự động' : e.label)}</option>`).join('');
  $('defaultEngine').innerHTML = $('ocrEngine').innerHTML;
  $('docTypeList').innerHTML = S.boot.doc_types.map(d => `<option value="${d.code}">${esc(d.label)}</option>`).join('');
  applyOcrDefaults();
  bindSettings();
  updateLicense(S.boot.license);
  document.querySelectorAll('.nav').forEach(el => el.addEventListener('click', () => navigate(el.dataset.page)));
  document.querySelectorAll('#ocrModes button').forEach(b => b.onclick = () => setQuality(b.dataset.mode));
  document.querySelectorAll('#ocrResultTabs button').forEach(b => b.onclick = () => resultTab(b.dataset.result));
  document.querySelectorAll('#settingsTabs button').forEach(b => b.onclick = () => settingsTab(b.dataset.settab));
  bindEditor();
  bindViewer();
  bindDrop();
  bindKeys();
  window.addEventListener('resize', debounce(() => applyZoom(), 150));
  setInterval(poll, 500);
  setInterval(refreshSystem, 3000);
  refreshSystem();
  navigate('overview');
  if (S.boot.license.state === 'expired') openLicense(true);
}
function applyTheme(value) {
  const theme = value === 'dark' ? 'dark' : 'light';
  document.documentElement.dataset.theme = theme;
  document.body.classList.toggle('dark', theme === 'dark');
  document.querySelectorAll('.theme-switch [data-theme]').forEach(button => {
    button.setAttribute('aria-pressed', String(button.dataset.theme === theme));
  });
  const select = document.querySelector('#settings [data-key="theme"]');
  if (select) select.value = theme;
  try { localStorage.setItem('offlineocr.theme', theme); } catch (_) {}
}
let themeSaving = false;
function setThemeBusy(busy) {
  document.querySelectorAll('.theme-switch button, #settings [data-key="theme"]').forEach(el => { el.disabled = busy; });
}
async function setTheme(theme) {
  if (!S.boot || themeSaving || !['light', 'dark'].includes(theme)) return;
  if (theme === S.settings.theme) { applyTheme(theme); return; }
  themeSaving = true;
  setThemeBusy(true);
  try { await saveSettings({ theme }); }
  finally { themeSaving = false; setThemeBusy(false); }
}
function applyOcrDefaults() {
  $('ocrEngine').value = S.settings.engine || 'auto';
  $('defaultEngine').value = S.settings.engine || 'auto';
  $('optRotate').checked = !!S.settings.auto_rotate;
  $('optDeskew').checked = !!S.settings.deskew;
  $('optDenoise').checked = !!S.settings.denoise;
  setQuality(S.settings.quality || 'fast', true);
  $('batchOut').textContent = S.settings.output_dir;
}

function navigate(page) {
  S.page = page;
  document.querySelectorAll('.page').forEach(el => el.classList.toggle('active', el.id === page));
  document.querySelectorAll('.nav').forEach(el => el.classList.toggle('active', el.dataset.page === page));
  $('breadcrumb').textContent = PAGE_NAMES[page];
  if (page === 'overview') renderOverview();
  if (page === 'history') renderHistory();
  if (page === 'models') renderModels();
  if (page === 'settings') loadSettingsForm();
  if (page === 'batch') renderBatchFiles();
  if (page === 'ocr') setTimeout(applyZoom, 30);
}

// ---------------------------------------------------------------- bản quyền
function updateLicense(lic) {
  S.license = lic;
  const p = $('pillLicense');
  p.textContent = lic.state === 'licensed' ? 'Đã kích hoạt' : lic.state === 'trial' ? `Dùng thử · ${lic.days} ngày` : 'Hết hạn dùng thử';
  p.title = 'Quản lý bản quyền';
  p.className = 'pill pillbtn ' + lic.state;
}
function openLicense(force = false) {
  const lic = S.license || {};
  openModal(`<h2>Bản quyền phần mềm</h2>
    <p class="sub">${lic.state === 'licensed' ? 'Phần mềm đã được kích hoạt.' : lic.state === 'trial' ? `Bạn đang dùng bản dùng thử - còn ${lic.days} ngày.` : 'Thời gian dùng thử đã hết. Vui lòng nhập License Key để tiếp tục sử dụng.'}</p>
    <div class="mutedbox" style="margin:14px 0"><div class="small muted">1. Copy Code của máy · 2. Gửi Code cho nhà cung cấp · 3. Dán License Key và bấm Kích hoạt</div></div>
    <label class="fieldlabel">Code của máy</label>
    <div class="row"><input class="input licensebox" style="flex:1" readonly value="${esc(lic.machine_id)}"><button class="btn" id="lCopy">${ic('copy')} Copy Code</button></div>
    <label class="fieldlabel mt">License Key</label><textarea class="input w100 licensebox" id="lKey" rows="3" placeholder="Dán License Key (Ctrl+V)"></textarea>
    <p class="small" id="lMsg" style="min-height:18px"></p>
    <div class="row between"><button class="btn" id="lClose">${force ? 'Thoát phần mềm' : 'Đóng'}</button><button class="btn primary" id="lAct">Kích hoạt</button></div>`, { locked: force });
  $('lCopy').onclick = () => copyText(lic.machine_id);
  $('lClose').onclick = () => { if (force) window.pywebview.api.quit_app && window.pywebview.api.quit_app(); else closeModal(); };
  $('lAct').onclick = async () => {
    try {
      const r = await call('activate_license', $('lKey').value);
      if (!r.ok) { $('lMsg').style.color = 'var(--red)'; $('lMsg').innerHTML = ic('circle-x') + ' ' + esc(r.message); return; }
      updateLicense(r.status);
      modalLocked = false; closeModal(); toast('Kích hoạt bản quyền thành công. Cảm ơn bạn!', [], 4200, 'ok');
      renderAbout();
    } catch (e) { fail(e); }
  };
}

// ---------------------------------------------------------------- tác vụ nền & hệ thống
async function poll() {
  let r;
  try { r = await window.pywebview.api.poll(S.pollVersion); } catch { return; }
  if (!r || r.error || r.version < S.pollVersion) return;
  S.pollVersion = r.version;
  r.jobs.forEach(j => { S.jobs[j.id] = j; onJob(j); });
  r.events.forEach(onEvent);
  renderFooter();
}
function activeJob() {
  return Object.values(S.jobs).filter(j => ['running', 'paused', 'queued', 'cancelling'].includes(j.status)).sort((a, b) => a.id - b.id)[0];
}
function renderFooter() {
  const j = activeJob();
  const prog = $('footerProg'), cancel = $('footerCancel');
  if (j) {
    const queued = Object.values(S.jobs).filter(x => x.status === 'queued').length;
    const cancelling = j.status === 'cancelling' || S.cancelRequests.has(j.id);
    const detail = cancelling ? 'Đang hủy…' : j.message && j.message !== j.title ? j.message : j.title;
    $('footerInfo').textContent = `${detail}${queued > 1 ? ` · ${queued - 1} tác vụ đang chờ` : ''}`;
    prog.classList.remove('hidden'); prog.firstElementChild.style.width = Math.round(j.progress * 100) + '%';
    cancel.classList.toggle('hidden', j.kind === 'warmup');
    cancel.disabled = cancelling;
    cancel.innerHTML = cancelling ? 'Đang hủy…' : `${ic('square')} Hủy`;
    cancel.onclick = () => cancelJob(j.id);
  } else {
    prog.classList.add('hidden'); cancel.classList.add('hidden');
    const last = Object.values(S.jobs).sort((a, b) => b.id - a.id)[0];
    $('footerInfo').textContent = last && !['warmup', 'split'].includes(last.kind) ? (last.message || last.title) : 'Sẵn sàng';
    $('footerInfo').title = $('footerInfo').textContent;
  }
}
async function cancelJob(id) {
  const job = S.jobs[id];
  if (!job || !['running', 'queued', 'paused'].includes(job.status) || S.cancelRequests.has(id)) return;
  S.cancelRequests.add(id);
  renderFooter();
  if (id === S.batchJob) renderBatchJob(job);
  try {
    const accepted = await call('job_cancel', id);
    if (!accepted) S.cancelRequests.delete(id);
    await poll();
  } catch (e) {
    S.cancelRequests.delete(id);
    fail(e);
  }
  renderFooter();
  if (id === S.batchJob && S.jobs[id]) renderBatchJob(S.jobs[id]);
}
function onJob(j) {
  if (['cancelling', 'cancelled', 'done', 'error'].includes(j.status)) S.cancelRequests.delete(j.id);
  if (j.kind === 'batch' && j.id === S.batchJob) renderBatchJob(j);
  if (j.kind === 'ocr' && j.meta.doc_id === S.ocrDoc) setOcrBusy(['running', 'queued', 'paused', 'cancelling'].includes(j.status));
  if (j.kind === 'split' && j.meta.doc_id === S.splitDoc) $('btnAnalyze').disabled = ['running', 'queued', 'paused', 'cancelling'].includes(j.status);
  if (!['done', 'error', 'cancelled'].includes(j.status) || S.handled.has(j.id)) return;
  S.handled.add(j.id);
  if (j.status === 'error') { toast(`${j.title}: ${j.error}`, [], 6000, 'warn'); return; }
  if (j.status === 'cancelled') { if (j.kind !== 'warmup') toast(`Đã hủy: ${j.title}`); refreshSystem(); if (S.page === 'models') renderModels(); return; }
  if (j.kind === 'warmup') refreshSystem();
  if (j.kind === 'ocr' && j.result) {
    if (j.result.notes && j.result.notes.length) toast(j.result.notes.join(' '), [], 7000);
    else toast(`Đã nhận dạng ${j.result.pages} trang trong ${j.result.seconds} giây`);
    if (j.result.doc_id === S.ocrDoc) { refreshOcrDoc(); loadOcrInfo(); }
  }
  if (j.kind === 'split' && j.result && j.result.doc_id === S.splitDoc) {
    toast(j.message); resetGroupNames(); S.selGroup = 0; S.cur = null; loadSplitGroups();
  }
  if (j.kind === 'model') { toast(j.message); if (S.page === 'models') renderModels(); refreshSystem(); }
  if (S.page === 'overview') renderOverview();
}
function onEvent(ev) {
  if (ev.type === 'page_ocr' && ev.doc_id === S.ocrDoc) {
    markThumb(ev.uid, 'ok');
    if (ev.uid === S.ocrUid) { showPageImage().then(loadOcrResult); }
  }
  if (ev.type === 'drop' && ev.paths && ev.paths.length) {
    if (S.page === 'batch') addBatchPaths(ev.paths);
    else openDocs(ev.paths, S.page === 'split' ? 'split' : 'ocr');
  }
}
async function refreshSystem() {
  let s;
  try { s = await call('system_status'); } catch { return; }
  S.system = s;
  $('footerLeft').textContent = systemLabel(s);
  if (S.page === 'overview') renderSysBars();
}
function systemLabel(s) {
  if (!s || !s.engine || s.engine === 'Đang khởi động') return '';
  const device = s.device && s.device !== '-' ? s.device : '';
  return [...new Set([device, s.engine].filter(Boolean))].join(' · ');
}
function bar(label, pct, right) {
  pct = Math.max(0, Math.min(100, pct || 0));
  return `<div class="sysrow"><div class="row between"><span>${esc(label)}</span><span class="muted">${esc(right)}</span></div><div class="progress"><span style="width:${pct}%"></span></div></div>`;
}
function renderSysBars() {
  const s = S.system;
  if (!s) return;
  let h = bar('CPU', s.cpu, `${s.cpu}% · ${s.cpu_count} luồng`) +
    bar('RAM hệ thống', s.ram_percent, `${s.ram_used_gb} / ${s.ram_total_gb} GB · phần mềm dùng ${s.process_ram_gb} GB`);
  if (s.gpus.length) s.gpus.forEach(g => {
    h += bar(`GPU · ${g.name}`, g.util, `${g.util}%`) + bar('VRAM', g.used_mb / g.total_mb * 100, `${(g.used_mb / 1024).toFixed(1)} / ${(g.total_mb / 1024).toFixed(1)} GB`);
  });
  else h += `<p class="small muted">Không phát hiện GPU NVIDIA - đang xử lý bằng CPU.</p>`;
  if (s.models.length) h += `<p class="small muted" style="margin-bottom:0">Mô hình đang dùng: ${s.models.map(m => '<span class="chip">' + esc(m.name) + '</span>').join(' ')}</p>`;
  $('sysBars').innerHTML = h;
  $('sysEngine').textContent = systemLabel(s) || 'Đang chuẩn bị';
}

// ---------------------------------------------------------------- tổng quan
async function renderOverview() {
  let d;
  try { d = await call('dashboard'); } catch (e) { return fail(e); }
  const st = d.stats;
  $('mPages').textContent = Number(st.pages).toLocaleString('vi-VN');
  $('mTasks').textContent = `${st.tasks} tác vụ`;
  $('mDocs').textContent = Number(st.split_docs).toLocaleString('vi-VN');
  $('mOk').textContent = `${st.done} / ${st.errors}`;
  $('mConf').textContent = 'Độ tin cậy: ' + (st.confidence != null ? st.confidence + '%' : '-');
  const ready = d.models.filter(m => m.ready).length;
  $('mModels').textContent = `${ready}/${d.models.length}`;
  $('mModelsLoaded').textContent = d.models.some(m => m.loaded) ? `${d.models.filter(m => m.loaded).length} đang sử dụng` : 'Chưa sử dụng';
  $('recentList').innerHTML = d.recent.length ? d.recent.map(r => `<div class="row between" style="margin-bottom:12px"><div><b>${ic('file-text', 'muted')}<span>${esc(r.name)}</span></b><div class="small muted" style="margin:5px 0 0 25px">${esc(r.kind_label)} · ${r.pages} trang${r.doc_count ? ' · ' + r.doc_count + ' văn bản' : ''} · ${fmtTime(r.created)}</div></div>${statusChip(r.status)}</div>`).join('')
    : '<div class="empty">Chưa có tài liệu đã xử lý.</div>';
  S.system = d.system; renderSysBars();
}
function statusChip(s) {
  const map = { done: 'Hoàn thành', error: 'Lỗi', cancelled: 'Đã hủy', running: 'Đang chạy', queued: 'Đang chờ', paused: 'Tạm dừng', cancelling: 'Đang hủy…' };
  return `<span class="status ${s === 'done' ? '' : s}">${map[s] || s}</span>`;
}
function quickOcr() { navigate('ocr'); addDocuments('ocr'); }

// ---------------------------------------------------------------- tài liệu
async function addDocuments(target) {
  try {
    const paths = await call('pick_files', true);
    if (paths && paths.length) await openDocs(paths, target);
  } catch (e) { fail(e); }
}
async function openDocs(paths, target) {
  $('footerInfo').textContent = 'Đang mở tài liệu…';
  try {
    const r = await call('open_documents', paths);
    r.docs.forEach(d => { S.docs[d.id] = d; });
    if (r.errors.length) toast('Không mở được: ' + r.errors.join('; '), [], 7000);
    refreshDocSelects();
    if (!r.docs.length) return;
    if (target === 'split') { navigate('split'); await selectSplitDoc(r.docs[0].id); }
    else { navigate('ocr'); await selectOcrDoc(r.docs[0].id); }
    if (r.docs.length > 1) toast(`Đã mở ${r.docs.length} tài liệu - chọn ở danh sách phía trên`);
    else if (r.docs[0].pages.some(p => p.ocr)) toast('Đã khôi phục bản nháp OCR đã lưu của tài liệu này');
    $('footerInfo').textContent = `Đã mở ${r.docs.length} tài liệu`;
  } catch (e) { fail(e); }
}
function refreshDocSelects() {
  const opts = Object.values(S.docs).map(d => `<option value="${d.id}">${esc(d.name)} · ${d.page_count} trang</option>`).join('');
  const empty = '<option value="">- Chưa có tài liệu -</option>';
  $('ocrDocSelect').innerHTML = opts || empty; $('ocrDocSelect').value = S.ocrDoc;
  $('splitDocSelect').innerHTML = opts || empty; $('splitDocSelect').value = S.splitDoc;
  renderMergeList();
}
async function loadThumbs(docId, uids) {
  const list = await call('thumbnails', docId, uids || null);
  S.thumbs[docId] = S.thumbs[docId] || {};
  list.forEach(t => S.thumbs[docId][t.uid] = t.src);
}

// ---------------------------------------------------------------- OCR
function setQuality(q, silent) {
  S.quality = q;
  document.querySelectorAll('#ocrModes button').forEach(b => b.classList.toggle('active', b.dataset.mode === q));
}
async function selectOcrDoc(id) {
  if (!id) return;
  S.ocrDoc = id; $('ocrDocSelect').value = id;
  try {
    const doc = await call('document', id); S.docs[id] = doc;
    await loadThumbs(id);
    renderOcrThumbs();
    await selectOcrPage(doc.pages[0].uid);
    loadOcrInfo();
  } catch (e) { fail(e); }
}
async function refreshOcrDoc() {
  if (!S.ocrDoc) return;
  const doc = await call('document', S.ocrDoc); S.docs[S.ocrDoc] = doc;
  await loadThumbs(S.ocrDoc);
  renderOcrThumbs();
  if (S.ocrUid) { await showPageImage(); await loadOcrResult(); }
}
function renderOcrThumbs() {
  const doc = S.docs[S.ocrDoc];
  if (!doc) return;
  $('ocrPageCount').textContent = `${doc.pages.findIndex(p => p.uid === S.ocrUid) + 1 || 1} / ${doc.page_count}`;
  $('ocrThumbs').innerHTML = doc.pages.map((p, i) => `<div class="thumb ${p.uid === S.ocrUid ? 'active' : ''}" data-uid="${p.uid}"><img src="${S.thumbs[doc.id][p.uid] || ''}" loading="lazy"><div class="tstate small muted"><span class="sdot ${p.edited ? 'edit' : p.ocr ? 'ok' : ''}" id="dot_${p.uid}"></span>Trang ${i + 1}</div></div>`).join('');
  $('ocrThumbs').querySelectorAll('.thumb').forEach(t => t.onclick = () => selectOcrPage(t.dataset.uid));
}
function markThumb(uid, state) {
  const d = $('dot_' + uid);
  if (d) d.className = 'sdot ' + state;
  const doc = S.docs[S.ocrDoc];
  const p = doc && doc.pages.find(x => x.uid === uid);
  if (p && state === 'ok') p.ocr = true;
}
async function selectOcrPage(uid) {
  await flushEdit();
  S.ocrUid = uid;
  document.querySelectorAll('#ocrThumbs .thumb').forEach(t => t.classList.toggle('active', t.dataset.uid === uid));
  const doc = S.docs[S.ocrDoc];
  const idx = doc.pages.findIndex(p => p.uid === uid);
  $('pageIndicator').textContent = `Trang ${idx + 1}`;
  $('ocrPageCount').textContent = `${idx + 1} / ${doc.page_count}`;
  await showPageImage();
  await loadOcrResult();
}
async function showPageImage() {
  if (!S.ocrDoc || !S.ocrUid) return;
  const img = await call('page_image', S.ocrDoc, S.ocrUid, 1800);
  S.img = img;
  $('viewer').innerHTML = `<div class="pagewrap" id="pagewrap"><img src="${img.src}" draggable="false"><div class="boxlayer ${S.showBoxes ? 'show' : ''}" id="boxlayer"></div><div class="regionsel" id="regionsel"></div></div>`;
  $('viewer').classList.toggle('regionmode', S.regionMode);
  applyZoom();
}
function applyZoom() {
  const wrap = $('pagewrap');
  if (!wrap || !S.img) return;
  const avail = $('paperWrap').clientWidth - 30;
  const w = Math.max(200, avail * S.zoom);
  wrap.style.width = w + 'px';
  $('zoomLabel').textContent = S.zoom === 1 ? 'Vừa khung' : Math.round(S.zoom * 100) + '%';
}
function zoom(d) { S.zoom = d === 0 ? 1 : Math.max(0.4, Math.min(4, S.zoom * (d > 0 ? 1.25 : 0.8))); applyZoom(); }
function toggleBoxes() {
  S.showBoxes = !S.showBoxes;
  $('btnBoxes').classList.toggle('on', S.showBoxes);
  const l = $('boxlayer'); if (l) l.classList.toggle('show', S.showBoxes);
  if (S.showBoxes && !(S.ocrResult && S.ocrResult.lines.length)) toast('Trang chưa có kết quả OCR để hiển thị khung tọa độ');
}
function toggleRegion() {
  S.regionMode = !S.regionMode;
  $('btnRegion').classList.toggle('on', S.regionMode);
  $('viewer').classList.toggle('regionmode', S.regionMode);
  if (S.regionMode) toast('Kéo chuột trên ảnh để chọn vùng cần OCR lại');
}
function drawBoxes() {
  const layer = $('boxlayer'), r = S.ocrResult;
  if (!layer) return;
  if (!r || !r.size || !r.size[0]) { layer.innerHTML = ''; return; }
  const [W, H] = r.size, thr = r.threshold || 0.8;
  const pos = b => `left:${b[0] / W * 100}%;top:${b[1] / H * 100}%;width:${(b[2] - b[0]) / W * 100}%;height:${(b[3] - b[1]) / H * 100}%`;
  layer.innerHTML = r.lines.map((ln, i) => `<div class="obox ${ln.score != null && ln.score < thr ? 'low' : ''}" data-i="${i}" style="${pos(ln.box)}" title="${esc(ln.text)}${ln.score != null ? ' · ' + Math.round(ln.score * 100) + '%' : ''}"></div>`).join('') +
    (r.blocks || []).map((b, i) => `<div class="obox block" id="blk_${i}" style="${pos(b.box)}"></div>`).join('');
  layer.querySelectorAll('.obox[data-i]').forEach(el => el.onclick = () => focusLine(r.lines[el.dataset.i].text));
}
function focusLine(text) {
  const rows = [...$('editor').querySelectorAll('.eline')];
  const row = rows.find(r => r.textContent.includes(text.slice(0, 30)));
  rows.forEach(r => r.classList.remove('hit'));
  if (row) { row.classList.add('hit'); row.scrollIntoView({ block: 'center' }); resultTab('text'); }
}
function setOcrBusy(busy) {
  $('btnOcrAll').disabled = busy; $('btnOcrPage').disabled = busy;
  $('btnOcrAll').innerHTML = busy ? ic('loader-circle', 'spin') + ' Đang nhận dạng…' : ic('sparkles') + ' Bắt đầu OCR';
}
async function runOcr(scope) {
  if (!S.ocrDoc) return addDocuments('ocr');
  await flushEdit();
  const engine = $('ocrEngine').value;
  if (engine === 'vl' && S.system && S.system.device === 'CPU') {
    const ok = await confirmBox('PaddleOCR-VL trên CPU', 'Máy không có GPU: mỗi trang có thể mất vài phút. Bạn vẫn có thể làm việc khác trong lúc chờ.', 'Vẫn chạy');
    if (!ok) return;
  }
  const opts = { quality: S.quality, engine, auto_rotate: $('optRotate').checked, deskew: $('optDeskew').checked, denoise: $('optDenoise').checked };
  const uids = scope === 'page' ? [S.ocrUid] : null;
  try {
    await call('ocr_run', S.ocrDoc, uids, opts);
    (uids || S.docs[S.ocrDoc].pages.map(p => p.uid)).forEach(u => markThumb(u, 'run'));
    setOcrBusy(true);
  } catch (e) { fail(e); }
}
async function loadOcrResult() {
  if (!S.ocrDoc || !S.ocrUid) return;
  const r = await call('ocr_result', S.ocrDoc, S.ocrUid);
  S.ocrResult = r;
  if (!r) {
    $('editor').innerHTML = '<div class="empty">Trang này chưa được nhận dạng.<br>Bấm “OCR trang này” hoặc “Bắt đầu OCR”.</div>';
    $('editor').contentEditable = 'false';
    $('ocrResultStatus').textContent = 'Chưa nhận dạng';
    $('resultChip').textContent = 'Chưa có kết quả';
    $('tableView').innerHTML = '<div class="empty">Chưa có kết quả</div>';
    $('layoutView').innerHTML = '';
    drawBoxes();
    return;
  }
  renderEditor(r);
  renderTables(r.markdown);
  renderLayout(r);
  drawBoxes();
  const conf = r.confidence != null ? ` · tin cậy ${Math.round(r.confidence * 100)}%` : '';
  const low = r.lines.filter(l => l.score != null && l.score < r.threshold).length;
  $('ocrResultStatus').textContent = `${r.engine} · ${r.seconds}s${conf}${low ? ` · ${low} dòng cần kiểm tra` : ''}`;
  $('resultChip').textContent = r.edited ? 'Đã chỉnh sửa' : 'Có thể chỉnh sửa';
}
function renderEditor(r) {
  const ed = $('editor');
  ed.contentEditable = 'true';
  const lowTexts = r.edited ? [] : r.lines.filter(l => l.score != null && l.score < r.threshold).map(l => l.text);
  const rows = (r.text || '').split('\n');
  ed.innerHTML = rows.map(t => `<div class="eline ${lowTexts.some(x => x && t.includes(x)) ? 'low' : ''}">${t ? esc(t) : '<br>'}</div>`).join('') || '<div class="eline"><br></div>';
  ed.dataset.dirty = '';
}
function editorText() {
  const rows = [...$('editor').children].map(el => el.innerText.replace(/\n$/, ''));
  return rows.join('\n');
}
function bindEditor() {
  const ed = $('editor');
  ed.addEventListener('input', () => { ed.dataset.dirty = '1'; saveEditSoon(); });
  ed.addEventListener('blur', () => {
    const sel = window.getSelection();
    if (sel.rangeCount && ed.contains(sel.anchorNode)) S.savedRange = sel.getRangeAt(0).cloneRange();
  });
  ed.addEventListener('paste', e => {   // dán chữ thuần, không mang định dạng
    e.preventDefault();
    document.execCommand('insertText', false, (e.clipboardData || window.clipboardData).getData('text'));
  });
}
const saveEditSoon = debounce(() => flushEdit(), 800);
async function flushEdit() {
  const ed = $('editor');
  if (!ed.dataset.dirty || !S.ocrDoc || !S.ocrUid) return;
  ed.dataset.dirty = '';
  try {
    await call('save_edit', S.ocrDoc, S.ocrUid, editorText());
    $('resultChip').textContent = 'Đã chỉnh sửa';
    markThumb(S.ocrUid, 'edit');
  } catch (e) { fail(e); }
}
async function saveDraft() {
  if (!S.ocrDoc) return;
  await flushEdit();
  try { await call('save_draft', S.ocrDoc); toast('Đã lưu bản nháp - lần sau mở lại tài liệu này sẽ khôi phục kết quả'); } catch (e) { fail(e); }
}
function copyResult() { copyText(editorText()); }
function openFind() { $('findBar').classList.toggle('hidden'); if (!$('findBar').classList.contains('hidden')) $('findText').focus(); }
function findNext() {
  const q = $('findText').value;
  if (!q) return;
  const rows = [...$('editor').querySelectorAll('.eline')];
  rows.forEach(r => r.classList.remove('hit'));
  const hits = rows.filter(r => r.textContent.toLowerCase().includes(q.toLowerCase()));
  hits.forEach(r => r.classList.add('hit'));
  $('findInfo').textContent = `${hits.length} dòng khớp`;
  if (hits[0]) { hits[0].scrollIntoView({ block: 'center' }); window.find && window.find(q); }
}
function replaceAll() {
  const q = $('findText').value, rep = $('replaceText').value;
  if (!q) return;
  let n = 0;
  const re = new RegExp(q.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'gi');
  $('editor').querySelectorAll('.eline').forEach(r => {
    const t = r.textContent;
    if (re.test(t)) { re.lastIndex = 0; const c = (t.match(re) || []).length; n += c; r.textContent = t.replace(re, rep); }
  });
  $('findInfo').textContent = `Đã thay ${n} chỗ`;
  $('editor').dataset.dirty = '1'; flushEdit();
}
function resultTab(k) {
  document.querySelectorAll('#ocrResultTabs button').forEach(x => x.classList.toggle('active', x.dataset.result === k));
  ['text', 'table', 'layout', 'info'].forEach(t => $('ocr' + t[0].toUpperCase() + t.slice(1) + 'Area').classList.toggle('hidden', t !== k));
  if (k === 'info') loadOcrInfo();
}
function sanitizeTable(html) {
  const tpl = document.createElement('template');
  tpl.innerHTML = html;
  const allowed = new Set(['TABLE', 'THEAD', 'TBODY', 'TR', 'TD', 'TH', 'BR']);
  tpl.content.querySelectorAll('*').forEach(el => {
    if (!allowed.has(el.tagName)) { el.replaceWith(...el.childNodes); return; }
    [...el.attributes].forEach(a => { if (!['rowspan', 'colspan'].includes(a.name)) el.removeAttribute(a.name); });
  });
  return tpl.innerHTML;
}
function renderTables(md) {
  const out = [];
  (md || '').replace(/<table[\s\S]*?<\/table>/gi, t => { out.push(sanitizeTable(t)); return t; });
  // bảng Markdown dạng |a|b|
  const lines = (md || '').split('\n'); let rows = [];
  const flush = () => { if (rows.length) out.push('<table>' + rows.map(r => '<tr>' + r.map(c => `<td>${esc(c)}</td>`).join('') + '</tr>').join('') + '</table>'); rows = []; };
  lines.forEach(l => { const t = l.trim(); if (/^\|.*\|$/.test(t)) { if (!/^\|[\s:\-|]+\|$/.test(t)) rows.push(t.slice(1, -1).split('|').map(c => c.trim())); } else flush(); });
  flush();
  $('tableView').innerHTML = out.length ? out.join('') : '<div class="empty">Không phát hiện bảng biểu trên trang này.<br>Chọn chế độ “Tự động”, “Chính xác” hoặc model PP-StructureV3 rồi OCR lại trang để nhận dạng bảng.</div>';
}
function renderLayout(r) {
  const blocks = r.blocks || [];
  if (!blocks.length) {
    $('layoutView').innerHTML = `<div class="mutedbox small">Chế độ ${esc(r.engine)} chỉ nhận dạng ${r.lines.length} dòng chữ, không phân tích bố cục.<br>Dùng chế độ “Tự động/Chính xác” hoặc model PP-StructureV3 / PaddleOCR-VL để tách vùng tiêu đề, đoạn văn, bảng, chữ ký…</div>`;
    return;
  }
  $('layoutView').innerHTML = blocks.map((b, i) => `<div class="layoutitem" data-i="${i}"><b>Vùng ${i + 1}: ${esc(BLOCK_LABELS[b.label] || b.label)}</b><div class="muted" style="margin-top:4px">${esc((b.content || '').replace(/<[^>]+>/g, ' ').slice(0, 140))}</div></div>`).join('');
  $('layoutView').querySelectorAll('.layoutitem').forEach(el => el.onclick = () => {
    document.querySelectorAll('.obox.block').forEach(x => x.classList.remove('active'));
    const box = $('blk_' + el.dataset.i);
    if (box) { box.classList.add('active'); box.scrollIntoView({ block: 'center' }); }
  });
}
// --- thông tin văn bản & đặt tên
async function loadOcrInfo() {
  if (!S.ocrDoc) return;
  try {
    const r = await call('doc_metadata', S.ocrDoc);
    const f = r.fields || {};
    $('fLoai').value = f.loai || ''; $('fCoquan').value = f.coquan || ''; $('fSo').value = f.so || '';
    $('fNgay').value = f.ngay || ''; $('fTrich').value = f.trichyeu || '';
    $('fFilename').value = r.filename || '';
  } catch (e) { fail(e); }
}
const updateFilename = debounce(async () => {
  const fields = { loai: $('fLoai').value, coquan: $('fCoquan').value, so: $('fSo').value, ngay: $('fNgay').value, trichyeu: $('fTrich').value };
  try { $('fFilename').value = await call('build_filename', fields); } catch (e) { fail(e); }
}, 250);
async function renameSource() {
  const name = $('fFilename').value.trim();
  if (!name) return toast('Chưa có tên file mới - hãy OCR hoặc điền thông tin văn bản');
  try {
    const r = await call('rename_source', S.ocrDoc, name);
    if (!r.ok) return toast(r.message, [], 5000, 'warn');
    S.docs[S.ocrDoc].name = r.name; refreshDocSelects();
    toast('Đã đổi tên file: ' + r.name, fileActions(r.path));
  } catch (e) { fail(e); }
}
async function exportWithName() {
  const name = $('fFilename').value.trim();
  try {
    const r = await call('export_document', S.ocrDoc, 'pdf', 'all', null, null, name || null);
    if (r.path) toast('Đã lưu ' + baseName(r.path), fileActions(r.path));
  } catch (e) { fail(e); }
}
// --- xuất kết quả
function openExport(preset) {
  if (!S.ocrDoc) return toast('Chưa có tài liệu để xuất');
  const fmts = S.boot.formats.map(f => `<option value="${f.key}" ${f.key === (preset || S.settings.export_format) ? 'selected' : ''}>${esc(f.label)}</option>`).join('');
  openModal(`<h2>Xuất kết quả OCR</h2><p class="sub">${esc(S.docs[S.ocrDoc].name)}</p>
    <label class="fieldlabel mt">Định dạng</label><select id="exFmt" class="select w100">${fmts}</select>
    <label class="fieldlabel mt">Phạm vi</label><div class="seg" id="exScope"><button class="active" data-v="all">Toàn bộ tài liệu</button><button data-v="page">Trang đang xem</button></div>
    <div class="notice" style="margin:15px 0">Word giữ đoạn văn và bảng biểu; Excel/CSV xuất các bảng phát hiện được; PDF có lớp chữ giữ nguyên ảnh gốc và cho phép tìm kiếm, sao chép.</div>
    <div class="row between"><button class="btn" onclick="closeModal()">Hủy</button><button class="btn primary" id="exGo">${ic('download')} Chọn nơi lưu & xuất</button></div>`);
  let scope = 'all';
  $('exScope').querySelectorAll('button').forEach(b => b.onclick = () => { scope = b.dataset.v; $('exScope').querySelectorAll('button').forEach(x => x.classList.toggle('active', x === b)); });
  $('exGo').onclick = async () => {
    await flushEdit();
    try {
      const r = await call('export_document', S.ocrDoc, $('exFmt').value, scope, S.ocrUid, null, null);
      closeModal();
      if (r.path) toast('Đã xuất ' + baseName(r.path), fileActions(r.path));
    } catch (e) { closeModal(); fail(e); }
  };
}
// --- vùng chọn để OCR lại
function bindViewer() {
  const v = $('viewer');
  let start = null;
  const rel = e => { const r = $('pagewrap').getBoundingClientRect(); return [Math.min(1, Math.max(0, (e.clientX - r.left) / r.width)), Math.min(1, Math.max(0, (e.clientY - r.top) / r.height))]; };
  v.addEventListener('mousedown', e => {
    if (!S.regionMode || !$('pagewrap')) return;
    start = rel(e); e.preventDefault();
  });
  window.addEventListener('mousemove', e => {
    if (!start) return;
    const p = rel(e), s = $('regionsel');
    s.style.display = 'block';
    s.style.left = Math.min(p[0], start[0]) * 100 + '%'; s.style.top = Math.min(p[1], start[1]) * 100 + '%';
    s.style.width = Math.abs(p[0] - start[0]) * 100 + '%'; s.style.height = Math.abs(p[1] - start[1]) * 100 + '%';
  });
  window.addEventListener('mouseup', async e => {
    if (!start) return;
    const p = rel(e), box = [Math.min(p[0], start[0]), Math.min(p[1], start[1]), Math.max(p[0], start[0]), Math.max(p[1], start[1])];
    start = null;
    if (box[2] - box[0] < 0.01 || box[3] - box[1] < 0.005) { $('regionsel').style.display = 'none'; return; }
    $('footerInfo').textContent = 'Đang OCR vùng chọn…';
    try {
      const r = await call('ocr_region', S.ocrDoc, S.ocrUid, box);
      showRegionResult(r);
    } catch (err) { fail(err); }
    $('regionsel').style.display = 'none';
  });
}
function showRegionResult(r) {
  openModal(`<h2>Kết quả OCR vùng chọn</h2><p class="sub small">${esc(r.engine || '')}</p>
    <textarea class="input w100" id="regText" rows="6">${esc(r.text)}</textarea>
    <div class="row between mt"><button class="btn" onclick="closeModal()">Đóng</button><div class="row"><button class="btn" id="regCopy">${ic('copy')} Copy</button><button class="btn primary" id="regInsert">${ic('corner-down-right')} Chèn vào vị trí con trỏ</button></div></div>`);
  $('regCopy').onclick = () => copyText($('regText').value);
  $('regInsert').onclick = () => {
    const text = $('regText').value;
    const ed = $('editor');
    ed.focus();
    const sel = window.getSelection();
    if (S.savedRange) { sel.removeAllRanges(); sel.addRange(S.savedRange); }
    else { const rg = document.createRange(); rg.selectNodeContents(ed); rg.collapse(false); sel.removeAllRanges(); sel.addRange(rg); }
    document.execCommand('insertText', false, text);
    closeModal(); resultTab('text');
  };
}

// ---------------------------------------------------------------- CẮT GHÉP & TÁCH AI
async function selectSplitDoc(id) {
  if (!id) return;
  S.splitDoc = id; $('splitDocSelect').value = id;
  S.sel = new Set(); S.cur = null; S.selGroup = 0; S.viewKey = null;
  S.groupNames = S.namesByDoc[id] = S.namesByDoc[id] || {};
  S.groupFields = S.fieldsByDoc[id] = S.fieldsByDoc[id] || {};
  $('btnSplitTools').disabled = $('btnExportGroups').disabled = false;
  $('btnAnalyze').disabled = Object.values(S.jobs).some(j => j.kind === 'split' && j.meta.doc_id === id && ['running', 'queued', 'paused', 'cancelling'].includes(j.status));
  try {
    await loadThumbs(id);
    await loadSplitGroups();
  } catch (e) { fail(e); }
}
function resetGroupNames() { S.groupNames = S.namesByDoc[S.splitDoc] = {}; S.groupFields = S.fieldsByDoc[S.splitDoc] = {}; }
function forgetGroup(uid) { delete S.groupNames[uid]; delete S.groupFields[uid]; }
async function loadSplitGroups() {
  const r = await call('split_groups', S.splitDoc);
  S.groups = r.groups || []; S.scores = r.scores || {};
  S.groups.forEach(g => { if (S.groupNames[g.start_uid]) g.name = S.groupNames[g.start_uid]; });
  S.docs[S.splitDoc].pages = r.pages; S.docs[S.splitDoc].page_count = r.pages.length;
  refreshDocSelects();
  renderSplit();
}
async function refreshSplitDoc(keepGroups = true, starts = null) {
  const doc = await call('document', S.splitDoc);
  S.docs[S.splitDoc] = doc;
  const missing = doc.pages.filter(p => !(S.thumbs[doc.id] || {})[p.uid]).map(p => p.uid);
  if (missing.length) await loadThumbs(doc.id, missing);
  if (keepGroups && S.groups.length) {
    const exist = new Set(doc.pages.map(p => p.uid));
    const r = await call('split_set', S.splitDoc, (starts || startsList()).filter(u => exist.has(u)), S.groupNames);
    S.groups = r.groups;
  } else if (!keepGroups) S.groups = [];
  refreshDocSelects();
  renderSplit();
}
function groupIndexOf(uid) { return S.groups.findIndex(g => g.uids.includes(uid)); }
function renderSplit() {
  const doc = S.docs[S.splitDoc];
  if (!doc) return;
  const thr = S.settings.split_threshold || 70;
  if (!doc.pages.some(p => p.uid === S.cur)) {
    S.cur = (S.groups[S.selGroup] || {}).start_uid || doc.pages[0].uid;
    S.sel = new Set();
  }
  const gi = groupIndexOf(S.cur);
  S.selGroup = gi >= 0 ? gi : Math.max(0, Math.min(S.selGroup, S.groups.length - 1));
  renderPageRail(doc);
  renderGroups();
  renderSelected();
  showSplitPage();
  $('countDocs').textContent = S.groups.length;
  $('splitInfo').textContent = S.groups.length ? `${S.groups.length} văn bản · ${S.groups.filter(g => g.confidence < thr).length} điểm tách cần kiểm tra` : `${doc.pages.length} trang · chưa phân tích`;
}
function renderPageRail(doc) {
  const starts = new Map(S.groups.map((g, i) => [g.start_uid, i]));
  let html = '', open = false;
  doc.pages.forEach((p, i) => {
    if (starts.has(p.uid)) {
      const n = starts.get(p.uid), g = S.groups[n];
      html += `${open ? '</div>' : ''}<div class="railhead ${S.selGroup === n ? 'chosen' : ''}"><span class="gdot" style="background:${GROUP_COLORS[n % GROUP_COLORS.length]}"></span>Văn bản ${n + 1}<span class="muted">${g.uids.length} trang</span></div><div class="railgrid">`;
      open = true;
    } else if (!open) { html += '<div class="railgrid">'; open = true; }
    const cls = ['pagecard', S.cur === p.uid ? 'selected' : '', S.sel.has(p.uid) && S.cur !== p.uid ? 'multi' : '', p.blank ? 'blankpg' : ''].join(' ');
    const tag = p.blank ? '<span class="tag">Trắng</span>' : (p.codes && p.codes.length ? '<span class="tag">QR</span>' : '');
    html += `<div class="${cls}" data-uid="${p.uid}" draggable="true"><div class="sheet"><img src="${(S.thumbs[doc.id] || {})[p.uid] || ''}" loading="lazy" draggable="false">${tag}<span class="num">${i + 1}</span></div></div>`;
  });
  $('pageStrip').innerHTML = html + (open ? '</div>' : '');
  bindPageCards();
  const cur = $('pageStrip').querySelector('.pagecard.selected');
  if (cur) cur.scrollIntoView({ block: 'nearest' });
}
function bindPageCards() {
  // Ô "tạo văn bản mới" chỉ hiện khi đang kéo trang
  const zone = $('newDocDrop');
  zone.ondragover = e => { e.preventDefault(); zone.classList.add('over'); };
  zone.ondragleave = () => zone.classList.remove('over');
  zone.ondrop = e => {
    e.preventDefault(); e.stopPropagation(); zone.classList.remove('over'); document.body.classList.remove('dragpages');
    if (S.dragUids) isolatePages(S.dragUids);
  };
  $('pageStrip').querySelectorAll('.pagecard').forEach(card => {
    const uid = card.dataset.uid;
    const dropAfter = e => { const r = card.getBoundingClientRect(); return e.clientX > r.left + r.width / 2; };
    card.onclick = e => selectPage(uid, e);
    card.ondragstart = e => { S.dragUids = S.sel.has(uid) ? [...S.sel] : [uid]; card.classList.add('dragging'); document.body.classList.add('dragpages'); e.dataTransfer.setData('text/plain', uid); };
    card.ondragend = () => { card.classList.remove('dragging'); document.body.classList.remove('dragpages'); };
    card.ondragover = e => { e.preventDefault(); card.classList.toggle('dropafter', dropAfter(e)); card.classList.toggle('dropbefore', !dropAfter(e)); };
    card.ondragleave = () => card.classList.remove('dropbefore', 'dropafter');
    card.ondrop = e => {
      e.preventDefault(); e.stopPropagation(); card.classList.remove('dropbefore', 'dropafter');
      if (S.dragUids && !S.dragUids.includes(uid)) movePages(S.dragUids, uid, dropAfter(e));
    };
  });
}
function selectPage(uid, e = {}) {
  const pages = S.docs[S.splitDoc].pages.map(p => p.uid);
  if (e.shiftKey && S.anchor) {
    const [a, b] = [pages.indexOf(S.anchor), pages.indexOf(uid)].sort((x, y) => x - y);
    S.sel = new Set(pages.slice(a, b + 1));
  } else if (e.ctrlKey || e.metaKey) {
    S.sel.has(uid) ? S.sel.delete(uid) : S.sel.add(uid); S.anchor = uid;
  } else { S.sel = new Set([uid]); S.anchor = uid; }
  S.cur = uid;
  renderSplit();
}
function stepPage(d) {
  const doc = S.docs[S.splitDoc];
  if (!doc) return;
  const next = doc.pages[doc.pages.findIndex(p => p.uid === S.cur) + d];
  if (next) selectPage(next.uid);
}
function renderGroups() {
  const thr = S.settings.split_threshold || 70;
  const pages = S.docs[S.splitDoc].pages.map(p => p.uid);
  if (!S.groups.length) { $('groups').innerHTML = '<div class="empty small">Bấm “Phân tích tài liệu” để tự tìm các văn bản, hoặc chọn một trang rồi bấm “Tách từ trang này”.</div>'; return; }
  $('groups').innerHTML = S.groups.map((g, i) => {
    const a = pages.indexOf(g.uids[0]) + 1, b = pages.indexOf(g.uids[g.uids.length - 1]) + 1;
    const cc = g.confidence < thr ? 'low' : g.confidence < 90 ? 'mid' : '';
    return `<div class="docgroup ${S.selGroup === i ? 'chosen' : ''} ${g.confidence < thr ? 'low' : ''}" data-i="${i}"><div class="row between"><strong style="font-size:12px"><span class="gdot" style="background:${GROUP_COLORS[i % GROUP_COLORS.length]}"></span><span class="gname">${esc(g.name)}</span></strong>${g.reasons.length ? `<span class="confidence ${cc}">${g.confidence}%</span>` : ''}</div><div class="muted small" style="margin:7px 0 0 15px">Trang ${a}–${b} · ${g.uids.length} trang${g.type ? ' · ' + esc(g.type) : ''}${g.agency && g.agency !== 'Khác' ? ' · ' + esc(g.agency) : ''}</div></div>`;
  }).join('');
  $('groups').querySelectorAll('.docgroup').forEach(el => {
    const g = S.groups[+el.dataset.i];
    el.onclick = () => { S.selGroup = +el.dataset.i; S.cur = g.start_uid; S.sel = new Set([S.cur]); renderSplit(); };
    // Thả trang lên một văn bản: chuyển trang về cuối văn bản đó
    el.ondragover = e => { e.preventDefault(); el.classList.add('droptarget'); };
    el.ondragleave = () => el.classList.remove('droptarget');
    el.ondrop = e => {
      e.preventDefault(); e.stopPropagation(); el.classList.remove('droptarget');
      const rest = g.uids.filter(u => !(S.dragUids || []).includes(u));
      if (S.dragUids && rest.length) movePages(S.dragUids, rest[rest.length - 1], true);
    };
  });
  const chosen = $('groups').querySelector('.docgroup.chosen');
  if (chosen) chosen.scrollIntoView({ block: 'nearest' });
}
function renderSelected() {
  const doc = S.docs[S.splitDoc];
  const idx = doc.pages.findIndex(p => p.uid === S.cur), p = doc.pages[idx];
  const gi = groupIndexOf(S.cur), g = S.groups[S.selGroup];
  const isStart = startsList().includes(S.cur), input = $('groupRename');
  if (document.activeElement !== input) input.value = g ? g.name : '';
  input.disabled = !g;
  const fields = g ? groupFields(g) : {};
  [['fgSo', 'so'], ['fgNgay', 'ngay'], ['fgTrich', 'trichyeu']].forEach(([id, key]) => {
    if (document.activeElement !== $(id)) $(id).value = fields[key] || '';
    $(id).disabled = !g;
  });
  $('btnExportOne').disabled = !g;
  $('btnAutoName').classList.toggle('hidden', !(g && S.groupNames[g.start_uid] && g.auto_name));
  $('splitPageNo').textContent = gi >= 0 ? `Trang ${S.groups[gi].uids.indexOf(S.cur) + 1}/${S.groups[gi].uids.length}` : `Trang ${idx + 1}/${doc.pages.length}`;
  $('btnPrevPage').disabled = idx <= 0;
  $('btnNextPage').disabled = idx >= doc.pages.length - 1;
  $('btnBoundary').innerHTML = `${ic(isStart ? 'undo-2' : 'scissors')} <span class="lbl">${isStart ? 'Bỏ điểm tách' : 'Tách từ trang này'}</span>`;
  $('btnBoundary').title = isStart ? 'Gộp trang này vào văn bản trước' : 'Bắt đầu một văn bản mới từ trang này';
  $('btnBoundary').disabled = (S.groups.length && gi < 0) || (S.groups[0] && S.groups[0].start_uid === S.cur);
  $('btnCombine').disabled = S.selGroup >= S.groups.length - 1;
  const sel = selectedOrCurrent();
  $('btnIsolate').disabled = (S.groups.length && gi < 0) || S.groups.some(x => x.uids.length === sel.length && sel.every(u => x.uids.includes(u)));
  const sc = S.scores[S.cur];
  let why = '';
  if (p.blank) why = 'Trang trắng, sẽ bỏ khi xuất nếu bật trong Cài đặt.';
  else if (p.codes && p.codes.length) why = 'Trang phân cách: ' + p.codes.join(', ');
  else if (isStart && sc) why = `Bắt đầu văn bản (${Math.round(sc.prob * 100)}%): ${sc.reasons.join(' · ')}`;
  else if (sc && sc.reasons.length) why = `Trang tiếp nối: ${sc.reasons.join(' · ')}`;
  $('splitWhy').textContent = why;
  $('splitWhy').title = why;
}
async function splitImage(docId, uid) {
  const key = docId + ':' + uid;
  if (!S.pageImgs.has(key)) {
    const r = await call('page_image', docId, uid, 2000, true);
    S.pageImgs.set(key, r.src);
    if (S.pageImgs.size > 30) S.pageImgs.delete(S.pageImgs.keys().next().value);
  }
  return S.pageImgs.get(key);
}
async function showSplitPage() {
  const docId = S.splitDoc, uid = S.cur, key = docId + ':' + uid, img = $('splitPageImg');
  $('splitEmpty').classList.add('hidden');
  ['splitPageImg', 'splitNameBar', 'splitViewBar'].forEach(id => $(id).classList.remove('hidden'));
  if (S.viewKey === key) return;
  S.viewKey = key;
  img.src = S.pageImgs.get(key) || (S.thumbs[docId] || {})[uid] || '';
  $('splitPaper').scrollTop = 0;
  try {
    const src = await splitImage(docId, uid);
    if (S.viewKey === key) img.src = src;
    const pages = S.docs[docId].pages, next = pages[pages.findIndex(p => p.uid === uid) + 1];
    if (next) splitImage(docId, next.uid).catch(() => { });
  } catch (e) { fail(e); }
}
function splitZoom(d) {
  S.splitZoom = d === 0 ? 1 : Math.max(0.5, Math.min(3, S.splitZoom * (d > 0 ? 1.25 : 0.8)));
  $('splitPageImg').style.width = S.splitZoom * 100 + '%';
  $('splitZoomLabel').textContent = Math.round(S.splitZoom * 100) + '%';
}
function startsList() { return S.groups.map(g => g.start_uid); }
async function applyStarts(starts) {
  const pages = S.docs[S.splitDoc].pages.map(p => p.uid);
  starts = [...new Set(starts)].sort((a, b) => pages.indexOf(a) - pages.indexOf(b));
  if (!starts.length || starts[0] !== pages[0]) starts.unshift(pages[0]);
  try { const r = await call('split_set', S.splitDoc, starts, S.groupNames); S.groups = r.groups; renderSplit(); } catch (e) { fail(e); }
}
// Trang đầu của từng văn bản sau khi trang thay đổi; tên đã sửa đi theo trang đầu mới
function startsAfter(lists) {
  const starts = [];
  lists.forEach((uids, i) => {
    const old = S.groups[i].start_uid, name = S.groupNames[old], fields = S.groupFields[old];
    if (uids[0] !== old) forgetGroup(old);
    if (!uids.length) return;
    if (name) S.groupNames[uids[0]] = name;
    if (fields) S.groupFields[uids[0]] = fields;
    starts.push(uids[0]);
  });
  return starts;
}
async function toggleBoundary() { return startsList().includes(S.cur) ? removeBoundary() : setBoundary(); }
async function setBoundary() {
  await applyStarts([...startsList(), S.cur]);
  toast('Đã tạo văn bản mới từ trang đang chọn');
}
async function removeBoundary() {
  forgetGroup(S.cur);
  await applyStarts(startsList().filter(u => u !== S.cur));
  toast('Đã bỏ điểm tách');
}
async function combineNext() {
  const i = S.selGroup;
  if (i >= S.groups.length - 1) return;
  const next = S.groups[i + 1].start_uid;
  forgetGroup(next);
  await applyStarts(startsList().filter(u => u !== next));
  toast('Đã ghép với văn bản tiếp theo');
}
// Các trang đang chọn thành một văn bản riêng, phần còn lại giữ nguyên thứ tự
async function isolatePages(picked = selectedOrCurrent()) {
  const pages = S.docs[S.splitDoc].pages.map(p => p.uid), chosen = new Set(picked);
  const uids = pages.filter(u => chosen.has(u) && (!S.groups.length || groupIndexOf(u) >= 0));
  if (!uids.length) return;
  if (S.groups.some(g => g.uids.length === uids.length && uids.every(u => g.uids.includes(u)))) return toast('Các trang này đã là một văn bản riêng');
  const first = uids[0], gi = groupIndexOf(first), src = gi >= 0 ? S.groups[gi].uids : pages, at = src.indexOf(first);
  const before = src.slice(0, at), after = src.slice(at).filter(u => !chosen.has(u));
  const lists = S.groups.map((g, i) => i === gi ? (before.length ? before : uids) : g.uids.filter(u => !chosen.has(u)));
  const order = pages.filter(u => !chosen.has(u));
  order.splice(pages.indexOf(first), 0, ...uids);
  const starts = [...startsAfter(lists), before[0], first, after[0]].filter(Boolean);
  try {
    await call('pages_reorder', S.splitDoc, order);
    S.docs[S.splitDoc] = await call('document', S.splitDoc);
    S.cur = first; S.sel = new Set(uids);
    await applyStarts(starts);
    toast(`Đã tách ${uids.length} trang thành văn bản riêng`);
  } catch (e) { fail(e); }
}
function groupFields(g) {
  const m = g.meta || {};
  return S.groupFields[g.start_uid] || { loai: m.loai_van_ban || '', coquan: m.co_quan_viet_tat || '', so: m.so_ky_hieu || '', ngay: m.ngay_ban_hanh || '', trichyeu: m.trich_yeu || '' };
}
function setGroupName(g, name) {
  g.name = name; S.groupNames[g.start_uid] = name;
  if (S.groups[S.selGroup] === g) { $('groupRename').value = name; $('btnAutoName').classList.toggle('hidden', !g.auto_name); }
  const el = $('groups').querySelector(`.docgroup[data-i="${S.groups.indexOf(g)}"] .gname`);
  if (el) el.textContent = name;
}
function editGroupField(key, value) {
  const g = S.groups[S.selGroup];
  if (!g) return;
  S.groupFields[g.start_uid] = { ...groupFields(g), [key]: value };
  syncGroupName(g.start_uid);
}
const syncGroupName = debounce(async start => {
  const fields = S.groupFields[start];
  try {
    const name = (await call('build_filename', fields)).replace(/\.pdf$/i, '');
    const g = S.groups.find(x => x.start_uid === start);
    if (g && S.groupFields[start] === fields) setGroupName(g, name);
  } catch (e) { fail(e); }
}, 250);
function renameGroup(v) {
  const g = S.groups[S.selGroup], clean = v.replace(/[\\/:*?"<>|]/g, '');
  if (clean !== v) { $('groupRename').value = clean; toast('Tên file không được chứa \\ / : * ? " < > |', [], 3000, 'warn'); }
  if (g) setGroupName(g, clean);
}
function restoreAutoName() {
  const g = S.groups[S.selGroup];
  if (!g) return;
  forgetGroup(g.start_uid);
  g.name = g.auto_name; $('groupRename').value = g.name;
  renderSplit();
}
async function analyzeSplit() {
  try { await call('split_analyze', S.splitDoc); $('btnAnalyze').disabled = true; toast('Đang nhận dạng và tìm điểm tách tài liệu'); } catch (e) { fail(e); }
}
function selectedOrCurrent() { return S.sel.size ? [...S.sel] : (S.cur ? [S.cur] : []); }
async function rotatePages(deg) {
  const uids = selectedOrCurrent();
  if (!uids.length) return;
  // Xoay làm mất OCR của trang, giữ lại tên và thông tin đã nhận dạng trước đó
  S.groups.forEach(g => { if (uids.includes(g.start_uid)) { S.groupFields[g.start_uid] = groupFields(g); S.groupNames[g.start_uid] = g.name; } });
  try {
    const th = await call('pages_rotate', S.splitDoc, uids, deg);
    th.forEach(t => { S.thumbs[S.splitDoc][t.uid] = t.src; S.pageImgs.delete(S.splitDoc + ':' + t.uid); });
    S.viewKey = null; renderSplit();
  } catch (e) { fail(e); }
}
async function movePages(uids, target, after) {
  const pages = S.docs[S.splitDoc].pages.map(p => p.uid), moving = new Set(uids);
  const order = pages.filter(u => !moving.has(u)), moved = pages.filter(u => moving.has(u));
  order.splice(order.indexOf(target) + (after ? 1 : 0), 0, ...moved);
  const lists = S.groups.map(g => {
    const list = g.uids.filter(u => !moving.has(u));
    if (list.includes(target)) list.splice(list.indexOf(target) + (after ? 1 : 0), 0, ...moved);
    return list;
  });
  try { await call('pages_reorder', S.splitDoc, order); await refreshSplitDoc(true, startsAfter(lists)); toast('Đã sắp xếp lại trang'); } catch (e) { fail(e); }
}
async function deletePages() {
  const uids = selectedOrCurrent();
  if (!uids.length) return;
  if (!await confirmBox('Xóa trang', `Xóa ${uids.length} trang khỏi tài liệu đang làm việc? File gốc không bị thay đổi.`, 'Xóa')) return;
  const gone = new Set(uids), pages = S.docs[S.splitDoc].pages.map(p => p.uid);
  const next = pages.slice(pages.indexOf(S.cur)).find(u => !gone.has(u));
  try {
    await call('pages_delete', S.splitDoc, uids);
    S.sel = new Set(); S.cur = next || null;
    await refreshSplitDoc(true, startsAfter(S.groups.map(g => g.uids.filter(u => !gone.has(u)))));
    toast(`Đã xóa ${uids.length} trang`);
  } catch (e) { fail(e); }
}
function openSplitTools() {
  openModal(`<h2>Cách chia khác</h2><p class="sub">Dùng khi không muốn tự động tách theo nội dung. Cách chia mới sẽ thay cho các văn bản hiện tại.</p>
    <label class="fieldlabel mt">Chia theo số trang</label>
    <div class="row"><select class="select" id="manualMethod" onchange="renderManualInputs()"><option value="ranges">Theo khoảng trang</option><option value="every">Mỗi N trang một file</option></select><input class="input" id="manualValue" style="flex:1"><button class="btn" onclick="planManual()">Chia</button></div>
    <label class="fieldlabel mt">Chia theo trang phân cách</label>
    <div class="row"><button class="btn" onclick="planSeparator('blank')">${ic('file')} Trang trắng</button><button class="btn" onclick="planSeparator('code')">${ic('qr-code')} Mã QR / barcode</button></div>
    <div class="divider"></div>
    <label class="fieldlabel">Ghép nhiều tài liệu đang mở thành một</label>
    <div id="mergeList"></div>
    <div class="row mt"><input class="input" id="mergeName" style="flex:1" value="Tai_lieu_ghep.pdf"><button class="btn" onclick="mergeDocs()">${ic('merge')} Ghép</button></div>
    <div class="row mt" style="justify-content:flex-end"><button class="btn" onclick="closeModal()">Đóng</button></div>`);
  renderManualInputs();
  renderMergeList();
}
function renderManualInputs() {
  $('manualValue').placeholder = $('manualMethod').value === 'every' ? 'Số trang mỗi file, VD: 2' : 'VD: 1-3, 4, 5-8';
}
async function planManual() {
  try {
    const r = await call('split_plan', S.splitDoc, $('manualMethod').value, $('manualValue').value);
    if (!r.groups.length) return toast('Chưa nhập đúng cách chia', [], 3000, 'warn');
    closeModal();
    S.groups = r.groups; resetGroupNames(); S.selGroup = 0; S.cur = null; renderSplit(); toast(`Chia thành ${r.groups.length} phần`);
  } catch (e) { fail(e); }
}
async function planSeparator(kind) {
  closeModal();
  $('footerInfo').textContent = kind === 'blank' ? 'Đang tìm trang trắng…' : 'Đang đọc mã QR / barcode…';
  try {
    const r = await call('split_plan', S.splitDoc, kind, '');
    S.groups = r.groups; resetGroupNames(); S.selGroup = 0; S.cur = null; S.docs[S.splitDoc].pages = r.pages; renderSplit();
    const n = r.pages.filter(p => kind === 'blank' ? p.blank : (p.codes || []).length).length;
    toast(`Tìm thấy ${n} trang phân cách, chia thành ${r.groups.length} phần`);
  } catch (e) { fail(e); }
}
function renderMergeList() {
  if (!$('mergeList')) return;
  const docs = Object.values(S.docs);
  $('mergeList').innerHTML = docs.map(d => `<label class="fileitem"><span><input type="checkbox" class="check mergechk" value="${d.id}" ${d.id === S.splitDoc ? 'checked' : ''}> ${esc(d.name)}</span><span class="meta">${d.page_count} trang</span></label>`).join('');
}
async function mergeDocs() {
  const ids = [...document.querySelectorAll('.mergechk:checked')].map(x => x.value);
  if (ids.length < 2) return toast('Chọn ít nhất 2 tài liệu để ghép');
  try {
    const d = await call('merge_documents', ids, $('mergeName').value || 'Tai_lieu_ghep.pdf');
    closeModal();
    S.docs[d.id] = d; refreshDocSelects(); await selectSplitDoc(d.id);
    toast(`Đã ghép ${ids.length} tài liệu thành ${d.page_count} trang - bấm “Xuất văn bản” để ghi ra file`);
  } catch (e) { fail(e); }
}
function previewGroupExport(only) {
  const doc = S.docs[S.splitDoc];
  const groups = only || (S.groups.length ? S.groups : [{ name: doc.name.replace(/\.[^.]+$/, ''), uids: doc.pages.map(p => p.uid), type: '', agency: '' }]);
  const pages = doc.pages.map(p => p.uid), picked = new Set(groups);
  openModal(`<h2>Xuất văn bản</h2><p class="sub">${groups.length > 1 ? 'Bỏ tích văn bản không cần xuất.' : 'File sẽ được tạo trong thư mục kết quả.'}</p>
    <div class="grid cols2 mt"><div><label class="fieldlabel">Định dạng</label><select class="select w100" id="groupFormat"><option value="pdf">PDF</option><option value="searchable_pdf">PDF có lớp chữ (Searchable)</option><option value="docx">Word DOCX</option><option value="txt">TXT</option></select></div>
    <div><label class="fieldlabel">Thư mục con</label><select class="select w100" id="classifyBy"><option value="none">Không tạo</option><option value="type">Theo loại văn bản</option><option value="agency">Theo cơ quan ban hành</option></select></div></div>
    <div class="mutedbox" id="gxList" style="margin:13px 0;max-height:300px;overflow:auto"></div>
    <div class="row between"><button class="btn" onclick="closeModal()">Hủy</button><div class="row">${groups.length > 1 ? '<button class="btn" id="gxAll"></button>' : ''}<button class="btn primary" id="gxGo"></button></div></div>`, { wide: true });
  const drawList = () => {
    const cls = $('classifyBy').value, ext = { pdf: '.pdf', searchable_pdf: '.pdf', docx: '.docx', txt: '.txt' }[$('groupFormat').value];
    const folderOf = g => cls === 'type' ? (g.type || 'Khác') + '\\' : cls === 'agency' ? (g.agency || 'Khác') + '\\' : '';
    $('gxList').innerHTML = groups.map((g, i) => `<label class="gxrow"><input type="checkbox" class="check" data-i="${i}" ${picked.has(g) ? 'checked' : ''} ${groups.length > 1 ? '' : 'hidden'}><span>${esc(folderOf(g) + (g.name || 'Van_ban') + ext)} <span class="muted">(trang ${pages.indexOf(g.uids[0]) + 1}–${pages.indexOf(g.uids[g.uids.length - 1]) + 1})</span></span></label>`).join('');
    $('gxList').querySelectorAll('input').forEach(c => c.onchange = () => { c.checked ? picked.add(groups[c.dataset.i]) : picked.delete(groups[c.dataset.i]); drawButtons(); });
    drawButtons();
  };
  const drawButtons = () => {
    $('gxGo').innerHTML = `${ic('download')} Xuất ${picked.size} file`;
    $('gxGo').disabled = !picked.size;
    if ($('gxAll')) $('gxAll').textContent = picked.size ? 'Bỏ chọn tất cả' : 'Chọn tất cả';
  };
  if ($('gxAll')) $('gxAll').onclick = () => { picked.size ? picked.clear() : groups.forEach(g => picked.add(g)); drawList(); };
  $('groupFormat').onchange = $('classifyBy').onchange = drawList;
  drawList();
  $('gxGo').onclick = async () => {
    const fmt = $('groupFormat').value, cls = $('classifyBy').value;
    $('gxGo').disabled = true; $('gxGo').textContent = 'Đang xuất…';
    try {
      const r = await call('export_groups', S.splitDoc, groups.filter(g => picked.has(g)), fmt, cls, null);
      closeModal();
      toast(`Đã xuất ${r.outputs.length} file`, [{ label: 'Mở thư mục', fn: () => call('open_path', r.folder) }]);
    } catch (e) { closeModal(); fail(e); }
  };
}

// ---------------------------------------------------------------- HÀNG LOẠT
async function addBatchFiles() { try { const p = await call('pick_files', true); if (p.length) addBatchPaths(p); } catch (e) { fail(e); } }
async function addBatchFolder() { try { const f = await call('pick_folder'); if (f) addBatchPaths([f]); } catch (e) { fail(e); } }
async function addBatchPaths(paths) {
  try {
    const items = await call('expand_paths', paths);
    const have = new Set(S.batchFiles.map(f => f.path));
    const add = items.filter(f => !have.has(f.path));
    S.batchFiles.push(...add);
    navigate('batch');
    toast(`Đã thêm ${add.length} file vào hàng đợi`);
  } catch (e) { fail(e); }
}
function clearBatch() { S.batchFiles = []; renderBatchFiles(); }
function renderBatchFiles() {
  $('batchOut').textContent = S.settings.output_dir;
  $('batchCount').textContent = S.batchFiles.length ? `${S.batchFiles.length} file` : '';
  $('batchFiles').innerHTML = S.batchFiles.map((f, i) => `<div class="fileitem"><span>${ic('file-text', 'muted')} ${esc(f.name)} <span class="meta">${(f.size / 1048576).toFixed(1)} MB</span></span><button class="btn small ghost danger" data-i="${i}" title="Bỏ khỏi hàng đợi">${ic('x')}</button></div>`).join('') || '<p class="small muted">Chưa có file trong hàng đợi</p>';
  $('batchFiles').querySelectorAll('button').forEach(b => b.onclick = () => { S.batchFiles.splice(+b.dataset.i, 1); renderBatchFiles(); });
}
function toggleBatchSplit() { $('batchSplitOpts').classList.toggle('hidden', !$('batchSplit').checked); }
async function startBatch() {
  if (!S.batchFiles.length) return toast('Vui lòng thêm ít nhất một file');
  const split = $('batchSplit').checked;
  try {
    const r = await call('batch_start', S.batchFiles.map(f => f.path), $('batchJob').value, { quality: $('batchQuality').value, split: split ? $('batchSplitMode').value : 'none', classify: split ? $('batchClassify').value : 'none' });
    S.batchJob = r.job_id;
    $('batchState').textContent = 'Đang chờ bắt đầu…';
    toast(`Đã đưa ${r.count} file vào hàng đợi`);
  } catch (e) { fail(e); }
}
function renderBatchJob(j) {
  $('batchProgress').style.width = Math.round(j.progress * 100) + '%';
  const cancelling = j.status === 'cancelling' || S.cancelRequests.has(j.id);
  $('batchState').textContent = cancelling ? 'Đang hủy…' : j.message;
  const running = ['running', 'queued', 'paused', 'cancelling'].includes(j.status);
  $('btnPause').classList.toggle('hidden', !running || cancelling || j.status === 'paused');
  $('btnResume').classList.toggle('hidden', cancelling || j.status !== 'paused');
  $('btnCancel').classList.toggle('hidden', !running);
  $('btnCancel').disabled = cancelling;
  $('btnCancel').innerHTML = cancelling ? 'Đang hủy…' : `${ic('square')} Hủy`;
  $('btnBatch').disabled = running;
  const failed = (j.items || []).some(it => ['error', 'cancelled'].includes(it.status));
  $('btnRetry').classList.toggle('hidden', running || !failed);
  $('btnBatchFolder').classList.toggle('hidden', !(j.result && j.result.folder));
  const icon = { queued: ic('clock', 'muted'), running: ic('loader-circle', 'spin'), done: ic('circle-check', 'ok'), error: ic('circle-x', 'bad'), cancelled: ic('square', 'muted') };
  $('batchItems').innerHTML = (j.items || []).map(it => `<div class="batchitem"><span>${icon[it.status] || '•'}</span><div><b>${esc(it.name)}</b>${it.message ? `<div class="msg">${esc(it.message)}</div>` : ''}</div>${statusChip(it.status)}</div>`).join('');
}
function pauseBatch() { call('job_pause', S.batchJob); }
function resumeBatch() { call('job_resume', S.batchJob); }
function cancelBatch() { return cancelJob(S.batchJob); }
async function retryBatch() { try { const r = await call('batch_retry', S.batchJob); S.batchJob = r.job_id; toast(`Thử lại ${r.count} file`); } catch (e) { fail(e); } }
function openBatchFolder() { const j = S.jobs[S.batchJob]; if (j && j.result) call('open_path', j.result.folder); }
function openOutput() { call('open_path', S.settings.output_dir).catch(fail); }

// ---------------------------------------------------------------- LỊCH SỬ
async function renderHistory() {
  let rows;
  try { rows = await call('history_search', $('historySearch').value, $('hKind').value, $('hStatus').value, +$('hDays').value); } catch (e) { return fail(e); }
  S.historyRows = rows;
  $('historyBody').innerHTML = rows.length ? rows.map(r => `<tr><td><b>${ic('file-text', 'muted')}<span>${esc(r.name)}</span></b>${r.tags ? r.tags.split(',').filter(Boolean).map(t => `<span class="tagchip">${esc(t.trim())}</span>`).join('') : ''}${r.snippet ? `<span class="snippet">${esc(r.snippet)}</span>` : r.detail ? `<span class="snippet" title="${esc(r.detail)}">${esc(r.detail.length > 140 ? r.detail.slice(0, 140) + '…' : r.detail)}</span>` : ''}</td><td>${esc(r.kind_label)}${r.doc_count ? `<div class="small muted">${r.doc_count} văn bản</div>` : ''}</td><td>${r.pages}</td><td class="muted small">${fmtTime(r.created)}</td><td class="small">${esc(r.engine || '-')}${r.confidence ? `<div class="muted">${Math.round(r.confidence * 100)}%</div>` : ''}</td><td>${statusChip(r.status)}</td><td><div class="acts">
      ${r.outputs.length ? `<button class="btn small" data-a="open" data-id="${r.id}">Mở</button>` : ''}
      <button class="btn small" data-a="folder" data-id="${r.id}">Thư mục</button>
      ${r.source ? `<button class="btn small" data-a="reopen" data-id="${r.id}">OCR lại</button>` : ''}
      <button class="btn small" data-a="tag" data-id="${r.id}">Nhãn</button>
      ${r.outputs.length ? `<button class="btn small" data-a="move" data-id="${r.id}">Di chuyển</button>` : ''}
      <button class="btn small danger" data-a="del" data-id="${r.id}">Xóa</button></div></td></tr>`).join('')
    : '<tr><td colspan="7"><div class="empty">Không có tác vụ phù hợp</div></td></tr>';
  $('historyBody').querySelectorAll('button[data-a]').forEach(b => b.onclick = () => historyAction(b.dataset.a, +b.dataset.id));
}
async function historyAction(a, id) {
  const r = S.historyRows.find(x => x.id === id);
  try {
    if (a === 'open') await call('open_path', r.outputs[0]);
    if (a === 'folder') await call('reveal', r.outputs[0] || r.source);
    if (a === 'reopen') await openDocs([r.source], r.kind === 'split' ? 'split' : 'ocr');
    if (a === 'move') { const m = await call('history_move', id); if (!m.cancelled) { toast(`Đã di chuyển ${m.outputs.length} file`); renderHistory(); } }
    if (a === 'tag') {
      openModal(`<h2>Gắn nhãn & đổi tên</h2><label class="fieldlabel">Tên hiển thị</label><input class="input w100" id="tgName" value="${esc(r.name)}"><label class="fieldlabel mt">Nhãn (cách nhau bằng dấu phẩy)</label><input class="input w100" id="tgTags" value="${esc(r.tags || '')}" placeholder="VD: Mật, Phòng TM, 2026"><div class="row between mt"><button class="btn" onclick="closeModal()">Hủy</button><button class="btn primary" id="tgSave">Lưu</button></div>`);
      $('tgSave').onclick = async () => { await call('history_update', id, { name: $('tgName').value, tags: $('tgTags').value }); closeModal(); renderHistory(); };
    }
    if (a === 'del') {
      const m = await confirmBox('Xóa khỏi lịch sử', `Xóa “${r.name}” khỏi lịch sử?`, 'Xóa', r.outputs.length ? '<p><label><input type="checkbox" class="check" id="delFiles"> Xóa luôn các file kết quả trên đĩa</label></p>' : '');
      if (!m) return;
      const delFiles = m !== true && m.querySelector('#delFiles') ? m.querySelector('#delFiles').checked : false;
      await call('history_delete', id, delFiles); renderHistory();
    }
  } catch (e) { fail(e); }
}
async function exportHistory() { try { const r = await call('history_export_csv'); if (r.path) toast('Đã xuất danh sách', fileActions(r.path)); } catch (e) { fail(e); } }

// ---------------------------------------------------------------- MÔ HÌNH
async function renderModels() {
  let d;
  try { d = await call('models'); } catch (e) { return fail(e); }
  $('defaultEngine').value = d.default_engine;
  const g = d.gpus[0];
  $('vramBox').innerHTML = g ? bar(`GPU ${g.name} · VRAM`, g.used_mb / g.total_mb * 100, `${(g.used_mb / 1024).toFixed(1)} / ${(g.total_mb / 1024).toFixed(1)} GB`) +
    (d.device === 'CPU' ? '<p class="small muted">Có GPU NVIDIA nhưng bản Paddle đang cài là bản CPU - cài paddlepaddle-gpu để tăng tốc.</p>' : '')
    : '<p class="small muted" style="margin:0">Không phát hiện GPU NVIDIA - các model chạy trên CPU. PaddleOCR-VL 1.6 sẽ rất chậm (vài phút/trang).</p>';
  $('modelNotice').classList.toggle('hidden', !!d.paddle);
  $('modelNotice').innerHTML = d.paddle ? '' : 'Đang dùng Tesseract vì bộ nhận dạng PaddleOCR chưa sẵn sàng.' +
    (d.error ? '<details class="mt"><summary>Chi tiết lỗi</summary><pre class="small" style="white-space:pre-wrap">' + esc(d.error.slice(-600)) + '</pre></details>' : '');
  $('modelCards').innerHTML = d.models.map(m => `<div class="card modelcard"><div style="flex:1"><b>${esc(m.name)}</b><p class="sub small" style="margin:4px 0 0">${esc(m.desc)}</p>
    <div class="mstate"><span class="badge ${m.ready ? 'ok' : ''}">${m.ready ? 'Đã cài · ' + m.size_mb.toLocaleString('vi-VN') + ' MB' : 'Chưa cài'}</span>${m.loaded ? '<span class="badge on">Đang sử dụng</span>' : ''}</div></div>
    ${m.ready ? (m.loaded ? `<button class="btn small" data-k="${m.key}" data-a="unload">Giải phóng</button>` : `<button class="btn small" data-k="${m.key}" data-a="load">Nạp</button>`) : ''}</div>`).join('');
  $('modelCards').querySelectorAll('button[data-k]').forEach(b => b.onclick = async () => {
    try {
      if (b.dataset.a === 'load') { await call('model_load', b.dataset.k); b.disabled = true; b.textContent = 'Đang nạp…'; }
      else { await call('model_unload', b.dataset.k); renderModels(); refreshSystem(); }
    } catch (e) { fail(e); }
  });
}
async function importModel() { try { const r = await call('model_import'); if (!r.cancelled) { toast(r.message, [], 4200, r.ok ? 'ok' : 'warn'); renderModels(); } } catch (e) { fail(e); } }

// ---------------------------------------------------------------- CÀI ĐẶT
function settingsTab(name) {
  document.querySelectorAll('#settingsTabs button').forEach(b => b.classList.toggle('active', b.dataset.settab === name));
  document.querySelectorAll('#settings .setpanel').forEach(p => p.classList.toggle('hidden', p.dataset.panel !== name));
}
function bindSettings() {
  document.querySelectorAll('#settings [data-key]').forEach(el => {
    el.addEventListener('change', () => {
      const k = el.dataset.key;
      let v = el.type === 'checkbox' ? el.checked : el.value;
      if (el.dataset.type === 'int') v = parseInt(v, 10) || 0;
      if (k === 'theme') setTheme(v); else saveSettings({ [k]: v });
    });
  });
  const slash = document.querySelector('#settings [data-key="slash_replacement"]');
  slash.addEventListener('input', () => {
    const clean = slash.value.replace(/[\\/:*?"<>|]/g, '');
    if (clean === slash.value) return;
    slash.value = clean;
    toast('Tên file trên Windows không được chứa các ký tự \\ / : * ? " < > |', [], 3000, 'warn');
  });
}
function loadSettingsForm() {
  document.querySelectorAll('#settings [data-key]').forEach(el => {
    const v = S.settings[el.dataset.key];
    if (el.type === 'checkbox') el.checked = !!v; else el.value = v;
    if (el.type === 'range' && el.nextElementSibling) el.nextElementSibling.textContent = v + '%';
  });
  renderMap('doc_type_map');
  renderMap('agency_map');
  renderAbout();
}
// Bảng viết tắt (loại văn bản / cơ quan ban hành) cho tên file - có tìm kiếm và phân trang
const MAP_UI = {
  doc_type_map: { el: 'typeMap', pager: 'typePager', search: 'typeSearch', ten: 'Tên loại (OCR đọc được)' },
  agency_map: { el: 'agencyMap', pager: 'agencyPager', search: 'agencySearch', ten: 'Tên cơ quan (OCR đọc được)' },
};
const MAP_PAGE = 8;
function mapView(key) { return (S.mapView = S.mapView || {})[key] = (S.mapView || {})[key] || { q: '', page: 0 }; }
// Lưu nhưng giữ nguyên mảng đang sửa (settings_save trả bản đã lọc dòng rỗng, dễ lệch chỉ số khi đang gõ)
const saveMap = debounce(async key => { const local = S.settings[key]; await saveSettings({ [key]: local }); S.settings[key] = local; }, 500);
function renderMap(key) {
  const cfg = MAP_UI[key], all = S.settings[key] = S.settings[key] || [], view = mapView(key);
  const q = (view.q || '').trim().toLowerCase();
  const items = all.map((r, i) => ({ r, i })).filter(({ r }) => !q || `${r.ten || ''} ${r.tat || ''}`.toLowerCase().includes(q));
  const pages = Math.max(1, Math.ceil(items.length / MAP_PAGE));
  view.page = Math.min(Math.max(0, view.page), pages - 1);
  const slice = items.slice(view.page * MAP_PAGE, view.page * MAP_PAGE + MAP_PAGE);
  $(cfg.el).innerHTML = slice.length ? slice.map(({ r, i }) => `<div class="maprow"><input class="input" data-f="ten" data-i="${i}" placeholder="${cfg.ten}" value="${esc(r.ten)}"><span class="maparrow">${ic('arrow-right')}</span><input class="input" data-f="tat" data-i="${i}" placeholder="Viết tắt" value="${esc(r.tat)}"><button class="btn small ghost danger" data-del="${i}" title="Xóa dòng">${ic('x')}</button></div>`).join('')
    : `<p class="small muted">${q ? 'Không tìm thấy mục khớp “' + esc(view.q) + '”.' : 'Chưa có mục nào. Bấm “Thêm” để tạo.'}</p>`;
  $(cfg.el).querySelectorAll('input').forEach(inp => inp.oninput = () => { (S.settings[key] || [])[+inp.dataset.i][inp.dataset.f] = inp.value; saveMap(key); });
  $(cfg.el).querySelectorAll('button[data-del]').forEach(b => b.onclick = () => { S.settings[key].splice(+b.dataset.del, 1); renderMap(key); saveMap(key); });
  $(cfg.pager).innerHTML = `<span class="muted small">${items.length} mục${q ? ' khớp' : ''}${pages > 1 ? ` · trang ${view.page + 1}/${pages}` : ''}</span>`
    + (pages > 1 ? `<span class="row" style="gap:6px"><button class="btn small" data-pg="-1" ${view.page <= 0 ? 'disabled' : ''}>${ic('arrow-left')}</button><button class="btn small" data-pg="1" ${view.page >= pages - 1 ? 'disabled' : ''}>${ic('arrow-right')}</button></span>` : '');
  $(cfg.pager).querySelectorAll('button[data-pg]').forEach(b => b.onclick = () => { view.page += +b.dataset.pg; renderMap(key); });
}
function searchMap(key, q) { const v = mapView(key); v.q = q; v.page = 0; renderMap(key); }
function addMapRow(key) {
  const all = S.settings[key] = S.settings[key] || [];
  all.push({ ten: '', tat: '' });
  const v = mapView(key); v.q = '';
  if ($(MAP_UI[key].search)) $(MAP_UI[key].search).value = '';
  v.page = Math.ceil(all.length / MAP_PAGE) - 1;
  renderMap(key);
  const last = $(MAP_UI[key].el).querySelector('.maprow:last-child input');
  if (last) last.focus();
}
async function resetMap(key) {
  if (!await confirmBox('Về mặc định', 'Đưa bảng viết tắt này về danh sách mặc định? Các mục bạn thêm sẽ mất.', 'Khôi phục')) return;
  S.settings[key] = (S.boot.defaults[key] || []).map(r => ({ ...r }));
  const v = mapView(key); v.q = ''; v.page = 0;
  if ($(MAP_UI[key].search)) $(MAP_UI[key].search).value = '';
  renderMap(key);
  saveSettings({ [key]: S.settings[key] });
}
function renderAbout() {
  const lic = S.license || {};
  $('aboutBox').innerHTML = `<div class="kv">${S.boot.app.author.map(a => `<span>${esc(a.label)}</span><span>${esc(a.value)}</span>`).join('')}
    <span>Phiên bản</span><span>${esc(S.boot.app.name)} ${esc(S.boot.app.version)}</span>
    <span>Công nghệ OCR</span><span>PP-OCRv6 · VietOCR · PP-StructureV3 · PaddleOCR-VL 1.6</span>
    <span>Bản quyền</span><span>${esc(lic.label || '')}</span><span>Code máy</span><span class="mono">${esc(lic.machine_id || '')}</span></div>`;
}
async function saveSettings(values) {
  const oldTheme = S.settings.theme || 'light';
  const changesTheme = Object.prototype.hasOwnProperty.call(values, 'theme');
  if (changesTheme) applyTheme(values.theme);
  try {
    S.settings = await call('settings_save', values);
    if (Object.keys(values).some(key => key !== 'theme')) applyOcrDefaults();
    applyTheme(S.settings.theme);
    if (!changesTheme) footerFlash('Đã lưu cài đặt');
    return true;
  } catch (e) {
    if (changesTheme) applyTheme(oldTheme);
    fail(e);
    return false;
  }
}
function footerFlash(t) { $('footerInfo').textContent = t; }
async function pickOutput() { try { const f = await call('pick_output_dir'); if (f) { S.settings.output_dir = f; loadSettingsForm(); applyOcrDefaults(); } } catch (e) { fail(e); } }
async function backupSettings() { try { const r = await call('settings_backup'); if (r.path) toast('Đã sao lưu cấu hình', fileActions(r.path)); } catch (e) { fail(e); } }
async function restoreSettings() { try { const r = await call('settings_restore'); if (!r.cancelled) { S.settings = r; loadSettingsForm(); applyOcrDefaults(); applyTheme(r.theme); toast('Đã khôi phục cấu hình'); } } catch (e) { fail(e); } }
async function resetSettings() {
  if (!await confirmBox('Khôi phục mặc định', 'Đưa toàn bộ cài đặt về giá trị mặc định?', 'Khôi phục')) return;
  try { S.settings = await call('settings_reset'); loadSettingsForm(); applyOcrDefaults(); applyTheme(S.settings.theme); toast('Đã khôi phục cài đặt mặc định'); } catch (e) { fail(e); }
}
async function cleanTemp() { try { const r = await call('clean_temp'); toast(`Đã dọn ${r.freed_mb} MB file tạm`); } catch (e) { fail(e); } }

// ---------------------------------------------------------------- kéo thả & phím tắt
function bindDrop() {
  let depth = 0;
  window.addEventListener('dragenter', e => { if (e.dataTransfer && [...e.dataTransfer.types].includes('Files')) { depth++; $('dropOverlay').classList.add('show'); } });
  window.addEventListener('dragleave', () => { depth = Math.max(0, depth - 1); if (!depth) $('dropOverlay').classList.remove('show'); });
  window.addEventListener('dragover', e => e.preventDefault());
  window.addEventListener('drop', e => { e.preventDefault(); depth = 0; $('dropOverlay').classList.remove('show'); });
}
function bindKeys() {
  window.addEventListener('keydown', e => {
    if (e.key === 'Escape') closeModal();
    if (e.ctrlKey && e.key.toLowerCase() === 'o') { e.preventDefault(); addDocuments(S.page === 'split' ? 'split' : 'ocr'); }
    if (S.page === 'ocr' && e.ctrlKey && e.key.toLowerCase() === 's') { e.preventDefault(); saveDraft(); }
    if (S.page === 'ocr' && e.ctrlKey && e.key.toLowerCase() === 'h') { e.preventDefault(); openFind(); }
    if (S.page === 'ocr' && !e.target.isContentEditable && !/INPUT|TEXTAREA|SELECT/.test(e.target.tagName)) {
      const doc = S.docs[S.ocrDoc];
      if (!doc) return;
      const i = doc.pages.findIndex(p => p.uid === S.ocrUid);
      if (e.key === 'PageDown' || e.key === 'ArrowDown') { if (i < doc.pages.length - 1) selectOcrPage(doc.pages[i + 1].uid); e.preventDefault(); }
      if (e.key === 'PageUp' || e.key === 'ArrowUp') { if (i > 0) selectOcrPage(doc.pages[i - 1].uid); e.preventDefault(); }
    }
    if (S.page === 'split' && !/INPUT|TEXTAREA|SELECT/.test(e.target.tagName) && !$('modalShade').classList.contains('show')) {
      if (e.key === 'Delete') deletePages();
      if (e.key === 'PageDown' || e.key === 'ArrowRight') { stepPage(1); e.preventDefault(); }
      if (e.key === 'PageUp' || e.key === 'ArrowLeft') { stepPage(-1); e.preventDefault(); }
    }
  });
}
