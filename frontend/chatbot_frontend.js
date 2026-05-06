/* chatbot_frontend.js  v1.3 — + Excel Upload */

const PORT = 8061;
const IS_FILE = window.location.protocol === 'file:';
const API_BASE = IS_FILE ? `http://192.168.105.11:${PORT}` : '';
const SESSION_ID = 'session_' + Math.random().toString(36).slice(2, 10);

const REQUIRED_FIELDS = [
  { key: 'requester_name',  label: 'ชื่อผู้ขอ / ผู้จัดทำ' },
  { key: 'project_name',    label: 'ชื่อโครงการ' },
  { key: 'markup_pct',      label: 'Markup %' },
  { key: 'prepare_items',   label: 'Prepare: หัวเรื่อง' },
  { key: 'implement_items', label: 'Implement: หัวเรื่อง' },
  { key: 'service_items',   label: 'Service: หัวเรื่อง' },
];

let chatStarted  = false;
let currentState = {};
let isComplete   = false;


// ── Status check ───────────────────────────────────────────────

async function checkStatus() {
  const banner = document.getElementById('portBanner');
  document.getElementById('correctUrl').textContent = `http://localhost:${PORT}`;
  try {
    const ctrl = new AbortController();
    const tid  = setTimeout(() => ctrl.abort(), 5000);
    const r    = await fetch(`${API_BASE}/health`, { signal: ctrl.signal, cache: 'no-store' });
    clearTimeout(tid);
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    await r.json();
    banner.classList.remove('show');
  } catch {
    banner.classList.add('show');
  }
}


// ── Input helpers ───────────────────────────────────────────────

function handleKey(e) {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); }
}
function autoResize(el) {
  el.style.height = 'auto';
  el.style.height = Math.min(el.scrollHeight, 120) + 'px';
}


// ── Send message ────────────────────────────────────────────────

async function sendMessage() {
  const input = document.getElementById('chatInput');
  const text  = input.value.trim();
  if (!text) return;

  if (!chatStarted) {
    document.getElementById('welcomeScreen').style.display = 'none';
    chatStarted = true;
  }

  input.value = '';
  input.style.height = 'auto';
  appendMessage('user', text);

  const typing = showTyping();
  document.getElementById('sendBtn').disabled = true;

  try {
    const ctrl = new AbortController();
    const tid  = setTimeout(() => ctrl.abort(), 300000);
    const res  = await fetch(`${API_BASE}/chat`, {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ session_id: SESSION_ID, message: text }),
      signal:  ctrl.signal,
    });
    clearTimeout(tid);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();

    removeTyping(typing);
    appendMessage('bot', data.reply);
    currentState = data.state_summary || {};
    isComplete   = data.is_complete;
    updateProgress(currentState);
    if (data.result) updateResultPanel(data.result);
    updateExportButtons(data.is_complete);

  } catch (err) {
    removeTyping(typing);
    const msg = err.name === 'AbortError'
      ? '⏱️ LLM ใช้เวลานานเกินไป ลองใหม่อีกครั้งครับ'
      : `⚠️ เชื่อมต่อ server ไม่ได้\n\nเปิด browser ที่: **http://localhost:${PORT}**`;
    appendMessage('bot', msg);
    checkStatus();
  }

  document.getElementById('sendBtn').disabled = false;
  input.focus();
}

function sendExample(text) {
  document.getElementById('chatInput').value = text;
  sendMessage();
}


// ── Excel Upload ───────────────────────────────────────────────

function handleDragOver(e) {
  e.preventDefault();
  document.getElementById('uploadDropZone').classList.add('drag-over');
}
function handleDragLeave() {
  document.getElementById('uploadDropZone').classList.remove('drag-over');
}
function handleDrop(e) {
  e.preventDefault();
  document.getElementById('uploadDropZone').classList.remove('drag-over');
  const file = e.dataTransfer.files[0];
  if (file) uploadExcel(file);
}
function handleFileSelect(e) {
  const file = e.target.files[0];
  if (file) uploadExcel(file);
  e.target.value = '';  // reset เพื่อให้เลือกไฟล์เดิมซ้ำได้
}

