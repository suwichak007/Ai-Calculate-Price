/* ==========================================
   Manday Cost Calculator — app.js
   ========================================== */

'use strict';

// ── State ──────────────────────────────────
let phases = [];
let nextPhaseId = 1;
let nextItemId  = 1;

const PHASE_COLORS = ['#2563eb','#7c3aed','#059669','#d97706','#dc2626','#0891b2','#65a30d'];

// ── Init ────────────────────────────────────
function init() {
  phases = [
    makePhase('1. Preparation Phase', false, [
      makeItem('', 1, 1, 1, 0),
    ]),
    makePhase('2. Implementation Phase', false, [
      makeItem('', 1, 1, 1, 0),
    ]),
    makePhase('3. Support Service 1 Year', true, [
      makeItem('', 1, 1, 1, 0),
    ]),
  ];
  renderAll();
  recalcTravel();
}

function makePhase(name, isSupport, items) {
  return { id: nextPhaseId++, name, isSupport, items };
}

function makeItem(name, person, times, days, rate) {
  return {
    id: nextItemId++, name,
    person, times, days, rate,
    fuel: 0, hotel: 0, allowance: 0,
    flight: 0, rental: 0, taxi: 0, travelAllow: 0,
  };
}

// ── Travel Calculations ──────────────────────
function recalcTravel() {
  const rate     = num('fuelRate');
  const dist     = num('distance');
  const toll     = num('tollCost');
  const fuel     = rate * dist;
  const perTrip  = fuel + toll;
  const roundtrip= perTrip * 2;

  setText('fuelCostOut',     fmt(fuel));
  setText('travelPerTripOut',fmt(perTrip));
  setText('travelRTOut',     fmt(roundtrip));

  recalcAll();
}

// ── Item cost formula: คน × ครั้ง × วัน × Rate + ค่าเดินทางรวม ──
function calcItemCost(item) {
  const base    = item.person * item.times * item.days * item.rate;
  const travel  = (item.fuel + item.hotel + item.allowance +
                   item.flight + item.rental + item.taxi + item.travelAllow)
                  * item.person * item.times * item.days;
  return base + travel;
}

// ── Full Recalc ──────────────────────────────
function recalcAll() {
  let implCost    = 0;
  let supportCost = 0;
  let totalManday = 0;

  phases.forEach(ph => {
    let phTotal = 0;
    ph.items.forEach(item => {
      const c = calcItemCost(item);
      phTotal    += c;
      totalManday += item.person * item.times * item.days;
      updateCostCell(ph.id, item.id, c);
    });
    updatePhaseBadge(ph.id, phTotal);
    if (ph.isSupport) supportCost += phTotal;
    else              implCost    += phTotal;
  });

  const markup   = (num('markupPct') || 0) / 100;
  const implSale = implCost * (1 + markup);
  const totalSale= implSale + supportCost;
  const suppPct  = implSale > 0 ? (supportCost / implSale * 100) : 0;

  // Summary
  setText('sumImplCost',  fmt(implCost));
  setText('sumImplSale',  fmt(implSale));
  setText('sumSupport',   fmt(supportCost));
  setText('sumTotal',     fmt(totalSale));
  setText('sumSuppPct',   suppPct.toFixed(2) + '%');
  setText('sumManday',    fmtN(totalManday));
  setText('statSalePrice',fmt(implSale));
  setText('statTotal',    fmt(totalSale));
  setText('statManday',   fmtN(totalManday));
  setText('statSuppPct',  suppPct.toFixed(1) + '%');
}

function updateCostCell(phId, itemId, cost) {
  const el = document.getElementById(`cost-${phId}-${itemId}`);
  if (el) el.textContent = fmt(cost);
}

function updatePhaseBadge(phId, total) {
  const el = document.getElementById(`phase-total-${phId}`);
  if (el) el.textContent = fmt(total);
}

