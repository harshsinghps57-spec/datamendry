'use strict';
(() => {
  const $ = id => document.getElementById(id);
  const account = () => window.DataMendryAccount;
  const ui = () => window.DataMendryUI;
  const gate = $('welcome-gate');
  const dialog = $('auth-dialog');
  let guest = false, signedIn = false, signedEmail = '';
  let lastFilter = null;
  const showAuthMessage = (message, error = false) => {
    $('auth-feedback').textContent = message;
    $('auth-feedback').style.color = error ? '#ffb4a7' : '#78efcb';
  };
  // A confirmed sign-in must never leave the welcome overlay on top of the workspace.
  // Preserve the door transition for guest entry and session restore, while allowing
  // successful password/OTP sign-in to complete the transition deterministically.
  let entryTimer = null;
  function enterWorkspace(immediate = false) {
    if (entryTimer !== null) {
      window.clearTimeout(entryTimer);
      entryTimer = null;
    }
    const finish = () => {
      gate.hidden = true;
      gate.classList.remove('entering');
      entryTimer = null;
    };
    if (immediate || gate.hidden || window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
      finish();
      return;
    }
    gate.classList.add('entering');
    entryTimer = window.setTimeout(finish, 770);
  }
  let authFlow = 'login';
  function openAuth(flow = 'login') {
    // Public beta: keep existing email login, but avoid new email signups/recovery without SMTP.
    authFlow = 'login';
    $('auth-method').value = 'google';
    setMethod();
    if (!account()?.isAvailable()) {
      showAuthMessage('Cloud login is not configured on this server. Choose Explore as guest for temporary CSV uploads.', true);
    }
    if (!dialog.open) dialog.showModal();
  }
  window.DataMendryOpenAuth = openAuth;
  const closeAuth = () => { if (dialog.open) dialog.close(); };
  function setMethod() {
    const method = $('auth-method').value;
    const email = method === 'email';
    for (const type of ['login','signup','recover']) {
      const active = type === authFlow;
      $('auth-tab-' + type).classList.toggle('active', active);
      $('auth-tab-' + type).setAttribute('aria-pressed', String(active));
    }
    $('auth-email-area').hidden = !email;
    $('auth-google-area').hidden = method !== 'google';
    $('auth-otp-area').hidden = true;
    $('auth-recovery-method-row').hidden = authFlow !== 'recover' || !email;
    $('auth-password-row').hidden = authFlow === 'recover' || !email;
    $('auth-password-confirm-row').hidden = authFlow !== 'signup' || !email;
    $('auth-password').autocomplete = authFlow === 'signup' ? 'new-password' : 'current-password';
    $('auth-login').hidden = authFlow !== 'login';
    $('auth-signup').hidden = authFlow !== 'signup';
    $('auth-password-buttons').hidden = authFlow === 'recover' || !email;
    $('auth-send-email').hidden = authFlow !== 'recover' || !email;
    $('auth-recovery-limit').hidden = authFlow !== 'recover';
    $('auth-send-email').textContent = $('auth-email-method').value === 'link' ? 'Send recovery link' : 'Send email code';
    $('auth-flow-hint').textContent = authFlow === 'signup'
      ? 'Create your account with a password, then verify your email if requested.'
      : authFlow === 'recover'
      ? 'Forgot your password? Use a one-time email code or link to sign in. Then set a new password from Account.'
      : 'Existing email account? Use your password. New users should select Google.';
    showAuthMessage('');
  }
  async function attempt(fn, success) {
    try { await fn(); if (success) showAuthMessage(success); }
    catch (e) { showAuthMessage(e.message || 'Could not complete request.', true); }
  }
  $('welcome-signin').addEventListener('click', () => openAuth('login'));
  $('welcome-guest').addEventListener('click', () => { guest = true; enterWorkspace(); });
  $('auth-close').addEventListener('click', closeAuth);
  $('auth-tab-login').addEventListener('click', () => { authFlow = 'login'; setMethod(); });
  $('auth-method').addEventListener('change', setMethod);
  $('auth-email-method').addEventListener('change', setMethod);
  $('auth-login').addEventListener('click', () => attempt(async () => {
    await account().login($('auth-email').value, $('auth-password').value);
    $('auth-password').value = '';
    closeAuth();
    // loadUser() has verified credentials and loaded the user at this point.
    // Do not rely solely on an earlier auth event or the transition timer.
    if (account()?.currentUser()) {
      guest = false;
      enterWorkspace(true);
      ui()?.navigate('overview');
    }
  }));
  $('auth-signup').addEventListener('click', () => attempt(async () => {
    if ($('auth-password').value !== $('auth-password-confirm').value) throw new Error('Passwords do not match.');
    await account().signup($('auth-email').value, $('auth-password').value);
    $('auth-password').value = ''; $('auth-password-confirm').value = '';
  }, 'Account request received. If confirmation is required, check your inbox, then follow the verification link.'));
  $('auth-send-email').addEventListener('click', () => attempt(async () => {
    await account().sendEmailVerification($('auth-email').value.trim());
    $('auth-otp-area').hidden = $('auth-email-method').value !== 'code';
  }, 'Request accepted. Check the newest email for your recovery code or link. Supabase Free has a shared email-sending quota.'));
  $('auth-verify-otp').addEventListener('click', () => attempt(async () => {
    await account().verifyOtp('email', $('auth-email').value.trim(), $('auth-otp').value.trim());
    $('auth-otp').value = ''; closeAuth();
    if (account()?.currentUser()) {
      guest = false;
      enterWorkspace(true);
      ui()?.navigate('overview');
    }
  }));
  $('auth-google').addEventListener('click', () => attempt(() => account().googleLogin()));
  // Password update remains identical to v0.9.3; the top-right account menu opens this dialog.
  $('password-close').addEventListener('click', () => $('password-dialog').close());
  $('password-save').addEventListener('click', async () => {
    const target = $('password-feedback'); target.textContent = '';
    try {
      const pass = $('password-new').value;
      if (pass !== $('password-confirm').value) throw new Error('Passwords do not match.');
      await account().setPassword(pass);
      $('password-new').value = ''; $('password-confirm').value = '';
      target.style.color = '#78efcb'; target.textContent = 'Password saved. Next time use email + password to log in.';
    } catch (e) { target.style.color = '#ffb4a7'; target.textContent = e.message || 'Could not update password.'; }
  });
  const profileMenus = [
    { toggle: 'profile-toggle', popover: 'profile-popover', label: 'profile-label', name: 'profile-top-name',
      login: 'profile-login', logout: 'profile-logout', password: 'profile-password', datasets: 'profile-my-datasets' }
  ];
  function hideProfile() {
    for (const menu of profileMenus) {
      $(menu.popover).hidden = true;
      $(menu.toggle).setAttribute('aria-expanded', 'false');
    }
  }
  for (const menu of profileMenus) {
    $(menu.toggle).addEventListener('click', () => {
      const shouldOpen = $(menu.popover).hidden;
      hideProfile();
      $(menu.popover).hidden = !shouldOpen;
      $(menu.toggle).setAttribute('aria-expanded', String(shouldOpen));
    });
    $(menu.password).addEventListener('click', () => {
      hideProfile();
      $('password-feedback').textContent = '';
      $('password-new').value = ''; $('password-confirm').value = '';
      $('password-dialog').showModal();
    });
    $(menu.login).addEventListener('click', () => { hideProfile(); openAuth('login'); });
    $(menu.logout).addEventListener('click', () => attempt(async () => {
      await account().logout(); guest = false; hideProfile();
      gate.hidden = false;
    }));
    $(menu.datasets).addEventListener('click', () => {
      hideProfile(); ui()?.navigate('overview');
      if (!signedIn) openAuth('login');
      else $('account-panel').scrollIntoView({behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth', block: 'center'});
    });
  }
  // Close the top-right account menu on outside click or Escape.
  document.addEventListener('click', event => {
    if (!event.target.closest('.profile-widget')) hideProfile();
  });
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape') hideProfile();
  });
  // Workspace breadcrumb: use either the home action or the section picker.
  const crumbMenu = $('crumb-menu');
  const crumbButton = $('crumb-page');
  const hideCrumbMenu = () => { crumbMenu.hidden = true; crumbButton.setAttribute('aria-expanded', 'false'); };
  $('crumb-workspace').addEventListener('click', () => { hideCrumbMenu(); ui()?.navigate('overview'); });
  crumbButton.addEventListener('click', () => {
    const shouldOpen = crumbMenu.hidden;
    crumbMenu.hidden = !shouldOpen;
    crumbButton.setAttribute('aria-expanded', String(shouldOpen));
  });
  document.querySelectorAll('[data-crumb-page]').forEach(button => {
    button.addEventListener('click', () => { hideCrumbMenu(); ui()?.navigate(button.dataset.crumbPage); });
  });
  document.addEventListener('click', event => { if (!event.target.closest('.crumb')) hideCrumbMenu(); });
  document.addEventListener('keydown', event => { if (event.key === 'Escape') hideCrumbMenu(); });
  function onAuth(info) {
    signedIn = Boolean(info.signedIn);
    signedEmail = info.email || '';
    for (const menu of profileMenus) {
      $(menu.label).textContent = signedIn ? `${signedEmail} · ${info.provider || 'email'} account` : 'Browsing as guest';
      $(menu.name).textContent = signedIn ? signedEmail.split('@')[0] : 'Account';
      $(menu.login).hidden = signedIn;
      $(menu.password).hidden = !signedIn;
      $(menu.logout).hidden = !signedIn;
    }
    if (signedIn) {
      closeAuth();
      if (!gate.hidden) enterWorkspace();
      try {
        if (!sessionStorage.getItem('datamendry.guide.seen.v07')) {
          sessionStorage.setItem('datamendry.guide.seen.v07', '1');
          window.setTimeout(() => ui()?.navigate('guide'), 850);
        }
      } catch {}
    } else if (!guest) {
      gate.hidden = false;
    }
  }
  window.addEventListener('datamendry:auth', e => onAuth(e.detail));
  // If credentials are unavailable, the user can always reach the existing guest upload feature.
  $('guide-account').addEventListener('click', () => { if (signedIn) { $('profile-toggle').click(); } else openAuth('login'); });
  $('guide-assistant').addEventListener('click', () => { toggleBot(true); });
  document.querySelectorAll('[data-guide-page]').forEach(button => button.addEventListener('click', () => ui()?.navigate(button.dataset.guidePage)));

  function filtersCurrent() {
    const ctx = ui()?.current();
    return Boolean(ctx?.id && Array.isArray(ctx?.columns));
  }
  function updateFilters() {
    const ctx = ui()?.current();
    $('filter-column').replaceChildren(); $('filter-columns').replaceChildren();
    if (!ctx?.columns) return;
    for (const name of ctx.columns) {
      const option = document.createElement('option'); option.value = name; option.textContent = name; $('filter-column').append(option);
      const label = document.createElement('label'); const checkbox = document.createElement('input');
      checkbox.type = 'checkbox'; checkbox.checked = true; checkbox.value = name; checkbox.className = 'filter-include';
      const text = document.createElement('span'); text.textContent = name;
      label.append(checkbox,text); $('filter-columns').append(label);
    }
    invalidateFilter();
  }
  function invalidateFilter() { lastFilter = null; $('filter-download').disabled = true; $('filter-summary').textContent = 'Preview your choices to enable export.'; $('filter-table').replaceChildren(); }
  $('filter-kind').addEventListener('change', () => {
    $('filter-value').disabled = ['all','empty','not_empty'].includes($('filter-kind').value);
    invalidateFilter();
  });
  ['filter-column','filter-value'].forEach(id => $(id).addEventListener('input', invalidateFilter));
  $('filter-columns').addEventListener('change', invalidateFilter);
  const filterSpec = () => ({
    filter_column: $('filter-column').value || null,
    kind: $('filter-kind').value,
    value: $('filter-value').value,
    included_columns: Array.from(document.querySelectorAll('.filter-include:checked'), x => x.value)
  });
  function showFilterPreview(result) {
    const table = document.createElement('table'); const header = document.createElement('tr');
    for (const col of result.columns) { const th = document.createElement('th'); th.textContent = col; header.append(th); }
    const thead = document.createElement('thead'); thead.append(header); table.append(thead);
    const body = document.createElement('tbody');
    for (const row of result.rows) {
      const tr = document.createElement('tr');
      for (const value of row) { const td = document.createElement('td'); td.textContent = value; tr.append(td); }
      body.append(tr);
    }
    table.append(body); $('filter-table').replaceChildren(table);
    $('filter-summary').textContent = `${result.matching_rows.toLocaleString()} matching rows · ${result.columns.length} kept columns. Showing the first 25 rows.`;
  }
  $('filter-preview').addEventListener('click', () => attempt(async () => {
    if (!filtersCurrent()) throw new Error('Upload a dataset first.');
    const spec = filterSpec(); if (!spec.included_columns.length) throw new Error('Keep at least one output column.');
    const ctx = ui().current();
    const response = await fetch(`/api/datasets/${ctx.id}/filters/preview`, {
      method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(spec)
    });
    if (!response.ok) throw new Error('Filter preview could not be completed.');
    showFilterPreview(await response.json()); lastFilter = spec; $('filter-download').disabled = false;
  }));
  $('filter-download').addEventListener('click', () => attempt(async () => {
    const ctx = ui()?.current(); if (!ctx?.id || !lastFilter) throw new Error('Preview a filter first.');
    const response = await fetch(`/api/datasets/${ctx.id}/filters/export`, {
      method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(lastFilter)
    });
    if (!response.ok) throw new Error('Export could not be generated.');
    const blob = await response.blob();
    const url = URL.createObjectURL(blob); const link = document.createElement('a');
    link.href = url; link.download = 'datamendry-filtered.csv'; link.click();
    window.setTimeout(() => URL.revokeObjectURL(url), 120000);
    $('filter-summary').textContent += ' · Export generated; saved original was not modified.';
  }));
  window.addEventListener('datamendry:dataset', updateFilters);
  updateFilters();

  const bot = $('assistant-panel');
  const updateAssistantContext = () => {
    const ctx = ui()?.current();
    const count = ctx?.columns?.length || 0;
    $('assistant-dataset').textContent = ctx?.id ? `${count} detected columns · CSV ready` : 'No CSV loaded';
  };
  const toggleBot = open => {
    bot.hidden = !open;
    $('assistant-toggle').setAttribute('aria-expanded', String(open));
    if (open) { updateAssistantContext(); $('assistant-input').focus(); }
  };
  // Wider by default, optional focus mode. No changes to suggestion or export logic.
  const expandButton = $('assistant-expand');
  const exampleButton = $('assistant-examples-toggle');
  const promptRow = $('assistant-prompts');
  const setAssistantExpanded = (expanded) => {
    bot.classList.toggle('is-expanded', expanded);
    expandButton.setAttribute('aria-pressed', String(expanded));
    expandButton.setAttribute('aria-label', expanded ? 'Minimize assistant' : 'Expand assistant');
    expandButton.title = expanded ? 'Minimize assistant workspace' : 'Expand assistant workspace';
    expandButton.querySelector('span').textContent = expanded ? 'Minimize' : 'Expand';
  };
  expandButton.addEventListener('click', () => setAssistantExpanded(!bot.classList.contains('is-expanded')));
  exampleButton.addEventListener('click', () => {
    promptRow.hidden = !promptRow.hidden;
    exampleButton.setAttribute('aria-expanded', String(!promptRow.hidden));
  });
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && bot.classList.contains('is-expanded')) setAssistantExpanded(false);
  });
  $('assistant-toggle').addEventListener('click', () => toggleBot(bot.hidden));
  $('assistant-close').addEventListener('click', () => { setAssistantExpanded(false); toggleBot(false); });
  window.addEventListener('datamendry:dataset', updateAssistantContext);
  updateAssistantContext();
  const botSay = (s, isUser = false) => {
    if (isUser) {
      $('assistant-intro').hidden = true;
      promptRow.hidden = true;
      exampleButton.setAttribute('aria-expanded', 'false');
    }
    const node = document.createElement('p');
    node.className = `assistant-bubble ${isUser ? 'assistant-user' : 'assistant-bot'}`;
    node.textContent = String(s); // Never interpolate untrusted instructions as HTML.
    $('assistant-messages').append(node);
    $('assistant-messages').scrollTop = $('assistant-messages').scrollHeight;
  };
  // Quick prompts use the same validated form submit handler as typed instructions.
  document.querySelectorAll('[data-assistant-prompt]').forEach(button => {
    button.addEventListener('click', () => {
      $('assistant-input').value = button.dataset.assistantPrompt;
      $('assistant-form').requestSubmit();
    });
  });
  let assistantBusy = false;
  const setAssistantBusy = busy => {
    assistantBusy = busy;
    $('assistant-thinking').hidden = !busy;
    $('assistant-send').disabled = busy;
    document.querySelectorAll('[data-assistant-prompt]').forEach(b => b.disabled = busy);
    if (busy) $('assistant-messages').scrollTop = $('assistant-messages').scrollHeight;
  };
  async function requestAiSuggestion(message) {
    if (!account()?.currentUser()) throw new Error('Please sign in before using paid AI suggestions.');
    const ctx = ui()?.current();
    const token = await account().getAccessToken();
    const response = await fetch(`/api/datasets/${ctx.id}/assistant/suggest`, {
      method: 'POST', headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
      body: JSON.stringify({ message, consent_to_column_names: true })
    });
    if (!response.ok) {
      let problem = `AI unavailable (${response.status})`;
      try { const body = await response.json(); if (body.detail) problem = body.detail; } catch {}
      throw new Error(problem);
    }
    return response.json();
  }
  function applyAiSuggestion(proposal) {
    const action = proposal.action, column = proposal.column;
    if (action === 'trim_whitespace' || action === 'normalize_blanks' || action === 'deduplicate') {
      const id = {'trim_whitespace':'opt-trim','normalize_blanks':'opt-blanks','deduplicate':'opt-dedupe'}[action];
      $(id).checked = true; $(id).dispatchEvent(new Event('change')); ui()?.navigate('repair');
      botSay('Opened Repair Studio and selected the suggested option. Calculate repair impact, then review before exporting. Your original was not changed.');
    } else if (action === 'filter' && column) {
      $('filter-column').value = column;
      $('filter-kind').value = proposal.kind || 'contains';
      $('filter-value').value = proposal.value || '';
      $('filter-value').disabled = ['all','empty','not_empty'].includes($('filter-kind').value);
      invalidateFilter(); ui()?.navigate('filter');
      botSay('Filter prepared. Click Preview filtered data to review the matching rows; export remains disabled until preview succeeds.');
    } else if (action === 'exclude_column' && column) {
      const checkbox = Array.from(document.querySelectorAll('.filter-include')).find(x => x.value === column);
      if (checkbox) checkbox.checked = false;
      invalidateFilter(); ui()?.navigate('filter');
      botSay('Column unchecked in Filter & export. Preview the new file before downloading.');
    }
  }
  // Reusable cleaning recipes contain action settings and headers only, NEVER CSV rows.
  const RECIPE_ACTIONS = new Set(['trim_whitespace','normalize_blanks','deduplicate','filter','exclude_column']);
  const RECIPE_FILTERS = new Set(['contains','not_contains','equals','not_equals','empty','not_empty','gt','gte','lt','lte']);
  const recipeHeaders = () => (ui()?.current()?.columns || []).map(String);
  function normalizeRecipe(raw) {
    if (!raw || raw.type !== 'datamendry-cleaning-recipe' || raw.version !== 1 ||
        !Array.isArray(raw.columns) || !Array.isArray(raw.steps)) {
      throw new Error('Not a supported DataMendry cleaning recipe (version 1).');
    }
    const current = recipeHeaders();
    if (!ui()?.current()?.id || current.length === 0) throw new Error('Open a CSV before importing a recipe.');
    if (raw.columns.length !== current.length || raw.columns.some((name,i) => name !== current[i])) {
      throw new Error('This recipe needs a dataset with the same column headers and order. No changes were made.');
    }
    if (raw.steps.length < 2 || raw.steps.length > 5) throw new Error('A cleaning recipe needs 2–5 steps.');
    const kinds = new Set();
    const steps = raw.steps.map(step => {
      if (!step || !RECIPE_ACTIONS.has(step.action) || kinds.has(step.action)) throw new Error('Recipe actions must be supported and unique.');
      kinds.add(step.action);
      const column = step.column ?? '';
      const kind = step.kind ?? 'all';
      const value = step.value ?? '';
      if (typeof column !== 'string' || typeof kind !== 'string' || typeof value !== 'string' || value.length > 500) {
        throw new Error('Invalid recipe parameters.');
      }
      if (step.action === 'filter') {
        if (!current.includes(column) || !RECIPE_FILTERS.has(kind)) throw new Error('Unknown filter column or condition.');
        if (['gt','gte','lt','lte'].includes(kind) && (!Number.isFinite(Number(value)) || !value.trim())) {
          throw new Error('Numeric filters require a valid number.');
        }
      } else if (step.action === 'exclude_column') {
        if (!current.includes(column) || kind !== 'all' || value) throw new Error('Unknown excluded column.');
      } else if (column || value || kind !== 'all') {
        throw new Error('Repair actions cannot include extra parameters.');
      }
      return {action:step.action,column,kind,value};
    });
    if (steps.filter(step=>step.action==='exclude_column').length && current.length < 2) throw new Error('Cannot remove the last CSV column.');
    return steps;
  }
  function saveRecipe(steps) {
    const columns = recipeHeaders();
    if (!ui()?.current()?.id || !columns.length) return botSay('Open a CSV to save a recipe.');
    const recipe = {type:'datamendry-cleaning-recipe',version:1,columns,steps};
    const blob = new Blob([JSON.stringify(recipe,null,2)+'\n'],{type:'application/json'});
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;link.download='datamendry-cleaning-recipe.json';link.click();
    window.setTimeout(() => URL.revokeObjectURL(url),5000);
  }
  $('assistant-recipe-import').addEventListener('click',()=> $('assistant-recipe-file').click());
  $('assistant-recipe-file').addEventListener('change',async event=>{
    const file = event.target.files?.[0];event.target.value='';
    if (!file) return;
    try {
      if (file.size > 32768) throw new Error('Recipe exceeds the 32 KB safety limit.');
      const raw = JSON.parse(await file.text());
      const steps = normalizeRecipe(raw);
      offerWorkflowProposal({action:'workflow',steps,message:'Imported cleaning recipe. Review all steps, then preview before downloading. No CSV data has changed.'});
    } catch(error) { botSay(error.message || 'Unable to open this cleaning recipe.'); }
  });

  function offerWorkflowProposal(proposal) {
    const active = ui()?.current();
    if (!active?.id) return botSay('Open a CSV before planning a workflow.');
    const datasetId = active.id;
    const steps = proposal.steps.map(step => ({action:step.action, column:step.column || '',
      kind:step.kind || 'all', value:step.value || ''}));
    const card = document.createElement('section');
    card.className = 'assistant-proposal assistant-workflow';
    const heading = document.createElement('strong');
    heading.textContent = `✦ Combined workflow · ${steps.length} reviewable steps`;
    const summary = document.createElement('p');
    summary.textContent = proposal.message;
    const list = document.createElement('ol');
    list.className = 'assistant-workflow-steps';
    proposal.steps.forEach(step => {
      const item = document.createElement('li');
      const label = {
        trim_whitespace:'Trim surrounding whitespace',
        normalize_blanks:'Normalize blank cells',
        deduplicate:'Remove exact duplicate rows',
        filter:`Filter ${step.column} (${step.kind}${step.value ? ': '+step.value : ''})`,
        exclude_column:`Exclude column ${step.column}`
      }[step.action] || 'Unknown action';
      item.textContent = label;
      list.append(item);
    });
    const actions = document.createElement('div');
    actions.className = 'assistant-proposal-actions';
    const previewBtn = document.createElement('button');
    previewBtn.type = 'button'; previewBtn.className = 'assistant-review';
    previewBtn.textContent = 'Preview combined result';
    const downloadBtn = document.createElement('button');
    downloadBtn.type = 'button'; downloadBtn.className = 'assistant-review';
    downloadBtn.textContent = 'Download combined CSV ↓'; downloadBtn.disabled = true;
    const saveBtn = document.createElement('button');
    saveBtn.type = 'button'; saveBtn.className = 'assistant-review';
    saveBtn.textContent = 'Save recipe ↓';
    saveBtn.addEventListener('click', () => {
      if (ui()?.current()?.id !== datasetId) return botSay('Load this dataset again to save its cleaning recipe.');
      saveRecipe(steps);
    });
    const dismiss = document.createElement('button');
    dismiss.type = 'button'; dismiss.className = 'assistant-dismiss';
    dismiss.textContent = 'Dismiss';
    const info = document.createElement('div');
    info.className = 'assistant-workflow-result';
    info.setAttribute('aria-live', 'polite');
    const message = document.createElement('p');
    message.textContent = 'Review all steps before preview. Only the downloaded copy will include changes.';
    info.append(message);
    actions.append(previewBtn,downloadBtn,saveBtn,dismiss);
    card.append(heading,summary,list,actions,info);
    $('assistant-messages').append(card);
    $('assistant-messages').scrollTop = $('assistant-messages').scrollHeight;
    let previewToken = '';
    const stillCurrent = () => ui()?.current()?.id === datasetId;
    const busy = value => { previewBtn.disabled = value; downloadBtn.disabled = value || !previewToken; };
    previewBtn.addEventListener('click', async () => {
      previewToken = ''; busy(true);
      message.textContent = 'Calculating combined preview…';
      info.replaceChildren(message);
      try {
        if (!stillCurrent()) throw new Error('Your dataset changed. Request a new workflow on the current CSV.');
        const response = await fetch(`/api/datasets/${datasetId}/workflows/preview`, {
          method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({steps})
        });
        if (!response.ok) throw new Error(`Preview failed (${response.status}). Check the selected steps.`);
        const result = await response.json();
        previewToken = result.preview_token;
        message.textContent = `${result.matching_rows.toLocaleString()} rows in the result · ${result.removed_duplicates} duplicates removed · ${result.filtered_out_rows} rows filtered out. Preview shows up to 5 rows; the original remains unchanged.`;
        info.replaceChildren(message);
        if (result.warnings?.length) {
          const warning = document.createElement('p'); warning.textContent = result.warnings.join(' ');
          warning.className = 'assistant-workflow-warning'; info.append(warning);
        }
        const wrapper = document.createElement('div'); wrapper.className = 'assistant-workflow-table-wrap';
        const table = document.createElement('table');
        const head = document.createElement('thead'); const tr = document.createElement('tr');
        result.columns.forEach(column => { const th = document.createElement('th'); th.textContent=column; tr.append(th); });
        head.append(tr); table.append(head);
        const body = document.createElement('tbody');
        result.rows.slice(0,5).forEach(row => {
          const rowEl = document.createElement('tr');
          row.forEach(cell => { const td=document.createElement('td');td.textContent=String(cell ?? '');rowEl.append(td); });
          body.append(rowEl);
        });
        table.append(body); wrapper.append(table); info.append(wrapper);
        if (!result.rows.length) {
          const empty = document.createElement('p');empty.textContent='No rows match this workflow. Review your conditions before downloading.';
          info.append(empty);
        }
      } catch(error) { message.textContent=error.message; }
      finally { busy(false); $('assistant-messages').scrollTop = $('assistant-messages').scrollHeight; }
    });
    downloadBtn.addEventListener('click', async () => {
      if (!previewToken) return;
      busy(true);
      try {
        if (!stillCurrent()) throw new Error('Your dataset changed. Preview a new workflow first.');
        const response = await fetch(`/api/datasets/${datasetId}/workflows/export`, {
          method:'POST',headers:{'Content-Type':'application/json'},
          body:JSON.stringify({steps, preview_token: previewToken})
        });
        if (!response.ok) throw new Error(`Download failed (${response.status}). Preview this workflow again.`);
        const blob = await response.blob();
        const url = URL.createObjectURL(blob);
        const link = document.createElement('a');link.href=url;link.download='datamendry-workflow.csv';link.click();
        window.setTimeout(() => URL.revokeObjectURL(url),120000);
        message.textContent='Combined CSV downloaded. The original dataset remains unchanged.';
      } catch(error) { message.textContent=error.message; }
      finally { busy(false); }
    });
    dismiss.addEventListener('click',() => card.remove());
  }

  function offerProposal(proposal) {
    if (proposal?.action === 'workflow') return offerWorkflowProposal(proposal);
    if (!proposal || proposal.action === 'none') {
      botSay(proposal?.message || 'I could not match that instruction to a supported operation.');
      return;
    }
    const box = document.createElement('div');
    box.className = 'assistant-proposal';
    const title = document.createElement('strong'); title.textContent = '✦ Suggested action · Review required';
    const detail = document.createElement('p'); detail.textContent = proposal.message || 'Review the suggested change in the workspace.';
    const bar = document.createElement('div'); bar.className = 'assistant-proposal-actions';
    const review = document.createElement('button'); review.type = 'button'; review.className = 'assistant-review';
    review.textContent = 'Review in workspace ↗';
    review.addEventListener('click', () => { applyAiSuggestion(proposal); box.remove(); });
    const dismiss = document.createElement('button'); dismiss.type = 'button'; dismiss.className = 'assistant-dismiss';
    dismiss.textContent = 'Dismiss'; dismiss.addEventListener('click', () => box.remove());
    bar.append(review, dismiss); box.append(title, detail, bar);
    $('assistant-messages').append(box);
    $('assistant-messages').scrollTop = $('assistant-messages').scrollHeight;
  }
  async function guidedPlan(message) {
    const ctx = ui()?.current();
    const response = await fetch(`/api/datasets/${ctx.id}/assistant/plan`, {
      method:'POST', headers:{'Content-Type':'application/json'},
      body:JSON.stringify({message})
    });
    if (!response.ok) throw new Error('Could not prepare your suggestion. Try again.');
    return response.json();
  }
  $('assistant-form').addEventListener('submit', async e => {
    e.preventDefault();
    if (assistantBusy) return;
    const message = $('assistant-input').value.trim(); if (!message) return;
    $('assistant-input').value = ''; botSay(message, true);
    if (!filtersCurrent()) return botSay('First upload a CSV. Then I can guide you through filters, duplicates and whitespace cleaning.');
    setAssistantBusy(true);
    try {
      // Combined workflows are always planned locally, not sent to an AI provider.
      const localPlan = await guidedPlan(message);
      if (localPlan.action === 'workflow' || /[,;]|\b(?:and|then)\b/i.test(message)) {
        offerProposal(localPlan);
        return;
      }
      if ($('assistant-ai-consent').checked) {
        try {
          const config = await fetch('/api/assistant/config', { cache:'no-store' }).then(r => r.json());
          if (config.ai_available) {
            $('assistant-mode').textContent = 'AI suggestions enabled · No CSV row data shared';
            offerProposal(await requestAiSuggestion(message));
            return;
          }
          botSay('A generative AI model is not configured. I can still suggest supported operations privately and for free.');
        } catch (error) {
          botSay(`AI connection unavailable: ${error.message}. Switching to private guided suggestions.`);
        }
      }
      offerProposal(localPlan);
    } catch (error) {
      botSay(error.message || 'Could not interpret the request.');
    } finally {
      setAssistantBusy(false);
    }
  });
})();
