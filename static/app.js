'use strict';
const byId = id => document.getElementById(id);
const state = { id: null, profile: null, fileName: '', offset: 0, impact: null, simulatedRecipe: null, isBusy: false };
const pageLabels = { overview: 'Overview', quality: 'Quality explorer', repair: 'Repair studio', rules: 'Rule checker' };
const number = n => Number(n).toLocaleString();
const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
const scrollBehavior = () => prefersReducedMotion.matches ? 'auto' : 'smooth';
function el(tag, className = '', content = '') { const node = document.createElement(tag); if (className) node.className = className; node.textContent = String(content); return node; }
function notice(message, ok = false) { const node = byId('notice'); node.textContent = message; node.hidden = false; node.classList.toggle('ok', ok); node.scrollIntoView({ block: 'nearest', behavior: scrollBehavior() }); }
function clearNotice() { byId('notice').hidden = true; }
async function api(path, options = {}) {
  const res = await fetch(path, { cache: 'no-store', ...options });
  if (!res.ok) { let detail = `Request failed (${res.status})`; try { const body = await res.json(); if (typeof body.detail === 'string') detail = body.detail; } catch {} throw new Error(detail); }
  if (res.headers.get('content-type')?.includes('application/json')) return res.json();
  return res;
}
function busy(value, message = 'Processing…') { state.isBusy = value; byId('loading').hidden = !value; byId('loading-label').textContent = message; document.querySelectorAll('button').forEach(button => { if (button.id !== 'remove-button') button.disabled = value; }); if (!value && state.profile) { byId('prev-page').disabled = state.offset === 0; byId('next-page').disabled = state.offset + 25 >= state.profile.rows; } }
function showPage(page) {
  document.querySelectorAll('.page').forEach(node => node.classList.toggle('active', node.id === `page-${page}`));
  document.querySelectorAll('.nav-link').forEach(node => node.classList.toggle('active', node.dataset.page === page));
  byId('crumb-page').textContent = pageLabels[page];
  clearNotice();
  window.scrollTo({ top: 0, behavior: scrollBehavior() });
}
function metric(label, value, note) { const node = el('div', 'metric'); node.append(el('div', 'metric-label', label), el('div', 'metric-value', value), el('div', 'metric-note', note)); return node; }
function renderMetrics(containerId) { const p = state.profile; const node = byId(containerId); node.replaceChildren(metric('Rows', number(p.rows), 'Full dataset'), metric('Columns', number(p.column_count), 'Fields detected'), metric('Missing cells', number(p.missing_cells), `${p.missing_pct}% of all cells`), metric('Duplicate rows', number(p.duplicate_rows), 'Exact matches')); }
function renderBars(containerId) {
  const node = byId(containerId); node.replaceChildren();
  for (const entry of state.profile.column_missing.slice(0, containerId === 'column-bars' ? 7 : 100)) {
    const wrap = el('div'); const head = el('div', 'bar-head'); head.append(el('span', '', entry.name), el('span', '', `${number(entry.missing)} · ${(entry.missing * 100 / state.profile.rows).toFixed(1)}%`));
    const track = el('progress', 'bar-progress'); track.max = state.profile.rows; track.value = entry.missing; wrap.append(head, track); node.append(wrap);
  }
}
function renderQualityTable() {
  const table = el('table'); const thead = el('thead'); const tr = el('tr'); for (const label of ['Column', 'Missing values', 'Missing %', 'Present values']) tr.append(el('th', '', label)); thead.append(tr); table.append(thead);
  const tbody = el('tbody'); for (const row of state.profile.column_missing) { const tr = el('tr'); tr.append(el('td', '', row.name), el('td', 'missing', number(row.missing)), el('td', '', `${(row.missing * 100 / state.profile.rows).toFixed(2)}%`), el('td', '', number(state.profile.rows - row.missing))); tbody.append(tr); } table.append(tbody); byId('quality-columns').replaceChildren(table);
}
async function loadPreview() {
  if (!state.id) return;
  const result = await api(`/api/datasets/${state.id}/preview?limit=25&offset=${state.offset}`);
  const table = el('table'); const thead = el('thead'); const tr = el('tr'); for (const label of result.columns) tr.append(el('th', '', label)); thead.append(tr); table.append(thead); const tbody = el('tbody');
  for (const row of result.rows) { const tr = el('tr'); for (const val of row) tr.append(el('td', '', val)); tbody.append(tr); } table.append(tbody); byId('table-container').replaceChildren(table);
  byId('page-number').textContent = `Page ${Math.floor(state.offset / 25) + 1}`;
  byId('prev-page').disabled = state.offset === 0;
  byId('next-page').disabled = state.offset + 25 >= state.profile.rows;
}
function renderDataset(profile) {
  state.profile = profile; state.offset = 0; state.impact = null; state.simulatedRecipe = null;
  byId('dataset-results').hidden = false; byId('dataset-name').textContent = profile.filename;
  document.querySelectorAll('.requires-data').forEach(node => node.hidden = false);
  document.querySelectorAll('[data-empty]').forEach(node => node.hidden = true);
  renderMetrics('metric-grid'); renderMetrics('quality-metrics'); renderBars('column-bars'); renderQualityTable();
  const column = byId('rule-column'); column.replaceChildren(); for (const item of profile.columns) { const opt = el('option', '', item); opt.value = item; column.append(opt); }
  byId('impact-empty').hidden = false; byId('impact-results').hidden = true; byId('rule-results').replaceChildren(el('p', 'subtle', 'No checks run yet.'));
  loadPreview().catch(e => notice(e.message));
}
async function uploadFile(file) {
  if (!file) return;
  if (!file.name.toLowerCase().endsWith('.csv')) return notice('Choose a UTF-8 CSV file. Other formats are not supported in this build.');
  if (file.size > 200 * 1024 * 1024) return notice('File exceeds the default 200 MiB upload limit.');
  if (state.isBusy) return;
  clearNotice(); busy(true, 'Streaming your file into the data-quality engine…');
  try {
    const form = new FormData(); form.append('file', file, file.name);
    const result = await api('/api/datasets', { method: 'POST', body: form });
    const oldId = state.id;
    state.id = result.dataset_id;
    renderDataset(result.profile);
    if (oldId) api(`/api/datasets/${oldId}`, { method: 'DELETE' }).catch(() => {});
    notice('Dataset imported successfully. Choose Quality explorer, Repair studio, or Rule checker to continue.', true);
  } catch (e) { notice(e.message); } finally { busy(false); }
}
function recipe() { return { trim_whitespace: byId('opt-trim').checked, normalize_blanks: byId('opt-blanks').checked, remove_exact_duplicates: byId('opt-dedupe').checked }; }
function invalidateSimulation() { state.impact = null; state.simulatedRecipe = null; byId('impact-empty').hidden = false; byId('impact-results').hidden = true; }
async function runSimulation() {
  if (!state.id) return;
  busy(true, 'Calculating exact repair impact (large datasets may take time)…'); clearNotice();
  try {
    const current = recipe();
    const outcome = await api(`/api/datasets/${state.id}/simulate`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(current) });
    state.impact = outcome; state.simulatedRecipe = current;
    const box = byId('impact-metrics'); box.replaceChildren();
    for (const [label, value, info] of [['Rows retained', outcome.after.rows, `Was ${number(outcome.before.rows)}`], ['Cells changed', outcome.impact.changed_cells_in_kept_rows, 'In retained rows'], ['Rows removed', outcome.impact.removed_rows, 'Identical after transformation'], ['Missing after', outcome.after.missing_cells, `Was ${number(outcome.before.missing_cells)}`]]) { const entry = el('div', 'impact-metric'); entry.append(el('small', '', label), el('strong', '', number(value)), el('small', '', info)); box.append(entry); }
    byId('impact-empty').hidden = true; byId('impact-results').hidden = false;
    const warnings = byId('impact-warning'); warnings.hidden = outcome.warnings.length === 0; warnings.textContent = outcome.warnings.join(' ');
    notice('Simulation complete. Export is enabled for this exact recipe.', true);
  } catch (e) { notice(e.message); } finally { busy(false); }
}
function downloadBlob(blob, name) { const link = document.createElement('a'); const url = URL.createObjectURL(blob); link.href = url; link.download = name; document.body.append(link); link.click(); link.remove(); setTimeout(() => URL.revokeObjectURL(url), 120_000); }
async function downloadCSV() {
  if (!state.id || !state.simulatedRecipe) return;
  const query = new URLSearchParams(state.simulatedRecipe);
  // Direct navigation streams bytes to the browser; no full CSV is held in JS memory.
  const link = document.createElement('a'); link.href = `/api/datasets/${state.id}/export.csv?${query}`; link.download = 'datamendry-cleaned.csv'; document.body.append(link); link.click(); link.remove();
}
function downloadAudit() {
  if (!state.id || !state.impact) return;
  const audit = { tool: 'DataMendry', version: '0.2.0', generated_at: new Date().toISOString(), source_sha256: state.profile.source_sha256, original_filename: state.profile.filename, simulation: state.impact, important: 'Do not assume transformations are always appropriate for your domain.' };
  downloadBlob(new Blob([JSON.stringify(audit, null, 2)], { type: 'application/json' }), 'datamendry-audit.json');
}
async function runRule() {
  if (!state.id) return;
  const kind = byId('rule-kind').value; const raw = byId('rule-threshold').value;
  if (['minimum', 'maximum'].includes(kind) && (raw.trim() === '' || !Number.isFinite(Number(raw)))) return notice('Enter a valid numeric threshold.');
  busy(true, 'Validating every record…'); clearNotice();
  try {
    const rule = { column: byId('rule-column').value, kind, threshold: ['minimum', 'maximum'].includes(kind) ? Number(raw) : null };
    const result = await api(`/api/datasets/${state.id}/rules`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ rules: [rule] }) });
    const r = result.results[0]; const div = el('div', 'rule-result'); const info = el('div'); info.append(el('strong', '', `${r.column}: ${kind.replace('_', ' ')}`), el('p', 'subtle', `Violating rows: ${number(r.violations)}${r.threshold === null ? '' : ` · Threshold: ${r.threshold}`}`)); const status = el('strong', r.passed ? 'ok' : 'bad', r.passed ? 'PASS ✓' : 'FAIL ✕'); div.append(info, status); byId('rule-results').prepend(div);
    notice('Validation finished. No data was changed.', true);
  } catch (e) { notice(e.message); } finally { busy(false); }
}
async function removeDataset() {
  if (!state.id || !window.confirm('Delete this dataset from the server? This cannot be undone.')) return;
  try { await api(`/api/datasets/${state.id}`, { method: 'DELETE' }); state.id = null; state.profile = null; state.impact = null; state.simulatedRecipe = null; byId('dataset-results').hidden = true; document.querySelectorAll('.requires-data').forEach(node => node.hidden = true); document.querySelectorAll('[data-empty]').forEach(node => node.hidden = false); showPage('overview'); notice('Dataset deleted from the server.', true); } catch (e) { notice(e.message); }
}
function bind() {
  document.querySelectorAll('.nav-link').forEach(b => b.addEventListener('click', () => showPage(b.dataset.page)));
  byId('file-input').addEventListener('change', e => uploadFile(e.target.files?.[0]));
  byId('demo-button').addEventListener('click', async () => { try { const r = await api('/api/demo.csv'); const blob = await r.blob(); await uploadFile(new File([blob], 'sample-sales.csv', { type: 'text/csv' })); } catch (e) { notice(e.message); } });
  const zone = byId('upload-zone'); zone.addEventListener('dragover', e => { e.preventDefault(); zone.classList.add('drag'); }); zone.addEventListener('dragleave', () => zone.classList.remove('drag')); zone.addEventListener('drop', e => { e.preventDefault(); zone.classList.remove('drag'); uploadFile(e.dataTransfer.files?.[0]); });
  byId('prev-page').addEventListener('click', () => { state.offset = Math.max(0, state.offset - 25); loadPreview().catch(e => notice(e.message)); });
  byId('next-page').addEventListener('click', () => { state.offset += 25; loadPreview().catch(e => notice(e.message)); });
  byId('remove-button').addEventListener('click', removeDataset);
  ['opt-trim', 'opt-blanks', 'opt-dedupe'].forEach(id => byId(id).addEventListener('change', invalidateSimulation));
  byId('simulate-button').addEventListener('click', runSimulation); byId('export-csv').addEventListener('click', downloadCSV); byId('export-json').addEventListener('click', downloadAudit);
  byId('rule-kind').addEventListener('change', () => { byId('threshold-wrap').hidden = !['minimum', 'maximum'].includes(byId('rule-kind').value); }); byId('run-rule').addEventListener('click', runRule);
}
bind();