// ── Render ───────────────────────────────────
function renderAll() {
  const container = document.getElementById('phases-container');
  container.innerHTML = '';
  phases.forEach((ph, idx) => {
    container.appendChild(renderPhase(ph, idx));
  });
  recalcAll();
}

function renderPhase(ph, idx) {
  const color = PHASE_COLORS[idx % PHASE_COLORS.length];
  const wrap  = document.createElement('div');
  wrap.className = 'phase-block';
  wrap.id = `phase-block-${ph.id}`;

  // Header
  const header = document.createElement('div');
  header.className = 'phase-header';

  const dot = document.createElement('div');
  dot.className = 'phase-color-dot';
  dot.style.background = color;

  const nameInput = document.createElement('input');
  nameInput.className  = 'phase-name-input';
  nameInput.type       = 'text';
  nameInput.value      = ph.name;
  nameInput.addEventListener('input', e => { ph.name = e.target.value; });

  const supportToggle = document.createElement('label');
  supportToggle.className = 'phase-support-toggle' + (ph.isSupport ? ' active' : '');
  supportToggle.innerHTML = `<input type="checkbox" ${ph.isSupport ? 'checked' : ''}> 🕐 Support/Service`;
  supportToggle.querySelector('input').addEventListener('change', e => {
    ph.isSupport = e.target.checked;
    supportToggle.classList.toggle('active', ph.isSupport);
    recalcAll();
  });

  const totalBadge = document.createElement('div');
  totalBadge.className = 'phase-total-badge';
  totalBadge.id = `phase-total-${ph.id}`;
  totalBadge.textContent = '฿0';

  const removeBtn = document.createElement('button');
  removeBtn.className = 'btn-remove-phase';
  removeBtn.title = 'ลบ Phase';
  removeBtn.innerHTML = '✕';
  removeBtn.addEventListener('click', () => removePhase(ph.id));

  header.append(dot, nameInput, supportToggle, totalBadge, removeBtn);
  wrap.appendChild(header);

  // Table
  const tableWrap = document.createElement('div');
  tableWrap.className = 'items-table-wrap';

  const table = document.createElement('table');
  table.className = 'items-table';

  table.innerHTML = `
    <thead>
      <tr>
        <th style="min-width:200px">รายการ</th>
        <th class="right" style="width:62px">คน</th>
        <th class="right" style="width:62px">ครั้ง</th>
        <th class="right" style="width:62px">วัน</th>
        <th style="width:110px">Rate (฿)</th>
        <th style="width:82px">น้ำมัน</th>
        <th style="width:82px">โรงแรม</th>
        <th style="width:82px">เบี้ยเลี้ยง</th>
        <th style="width:82px">เครื่องบิน</th>
        <th style="width:82px">เช่ารถ</th>
        <th style="width:72px">Taxi</th>
        <th style="width:82px">เบี้ยเดินทาง</th>
        <th class="right" style="width:110px">Cost</th>
        <th style="width:36px"></th>
      </tr>
    </thead>
    <tbody id="tbody-${ph.id}"></tbody>
  `;

  tableWrap.appendChild(table);
  wrap.appendChild(tableWrap);

  // Render rows
  ph.items.forEach(item => appendItemRow(ph, item));

  // Add item row
  const tfoot = document.createElement('tfoot');
  tfoot.innerHTML = `
    <tr class="add-item-row">
      <td colspan="14">
        <button class="btn-add-item" id="add-item-${ph.id}">
          <span style="font-size:16px;line-height:1">+</span> เพิ่มรายการ
        </button>
      </td>
    </tr>
  `;
  table.appendChild(tfoot);
  table.querySelector(`#add-item-${ph.id}`).addEventListener('click', () => addItem(ph.id));

  return wrap;
}

