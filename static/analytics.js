'use strict';
/* DataMendry Analytics: private, read-only visualizations of an existing dataset. */
(() => {
  const $ = id => document.getElementById(id);
  const section = $('page-analytics');
  if (!section) return;
  const ui = () => window.DataMendryUI;
  let activeDataset = '';
  let selectedInsights = null;
  let latestRequest = 0;
  let profileRequest = 0;
  let galleryVersion = 0;
  let galleryColumns = [];
  let galleryLoaded = 0;
  let galleryDatasetId = '';
  let galleryLoading = false;
  let analyticsView = 'single';
  let currentProfile = null;
  const GALLERY_BATCH = 8;
  const GALLERY_CONCURRENCY = 3;
  const number = value => Number(value).toLocaleString();
  const pretty = value => value === null || value === undefined || !Number.isFinite(Number(value))
    ? '—' : Number(value).toLocaleString(undefined, {maximumFractionDigits: 3});
  const elem = (type, cls, content) => {
    const node = document.createElement(type);
    if (cls) node.className = cls;
    if (content !== undefined) node.textContent = String(content);
    return node;
  };
  function emptyState(text) {
    $('analytics-column-chart').replaceChildren(elem('p', 'analytics-empty', text));
  }
  function stat(label, value) {
    const box = elem('div', 'analytics-stat');
    box.append(elem('span', '', label), elem('strong', '', value));
    return box;
  }
  function status(text, warning = false) {
    const target = $('analytics-status');
    target.textContent = text;
    target.style.color = warning ? '#ffc2a9' : '';
  }
  function drawMissingness(profile) {
    const rows = (profile.column_missing || []).slice()
      .sort((a, b) => b.missing - a.missing || a.name.localeCompare(b.name));
    const chart = $('analytics-missing-chart');
    chart.replaceChildren();
    const missingTotal = rows.reduce((sum, row) => sum + Number(row.missing || 0), 0);
    const allComplete = profile.rows > 0 && rows.length > 0 && missingTotal === 0;
    // Completeness bars remain visible even when just 0.04% of a column is missing.
    // Exact missing counts are shown separately; bar lengths are never exaggerated.
    $('analytics-missing-heading').textContent = 'Data completeness across columns';
    $('analytics-missing-caption').textContent = 'Bars = present values · counts = missing';
    if (!rows.length) {
      chart.append(elem('p', 'subtle', 'No column data available.'));
    } else {
      if (allComplete) {
        const banner = elem('div', 'analytics-quality-banner');
        const copy = elem('div');
        copy.append(elem('strong', '', '✓ No missing values found'),
          elem('span', '', `All ${number(profile.column_count)} columns are complete across ${number(profile.rows)} rows. The full bars below show completeness, not missing values.`));
        banner.append(elem('span', 'analytics-quality-icon', '✓'), copy);
        chart.append(banner);
      }
      if (!allComplete && missingTotal > 0) {
        const affected = rows.filter(row => row.missing > 0).length;
        const banner = elem('div', 'analytics-quality-banner analytics-quality-attention');
        const copy = elem('div');
        copy.append(elem('strong', '', `${number(missingTotal)} missing cells across ${number(affected)} columns`),
          elem('span', '', 'The bars show the share of present values. Exact missing counts appear beside each column, even when the missing percentage is tiny.'));
        banner.append(elem('span', 'analytics-quality-icon', '!'), copy);
        chart.append(banner);
      }
      for (const row of rows) {
        const wrap = elem('div', 'analytics-missing-row');
        if (row.missing > 0) wrap.classList.add('has-missing');
        const label = elem('span', 'analytics-label', row.name);
        const progress = elem('progress');
        progress.max = Math.max(profile.rows, 1);
        progress.value = Math.max(0, profile.rows - row.missing);
        const pct = profile.rows ? row.missing * 100 / profile.rows : 0;
        progress.setAttribute('aria-label', `${row.name}: ${pretty(100 - pct)}% complete; ${number(row.missing)} missing of ${number(profile.rows)} rows`);
        const count = elem('span', 'analytics-count', row.missing
          ? `${number(row.missing)} missing · ${pretty(pct)}%`
          : '100% complete');
        if (row.missing > 0) count.classList.add('analytics-count-missing');
        wrap.append(label, progress, count);
        chart.append(wrap);
      }
    }
    const kpis = $('analytics-overview-metrics');
    kpis.replaceChildren(
      stat('Total rows', number(profile.rows)),
      stat('Columns', number(profile.column_count)),
      stat('Missing cells', number(profile.missing_cells)),
      stat('Exact duplicate rows', number(profile.duplicate_rows))
    );
    renderQualityNextSteps(profile);
  }
  function renderQualityNextSteps(profile) {
    const target = $('analytics-quality-next');
    target.replaceChildren();
    if (!profile.rows) return;
    const header = elem('h4', '', 'Suggested next steps');
    const note = elem('p', 'subtle', 'These are recommendations only; nothing is changed until you review an export.');
    const grid = elem('div', 'analytics-quality-actions');
    const makeAction = (title, body, page, label) => {
      const card = elem('article', 'analytics-quality-action');
      card.append(elem('strong', '', title), elem('p', '', body));
      const button = elem('button', 'button secondary tiny', label);
      button.type = 'button';
      button.addEventListener('click', () => ui()?.navigate?.(page));
      card.append(button);
      grid.append(card);
    };
    const affected = (profile.column_missing || []).filter(row => row.missing > 0).length;
    if (profile.missing_cells > 0) {
      makeAction('Review missing values',
        `${number(profile.missing_cells)} empty cells across ${number(affected)} columns. Inspect exact fields before choosing a repair or filter.`,
        'quality', 'Open Quality explorer →');
    }
    if (profile.duplicate_rows > 0) {
      makeAction('Check duplicate rows',
        `${number(profile.duplicate_rows)} exact duplicate rows detected. Review the removal impact before exporting.`,
        'repair', 'Open Repair studio →');
    }
    if (profile.missing_cells === 0 && profile.duplicate_rows === 0) {
      makeAction('Basic completeness checks passed',
        'No blank cells or exact duplicate rows found. Other issues may still exist; validate values and ranges using rules.',
        'rules', 'Open Rule checker →');
    } else {
      makeAction('Validate your column rules',
        'Check uniqueness, required values, and numeric limits before deciding which rows to keep.',
        'rules', 'Open Rule checker →');
    }
    target.append(header, note, grid);
  }
  function detailButton(column) {
    const button = elem('button', 'button secondary tiny', 'Details ↗');
    button.type = 'button';
    button.setAttribute('aria-label', `Analyze ${column} in detail`);
    button.addEventListener('click', () => {
      // Gallery details always open the same existing single-column analysis.
      setAnalyticsView('single');
      $('analytics-column').value = column;
      void analyze();
      $('analytics-single-panel').scrollIntoView({block: 'start', behavior: 'smooth'});
    });
    return button;
  }
  function miniChart(target, result) {
    target.replaceChildren();
    if (result.mode === 'empty') {
      target.append(elem('p', 'analytics-empty', 'No nonblank values to chart.'));
      return;
    }
    const missing = result.missing ? ` · ${number(result.missing)} missing` : '';
    if (result.mode === 'numeric') {
      const s = result.stats;
      target.append(elem('p', 'analytics-gallery-meta',
        `Numeric · Mean ${pretty(s.mean)} · Min ${pretty(s.min)} · Max ${pretty(s.max)}${missing}`));
      const chart = elem('div', 'analytics-mini-hist');
      chart.setAttribute('role', 'img');
      chart.setAttribute('aria-label', `Histogram for ${result.column}`);
      const peak = Math.max(1, ...result.bars.map(x => x.count));
      for (const bar of result.bars) {
        const line = elem('div', 'analytics-mini-hist-bar');
        line.style.height = `${Math.max(2, Math.round(100 * bar.count / peak))}%`;
        line.title = `${bar.label}: ${number(bar.count)} rows`;
        chart.append(line);
      }
      target.append(chart);
      target.append(elem('p', 'analytics-gallery-meta',
        `${number(result.numeric_count)} numeric values · ${number(s.possible_outliers_3sigma)} potential outliers (3σ)`));
    } else {
      target.append(elem('p', 'analytics-gallery-meta',
        `Categorical · ${number(result.present)} present values${missing} · top values`));
      const peak = Math.max(1, ...result.bars.map(x => x.count));
      for (const bar of result.bars.slice(0, 5)) {
        const row = elem('div', 'analytics-mini-category');
        const label = elem('span', 'analytics-mini-category-label', bar.label);
        label.title = bar.label;
        const track = elem('div', 'analytics-mini-category-track');
        const fill = elem('div', 'analytics-mini-category-fill');
        fill.style.width = `${100 * bar.count / peak}%`;
        track.append(fill);
        row.append(label, track, elem('span', 'analytics-mini-category-count', number(bar.count)));
        target.append(row);
      }
    }
  }
  function galleryMessage(message, warning = false) {
    const node = $('analytics-gallery-status');
    node.textContent = message;
    node.style.color = warning ? '#ffc2a9' : '';
  }
  function resetGallery() {
    galleryVersion += 1; // Make old asynchronous results safe to ignore.
    galleryLoaded = 0;
    galleryColumns = [];
    galleryDatasetId = '';
    galleryLoading = false;
    $('analytics-all-charts').replaceChildren();
    $('analytics-gallery-more').hidden = true;
    $('analytics-gallery-more').disabled = false;
    galleryMessage('Open a CSV to explore its columns.');
  }
  async function loadGalleryBatch() {
    if (galleryLoading || analyticsView !== 'all' || !galleryDatasetId || !galleryColumns.length) return;
    galleryLoading = true;
    const id = galleryDatasetId;
    const version = galleryVersion;
    const start = galleryLoaded;
    const names = galleryColumns.slice(start, start + GALLERY_BATCH);
    if (!names.length) { galleryLoading = false; return; }
    const button = $('analytics-gallery-more');
    button.disabled = true;
    button.hidden = true;
    const tiles = names.map(column => {
      const card = elem('article', 'analytics-gallery-card');
      const head = elem('div', 'analytics-gallery-header');
      head.append(elem('strong', '', column), detailButton(column));
      const body = elem('div', 'analytics-gallery-body', 'Loading chart…');
      card.append(head, body);
      $('analytics-all-charts').append(card);
      return {column, body};
    });
    galleryMessage(`Loading charts ${start + 1}–${start + names.length} of ${galleryColumns.length}…`);
    let cursor = 0;
    const workers = Array.from({length: Math.min(GALLERY_CONCURRENCY, tiles.length)}, async () => {
      while (cursor < tiles.length) {
        const tile = tiles[cursor++];
        try {
          const response = await fetch(`/api/datasets/${encodeURIComponent(id)}/analytics?column=${encodeURIComponent(tile.column)}`, {cache:'no-store'});
          if (!response.ok) throw new Error(`HTTP ${response.status}`);
          const result = await response.json();
          if (version !== galleryVersion || ui()?.current()?.id !== id) return;
          miniChart(tile.body, result);
        } catch (error) {
          if (version !== galleryVersion) return;
          tile.body.replaceChildren(elem('p', 'analytics-empty', 'Chart unavailable; try opening column details.'));
        }
      }
    });
    try {
      await Promise.all(workers);
      if (version !== galleryVersion || ui()?.current()?.id !== id) return;
      galleryLoaded += names.length;
      galleryMessage(`Showing ${galleryLoaded} of ${galleryColumns.length} columns. Select Details on any chart for full statistics.`);
      button.hidden = galleryLoaded >= galleryColumns.length;
      button.disabled = false;
    } finally {
      if (version === galleryVersion) galleryLoading = false;
    }
  }
  function startGallery(id, profile) {
    resetGallery();
    galleryDatasetId = id;
    galleryColumns = (profile.columns || []).slice();
    if (!galleryColumns.length) return galleryMessage('No columns available to chart.');
    galleryMessage('Choose “All columns — chart overview” to load charts together.');
    // Lazy-load: on the individual view, no extra per-column requests are made.
    if (analyticsView === 'all') void loadGalleryBatch();
  }
  function setAnalyticsView(mode) {
    analyticsView = mode === 'all' ? 'all' : mode === 'compare' ? 'compare' : 'single';
    $('analytics-view-mode').value = analyticsView;
    $('analytics-single-panel').hidden = analyticsView !== 'single';
    $('analytics-gallery-panel').hidden = analyticsView !== 'all';
    $('analytics-relations-panel').hidden = analyticsView !== 'compare';
    if (analyticsView === 'compare' && activeDataset) void loadRelationships();
    // Existing cards are retained when switching away and back.
    if (analyticsView === 'all' && galleryDatasetId && galleryLoaded === 0 && !galleryLoading)
      void loadGalleryBatch();
  }
  function drawInsights(result) {
    selectedInsights = result;
    const target = $('analytics-column-metrics');
    const missingPct = result.rows ? 100 * result.missing / result.rows : 0;
    target.replaceChildren(
      stat('Present values', number(result.present)),
      stat('Missing values', `${number(result.missing)} (${pretty(missingPct)}%)`),
      stat('Column type', result.mode === 'numeric' ? 'Mostly numeric' : result.mode === 'categorical' ? 'Categorical / mixed' : 'Empty'),
      stat('Valid numbers', number(result.numeric_count))
    );
    const chart = $('analytics-column-chart');
    chart.replaceChildren();
    if (result.mode === 'empty') {
      emptyState('No nonblank values to visualize in this column.');
    } else if (result.mode === 'numeric') {
      const s = result.stats;
      target.append(
        stat('Minimum', pretty(s.min)), stat('Maximum', pretty(s.max)),
        stat('Mean', pretty(s.mean)), stat('Std. deviation', pretty(s.std_dev)),
        stat('Potential 3σ outliers', number(s.possible_outliers_3sigma)),
        stat('Unparseable values', number(result.invalid_numeric))
      );
      chart.append(elem('h4', '', `Value distribution — ${result.column}`));
      const plot = elem('div', 'analytics-histogram');
      const peak = Math.max(1, ...result.bars.map(bar => bar.count));
      for (const bar of result.bars) {
        const item = elem('div', 'analytics-histogram-bar');
        const count = elem('span', 'analytics-histogram-count', number(bar.count));
        const fill = elem('div', 'analytics-histogram-fill');
        fill.style.height = `${Math.max(3, Math.round(130 * bar.count / peak))}px`;
        const label = elem('span', 'analytics-histogram-label', bar.label);
        item.setAttribute('title', `${bar.label}: ${number(bar.count)} records`);
        item.setAttribute('aria-label', `${bar.label}: ${number(bar.count)} records`);
        item.append(count, fill, label);
        plot.append(item);
      }
      chart.append(plot);
    } else {
      chart.append(elem('h4', '', `Most frequent values — ${result.column}`));
      const peak = Math.max(1, ...result.bars.map(bar => bar.count));
      for (const bar of result.bars) {
        const row = elem('div', 'analytics-category-row');
        const label = elem('span', 'analytics-category-label', bar.label);
        const track = elem('div', 'analytics-bar-track');
        const fill = elem('div', 'analytics-bar-fill');
        fill.style.width = `${100 * bar.count / peak}%`;
        track.append(fill);
        const count = elem('span', 'analytics-category-count', number(bar.count));
        row.append(label, track, count);
        chart.append(row);
      }
    }
    $('analytics-note').textContent = result.note || '';
    $('analytics-report').disabled = false;
    status(`Analysis ready: ${result.column} · ${number(result.rows)} rows inspected. Your original dataset is unchanged.`);
  }
  async function analyze() {
    const id = ui()?.current()?.id;
    const column = $('analytics-column').value;
    if (!id || !column) return;
    const requestId = ++latestRequest;
    selectedInsights = null;
    $('analytics-report').disabled = true;
    $('analytics-refresh').disabled = true;
    status(`Analyzing ${column} privately…`);
    try {
      const response = await fetch(`/api/datasets/${encodeURIComponent(id)}/analytics?column=${encodeURIComponent(column)}`,
        {cache:'no-store'});
      if (!response.ok) {
        let detail = `Insights unavailable (${response.status})`;
        try { const body = await response.json(); if (typeof body.detail === 'string') detail = body.detail; } catch {}
        throw new Error(detail);
      }
      const result = await response.json();
      if (requestId === latestRequest && ui()?.current()?.id === id && $('analytics-column').value === column)
        drawInsights(result);
    } catch(error) {
      if (requestId !== latestRequest) return;
      emptyState('Analysis unavailable for this column.');
      status(error.message || 'Analysis unavailable.', true);
    } finally {
      if (requestId === latestRequest) $('analytics-refresh').disabled = false;
    }
  }
  async function prepareDataset() {
    const id = ui()?.current()?.id;
    if (!id) return;
    // Check the active id BEFORE incrementing the request token. Repeated page
    // notifications must not invalidate an in-flight profile response.
    if (activeDataset === id) return;
    const thisProfile = ++profileRequest;
    activeDataset = id;
    latestRequest += 1;
    selectedInsights = null;
    $('analytics-report').disabled = true;
    $('analytics-column-metrics').replaceChildren();
    $('analytics-note').textContent = '';
    status('Loading dataset profile…');
    try {
      const response = await fetch(`/api/datasets/${encodeURIComponent(id)}/profile`, {cache:'no-store'});
      if (!response.ok) throw new Error('Dataset expired or unavailable; reopen a CSV.');
      const profile = await response.json();
      if (thisProfile !== profileRequest || ui()?.current()?.id !== id) return;
      currentProfile = profile;
      $('analytics-visual-report').disabled = false;
      drawMissingness(profile);
      startGallery(id, profile);
      const options = $('analytics-column');
      options.replaceChildren();
      for (const name of profile.columns) {
        const option = elem('option', '', name); option.value = name; options.append(option);
      }
      // Prefer the first column which is not entirely missing.
      const firstUseful = profile.column_missing?.find(row => row.missing < profile.rows);
      if (firstUseful) options.value = firstUseful.name;
      await analyze();
    } catch(error) {
      if (thisProfile !== profileRequest) return;
      activeDataset = '';
      status(error.message || 'Could not open dataset analytics.', true);
    }
  }
  function reset() {
    setAnalyticsView('single');
    latestRequest += 1;
    profileRequest += 1;
    activeDataset = '';
    selectedInsights = null;
    currentProfile = null;
    relationships = null;
    relationshipRequest += 1;
    pairRequest += 1;
    $('analytics-visual-report').disabled = true;
    $('analytics-correlation-matrix').replaceChildren();
    $('analytics-pair-controls').hidden = true;
    $('analytics-pair-metrics').replaceChildren();
    $('analytics-pair-density').replaceChildren();
    $('analytics-pair-mini-charts').replaceChildren();
    resetGallery();
    $('analytics-missing-heading').textContent = 'Data completeness across columns';
    $('analytics-missing-caption').textContent = 'Bars = present values · counts = missing';
    $('analytics-quality-next').replaceChildren();
    $('analytics-pearson-section').hidden = true;
    $('analytics-pearson-unavailable').hidden = true;
    $('analytics-pearson-unavailable').textContent = '';
    $('analytics-column').replaceChildren();
    $('analytics-overview-metrics').replaceChildren();
    $('analytics-missing-chart').replaceChildren();
    $('analytics-column-metrics').replaceChildren();
    $('analytics-column-chart').replaceChildren();
    $('analytics-note').textContent = '';
    $('analytics-report').disabled = true;
    $('analytics-refresh').disabled = false;
    status('Open a CSV to explore data insights.');
  }
  // Milestone 6: private, bounded correlation and print-ready visual reports.
  let relationships = null;
  let relationshipRequest = 0;
  let pairRequest = 0;
  let reportBusy = false;
  const REPORT_COLUMN_LIMIT = 12;
  function correlationLookup(a, b) {
    if (!relationships) return null;
    const pair = relationships.pairs.find(item => (item.x === a && item.y === b) || (item.x === b && item.y === a));
    return pair || null;
  }
  function relationshipStatus(message, warning = false) {
    const node = $('analytics-correlation-status');
    node.textContent = message;
    node.style.color = warning ? '#ffc2a9' : '';
  }
  function setPairInputs(a, b) {
    $('analytics-pair-x').value = a;
    $('analytics-pair-y').value = b;
  }
  function renderCorrelationMatrix(result) {
    const panel = $('analytics-correlation-matrix');
    panel.replaceChildren();
    const names = result.columns;
    const pairControls = $('analytics-pair-controls');
    const pearsonSection = $('analytics-pearson-section');
    const fallback = $('analytics-pearson-unavailable');
    const supported = names.length >= 2;
    pairControls.hidden = !supported;
    pearsonSection.hidden = !supported;
    fallback.hidden = supported;
    if (!supported) {
      fallback.textContent = `Pearson matrix hidden: ${names.length} eligible numeric measurement columns detected; two or more are needed. Use Smart comparisons above for this dataset.`;
      return;
    }
    fallback.textContent = '';
    const table = elem('table', 'analytics-matrix');
    const header = elem('tr');
    header.append(elem('th', '', 'Column'));
    names.forEach(name => header.append(elem('th', '', name)));
    table.append(header);
    for (const y of names) {
      const row = elem('tr');
      row.append(elem('th', '', y));
      for (const x of names) {
        const cell = elem('td');
        const pair = correlationLookup(x, y);
        const r = pair?.r;
        const button = elem('button', '', r === null || r === undefined ? '—' : Number(r).toFixed(2));
        button.type = 'button';
        button.disabled = x === y || r === null || r === undefined;
        if (r !== null && r !== undefined) {
          const strength = Math.min(1, Math.abs(r));
          button.style.background = r < 0
            ? `rgba(238,143,110,${0.14 + strength * 0.68})`
            : `rgba(55,202,173,${0.14 + strength * 0.63})`;
        }
        button.title = `${x} vs ${y}: ${r === null || r === undefined ? 'unavailable' : pretty(r)} · ${pair?.paired_rows || 0} paired records`;
        button.setAttribute('aria-label', button.title);
        if (!button.disabled) button.addEventListener('click', () => {
          setPairInputs(x, y);
          void comparePair();
          $('analytics-pair-controls').scrollIntoView({block:'nearest',behavior:'smooth'});
        });
        cell.append(button);
        row.append(cell);
      }
      table.append(row);
    }
    panel.append(table);
    const hint = result.truncated ? ' (sampled first 10,000 rows)' : '';
    relationshipStatus(`${names.length} numeric columns · ${number(result.sampled_rows)} rows inspected${hint}. Select a matrix cell or compare two columns below.`);
    for (const id of ['analytics-pair-x', 'analytics-pair-y']) {
      const select = $(id);
      select.replaceChildren();
      names.forEach(name => { const option = elem('option', '', name); option.value = name; select.append(option); });
    }
    setPairInputs(names[0], names[1]);
    void comparePair();
  }
  async function loadRelationships() {
    const id = ui()?.current()?.id;
    if (!id || analyticsView !== 'compare') return;
    if (relationships) { renderCorrelationMatrix(relationships); return; }
    const version = ++relationshipRequest;
    $('analytics-pearson-section').hidden = true;
    $('analytics-pearson-unavailable').hidden = true;
    relationshipStatus('Calculating numeric correlations privately…');
    try {
      const response = await fetch(`/api/datasets/${encodeURIComponent(id)}/relationships`, {cache:'no-store'});
      if (!response.ok) throw new Error(`Correlation analysis unavailable (${response.status})`);
      const result = await response.json();
      if (version !== relationshipRequest || ui()?.current()?.id !== id) return;
      relationships = result;
      renderCorrelationMatrix(result);
    } catch (error) {
      if (version === relationshipRequest) {
        $('analytics-pearson-section').hidden = true;
        const fallback = $('analytics-pearson-unavailable');
        fallback.hidden = false;
        fallback.textContent = error.message || 'Unable to calculate numeric correlations. Smart comparisons remain available.';
      }
    }
  }
  async function comparePair() {
    const id = ui()?.current()?.id;
    const x = $('analytics-pair-x').value;
    const y = $('analytics-pair-y').value;
    if (!id || !x || !y) return;
    const version = ++pairRequest;
    const statusNode = $('analytics-pair-status');
    $('analytics-pair-metrics').replaceChildren();
    $('analytics-pair-density').replaceChildren();
    $('analytics-pair-mini-charts').replaceChildren();
    if (x === y) { statusNode.textContent = 'Select two different numeric columns.'; return; }
    $('analytics-pair-analyze').disabled = true;
    statusNode.textContent = `Comparing ${x} and ${y}…`;
    try {
      const base = `/api/datasets/${encodeURIComponent(id)}`;
      const calls = [
        `${base}/relationships/pair?x=${encodeURIComponent(x)}&y=${encodeURIComponent(y)}`,
        `${base}/analytics?column=${encodeURIComponent(x)}`,
        `${base}/analytics?column=${encodeURIComponent(y)}`
      ];
      const data = await Promise.all(calls.map(async url => {
        const response = await fetch(url, {cache:'no-store'});
        if (!response.ok) throw new Error(`Comparison unavailable (${response.status})`);
        return response.json();
      }));
      if (version !== pairRequest || ui()?.current()?.id !== id || analyticsView !== 'compare') return;
      const [pair, xData, yData] = data;
      $('analytics-pair-metrics').replaceChildren(
        stat('Pearson r', pair.r === null ? 'Not defined' : pretty(pair.r)),
        stat('Paired numeric records', number(pair.paired_rows)),
        stat('X range', `${pretty(pair.x_min)} – ${pretty(pair.x_max)}`),
        stat('Y range', `${pretty(pair.y_min)} – ${pretty(pair.y_max)}`)
      );
      const density = $('analytics-pair-density');
      density.append(elem('h4', '', `Density comparison · ${x} × ${y}`));
      const grid = elem('div', 'analytics-density-grid');
      grid.setAttribute('role', 'img');
      grid.setAttribute('aria-label', `Ten by ten aggregated density bins for ${x} and ${y}`);
      const peak = Math.max(1, ...pair.bins.flat());
      for (let yi = 0; yi < pair.bins.length; yi++) for (let xi = 0; xi < pair.bins[yi].length; xi++) {
        const count = pair.bins[yi][xi];
        const square = elem('div', 'analytics-density-cell');
        square.style.background = count ? `rgba(67,221,195,${0.16 + 0.84 * count / peak})` : '';
        square.title = `Bin ${xi + 1}, ${10 - yi}: ${number(count)} rows`;
        grid.append(square);
      }
      density.append(grid);
      const caption = elem('div', 'analytics-density-caption');
      caption.append(elem('span', '', `← ${x}: ${pretty(pair.x_min)} to ${pretty(pair.x_max)} →`),
        elem('span', '', `${y}: ${pretty(pair.y_min)} to ${pretty(pair.y_max)} ↑`));
      density.append(caption);
      const charts = $('analytics-pair-mini-charts');
      for (const insight of [xData, yData]) {
        const card = elem('article', 'analytics-pair-mini');
        card.append(elem('strong', '', insight.column));
        const chart = elem('div');
        miniChart(chart, insight);
        card.append(chart);
        charts.append(card);
      }
      statusNode.textContent = `${number(pair.paired_rows)} paired values, among ${number(pair.sampled_rows)} inspected rows${pair.truncated ? ' (first 10,000 rows only)' : ''}. Correlation is not causation.`;
    } catch(error) {
      if (version === pairRequest) statusNode.textContent = error.message || 'Unable to compare these columns.';
    } finally {
      if (version === pairRequest) $('analytics-pair-analyze').disabled = false;
    }
  }
  function reportEsc(value) {
    return String(value ?? '').replace(/[&<>"']/g, character => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;', "'":'&#39;'}[character]));
  }
  function reportBarChart(insight) {
    if (!insight.bars?.length) return '<p>No available values for this chart.</p>';
    const peak = Math.max(1, ...insight.bars.map(row => row.count));
    if (insight.mode === 'numeric') {
      return `<div class="hist">${insight.bars.map(bar => `<div class="hist-item"><span>${reportEsc(number(bar.count))}</span><div class="hist-fill" style="height:${Math.max(2, 110 * bar.count / peak).toFixed(1)}px"></div><small>${reportEsc(bar.label)}</small></div>`).join('')}</div>`;
    }
    return insight.bars.slice(0, 7).map(bar => `<div class="cat-row"><span>${reportEsc(bar.label)}</span><div class="cat-track"><div class="cat-fill" style="width:${(100 * bar.count / peak).toFixed(1)}%"></div></div><b>${reportEsc(number(bar.count))}</b></div>`).join('');
  }
  function makeHtmlReport(profile, insights, relation) {
    const missing = (profile.column_missing || []).slice(0, 30);
    const summary = `<div class="summary"><div><span>Rows</span><strong>${reportEsc(number(profile.rows))}</strong></div><div><span>Columns</span><strong>${reportEsc(number(profile.column_count))}</strong></div><div><span>Missing cells</span><strong>${reportEsc(number(profile.missing_cells))}</strong></div><div><span>Duplicate rows</span><strong>${reportEsc(number(profile.duplicate_rows))}</strong></div></div>`;
    const allComplete = profile.rows > 0 && missing.length > 0 && profile.missing_cells === 0;
    const missingChart = missing.map(row => `<div class="cat-row"><span>${reportEsc(row.name)}</span><div class="cat-track"><div class="cat-fill" style="width:${profile.rows ? (100 * Math.max(0, profile.rows - row.missing) / profile.rows).toFixed(3) : 0}%"></div></div><b>${row.missing ? `${reportEsc(number(row.missing))} missing (${reportEsc(pretty(100 * row.missing / Math.max(profile.rows, 1)))}%)` : '100% complete'}</b></div>`).join('');
    const charts = insights.map(insight => `<section class="card"><h3>${reportEsc(insight.column)}</h3><p>${reportEsc(insight.mode)} · ${reportEsc(number(insight.present))} present · ${reportEsc(number(insight.missing))} missing${insight.stats ? ` · Mean ${reportEsc(pretty(insight.stats.mean))}` : ''}</p>${reportBarChart(insight)}</section>`).join('');
    let correlation = '';
    if (relation.columns.length > 1) {
      const headings = relation.columns;
      correlation = `<div class="scroll"><table><thead><tr><th>Column</th>${headings.map(n => `<th>${reportEsc(n)}</th>`).join('')}</tr></thead><tbody>${headings.map(y => `<tr><th>${reportEsc(y)}</th>${headings.map(x => { const p = relation.pairs.find(p => p.x === x && p.y === y || p.x === y && p.y === x); return `<td>${p?.r === null || p?.r === undefined ? '—' : reportEsc(pretty(p.r))}</td>`; }).join('')}</tr>`).join('')}</tbody></table></div>`;
    }
    const correlationSection = relation.columns.length > 1
      ? `<h2>Pearson correlation overview</h2><p class="muted">From ${reportEsc(number(relation.sampled_rows))} rows${relation.truncated ? ' (first 10,000 only)' : ''}; a maximum of 12 numeric columns are considered. Coefficients are undefined for insufficient variation or overlap.</p>${correlation}`
      : '';
    return `<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>DataMendry · Visual data report</title><style>
:root{font-family:system-ui,Arial,sans-serif;color:#143047;background:#eef6f8}*{box-sizing:border-box}body{max-width:1100px;margin:auto;padding:26px}h1{font-size:32px}h2{margin:32px 0 14px}h3{font-size:18px;margin:0 0 12px}.muted,p{color:#496174;font-size:13px;line-height:1.6}.summary{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}.summary div,.card{border:1px solid #c5dbe3;background:white;padding:17px;border-radius:12px}.summary span{display:block;color:#537185;font-size:12px}.summary strong{font-size:25px;display:block;margin-top:8px;color:#08776a}.columns{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}.card{break-inside:avoid;overflow:hidden}.cat-row{display:grid;grid-template-columns:minmax(95px,1fr) 2fr minmax(55px,100px);gap:12px;align-items:center;font-size:11px;padding:7px 0}.cat-row span{overflow-wrap:anywhere}.cat-track{height:12px;border-radius:7px;background:#e4eff3;overflow:hidden}.cat-fill{height:100%;background:#26aa9e;border-radius:7px}.cat-row b{text-align:right}.hist{display:flex;align-items:end;gap:4px;overflow:hidden;min-height:170px;padding-top:15px}.hist-item{flex:1;min-width:0;display:flex;flex-direction:column;align-items:stretch;text-align:center;gap:4px;font-size:9px}.hist-item span{font-size:10px}.hist-fill{background:linear-gradient(#6bdfce,#159d9d);border-radius:4px 4px 0 0}.hist-item small{font-size:8px;overflow-wrap:anywhere;max-height:26px;overflow:hidden}.scroll{overflow-x:auto}table{border-collapse:collapse;min-width:650px;background:white;width:100%;font-size:11px}th,td{padding:8px;border:1px solid #cddfe5;text-align:center;overflow-wrap:anywhere}th{background:#ecf7f8}.notice{border-left:4px solid #17a997;padding:12px 16px;background:#e0f5f1}.toolbar{text-align:right}.toolbar button{background:#118e87;color:white;border:none;padding:10px 15px;border-radius:7px;cursor:pointer}@media(max-width:800px){body{padding:12px}.columns{grid-template-columns:1fr}.summary{grid-template-columns:repeat(2,1fr)}}@media print{body{padding:0;background:white}.toolbar{display:none}.card{box-shadow:none}.columns{display:block}.columns .card{margin:0 0 12px;page-break-inside:avoid}}
</style></head><body><div class="toolbar"><strong>To save as PDF: open your browser Print menu (Ctrl+P) and choose Save as PDF.</strong></div><h1>✦ DataMendry · Visual insights report</h1><p class="muted">Generated ${reportEsc(new Date().toLocaleString())} · Dataset: ${reportEsc(profile.filename || 'Selected CSV')} · Aggregate statistics only</p><p class="notice">This report is a locally generated copy of summary statistics, not a data-cleaning export. Charts are descriptive; correlations do not imply causation. Although individual CSV rows are excluded, column names and top categorical labels may contain sensitive information—review before sharing.</p>${summary}<h2>Data completeness by column</h2><section class="card"><p>Bars show present values, not missing values. Read the exact missing counts on the right; tiny missing rates may not be visually distinct.</p>${allComplete ? '<p>✓ All columns are complete.</p>' : ''}${missingChart || '<p>No missingness metrics.</p>'}${profile.column_missing?.length > 30 ? '<p>Only the first 30 columns are shown.</p>' : ''}</section><h2>Column distributions (${insights.length} of ${profile.column_count})</h2><div class="columns">${charts}</div>${correlationSection}<p class="muted">Generated locally by DataMendry. No CSV rows were included; the source file was not changed.</p></body></html>`;
  }
  async function downloadVisualReport() {
    const id = ui()?.current()?.id;
    if (!id || !currentProfile || reportBusy) return;
    reportBusy = true;
    const button = $('analytics-visual-report');
    button.disabled = true;
    const original = button.textContent;
    try {
      const names = currentProfile.columns.slice(0, REPORT_COLUMN_LIMIT);
      button.textContent = `Preparing ${names.length} charts…`;
      const results = [];
      let cursor = 0;
      const workers = Array.from({length:Math.min(3, names.length)}, async () => {
        while (cursor < names.length) {
          const i = cursor++;
          const url = `/api/datasets/${encodeURIComponent(id)}/analytics?column=${encodeURIComponent(names[i])}`;
          const response = await fetch(url, {cache:'no-store'});
          if (!response.ok) throw new Error(`Report preparation failed (${response.status})`);
          results[i] = await response.json();
          if (ui()?.current()?.id !== id) throw new Error('The selected dataset changed. Generate a fresh report.');
        }
      });
      await Promise.all(workers);
      let relation = relationships;
      if (!relation) {
        const response = await fetch(`/api/datasets/${encodeURIComponent(id)}/relationships`, {cache:'no-store'});
        if (!response.ok) throw new Error('Could not calculate the correlation overview.');
        relation = await response.json();
      }
      if (ui()?.current()?.id !== id) throw new Error('The selected dataset changed.');
      const html = makeHtmlReport(currentProfile, results, relation);
      const url = URL.createObjectURL(new Blob([html],{type:'text/html;charset=utf-8'}));
      const link = document.createElement('a');
      link.href = url; link.download = 'datamendry-visual-report.html'; link.click();
      window.setTimeout(() => URL.revokeObjectURL(url), 60000);
      status('Visual report downloaded. Open the HTML file to print or save it as PDF.');
    } catch (error) {
      status(error.message || 'Unable to prepare visual report.', true);
    } finally {
      button.textContent = original;
      reportBusy = false;
      button.disabled = !ui()?.current()?.id;
    }
  }
  $('analytics-pair-analyze').addEventListener('click', comparePair);
  $('analytics-visual-report').addEventListener('click', downloadVisualReport);

  $('analytics-view-mode').addEventListener('change', event => setAnalyticsView(event.target.value));
  $('analytics-gallery-more').addEventListener('click', loadGalleryBatch);
  $('analytics-column').addEventListener('change', analyze);
  $('analytics-refresh').addEventListener('click', analyze);
  $('analytics-report').addEventListener('click', () => {
    if (!selectedInsights) return;
    // Export aggregates and statistics only; not underlying rows.
    const report = {format:'DataMendry column insights v1',generated_at:new Date().toISOString(),
      column: selectedInsights.column, insight: selectedInsights};
    const blob = new Blob([JSON.stringify(report, null, 2)], {type:'application/json'});
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a'); a.href = url;
    a.download = 'datamendry-insights.json'; a.click();
    window.setTimeout(() => URL.revokeObjectURL(url), 60000);
  });
  window.addEventListener('datamendry:dataset', () => {
    reset();
    if (section.classList.contains('active')) prepareDataset();
  });
  window.addEventListener('datamendry:page', event => {
    if (event.detail?.page === 'analytics') prepareDataset();
  });
})();