async function uploadExcel(file) {
  const status = document.getElementById('uploadStatus');

  if (!file.name.match(/\.xlsx?$/i)) {
    setUploadStatus('error', '❌ รองรับเฉพาะไฟล์ .xlsx / .xls เท่านั้น');
    return;
  }

  // show loading
  status.className   = 'upload-status loading';
  status.style.display = 'flex';
  status.innerHTML   = `<div class="upload-spinner"></div> กำลังอ่านไฟล์ <strong>${file.name}</strong>…`;

  const formData = new FormData();
  formData.append('file', file);

  try {
    const ctrl = new AbortController();
    const tid  = setTimeout(() => ctrl.abort(), 60000);

    const res = await fetch(`${API_BASE}/upload/excel/${SESSION_ID}`, {
      method: 'POST',
      body:   formData,
      signal: ctrl.signal,
    });
    clearTimeout(tid);

    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: `HTTP ${res.status}` }));
      throw new Error(err.detail || `HTTP ${res.status}`);
    }

    const data = await res.json();

    // แสดง welcome screen ออก
    if (!chatStarted) {
      document.getElementById('welcomeScreen').style.display = 'none';
      chatStarted = true;
    }

    // แสดงข้อความใน chat
    appendMessage('bot', data.reply);
    currentState = data.state_summary || {};
    isComplete   = data.is_complete;
    updateProgress(currentState);
    if (data.result) updateResultPanel(data.result);
    updateExportButtons(data.is_complete);

    // status badge
    const items    = data.state_summary?.phase_items || [];
    const newCount = items.length;
    setUploadStatus('success',
      `✅ นำเข้า <strong>${newCount} หัวเรื่อง</strong> จาก <em>${file.name}</em>`
    );

  } catch (err) {
    const msg = err.name === 'AbortError'
      ? 'หมดเวลา — ไฟล์อาจใหญ่เกินไป หรือ server ไม่ตอบ'
      : err.message || 'เกิดข้อผิดพลาด';
    setUploadStatus('error', `❌ ${msg}`);
    checkStatus();
  }
}

function setUploadStatus(type, html) {
  const el = document.getElementById('uploadStatus');
  el.className     = `upload-status ${type}`;
  el.style.display = 'block';
  el.innerHTML     = html;
  if (type === 'success') {
    setTimeout(() => { el.style.display = 'none'; }, 9000);
  }
}


// ── Export ──────────────────────────────────────────────────────

