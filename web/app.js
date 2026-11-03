// === app.js === Giao diện OfflineOCR Studio - gọi xuống Python qua window.pywebview.api
'use strict';
const $ = id => document.getElementById(id);
const S = {
  boot: null, settings: {}, docs: {}, thumbs: {}, page: 'overview',
  ocrDoc: '', ocrUid: '', ocrResult: null, img: null, zoom: 1, showBoxes: false, regionMode: false, quality: 'fast',
  savedRange: null, splitDoc: '', splitTab: 'ai', groups: [], scores: {}, sel: new Set(), anchor: null, cur: null,
  selGroup: 0, groupNames: {}, batchFiles: [], batchJob: null, jobs: {}, handled: new Set(), pollVersion: 0,
  system: null,
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
  overview: 'Tổng quan', ocr: 'OCR tài liệu', split: 'Cắt, ghép & Tách AI', batch: 'Xử lý hàng loạt',
  history: 'Lịch sử & Kết quả', models: 'Quản lý mô hình', settings: 'Cài đặt'
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
  $('sbVersion').textContent = `v${S.boot.app.version} · ${S.boot.app.name}`;
  $('sbAuthor').textContent = S.boot.app.author.map(a => a.value).join(' · ');
  $('ocrEngine').innerHTML = S.boot.engines.map(e => `<option value="${e.key}">${esc(e.label)}</option>`).join('');
  $('defaultEngine').innerHTML = $('ocrEngine').innerHTML;
  $('docTypeList').innerHTML = S.boot.doc_types.map(d => `<option value="${d.code}">${esc(d.label)}</option>`).join('');
  applyOcrDefaults();
  bindSettings();
  updateLicense(S.boot.license);
  document.querySelectorAll('.nav').forEach(el => el.addEventListener('click', () => navigate(el.dataset.page)));
  document.querySelectorAll('#ocrModes button').forEach(b => b.onclick = () => setQuality(b.dataset.mode));
  document.querySelectorAll('#ocrResultTabs button').forEach(b => b.onclick = () => resultTab(b.dataset.result));
  document.querySelectorAll('#splitTabs button').forEach(b => b.onclick = () => splitTab(b.dataset.splittab));
  bindEditor();
  bindViewer();
  bindDrop();
  bindKeys();
  window.addEventListener('resize', debounce(() => applyZoom(), 150));
  setInterval(poll, 500);
  setInterval(refreshSystem, 3000);
  refreshSystem();
  navigate('overview');
  renderManualInputs();
  if (S.boot.license.state === 'expired') openLicense(true);
}
function applyTheme(t) { document.body.classList.toggle('dark', t === 'dark'); }
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
  p.innerHTML = ic(lic.state === 'licensed' ? 'badge-check' : lic.state === 'trial' ? 'hourglass' : 'triangle-alert') + ' ' + esc(lic.label);
  p.className = 'pill pillbtn ' + lic.state;
}
function openLicense(force = false) {
  const lic = S.license || {};
  openModal(`<h2>${ic('key-round')} Bản quyền phần mềm</h2>
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
  if (!r || r.error) return;
  S.pollVersion = r.version;
  r.jobs.forEach(j => { S.jobs[j.id] = j; onJob(j); });
  r.events.forEach(onEvent);
  renderFooter();
}
function activeJob() {
  return Object.values(S.jobs).filter(j => ['running', 'paused', 'queued'].includes(j.status)).sort((a, b) => a.id - b.id)[0];
}
function renderFooter() {
  const j = activeJob();
  const prog = $('footerProg'), cancel = $('footerCancel');
  if (j) {
    const queued = Object.values(S.jobs).filter(x => x.status === 'queued').length;
    $('footerInfo').textContent = `${j.title} · ${j.message}${queued > 1 ? ` · ${queued - 1} tác vụ đang chờ` : ''}`;
    prog.classList.remove('hidden'); prog.firstElementChild.style.width = Math.round(j.progress * 100) + '%';
    cancel.classList.toggle('hidden', j.kind === 'warmup');
    cancel.onclick = () => call('job_cancel', j.id);
  } else {
    prog.classList.add('hidden'); cancel.classList.add('hidden');
    const last = Object.values(S.jobs).sort((a, b) => b.id - a.id)[0];
    if (last) $('footerInfo').textContent = last.kind === 'warmup' ? last.message : `${last.title} · ${last.message}`;
  }
}
function onJob(j) {
  if (j.kind === 'batch' && j.id === S.batchJob) renderBatchJob(j);
  if (j.kind === 'ocr' && j.meta.doc_id === S.ocrDoc) setOcrBusy(['running', 'queued', 'paused'].includes(j.status));
  if (j.kind === 'split' && j.meta.doc_id === S.splitDoc) $('btnAnalyze').disabled = ['running', 'queued'].includes(j.status);
  if (!['done', 'error', 'cancelled'].includes(j.status) || S.handled.has(j.id)) return;
  S.handled.add(j.id);
  if (j.status === 'error') { toast(`${j.title}: ${j.error}`, [], 6000, 'warn'); return; }
  if (j.status === 'cancelled') { if (j.kind !== 'warmup') toast(`Đã hủy: ${j.title}`); return; }
  if (j.kind === 'warmup') refreshSystem();
  if (j.kind === 'ocr' && j.result) {
    if (j.result.notes && j.result.notes.length) toast(j.result.notes.join(' '), [], 7000);
    else toast(`Đã nhận dạng ${j.result.pages} trang trong ${j.result.seconds} giây`);
    if (j.result.doc_id === S.ocrDoc) { refreshOcrDoc(); loadOcrInfo(); }
  }
  if (j.kind === 'split' && j.result && j.result.doc_id === S.splitDoc) {
    toast(j.message); S.groupNames = {}; S.selGroup = 0; loadSplitGroups();
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
  const gpu = s.gpus && s.gpus[0];
  if (gpu) {
    $('sbDevice').textContent = `${gpu.name} · VRAM ${(gpu.total_mb / 1024).toFixed(0)} GB`;
    $('sbBar').style.width = Math.round(gpu.used_mb / gpu.total_mb * 100) + '%';
    $('sbMem').textContent = `VRAM ${(gpu.used_mb / 1024).toFixed(1)} / ${(gpu.total_mb / 1024).toFixed(1)} GB · Xử lý: ${s.device}`;
  } else {
    $('sbDevice').textContent = `CPU ${s.cpu_count} luồng · RAM ${s.ram_total_gb} GB`;
    $('sbBar').style.width = s.ram_percent + '%';
    $('sbMem').textContent = `RAM ${s.ram_used_gb} / ${s.ram_total_gb} GB · Xử lý: ${s.device}`;
  }
  $('pillDevice').innerHTML = `${ic(s.gpus && s.gpus.length && s.device === 'GPU' ? 'monitor' : 'cpu')} ${esc(s.device === '-' ? 'Đang khởi động' : s.device)} · ${esc(s.engine)}`;
  if (S.page === 'overview') renderSysBars();
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
  h += `<p class="small muted" style="margin-bottom:0">Model đang hoạt động: ${s.models.length ? s.models.map(m => '<span class="chip">' + esc(m.name) + '</span>').join(' ') : 'chưa nạp'}</p>`;
  $('sysBars').innerHTML = h;
  $('sysEngine').textContent = `${s.device} · ${s.engine}`;
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
  $('mConf').textContent = 'Độ tin cậy OCR ước tính: ' + (st.confidence != null ? st.confidence + '%' : '-');
  const ready = d.models.filter(m => m.ready).length;
  $('mModels').textContent = `${ready}/${d.models.length}`;
  $('mModelsLoaded').textContent = 'Đang nạp: ' + (d.models.filter(m => m.loaded).map(m => m.name).join(', ') || '-');
  $('recentList').innerHTML = d.recent.length ? d.recent.map(r => `<div class="row between" style="margin-bottom:12px"><div>${ic('file-text', 'muted')} <b>${esc(r.name)}</b><div class="small muted" style="margin:5px 0 0 25px">${esc(r.kind_label)} · ${r.pages} trang${r.doc_count ? ' · ' + r.doc_count + ' văn bản' : ''} · ${fmtTime(r.created)}</div></div>${statusChip(r.status)}</div>`).join('')
    : '<div class="empty">Chưa có tác vụ nào. Bấm “Bắt đầu OCR” để xử lý tài liệu đầu tiên.</div>';
  S.system = d.system; renderSysBars();
}
function statusChip(s) {
  const map = { done: 'Hoàn thành', error: 'Lỗi', cancelled: 'Đã hủy', running: 'Đang chạy', queued: 'Đang chờ', paused: 'Tạm dừng' };
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
  if (!silent) toast({ fast: 'Nhanh: PP-OCRv6 + VietOCR', auto: 'Tự động: trang có bảng dùng PP-StructureV3, còn lại PP-OCRv6 + VietOCR', accurate: 'Chính xác: PaddleOCR-VL 1.6 (có GPU) hoặc PP-StructureV3' }[q]);
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
  openModal(`<h2>${ic('download')} Xuất kết quả OCR</h2><p class="sub">${esc(S.docs[S.ocrDoc].name)}</p>
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
  openModal(`<h2>${ic('square-dashed-mouse-pointer')} Kết quả OCR vùng chọn</h2><p class="sub small">${esc(r.engine || '')}</p>
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
const SPLIT_HINTS = {
  ai: 'Dải màu đánh dấu trang bắt đầu văn bản mới do AI đề xuất (vàng = độ tin cậy thấp, cần kiểm tra). Chọn trang để xem lý do và chỉnh điểm tách.',
  manual: 'Chọn cách chia ở khung bên phải, hoặc chọn một trang và bấm “Đặt điểm tách tại đây”.',
  merge: 'Kéo thả trang để sắp xếp; chọn nhiều trang bằng Ctrl/Shift rồi xoay, xóa. Ghép nhiều tài liệu ở khung bên phải.',
  blank: 'Tự tìm trang trắng hoặc trang có mã QR/barcode làm điểm phân cách giữa các văn bản.',
};
function splitTab(t) {
  S.splitTab = t;
  document.querySelectorAll('#splitTabs button').forEach(x => x.classList.toggle('active', x.dataset.splittab === t));
  $('sideManual').classList.toggle('hidden', t !== 'manual');
  $('sideMerge').classList.toggle('hidden', t !== 'merge');
  $('sideBlank').classList.toggle('hidden', t !== 'blank');
  $('sideTitle').textContent = { ai: 'Văn bản AI phát hiện', manual: 'Các phần sau khi chia', merge: 'Các phần của tài liệu', blank: 'Các phần theo điểm phân cách' }[t];
  $('splitHint').innerHTML = ic({ ai: 'lightbulb', manual: 'scissors', merge: 'merge', blank: 'file' }[t]) + ' ' + esc(SPLIT_HINTS[t]);
  renderMergeList();
}
async function selectSplitDoc(id) {
  if (!id) return;
  S.splitDoc = id; $('splitDocSelect').value = id;
  S.sel = new Set(); S.cur = null; S.groupNames = {}; S.selGroup = 0;
  try {
    await loadThumbs(id);
    await loadSplitGroups();
  } catch (e) { fail(e); }
  splitTab(S.splitTab);
}
async function loadSplitGroups() {
  const r = await call('split_groups', S.splitDoc);
  S.groups = r.groups || []; S.scores = r.scores || {};
  S.docs[S.splitDoc].pages = r.pages; S.docs[S.splitDoc].page_count = r.pages.length;
  refreshDocSelects();
  renderSplit();
}
async function refreshSplitDoc(keepGroups = true) {
  const doc = await call('document', S.splitDoc);
  S.docs[S.splitDoc] = doc;
  const missing = doc.pages.filter(p => !(S.thumbs[doc.id] || {})[p.uid]).map(p => p.uid);
  if (missing.length) await loadThumbs(doc.id, missing);
  if (keepGroups && S.groups.length) {
    const exist = new Set(doc.pages.map(p => p.uid));
    const starts = S.groups.map(g => g.start_uid).filter(u => exist.has(u));
    const r = await call('split_set', S.splitDoc, starts, S.groupNames);
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
  const starts = new Map(S.groups.map((g, i) => [g.start_uid, g]));
  $('pagesTitle').textContent = `Xem trước ${doc.pages.length} trang`;
  $('splitPageInfo').textContent = `${doc.pages.length} trang`;
  $('pageStrip').innerHTML = doc.pages.map((p, i) => {
    const gi = groupIndexOf(p.uid), g = starts.get(p.uid);
    const cls = ['pagecard', S.cur === p.uid ? 'selected' : '', S.sel.has(p.uid) && S.cur !== p.uid ? 'multi' : '', g ? 'boundary' : '',
      g && g.confidence < thr ? 'lowb' : '', p.blank ? 'blankpg' : ''].join(' ');
    const tag = p.blank ? '<span class="tag">Trắng</span>' : (p.codes && p.codes.length ? '<span class="tag">QR</span>' : '');
    return `<div class="${cls}" data-uid="${p.uid}" draggable="true"><div class="sheet">${gi >= 0 ? `<span class="gband" style="background:${GROUP_COLORS[gi % GROUP_COLORS.length]}"></span>` : ''}<img src="${(S.thumbs[doc.id] || {})[p.uid] || ''}" loading="lazy" draggable="false">${tag}<span class="num">${i + 1}</span></div><div class="breakbar"></div><small>Trang ${i + 1}${g ? ' · Bắt đầu' : ''}</small></div>`;
  }).join('');
  bindPageCards();
  renderGroups();
  renderSelected();
  $('countDocs').textContent = S.groups.length + ' nhóm';
  $('splitInfo').textContent = S.groups.length ? `${S.groups.length} văn bản · ${S.groups.filter(g => g.confidence < thr).length} điểm tách cần kiểm tra` : 'Chưa phân tích';
}
function bindPageCards() {
  let dragUids = null;
  $('pageStrip').querySelectorAll('.pagecard').forEach(card => {
    const uid = card.dataset.uid;
    card.onclick = e => selectPage(uid, e);
    card.ondblclick = () => previewPage(uid);
    card.ondragstart = e => { dragUids = S.sel.has(uid) ? [...S.sel] : [uid]; card.classList.add('dragging'); e.dataTransfer.setData('text/plain', uid); };
    card.ondragend = () => card.classList.remove('dragging');
    card.ondragover = e => { e.preventDefault(); card.classList.add('dragover'); };
    card.ondragleave = () => card.classList.remove('dragover');
    card.ondrop = async e => {
      e.preventDefault(); e.stopPropagation(); card.classList.remove('dragover');
      if (!dragUids || dragUids.includes(uid)) return;
      const order = S.docs[S.splitDoc].pages.map(p => p.uid).filter(u => !dragUids.includes(u));
      order.splice(order.indexOf(uid), 0, ...dragUids);
      try { await call('pages_reorder', S.splitDoc, order); await refreshSplitDoc(); toast('Đã sắp xếp lại trang'); } catch (err) { fail(err); }
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
  const gi = groupIndexOf(uid); if (gi >= 0) S.selGroup = gi;
  renderSplit();
}
function renderGroups() {
  const thr = S.settings.split_threshold || 70;
  const pages = S.docs[S.splitDoc].pages.map(p => p.uid);
  if (!S.groups.length) { $('groups').innerHTML = '<div class="empty small">Bấm “Phân tích tài liệu” để AI đề xuất điểm tách, hoặc tự đặt điểm tách / chọn cách chia.</div>'; $('groupRename').value = ''; return; }
  $('groups').innerHTML = S.groups.map((g, i) => {
    const a = pages.indexOf(g.uids[0]) + 1, b = pages.indexOf(g.uids[g.uids.length - 1]) + 1;
    const cc = g.confidence < thr ? 'low' : g.confidence < 90 ? 'mid' : '';
    return `<div class="docgroup ${S.selGroup === i ? 'chosen' : ''} ${g.confidence < thr ? 'low' : ''}" data-i="${i}"><div class="row between"><strong style="font-size:12px"><span class="gdot" style="background:${GROUP_COLORS[i % GROUP_COLORS.length]}"></span>${esc(g.name)}</strong>${S.splitTab === 'ai' || g.reasons.length ? `<span class="confidence ${cc}">${g.confidence}%</span>` : ''}</div><div class="muted small" style="margin:7px 0 0 15px">Trang ${a}–${b} · ${g.uids.length} trang${g.type ? ' · ' + esc(g.type) : ''}${g.agency && g.agency !== 'Khác' ? ' · ' + esc(g.agency) : ''}</div></div>`;
  }).join('');
  $('groups').querySelectorAll('.docgroup').forEach(el => el.onclick = () => { S.selGroup = +el.dataset.i; S.cur = S.groups[S.selGroup].start_uid; S.sel = new Set([S.cur]); renderSplit(); });
  const g = S.groups[S.selGroup]; $('groupRename').value = g ? g.name : '';
}
function renderSelected() {
  const doc = S.docs[S.splitDoc];
  if (!S.cur || !doc) { $('selectedPageNum').textContent = '-'; $('selectedGroupName').textContent = '-'; $('pageExplainer').textContent = 'Chọn một trang để xem chi tiết.'; return; }
  const idx = doc.pages.findIndex(p => p.uid === S.cur), p = doc.pages[idx];
  $('selectedPageNum').textContent = S.sel.size > 1 ? `${idx + 1} (+${S.sel.size - 1} trang)` : idx + 1;
  const gi = groupIndexOf(S.cur);
  $('selectedGroupName').textContent = gi >= 0 ? S.groups[gi].name : 'Chưa nhóm';
  const sc = S.scores[S.cur], isStart = S.groups.some(g => g.start_uid === S.cur);
  let html = isStart ? '<b>Trang bắt đầu văn bản.</b> ' : (gi >= 0 ? 'Trang tiếp nối của văn bản. ' : '');
  if (p.blank) html += 'Trang trắng (bỏ qua khi xuất nếu bật trong Cài đặt). ';
  if (p.codes && p.codes.length) html += 'Có mã phân cách: ' + esc(p.codes.join(', ')) + '. ';
  if (sc) html += `AI đánh giá khả năng là trang đầu: <b>${Math.round(sc.prob * 100)}%</b><ul class="reasons">${sc.reasons.map(r => `<li>${esc(r)}</li>`).join('')}</ul>`;
  $('pageExplainer').innerHTML = html || 'Chưa có phân tích AI cho trang này.';
}
function startsList() { return S.groups.map(g => g.start_uid); }
async function applyStarts(starts) {
  const pages = S.docs[S.splitDoc].pages.map(p => p.uid);
  starts = [...new Set(starts)].sort((a, b) => pages.indexOf(a) - pages.indexOf(b));
  if (!starts.length || starts[0] !== pages[0]) starts.unshift(pages[0]);
  try { const r = await call('split_set', S.splitDoc, starts, S.groupNames); S.groups = r.groups; renderSplit(); } catch (e) { fail(e); }
}
async function setBoundary() {
  if (!S.cur) return toast('Chọn một trang trước');
  if (startsList().includes(S.cur)) return toast('Trang này đã là điểm tách');
  await applyStarts([...startsList(), S.cur]);
  toast('Đã tạo điểm tách tại trang đang chọn');
}
async function removeBoundary() {
  const pages = S.docs[S.splitDoc].pages.map(p => p.uid);
  if (!S.cur) return;
  if (S.cur === pages[0]) return toast('Trang đầu luôn bắt đầu một văn bản');
  if (!startsList().includes(S.cur)) return toast('Trang này không có điểm tách');
  delete S.groupNames[S.cur];
  await applyStarts(startsList().filter(u => u !== S.cur));
  toast('Đã bỏ điểm tách');
}
async function combineNext() {
  const i = S.selGroup;
  if (i >= S.groups.length - 1) return toast('Đây là nhóm cuối, không có nhóm tiếp theo');
  const next = S.groups[i + 1].start_uid;
  delete S.groupNames[next];
  await applyStarts(startsList().filter(u => u !== next));
  toast('Đã ghép nhóm tiếp theo');
}
function renameGroup(v) {
  const g = S.groups[S.selGroup];
  if (!g) return;
  g.name = v; S.groupNames[g.start_uid] = v;
  const el = $('groups').querySelector(`.docgroup[data-i="${S.selGroup}"] strong`);
  if (el) el.lastChild.textContent = v;
}
async function toggleAutoNames() {
  if ($('nameAuto').checked) { S.groupNames = {}; }
  else { S.groups.forEach((g, i) => S.groupNames[g.start_uid] = `${baseName(S.docs[S.splitDoc].name).replace(/\.[^.]+$/, '')}_Van_ban_${String(i + 1).padStart(2, '0')}`); }
  await applyStarts(startsList());
}
async function analyzeSplit() {
  if (!S.splitDoc) return addDocuments('split');
  try { await call('split_analyze', S.splitDoc); $('btnAnalyze').disabled = true; splitTab('ai'); toast('AI đang phân tích - OCR từng trang rồi tìm ranh giới văn bản'); } catch (e) { fail(e); }
}
function selectedOrCurrent() { return S.sel.size ? [...S.sel] : (S.cur ? [S.cur] : []); }
async function rotatePages(deg) {
  const uids = selectedOrCurrent();
  if (!uids.length) return toast('Chọn trang cần xoay');
  try { const th = await call('pages_rotate', S.splitDoc, uids, deg); th.forEach(t => S.thumbs[S.splitDoc][t.uid] = t.src); renderSplit(); } catch (e) { fail(e); }
}
async function movePage(dir) {
  if (!S.cur) return toast('Chọn trang cần di chuyển');
  const order = S.docs[S.splitDoc].pages.map(p => p.uid), i = order.indexOf(S.cur), j = i + dir;
  if (j < 0 || j >= order.length) return toast('Không thể di chuyển vượt giới hạn');
  [order[i], order[j]] = [order[j], order[i]];
  try { await call('pages_reorder', S.splitDoc, order); await refreshSplitDoc(); } catch (e) { fail(e); }
}
async function reversePages() { try { await call('pages_reverse', S.splitDoc); await refreshSplitDoc(false); toast('Đã đảo thứ tự trang'); } catch (e) { fail(e); } }
async function deletePages() {
  const uids = selectedOrCurrent();
  if (!uids.length) return toast('Chọn trang cần xóa');
  if (!await confirmBox('Xóa trang', `Xóa ${uids.length} trang khỏi tài liệu đang làm việc? File gốc không bị thay đổi cho tới khi bạn lưu.`, 'Xóa')) return;
  try { await call('pages_delete', S.splitDoc, uids); S.sel = new Set(); S.cur = null; await refreshSplitDoc(); toast(`Đã xóa ${uids.length} trang`); } catch (e) { fail(e); }
}
async function insertPages() {
  if (!S.splitDoc) return;
  const order = S.docs[S.splitDoc].pages.map(p => p.uid);
  const pos = S.cur ? order.indexOf(S.cur) + 1 : order.length;
  try { const r = await call('pages_insert', S.splitDoc, pos, null); if (r.added) { await refreshSplitDoc(); toast(`Đã chèn ${r.added} trang sau trang ${pos}`); } } catch (e) { fail(e); }
}
async function replacePage() {
  if (!S.cur) return toast('Chọn trang cần thay');
  openModal(`<h2>${ic('replace')} Thay trang</h2><p class="sub">Chọn file nguồn và số trang dùng để thay cho trang đang chọn.</p><label class="fieldlabel mt">Lấy trang số</label><input class="input" id="repNo" type="number" min="1" value="1"><div class="row between mt"><button class="btn" onclick="closeModal()">Hủy</button><button class="btn primary" id="repGo">Chọn file…</button></div>`);
  $('repGo').onclick = async () => {
    const no = +$('repNo').value || 1; closeModal();
    try { const r = await call('page_replace', S.splitDoc, S.cur, null, no); if (!r.cancelled) { S.cur = null; await refreshSplitDoc(); toast('Đã thay trang'); } } catch (e) { fail(e); }
  };
}
async function saveSplitDoc() {
  if (!S.splitDoc) return;
  try { const r = await call('save_document', S.splitDoc, null); if (r.path) toast('Đã lưu ' + baseName(r.path), fileActions(r.path)); } catch (e) { fail(e); }
}
async function previewPage(uid) {
  uid = uid || S.cur;
  if (!uid) return;
  const img = await call('page_image', S.splitDoc, uid, 1400);
  openModal(`<img class="bigimg" src="${img.src}"><div class="row between mt"><span class="small muted">Trang ${S.docs[S.splitDoc].pages.findIndex(p => p.uid === uid) + 1}</span><button class="btn" onclick="closeModal()">Đóng</button></div>`, { wide: true });
}
function renderManualInputs() {
  const m = $('manualMethod').value, v = $('manualValue');
  v.classList.toggle('hidden', m === 'odd_even' || m === 'extract');
  v.placeholder = m === 'every' ? 'Số trang mỗi file, VD: 2' : '1-3, 4, 5-8';
}
async function planManual() {
  if (!S.splitDoc) return toast('Chưa có tài liệu');
  const m = $('manualMethod').value;
  const value = m === 'extract' ? selectedOrCurrent() : $('manualValue').value;
  if (m === 'extract' && !value.length) return toast('Chọn các trang cần trích xuất');
  try { const r = await call('split_plan', S.splitDoc, m, value); S.groups = r.groups; S.groupNames = {}; S.selGroup = 0; renderSplit(); toast(`Chia thành ${r.groups.length} phần`); } catch (e) { fail(e); }
}
async function planSeparator(kind) {
  if (!S.splitDoc) return toast('Chưa có tài liệu');
  $('footerInfo').textContent = kind === 'blank' ? 'Đang tìm trang trắng…' : 'Đang đọc mã QR / barcode…';
  try {
    const r = await call('split_plan', S.splitDoc, kind, '');
    S.groups = r.groups; S.groupNames = {}; S.docs[S.splitDoc].pages = r.pages; renderSplit();
    const n = r.pages.filter(p => kind === 'blank' ? p.blank : (p.codes || []).length).length;
    toast(`Tìm thấy ${n} trang phân cách, chia thành ${r.groups.length} phần`);
  } catch (e) { fail(e); }
}
function renderMergeList() {
  const docs = Object.values(S.docs);
  $('mergeList').innerHTML = docs.length ? docs.map(d => `<label class="fileitem"><span><input type="checkbox" class="check mergechk" value="${d.id}" ${d.id === S.splitDoc ? 'checked' : ''}> ${esc(d.name)}</span><span class="meta">${d.page_count} trang</span></label>`).join('') : '<p class="small muted">Chưa mở tài liệu nào</p>';
}
async function mergeDocs() {
  const ids = [...document.querySelectorAll('.mergechk:checked')].map(x => x.value);
  if (ids.length < 2) return toast('Chọn ít nhất 2 tài liệu để ghép');
  try {
    const d = await call('merge_documents', ids, $('mergeName').value || 'Tai_lieu_ghep.pdf');
    S.docs[d.id] = d; refreshDocSelects(); await selectSplitDoc(d.id);
    toast(`Đã ghép ${ids.length} tài liệu thành ${d.page_count} trang - bấm “Lưu PDF” để ghi ra file`);
  } catch (e) { fail(e); }
}
function previewGroupExport() {
  if (!S.splitDoc) return toast('Chưa có tài liệu');
  const doc = S.docs[S.splitDoc];
  const groups = S.groups.length ? S.groups : [{ name: doc.name.replace(/\.[^.]+$/, ''), uids: doc.pages.map(p => p.uid), type: '', agency: '' }];
  const pages = doc.pages.map(p => p.uid), cls = $('classifyBy').value, fmt = $('groupFormat').value;
  const ext = { pdf: '.pdf', searchable_pdf: '.pdf', docx: '.docx', txt: '.txt' }[fmt];
  const folderOf = g => cls === 'type' ? (g.type || 'Khác') + '\\' : cls === 'agency' ? (g.agency || 'Khác') + '\\' : '';
  openModal(`<h2>${ic('download')} Xuất các văn bản đã tách</h2><p class="sub">${groups.length} file sẽ được tạo trong thư mục kết quả:</p>
    <div class="mutedbox" style="margin:13px 0;max-height:300px;overflow:auto">${groups.map(g => `<div style="margin:8px 0">${ic('file-text', 'muted')} ${esc(folderOf(g) + g.name.replace(/[\\/:*?"<>|]/g, '_') + ext)} <span class="muted">(trang ${pages.indexOf(g.uids[0]) + 1}–${pages.indexOf(g.uids[g.uids.length - 1]) + 1})</span></div>`).join('')}</div>
    <div class="row between"><button class="btn" onclick="closeModal()">Hủy</button><button class="btn primary" id="gxGo">${ic('download')} Xuất ${groups.length} file</button></div>`);
  $('gxGo').onclick = async () => {
    $('gxGo').disabled = true; $('gxGo').textContent = 'Đang xuất…';
    try {
      const r = await call('export_groups', S.splitDoc, groups, fmt, cls, null);
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
async function startBatch() {
  if (!S.batchFiles.length) return toast('Vui lòng thêm ít nhất một file');
  try {
    const r = await call('batch_start', S.batchFiles.map(f => f.path), $('batchJob').value, { quality: $('batchQuality').value, classify: $('batchClassify').value });
    S.batchJob = r.job_id;
    $('batchState').textContent = 'Đang chờ bắt đầu…';
    toast(`Đã đưa ${r.count} file vào hàng đợi`);
  } catch (e) { fail(e); }
}
function renderBatchJob(j) {
  $('batchProgress').style.width = Math.round(j.progress * 100) + '%';
  $('batchState').textContent = j.message;
  const running = ['running', 'queued', 'paused'].includes(j.status);
  $('btnPause').classList.toggle('hidden', !running || j.status === 'paused');
  $('btnResume').classList.toggle('hidden', j.status !== 'paused');
  $('btnCancel').classList.toggle('hidden', !running);
  $('btnBatch').disabled = running;
  const failed = (j.items || []).some(it => it.status === 'error');
  $('btnRetry').classList.toggle('hidden', running || !failed);
  $('btnBatchFolder').classList.toggle('hidden', !(j.result && j.result.folder));
  const icon = { queued: ic('clock', 'muted'), running: ic('loader-circle', 'spin'), done: ic('circle-check', 'ok'), error: ic('circle-x', 'bad'), cancelled: ic('square', 'muted') };
  $('batchItems').innerHTML = (j.items || []).map(it => `<div class="batchitem"><span>${icon[it.status] || '•'}</span><div><b>${esc(it.name)}</b>${it.message ? `<div class="msg">${esc(it.message)}</div>` : ''}</div>${statusChip(it.status)}</div>`).join('');
}
function pauseBatch() { call('job_pause', S.batchJob); }
function resumeBatch() { call('job_resume', S.batchJob); }
function cancelBatch() { call('job_cancel', S.batchJob); }
async function retryBatch() { try { const r = await call('batch_retry', S.batchJob); S.batchJob = r.job_id; toast(`Thử lại ${r.count} file`); } catch (e) { fail(e); } }
function openBatchFolder() { const j = S.jobs[S.batchJob]; if (j && j.result) call('open_path', j.result.folder); }
function openOutput() { call('open_path', S.settings.output_dir).catch(fail); }

// ---------------------------------------------------------------- LỊCH SỬ
async function renderHistory() {
  let rows;
  try { rows = await call('history_search', $('historySearch').value, $('hKind').value, $('hStatus').value, +$('hDays').value); } catch (e) { return fail(e); }
  S.historyRows = rows;
  $('historyBody').innerHTML = rows.length ? rows.map(r => `<tr><td><b>${ic('file-text', 'muted')} ${esc(r.name)}</b>${r.tags ? r.tags.split(',').filter(Boolean).map(t => `<span class="tagchip">${esc(t.trim())}</span>`).join('') : ''}${r.snippet ? `<span class="snippet">${esc(r.snippet)}</span>` : r.detail ? `<span class="snippet">${esc(r.detail)}</span>` : ''}</td><td>${esc(r.kind_label)}${r.doc_count ? `<div class="small muted">${r.doc_count} văn bản</div>` : ''}</td><td>${r.pages}</td><td class="muted small">${fmtTime(r.created)}</td><td class="small">${esc(r.engine || '-')}${r.confidence ? `<div class="muted">${Math.round(r.confidence * 100)}%</div>` : ''}</td><td>${statusChip(r.status)}</td><td><div class="acts">
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
  $('modelDevice').textContent = `Thiết bị: ${d.device}`;
  $('defaultEngine').value = d.default_engine;
  const g = d.gpus[0];
  $('vramBox').innerHTML = g ? bar(`GPU ${g.name} · VRAM`, g.used_mb / g.total_mb * 100, `${(g.used_mb / 1024).toFixed(1)} / ${(g.total_mb / 1024).toFixed(1)} GB`) +
    (d.device === 'CPU' ? '<p class="small muted">Có GPU NVIDIA nhưng bản Paddle đang cài là bản CPU - cài paddlepaddle-gpu để tăng tốc.</p>' : '')
    : '<p class="small muted" style="margin:0">Không phát hiện GPU NVIDIA - các model chạy trên CPU. PaddleOCR-VL 1.6 sẽ rất chậm (vài phút/trang).</p>';
  if (!d.paddle) $('modelNotice').innerHTML = ic('triangle-alert') + ' Chưa cài PaddleOCR - phần mềm đang dùng Tesseract. Chi tiết: <pre class="small" style="white-space:pre-wrap">' + esc((d.error || '').slice(-600)) + '</pre>';
  $('modelCards').innerHTML = d.models.map(m => `<div class="card modelcard"><div class="modelico">${ic(m.icon)}</div><div style="flex:1"><b>${esc(m.name)}</b><p class="sub small" style="margin:4px 0 0">${esc(m.desc)}</p>
    <div class="mstate"><span class="badge ${m.ready ? 'ok' : 'bad'}">${m.ready ? 'Đã cài · ' + m.size_mb.toLocaleString('vi-VN') + ' MB' : 'Chưa có file model'}</span>${m.loaded ? '<span class="badge on">Đang nạp trong bộ nhớ</span>' : '<span class="badge">Chưa nạp</span>'}</div></div>
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
function bindSettings() {
  document.querySelectorAll('#settings [data-key]').forEach(el => {
    el.addEventListener('change', () => {
      const k = el.dataset.key;
      let v = el.type === 'checkbox' ? el.checked : el.value;
      if (el.dataset.type === 'int') v = parseInt(v, 10) || 0;
      saveSettings({ [k]: v });
    });
  });
}
function loadSettingsForm() {
  document.querySelectorAll('#settings [data-key]').forEach(el => {
    const v = S.settings[el.dataset.key];
    if (el.type === 'checkbox') el.checked = !!v; else el.value = v;
    if (el.type === 'range' && el.nextElementSibling) el.nextElementSibling.textContent = v + '%';
  });
  renderAbout();
}
function renderAbout() {
  const lic = S.license || {};
  $('aboutBox').innerHTML = `<div class="kv">${S.boot.app.author.map(a => `<span>${esc(a.label)}</span><span>${esc(a.value)}</span>`).join('')}
    <span>Phiên bản</span><span>${esc(S.boot.app.name)} ${esc(S.boot.app.version)}</span>
    <span>Công nghệ OCR</span><span>PP-OCRv6 · VietOCR · PP-StructureV3 · PaddleOCR-VL 1.6</span>
    <span>Bản quyền</span><span>${esc(lic.label || '')}</span><span>Code máy</span><span class="mono">${esc(lic.machine_id || '')}</span></div>`;
}
async function saveSettings(values) {
  try {
    S.settings = await call('settings_save', values);
    applyOcrDefaults();
    footerFlash('Đã lưu cấu hình');
  } catch (e) { fail(e); }
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
    if (S.page === 'split' && e.key === 'Delete' && !/INPUT|TEXTAREA/.test(e.target.tagName)) deletePages();
  });
}