function appendItemRow(ph, item) {
  const tbody = document.getElementById(`tbody-${ph.id}`);
  if (!tbody) return;

  const tr = document.createElement('tr');
  tr.id = `row-${ph.id}-${item.id}`;

  const fields = [
    { key:'name',        type:'text',   cls:'',     style:'min-width:190px' },
    { key:'person',      type:'number', cls:'num',  style:'width:56px' },
    { key:'times',       type:'number', cls:'num',  style:'width:56px' },
    { key:'days',        type:'number', cls:'num',  style:'width:56px' },
    { key:'rate',        type:'number', cls:'rate', style:'width:100px' },
    { key:'fuel',        type:'number', cls:'num',  style:'width:72px' },
    { key:'hotel',       type:'number', cls:'num',  style:'width:72px' },
    { key:'allowance',   type:'number', cls:'num',  style:'width:72px' },
    { key:'flight',      type:'number', cls:'num',  style:'width:72px' },
    { key:'rental',      type:'number', cls:'num',  style:'width:72px' },
    { key:'taxi',        type:'number', cls:'num',  style:'width:62px' },
    { key:'travelAllow', type:'number', cls:'num',  style:'width:72px' },
  ];

  let html = '';
  fields.forEach(f => {
    html += `<td>
      <input
        class="tbl-input ${f.cls}"
        type="${f.type}"
        value="${esc(item[f.key])}"
        style="${f.style}"
        ${f.type === 'number' ? 'min="0" step="' + (f.key==='rate'?'500':'0.5') + '"' : ''}
        data-key="${f.key}"
      >
    </td>`;
  });

  html += `
    <td class="cost-cell" id="cost-${ph.id}-${item.id}">฿0</td>
    <td><button class="btn-remove-row" title="ลบรายการ">✕</button></td>
  `;

  tr.innerHTML = html;

  // Events
  tr.querySelectorAll('input[data-key]').forEach(input => {
    input.addEventListener('input', e => {
      const k = e.target.dataset.key;
      item[k] = k === 'name' ? e.target.value : (parseFloat(e.target.value) || 0);
      recalcAll();
    });
  });

  tr.querySelector('.btn-remove-row').addEventListener('click', () => removeItem(ph.id, item.id));

  tbody.appendChild(tr);
}

// ── Mutations ────────────────────────────────
function addPhase() {
  const ph = makePhase('Phase ใหม่', false, [
    makeItem('', 1, 1, 1, 0),
  ]);
  phases.push(ph);
  renderAll();
}

function removePhase(phId) {
  phases = phases.filter(p => p.id !== phId);
  renderAll();
}

function addItem(phId) {
  const ph = phases.find(p => p.id === phId);
  if (!ph) return;
  const item = makeItem('', 1, 1, 1, 0);
  ph.items.push(item);
  appendItemRow(ph, item);
  recalcAll();
}

function removeItem(phId, itemId) {
  const ph = phases.find(p => p.id === phId);
  if (!ph) return;
  ph.items = ph.items.filter(i => i.id !== itemId);
  const row = document.getElementById(`row-${phId}-${itemId}`);
  if (row) row.remove();
  recalcAll();
}

// ── Helpers ──────────────────────────────────
function num(id) { return parseFloat(document.getElementById(id)?.value) || 0; }
function setVal(id, v) { const el = document.getElementById(id); if (el) el.value = v; }
function setText(id, v) { const el = document.getElementById(id); if (el) el.textContent = v; }

function fmt(n) {
  if (!isFinite(n)) return '—';
  return '฿' + Math.round(n).toLocaleString('th-TH');
}

function fmtN(n) {
  return Number.isFinite(n) ? n.toLocaleString('th-TH') : '0';
}

function esc(s) {
  return String(s)
    .replace(/&/g,'&amp;')
    .replace(/</g,'&lt;')
    .replace(/>/g,'&gt;')
    .replace(/"/g,'&quot;');
}

// ── Boot ─────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  // Travel inputs
  ['fuelRate','distance','tollCost'].forEach(id => {
    document.getElementById(id)?.addEventListener('input', recalcTravel);
  });

  // Markup
  document.getElementById('markupPct')?.addEventListener('input', recalcAll);

  // Add phase button
  document.getElementById('btnAddPhase')?.addEventListener('click', addPhase);

  init();
});