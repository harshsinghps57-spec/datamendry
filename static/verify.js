'use strict';
(() => {
  const setStatus = (title, message) => {
    document.getElementById('verify-title').textContent = title;
    document.getElementById('verify-status').textContent = message;
  };
  const fragments = new URLSearchParams(location.hash.slice(1));
  const params = new URLSearchParams(location.search);
  // The URL fragment may contain bearer tokens. Remove it immediately.
  history.replaceState(null, '', location.pathname);
  const access = fragments.get('access_token');
  const refresh = fragments.get('refresh_token');
  if (access && refresh) {
    try {
      sessionStorage.setItem('datamendry.supabase-session.v1', JSON.stringify({
        access_token: access, refresh_token: refresh,
        expires_at: Math.floor(Date.now() / 1000) + (Number(fragments.get('expires_in')) || 3600)
      }));
      setStatus('Account verified ✓', 'Taking you to your DataMendry workspace…');
      window.setTimeout(() => location.replace('/'), 1100);
    } catch {
      setStatus('Browser storage unavailable', 'Open DataMendry and sign in using your email and password.');
    }
  } else if (fragments.get('error') || params.get('error')) {
    const code = String(fragments.get('error_code') || params.get('error_code') || fragments.get('error') || params.get('error') || 'oauth_failed').slice(0, 90);
    setStatus('Sign-in could not be completed', `Error: ${code}. Check the Google OAuth configuration or request a new email link. No session was created.`);
  } else {
    setStatus('Open your verification email', 'Use the link from your latest confirmation email, or sign in if your account is already confirmed.');
  }
})();
