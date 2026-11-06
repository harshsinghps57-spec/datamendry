'use strict';
/* Optional Supabase cloud-originals integration. No service-role key is used.
 * Auth tokens live only in this tab's sessionStorage, not on Render.
 * Private bucket RLS is REQUIRED; the UI is not an authorization boundary.
 */
(() => {
  const $ = id => document.getElementById(id);
  const STORAGE_KEY = 'datamendry.supabase-session.v1';
  const status = message => { $('account-info').textContent = message; };
  const state = { config: null, session: null, user: null, refreshPromise: null };
  const uuid = v => /^[a-f0-9]{8}-[a-f0-9]{4}-[1-8][a-f0-9]{3}-[89ab][a-f0-9]{3}-[a-f0-9]{12}$/i.test(v);

  function authEvent() { window.dispatchEvent(new CustomEvent('datamendry:auth', { detail: { email: state.user?.email || state.user?.phone || '', provider: state.user?.app_metadata?.provider || '', signedIn: Boolean(state.user), available: Boolean(state.config?.enabled) } })); }
  function saveSession(data) {
    if (!data?.access_token || !data?.refresh_token) throw new Error('Authentication did not return a session. Confirm your email, then log in.');
    state.session = { access_token: data.access_token, refresh_token: data.refresh_token,
      expires_at: Math.floor(Date.now() / 1000) + (Number(data.expires_in) || 3600) };
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(state.session));
  }
  function clearSession() {
    state.session = null; state.user = null;
    sessionStorage.removeItem(STORAGE_KEY);
    $('account-panel').hidden = true;
    $('account-form').hidden = false;
    $('account-signed').hidden = true;
    $('account-identity').textContent = '';
    $('account-files').replaceChildren();
    authEvent();
  }
  function endpoint(path) { return `${state.config.url}${path}`; }
  async function request(path, opts = {}, authorized = false) {
    const headers = { apikey: state.config.publishable_key, ...(opts.headers || {}) };
    if (authorized) headers.Authorization = `Bearer ${await accessToken()}`;
    const response = await fetch(endpoint(path), { ...opts, headers, cache: 'no-store' });
    if (!response.ok) {
      let message = `Cloud request failed (${response.status})`;
      try { const body = await response.json(); message = String(body.msg || body.message || body.error_description || body.error || message).slice(0, 300); } catch {}
      if (response.status === 429) {
        if (/email|send.rate|over_email/i.test(message)) message = 'Email sending limit reached for this Supabase project. Try again later or sign in with your password or Google.';
        else message = 'Too many authentication requests. Please wait before trying again. You can use password login without sending an email.';
      }
      throw new Error(message);
    }
    if (response.status === 204) return null;
    return response.headers.get('content-type')?.includes('application/json') ? response.json() : response;
  }
  async function accessToken() {
    if (!state.session) throw new Error('Log in again to access My Datasets.');
    if (state.session.expires_at > Math.floor(Date.now() / 1000) + 90) return state.session.access_token;
    if (!state.refreshPromise) {
      state.refreshPromise = (async () => {
        const data = await request('/auth/v1/token?grant_type=refresh_token', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ refresh_token: state.session.refresh_token })
        });
        saveSession(data);
      })().finally(() => { state.refreshPromise = null; });
    }
    try { await state.refreshPromise; } catch { clearSession(); throw new Error('Session expired. Please log in again.'); }
    return state.session.access_token;
  }
  async function login(providedEmail, providedPassword) {
    const email = (providedEmail ?? $('account-email').value).trim(), password = providedPassword ?? $('account-password').value;
    const data = await request('/auth/v1/token?grant_type=password', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ email, password })
    });
    saveSession(data);
    $('account-password').value = '';
    await loadUser();
  }
  async function signup(providedEmail, providedPassword) {
    const email = (providedEmail ?? $('account-email').value).trim(), password = providedPassword ?? $('account-password').value;
    if (password.length < 8) throw new Error('Use a password with at least 8 characters.');
    await request(`/auth/v1/signup?redirect_to=${encodeURIComponent(location.origin + '/verify')}`, { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password }) });
    $('account-password').value = '';
    status('Account request sent. Check your email for a verification link (if required), then log in.');
  }
  async function loadUser() {
    const user = await request('/auth/v1/user', {}, true);
    if (!uuid(user?.id)) { clearSession(); throw new Error('Could not verify the signed-in user.'); }
    state.user = user;
    authEvent();
    $('account-panel').hidden = false;
    $('account-form').hidden = true;
    $('account-signed').hidden = false;
    $('account-identity').textContent = `Signed in: ${String(user.email || 'verified user')}`;
    status('Private cloud storage is connected. CSV originals uploaded while signed in will be saved to My Datasets.');
    await listFiles();
  }
  function objectName(name) {
    const safe = name.replace(/[^A-Za-z0-9_.-]/g, '_').slice(0, 70);
    return safe.toLowerCase().endsWith('.csv') ? safe : safe + '.csv';
  }
  function objectPath(name) { return `${state.user.id}/${crypto.randomUUID()}__${objectName(name)}`; }
  async function saveOriginal(file) {
    if (!state.user) return false; // Anonymous uploads still work as temporary guest data.
    if (!file.name.toLowerCase().endsWith('.csv')) throw new Error('Only CSV files can be saved.');
    if (file.size > (Number(state.config.cloud_max_upload_mb) || 8) * 1000 * 1000) throw new Error('File exceeds the private cloud bucket limit (8 MB). Your temporary analysis still works.');
    const path = objectPath(file.name);
    await request(`/storage/v1/object/${state.config.bucket}/${encodeURIComponent(state.user.id)}/${encodeURIComponent(path.slice(state.user.id.length + 1))}`, {
      method: 'POST', headers: { 'Content-Type': 'text/csv', 'x-upsert': 'false', 'cache-control': 'no-store' }, body: file
    }, true);
    await listFiles();
    return true;
  }
  async function listFiles() {
    if (!state.user) return;
    const files = await request(`/storage/v1/object/list/${state.config.bucket}`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ prefix: `${state.user.id}/`, limit: 100, offset: 0,
        sortBy: { column: 'created_at', order: 'desc' } })
    }, true);
    const target = $('account-files'); target.replaceChildren();
    if (!Array.isArray(files) || !files.length) {
      target.textContent = 'No saved CSV files yet. Choose CSV File above while signed in to save one.';
      return;
    }
    for (const obj of files) {
      const name = String(obj.name || '');
      // Storage list() commonly returns the base filename instead of the full path.
      const fullPath = name.startsWith(`${state.user.id}/`) ? name : `${state.user.id}/${name}`;
      if (!fullPath.startsWith(`${state.user.id}/`) || !/^[-A-Za-z0-9_./]+$/.test(fullPath)) continue;
      const displayName = name.split('/').pop().replace(/^[0-9a-f-]{36}__/, '');
      const row = document.createElement('div'); row.className = 'account-file';
      const label = document.createElement('span'); label.className = 'account-file-name'; label.textContent = displayName;
      const actions = document.createElement('span'); actions.className = 'account-file-buttons';
      const open = document.createElement('button'); open.type = 'button'; open.className = 'button tiny primary'; open.textContent = 'Open';
      open.addEventListener('click', () => openSaved(fullPath, displayName).catch(e => status(e.message)));
      const remove = document.createElement('button'); remove.type = 'button'; remove.className = 'button tiny secondary'; remove.textContent = 'Delete';
      remove.addEventListener('click', () => deleteSaved(fullPath).catch(e => status(e.message)));
      actions.append(open, remove); row.append(label, actions); target.append(row);
    }
  }
  async function openSaved(path, name) {
    if (!state.user || !path.startsWith(`${state.user.id}/`)) throw new Error('Access denied.');
    status('Retrieving saved original and preparing a new temporary analysis workspace…');
    const response = await request(`/storage/v1/object/authenticated/${state.config.bucket}/${path.split('/').map(encodeURIComponent).join('/')}`, {}, true);
    const blob = await response.blob();
    const file = new File([blob], name, { type: 'text/csv' });
    if (typeof window.DataMendryImportSaved !== 'function') throw new Error('Data engine has not loaded. Refresh the page.');
    await window.DataMendryImportSaved(file);
    status('Saved CSV loaded for analysis. The original remains in My Datasets.');
  }
  async function deleteSaved(path) {
    if (!state.user || !path.startsWith(`${state.user.id}/`)) throw new Error('Access denied.');
    if (!window.confirm('Permanently delete this saved original from My Datasets?')) return;
    await request(`/storage/v1/object/${state.config.bucket}`, {
      method: 'DELETE', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ prefixes: [path] })
    }, true);
    status('Saved original deleted from My Datasets.');
    await listFiles();
  }
  async function logout() {
    try { await request('/auth/v1/logout', { method: 'POST' }, true); } catch {}
    const cleared = window.DataMendryDiscardCurrent ? await window.DataMendryDiscardCurrent() : false;
    clearSession();
    status(cleared ? 'Signed out. The temporary working dataset was cleared.'
      : 'Signed out, but temporary processing data could not be deleted from the server. It should expire automatically; avoid shared browsers until it does.');
  }
  async function sendEmailVerification(email) {
    if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) throw new Error('Enter a valid email address.');
    await request(`/auth/v1/otp?redirect_to=${encodeURIComponent(location.origin + '/verify')}`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      // Recovery must never create an account. New users must sign up with a password.
      body: JSON.stringify({ email, create_user: false })
    });
  }
  async function sendPhoneOtp(_phone) {
    throw new Error('Phone OTP is unavailable: an SMS provider is required. No SMS was sent.');
  }
  async function setPassword(password) {
    if (!state.user) throw new Error('Sign in first using your verified email or Google account.');
    if (typeof password !== 'string' || password.length < 8) throw new Error('Use a password with at least 8 characters.');
    await request('/auth/v1/user', {
      method: 'PUT', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ password })
    }, true);
    status('Your password has been updated. You can use email + password next time.');
  }
  async function verifyOtp(kind, identity, token) {
    if (!/^\d{6,10}$/.test(token)) throw new Error('Enter the numeric code from your latest message.');
    const payload = kind === 'phone'
      ? { phone: identity, token, type: 'sms' }
      : { email: identity, token, type: 'email' };
    const session = await request('/auth/v1/verify', { method: 'POST',
      headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
    saveSession(session);
    await loadUser();
  }
  function googleLogin() {
    if (!state.config?.enabled) throw new Error('Account service is not configured.');
    window.location.assign(endpoint(`/auth/v1/authorize?provider=google&redirect_to=${encodeURIComponent(location.origin + '/verify')}`));
  }
  window.DataMendryAccount = { login, signup, sendEmailVerification, sendPhoneOtp, verifyOtp, googleLogin, setPassword, logout,
    isAvailable: () => Boolean(state.config?.enabled), currentUser: () => state.user, getAccessToken: accessToken };
  function consumeEmailConfirmationRedirect() {
    const fragment = new URLSearchParams(window.location.hash.replace(/^#/, ''));
    if (!fragment.has('access_token') || !fragment.has('refresh_token')) return;
    try {
      saveSession({ access_token: fragment.get('access_token'),
        refresh_token: fragment.get('refresh_token'), expires_in: Number(fragment.get('expires_in')) || 3600 });
    } finally {
      // Do not leave tokens visible in browser history or copied URLs.
      history.replaceState(null, '', location.pathname + location.search);
    }
  }
  async function start() {
    try {
      const result = await fetch('/api/account-config', { cache: 'no-store' });
      if (!result.ok) return;
      state.config = await result.json();
      if (!state.config.enabled) { authEvent(); return; } // Guest CSV uploads remain available.
      $('account-panel').hidden = true;
      authEvent();
      status('Log in or create an account to save CSV originals across visits. Guest uploads remain temporary.');
      $('account-form').addEventListener('submit', e => { e.preventDefault(); login().catch(err => status(err.message)); });
      $('account-signup').addEventListener('click', () => { if (typeof window.DataMendryOpenAuth === 'function') window.DataMendryOpenAuth('signup'); else status('Use the account menu to create an account.'); });
      $('account-signout').addEventListener('click', () => logout().catch(err => status(err.message)));
      $('account-refresh').addEventListener('click', () => listFiles().catch(err => status(err.message)));
      window.DataMendrySaveOriginal = saveOriginal;
      consumeEmailConfirmationRedirect();
      try { state.session = JSON.parse(sessionStorage.getItem(STORAGE_KEY) || 'null'); } catch { state.session = null; }
      if (state.session) await loadUser().catch(() => { clearSession(); status('Please log in to open saved files.'); });
      else authEvent();
    } catch {
      // Failure of cloud account integration must never disable guest CSV uploads.
      if (state.config?.enabled) status('Account storage is temporarily unavailable; CSV uploads still work as temporary guest datasets.');
    }
  }
  start();
})();