async function exportFile(type) {
  const btn  = document.getElementById(type === 'excel' ? 'btnExcel' : 'btnPdf');
  const orig = btn.innerHTML;
  btn.disabled = true;
  btn.innerHTML = `<span class="icon-badge">⏳</span> กำลังสร้างไฟล์...`;

  try {
    const res = await fetch(`${API_BASE}/export/${type}/${SESSION_ID}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);

    const blob  = await res.blob();
    const a     = document.createElement('a');
    a.href      = URL.createObjectURL(blob);
    const cd    = res.headers.get('Content-Disposition') || '';
    const match = cd.match(/filename\*=UTF-8''(.+)/i) || cd.match(/filename="?([^"]+)"?/i);
    a.download  = match
      ? decodeURIComponent(match[1])
      : `manday_${Date.now()}.${type === 'excel' ? 'xlsx' : 'pdf'}`;

    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(a.href);

    btn.innerHTML = `<span class="icon-badge">✅</span> ดาวน์โหลดสำเร็จ!`;
    setTimeout(() => { btn.innerHTML = orig; btn.disabled = false; }, 2500);
  } catch {
    btn.innerHTML = `<span class="icon-badge">❌</span> เกิดข้อผิดพลาด`;
    setTimeout(() => { btn.innerHTML = orig; btn.disabled = false; }, 2500);
  }
}


// ── Markdown renderer ────────────────────────────────────────────

function md(t) {
  t = t.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  t = t.replace(/```[\w]*\n?([\s\S]*?)```/g, (_, c) => `<pre>${c.trim()}</pre>`);
  t = t.replace(/`([^`]+)`/g, '<code>$1</code>');
  t = t.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
  t = t.replace(/\*(.*?)\*/g, '<em>$1</em>');
  t = t.replace(/^## (.+)$/gm, '<h2>$1</h2>');
  t = t.replace(/^---$/gm, '<hr style="border:none;border-top:1px solid rgba(0,0,0,.1);margin:.5em 0">');
  t = t.replace(/\|(.+)\|\n\|[-| :]+\|\n((?:\|.+\|\n?)*)/g, (_, head, body) => {
    const ths = head.split('|').filter(Boolean).map(c => `<th>${c.trim()}</th>`).join('');
    const trs = body.trim().split('\n').map(row => {
      const tds = row.split('|').filter(Boolean).map(c => `<td>${c.trim()}</td>`).join('');
      return `<tr>${tds}</tr>`;
    }).join('');
    return `<table><thead><tr>${ths}</tr></thead><tbody>${trs}</tbody></table>`;
  });
  t = t.replace(/\n/g, '<br>');
  return t;
}


// ── Chat render helpers ──────────────────────────────────────────

function appendMessage(role, text) {
  const wrap = document.getElementById('messagesWrap');
  const div  = document.createElement('div');
  div.className = `msg ${role === 'user' ? 'user' : ''}`;
  const time = new Date().toLocaleTimeString('th-TH', { hour: '2-digit', minute: '2-digit' });
  div.innerHTML = `
    <div class="msg-avatar">${role === 'user' ? '👤' : '🤖'}</div>
    <div>
      <div class="msg-bubble">${md(text)}</div>
      <div class="msg-time">${time}</div>
    </div>`;
  wrap.appendChild(div);
  wrap.scrollTop = wrap.scrollHeight;
}

function showTyping() {
  const wrap = document.getElementById('messagesWrap');
  const div  = document.createElement('div');
  div.className = 'typing-indicator';
  div.id = 'typingIndicator';
  div.innerHTML = `<div class="msg-avatar">🤖</div><div class="typing-dots"><span></span><span></span><span></span></div>`;
  wrap.appendChild(div);
  wrap.scrollTop = wrap.scrollHeight;
  return div;
}
function removeTyping(el) { el && el.remove(); }


// ── Sidebar: progress steps ──────────────────────────────────────

function updateProgress(state) {
  const container = document.getElementById('progressSteps');
  container.innerHTML = '';
  REQUIRED_FIELDS.forEach((f, i) => {
    const val      = stateValue(state, f.key);
    const isDone   = val !== undefined && val !== '';
    const isActive = !isDone && i === REQUIRED_FIELDS.findIndex(
      x => stateValue(state, x.key) === undefined || stateValue(state, x.key) === ''
    );
    const div     = document.createElement('div');
    div.className = `step-item ${isDone ? 'done' : isActive ? 'active' : 'pending'}`;
    div.innerHTML = `
      <div class="step-dot">${isDone ? '✓' : i + 1}</div>
      <div style="min-width:0">
        <div class="step-label">${f.label}</div>
        ${isDone ? `<div class="step-value">${fmtVal(f.key, val)}</div>` : ''}
      </div>`;
    container.appendChild(div);
  });
}

function stateValue(state, key) {
  if (!key.endsWith('_items')) return state[key];
  const phase = key.replace('_items', '');
  const items = Array.isArray(state.phase_items) ? state.phase_items : [];
  const count = items.filter(x => x && x.phase === phase).length;
  if (count)                               return count;
  if (state[`${phase}_cost`] !== undefined) return 'รวม ' + state[`${phase}_cost`];
  return undefined;
}

function fmtVal(key, val) {
  if (key === 'requester_name') return String(val);
  if (key === 'project_name')   return String(val);
  if (key === 'markup_pct')     return val + '%';
  if (key.endsWith('_rate'))    return '฿' + Number(val).toLocaleString('th-TH') + '/วัน';
  if (key.endsWith('_person'))  return val + ' คน';
  if (key.endsWith('_times'))   return val + ' ครั้ง';
  if (key.endsWith('_days'))    return val + ' วัน';
  if (key.endsWith('_items'))   return val + ' หัวเรื่อง';
  return String(val);
}


// ── Sidebar: result panel ────────────────────────────────────────

function updateResultPanel(result) {
  document.getElementById('resultPlaceholder').style.display = 'none';
  const rows = document.getElementById('resultRows');
  rows.style.display = 'block';
  const b = n => '฿' + Number(n).toLocaleString('th-TH');
  const phases = result.phase_costs || [];
  const phaseRows = phases.map(p => `
    <div class="phase-group">
      <div class="phase-total">
        <span class="phase-name">${p.label}</span>
        <span>${Number(p.manday || 0).toLocaleString('th-TH', {minimumFractionDigits: 0, maximumFractionDigits: 2})} md</span>
        <strong>${b(p.cost || 0)}</strong>
      </div>
      ${(p.items || []).map(item => `
        <div class="phase-row">
          <span>${item.title || '-'}</span>
          <span>${Number(item.person || 0).toLocaleString('th-TH')} คน</span>
          <span>${Number(item.times || 0).toLocaleString('th-TH')} ครั้ง</span>
          <span>${Number(item.days || 0).toLocaleString('th-TH', {minimumFractionDigits: 0, maximumFractionDigits: 2})} วัน</span>
          <span>${b(item.rate || 0)}</span>
          <strong>${b(item.cost || 0)}</strong>
        </div>`).join('')}
    </div>`).join('');
  rows.innerHTML = `
    <div class="result-row"><span class="r-label">Manday รวม</span><span class="r-value">${Number(result.manday).toLocaleString('th-TH', {minimumFractionDigits: 0, maximumFractionDigits: 2})} วัน</span></div>
    <div class="phase-table">
      <div class="phase-head">
        <span>หัวเรื่อง</span><span>คน</span><span>ครั้ง</span><span>วัน</span><span>Rate</span><span>ต้นทุน</span>
      </div>
      ${phaseRows}
    </div>
    <div class="result-row"><span class="r-label">รวม 3 Phase</span><span class="r-value blue">${b(result.subtotal_cost || 0)}</span></div>
    <div class="result-row"><span class="r-label">กำไรหลังรวม 3 Phase (${result.markup_pct || 0}%)</span><span class="r-value">${b(result.profit || 0)}</span></div>
    <div class="result-row"><span class="r-label">ยอดรวม</span><span class="r-value green">${b(result.total)}</span></div>`;
}

function updateExportButtons(complete) {
  document.getElementById('exportGroup').style.display = complete ? 'block' : 'none';
}


// ── Reset ────────────────────────────────────────────────────────

async function resetChat() {
  await fetch(`${API_BASE}/session/${SESSION_ID}`, { method: 'DELETE' }).catch(() => {});
  document.getElementById('messagesWrap').innerHTML = buildWelcomeHTML();
  currentState = {};
  isComplete   = false;
  chatStarted  = false;
  updateProgress({});
  document.getElementById('resultPlaceholder').style.display = 'block';
  document.getElementById('resultRows').style.display = 'none';
  document.getElementById('exportGroup').style.display = 'none';
  document.getElementById('uploadStatus').style.display = 'none';
  document.getElementById('uploadDropZone').classList.remove('drag-over');
}

function buildWelcomeHTML() {
  return `
    <div class="welcome" id="welcomeScreen">
      <div class="welcome-icon">🤖</div>
      <h2>สวัสดีครับ!</h2>
      <p>เริ่มต้นด้วยการ <strong>อัพโหลดไฟล์ Excel</strong> (Project Plan) หรือพิมพ์ข้อมูลโดยตรง</p>
      <div class="welcome-examples">
        <button class="example-btn" onclick="document.getElementById('excelFileInput').click()">
          <span class="ex-icon">📂</span><span>อัพโหลดไฟล์ Excel Project Plan (.xlsx)</span>
        </button>
        <button class="example-btn" onclick="sendExample('ชื่อผู้ขอ สมชาย ใจดี โครงการ ERP ลูกค้า ABC markup 15%\\n\\nPrepare:\\n- หัวข้อ: Requirement Workshop\\n  คน: 1\\n  ครั้ง: 1\\n  วัน/ครั้ง: 2\\n  Rate: 4500\\n\\nImplement:\\n- หัวข้อ: Setup ระบบ\\n  คน: 2\\n  ครั้ง: 2\\n  วัน/ครั้ง: 4\\n  Rate: 4500\\n- หัวข้อ: Training\\n  คน: 1\\n  ครั้ง: 1\\n  วัน/ครั้ง: 2\\n  Rate: 4500\\n\\nService:\\n- หัวข้อ: Support หลัง Go-live\\n  คน: 1\\n  ครั้ง: 1\\n  วัน/ครั้ง: 3\\n  Rate: 3500')">
          <span class="ex-icon">⚡</span><span>ERP ABC · หัวเรื่องย่อยในแต่ละ phase พร้อม markup 15%</span>
        </button>
        <button class="example-btn" onclick="sendExample('ต้องการคำนวณค่าใช้จ่ายโครงการ')">
          <span class="ex-icon">🧮</span><span>เริ่มต้นคำนวณค่าใช้จ่ายโครงการใหม่</span>
        </button>
      </div>
    </div>`;
}


// ── Init ─────────────────────────────────────────────────────────

updateProgress({});
checkStatus();
setInterval(checkStatus, 20000);
document.getElementById('chatInput').focus();