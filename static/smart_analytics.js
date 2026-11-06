'use strict';
/* DataMendry M7: bounded, type-aware private relationships. No external libraries. */
(() => {
  const $ = id => document.getElementById(id);
  const section = $('page-analytics');
  if (!section || !$('analytics-smart-controls')) return;
  const ui = () => window.DataMendryUI;
  const el = (type, cls = '', text) => {
    const node = document.createElement(type);
    if (cls) node.className = cls;
    if (text !== undefined) node.textContent = String(text);
    return node;
  };
  // Stable color-to-category mapping; the legend uses the exact same colors as the bars.
  const CATEGORY_COLORS = ['#50dcc2', '#38bdf8', '#fbbf24', '#c4b5fd', '#fb7185'];
  const categoryColor = index => CATEGORY_COLORS[index % CATEGORY_COLORS.length];
  function colorLegend(labels) {
    const list = el('ul', 'analytics-smart-legend');
    list.setAttribute('aria-label', 'Chart color legend');
    for (const [index, name] of labels.entries()) {
      const item = el('li', 'analytics-smart-legend-item');
      const swatch = el('span', 'analytics-smart-swatch');
      swatch.style.backgroundColor = categoryColor(index);
      swatch.setAttribute('aria-hidden', 'true');
      item.append(swatch, el('span', '', name));
      list.append(item);
    }
    return list;
  }
  function gradientLegend(label) {
    const box = el('div', 'analytics-smart-gradient-legend');
    const swatch = el('span', 'analytics-smart-gradient-swatch');
    swatch.setAttribute('aria-hidden', 'true');
    box.append(swatch, el('span', '', label));
    return box;
  }
  const fmt = v => v === null || v === undefined || !Number.isFinite(Number(v)) ? '—'
    : Number(v).toLocaleString(undefined, {maximumFractionDigits: 3});
  let currentId = '';
  let overview = null;
  let sequence = 0;
  let busy = false;
  const result = $('analytics-smart-result');
  const message = (text, warning = false) => {
    const target = $('analytics-smart-status');
    target.textContent = text;
    target.style.color = warning ? '#ffc2a9' : '';
  };
  const metric = (label, value) => {
    const card = el('div', 'analytics-smart-stat');
    card.append(el('span', '', label), el('strong', '', value));
    return card;
  };
  function metrics(entries) {
    const wrap = el('div', 'analytics-smart-metrics');
    for (const [label, value] of Object.entries(entries || {})) {
      const readable = label.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
      wrap.append(metric(readable, typeof value === 'number' ? fmt(value) : String(value ?? '—')));
    }
    return wrap;
  }
  function notice(text) { return el('p', 'subtle analytics-smart-note', text); }
  function heading(text) { return el('h4', '', text); }
  function barRows(items, title, labelKey = 'label', valueKey = 'count') {
    const container = el('div', 'analytics-smart-bars');
    container.append(heading(title));
    const max = Math.max(1, ...items.map(item => Math.abs(Number(item[valueKey]) || 0)));
    for (const item of items) {
      const row = el('div', 'analytics-smart-bar-row');
      const label = el('span', 'analytics-smart-bar-label', item[labelKey]);
      label.title = String(item[labelKey]);
      const track = el('div', 'analytics-smart-bar-track');
      const fill = el('div', 'analytics-smart-bar-fill');
      fill.style.width = `${100 * Math.abs(Number(item[valueKey]) || 0) / max}%`;
      track.append(fill);
      row.append(label, track, el('strong', '', fmt(item[valueKey])));
      container.append(row);
    }
    return container;
  }
  function matrix(rows, xNames, yNames, title) {
    const wrap = el('div', 'analytics-smart-matrix-wrap');
    wrap.append(heading(title));
    const table = el('table', 'analytics-smart-matrix');
    const header = el('tr');
    header.append(el('th', '', 'Values'));
    xNames.forEach(name => header.append(el('th', '', name)));
    table.append(header);
    const peak = Math.max(1, ...rows.flat());
    rows.forEach((data, i) => {
      const tr = el('tr');
      tr.append(el('th', '', yNames[i]));
      data.forEach(val => {
        const cell = el('td', '', fmt(val));
        if (val > 0) cell.style.background = `rgba(69, 211, 192, ${0.12 + 0.63 * val / peak})`;
        tr.append(cell);
      });
      table.append(tr);
    });
    wrap.append(table, gradientLegend('Darker teal indicates a larger count; empty cells represent zero.'));
    return wrap;
  }
  function qualityCards(payload) {
    const wrap = el('div', 'analytics-smart-quality');
    for (const c of payload.columns || []) {
      const card = el('div', 'analytics-smart-quality-card');
      card.append(heading(c.name), el('p', 'subtle', `${c.kind} · ${c.note}`),
        metrics({'sampled_rows': c.sampled, 'nonblank': c.present, 'missing': c.missing, 'distinct_values': c.unique}));
      wrap.append(card);
    }
    return wrap;
  }
  function render(payload) {
    result.replaceChildren();
    const header = el('div', 'analytics-smart-result-head');
    header.append(heading(`${payload.x} × ${payload.y}`), el('span', 'analytics-smart-kind', `${payload.x_kind} + ${payload.y_kind}`));
    result.append(header);
    const mode = payload.mode;
    if (mode === 'quality') {
      result.append(el('p', 'analytics-smart-guidance', payload.reason || 'A descriptive data-quality comparison is most appropriate.'),
        ...(payload.columns ? [qualityCards(payload)] : []), metrics(payload.metrics));
    } else if (mode === 'category_category') {
      result.append(metrics({...payload.metrics, 'Cramers V': payload.cramers_v === null ? 'Not estimated' : fmt(payload.cramers_v)}),
        matrix(payload.cells, payload.x_labels, payload.y_labels, 'Category cross-tabulation'));
    } else if (mode === 'category_numeric') {
      result.append(metrics(payload.metrics), barRows(payload.groups, `Mean ${payload.numeric_column} by ${payload.category_column}`, 'category', 'mean'));
      const counts = el('p', 'subtle', payload.groups.map(c => `${c.category}: ${fmt(c.count)}`).join(' · '));
      result.append(counts, gradientLegend('Teal bar length represents the mean; the category is labeled on each row.'));
    } else if (mode === 'numeric_numeric') {
      result.append(metrics({...payload.metrics, 'Pearson r': payload.r === null ? 'Undefined' : fmt(payload.r)}),
        matrix(payload.bins, Array.from({length:10},(_,i)=>`X${i+1}`), Array.from({length:10},(_,i)=>`Y${10-i}`), 'Aggregated numeric density (10 × 10)'));
      result.append(notice(`X: ${fmt(payload.x_range[0])} – ${fmt(payload.x_range[1])} · Y: ${fmt(payload.y_range[0])} – ${fmt(payload.y_range[1])}`));
    } else if (mode === 'date_numeric') {
      result.append(metrics(payload.metrics), barRows(payload.months, `Monthly average · ${payload.numeric_column}`, 'month', 'mean'), gradientLegend('Teal bar length represents the monthly mean.'));
    } else if (mode === 'date_category') {
      result.append(metrics(payload.metrics));
      const panel = el('div', 'analytics-smart-monthly');
      panel.append(heading(`Category counts by month · ${payload.category_column}`));
      panel.append(colorLegend(payload.categories));
      const peak = Math.max(1, ...payload.months.map(row=>row.counts.reduce((s,c)=>s+c,0)));
      for (const m of payload.months) {
        const r = el('div', 'analytics-smart-month-row');
        const track = el('div', 'analytics-smart-stacked');
        m.counts.forEach((v,i)=>{
          const segment = el('div', 'analytics-smart-segment');
          segment.style.width = `${v/peak*100}%`;
          segment.style.backgroundColor = categoryColor(i);
          segment.title = `${payload.categories[i]}: ${fmt(v)}`;
          segment.setAttribute('aria-label', `${payload.categories[i]}: ${fmt(v)}`);
          track.append(segment);
        });
        r.append(el('span', '', m.month), track, el('strong','',fmt(m.counts.reduce((s,c)=>s+c,0))));
        panel.append(r);
      }
      result.append(panel);
    } else if (mode === 'date_date') {
      result.append(metrics(payload.metrics));
    } else {
      result.append(notice('No reliable comparison can be computed. Use Explore a column to review values individually.'));
    }
    result.append(notice(payload.note || 'Descriptive analysis.'));
    result.append(notice(`${fmt(payload.sampled_rows)} records inspected${payload.truncated ? ' (first 10,000 rows)' : ''}. Original CSV unchanged; no rows sent to an external service.`));
  }
  function selectOptions(node, columns) {
    node.replaceChildren();
    for (const col of columns) {
      const option = el('option', '', `${col.name} · ${col.kind}`);
      option.value = col.name;
      node.append(option);
    }
  }
  function isActive() {
    return $('analytics-view-mode')?.value === 'compare' && section.classList.contains('active');
  }
  async function fetchOverview() {
    const id = ui()?.current()?.id;
    if (!id || !isActive()) return;
    const current = ++sequence;
    if (overview && currentId === id) return;
    currentId = id;
    overview = null;
    result.replaceChildren();
    $('analytics-smart-controls').hidden = true;
    message('Detecting column types and available comparisons…');
    try {
      const response = await fetch(`/api/datasets/${encodeURIComponent(id)}/smart/overview`, {cache:'no-store'});
      if (!response.ok) throw new Error(`Smart analysis unavailable (HTTP ${response.status})`);
      const info = await response.json();
      if (current !== sequence || ui()?.current()?.id !== id) return;
      overview = info;
      const counts = {};
      info.columns.forEach(c => counts[c.kind] = (counts[c.kind] || 0) + 1);
      $('analytics-smart-types').replaceChildren();
      Object.entries(counts).forEach(([kind,count]) => $('analytics-smart-types').append(el('span', 'analytics-smart-chip', `${fmt(count)} ${kind}`)));
      message(`${fmt(info.columns.length)} columns classified from ${fmt(info.sampled_rows)} sampled rows. Choose any two columns below.`);
      if (info.columns.length < 2) {
        result.append(notice('This CSV contains only one column. Use Explore a column for its distribution and quality analysis.'));
        return;
      }
      selectOptions($('analytics-smart-x'), info.columns);
      selectOptions($('analytics-smart-y'), info.columns);
      $('analytics-smart-controls').hidden = false;
      $('analytics-smart-x').value = info.suggested[0];
      $('analytics-smart-y').value = info.suggested[1];
      await compare();
    } catch(error) {
      if (current === sequence) message(error.message || 'Unable to profile columns.', true);
    }
  }
  async function compare() {
    const id = ui()?.current()?.id;
    const x = $('analytics-smart-x').value;
    const y = $('analytics-smart-y').value;
    if (!id || !isActive()) return;
    if (!x || !y || x === y) { message('Choose two different columns.', true); return; }
    const current = ++sequence;
    busy = true;
    const button = $('analytics-smart-analyze');
    button.disabled = true;
    message(`Comparing ${x} and ${y}…`);
    try {
      const response = await fetch(`/api/datasets/${encodeURIComponent(id)}/smart/pair?x=${encodeURIComponent(x)}&y=${encodeURIComponent(y)}`, {cache:'no-store'});
      if (!response.ok) {
        let text = `Comparison unavailable (${response.status})`;
        try {const body = await response.json(); if (typeof body.detail === 'string') text = body.detail;} catch {}
        throw new Error(text);
      }
      const payload = await response.json();
      if (current !== sequence || ui()?.current()?.id !== id || !isActive()) return;
      render(payload);
      message(`${fmt(payload.sampled_rows)} rows inspected · ${payload.x_kind} × ${payload.y_kind}.`);
    } catch(error) {
      if (current === sequence) message(error.message || 'Unable to compare this pair.', true);
    } finally {
      if (current === sequence) { busy = false; button.disabled = false; }
    }
  }
  function reset() {
    sequence++;
    overview = null;
    currentId = '';
    busy = false;
    $('analytics-smart-analyze').disabled = false;
    $('analytics-smart-controls').hidden = true;
    $('analytics-smart-types').replaceChildren();
    result.replaceChildren();
    message('Open Compare & correlations to explore your dataset.');
  }
  $('analytics-smart-analyze').addEventListener('click', compare);
  $('analytics-view-mode').addEventListener('change', () => {if (isActive()) void fetchOverview();});
  window.addEventListener('datamendry:dataset', () => {reset(); if (isActive()) void fetchOverview();});
  window.addEventListener('datamendry:page', event => {if (event.detail?.page === 'analytics' && isActive()) void fetchOverview();});
})();
