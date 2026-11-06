"""Regression checks: password-first authentication, no accidental account creation."""
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]

def test_password_signup_and_password_recovery_menu():
    page = (ROOT/'static/index.html').read_text(encoding='utf-8')
    logic = (ROOT/'static/experience.js').read_text(encoding='utf-8')
    assert 'id="auth-tab-signup"' in page
    assert 'id="auth-tab-recover"' in page
    assert 'id="auth-password-confirm"' in page
    assert 'id="profile-password"' in page
    assert 'Passwords do not match.' in logic
    assert "authFlow === 'recover'" in logic

def test_otp_recovery_cannot_create_users_and_password_is_authenticated():
    js = (ROOT/'static/account.js').read_text(encoding='utf-8')
    assert 'create_user: false' in js
    assert 'create_user: true' not in js
    assert 'setPassword(password)' in js
    assert "request('/auth/v1/user'" in js
    assert "}, true);" in js

def test_login_dropdown_only_shows_email_and_google():
    page = (ROOT/'static/index.html').read_text(encoding='utf-8')
    js = (ROOT/'static/experience.js').read_text(encoding='utf-8')
    method_html = page.split('<select id="auth-method">', 1)[1].split('</select>', 1)[0]
    assert method_html.count('<option ') == 2
    # Google is the default for new public-beta visitors; existing email users can sign in.
    assert '<option value="google" selected>Google account (new or existing)</option>' in method_html
    assert '<option value="email">Existing email + password</option>' in method_html
    assert method_html.index('value="google"') < method_html.index('value="email"')
    # Email registration and recovery are hidden until reliable SMTP is available.
    assert 'id="auth-tab-signup" aria-pressed="false" hidden' in page
    assert 'id="auth-tab-recover" aria-pressed="false" hidden' in page
    assert 'id="account-signup" type="button" class="button secondary" hidden' in page
    assert 'id="welcome-guest"' in page
    assert "$('auth-method').value = 'google';" in js
    assert 'value="phone"' not in method_html
    assert 'auth-phone-area' not in page
    assert 'auth-phone' not in js
    assert "verifyOtp('email'," in js
    # The existing email recovery and google login handlers are preserved.
    assert "$('auth-google').addEventListener('click'" in js
    assert "$('auth-send-email').addEventListener('click'" in js

def test_existing_upload_stays_available():
    page = (ROOT/'static/index.html').read_text(encoding='utf-8')
    assert 'id="file-input"' in page
    assert 'id="account-panel"' in page
    assert 'id="assistant-panel"' in page
