"""Private guest workspace and cookie-isolation regression tests."""
from pathlib import Path

from fastapi.testclient import TestClient

from datamendry.api import Settings, create_app


def test_browser_isolation_for_every_sensitive_route(tmp_path: Path):
    app = create_app(Settings(data_dir=tmp_path / 'workspaces', demo_only=True))
    with TestClient(app) as alice, TestClient(app) as bob:
        created = alice.post('/api/datasets/demo')
        assert created.status_code == 201
        dataset_id = created.json()['dataset_id']
        prefix = f'/api/datasets/{dataset_id}'
        assert alice.get(prefix + '/profile').status_code == 200
        assert alice.get(prefix + '/preview').status_code == 200
        assert alice.get(prefix + '/export.csv').status_code == 200
        assert alice.post(prefix + '/simulate', json={}).status_code == 200
        rule = {'rules': [{'column': 'region', 'kind': 'not_empty'}]}
        # Test privacy before any SQL validation of a rule takes place.
        for method, url, kw in (
            ('get', prefix + '/profile', {}),
            ('get', prefix + '/preview', {}),
            ('get', prefix + '/export.csv', {}),
            ('post', prefix + '/simulate', {'json': {}}),
            ('post', prefix + '/rules', {'json': rule}),
            ('delete', prefix, {}),
        ):
            result = getattr(bob, method)(url, **kw)
            assert result.status_code == 404, (method, url, result.text)
        assert alice.get(prefix + '/profile').status_code == 200
        assert alice.delete(prefix).status_code == 200
        assert alice.get(prefix + '/profile').status_code == 404


def test_session_cookie_is_httponly_host_only_strict(tmp_path: Path):
    app = create_app(Settings(data_dir=tmp_path / 'workspaces', demo_only=True, secure_cookie=True))
    with TestClient(app, base_url='https://testserver') as browser:
        result = browser.get('/api/config')
        cookie = result.headers['set-cookie']
        assert '__Host-datamendry_guest=' in cookie
        assert 'httponly' in cookie.lower()
        assert 'secure' in cookie.lower()
        assert 'samesite=lax' in cookie.lower()
        assert 'path=/' in cookie.lower()
        assert 'domain=' not in cookie.lower()
        assert result.json()['private_guest_workspace'] is True
        assert browser.post('/api/datasets/demo').status_code == 201


def test_guest_cap_and_upload_rate_limit(tmp_path: Path):
    app = create_app(Settings(data_dir=tmp_path / 'workspaces', max_datasets_per_guest=1,
                              upload_creates_per_minute=1, max_upload_bytes=1024 * 1024))
    with TestClient(app) as browser1, TestClient(app) as browser2:
        first = browser1.post('/api/datasets', files={'file': ('first.csv', b'id\n1\n', 'text/csv')})
        assert first.status_code == 201
        # Rate limiter operates globally, even across guest sessions.
        second = browser2.post('/api/datasets', files={'file': ('second.csv', b'id\n2\n', 'text/csv')})
        assert second.status_code == 429
        assert browser1.post('/api/datasets/demo').status_code == 429
        assert browser1.delete('/api/datasets/' + first.json()['dataset_id']).status_code == 200
        assert browser2.post('/api/datasets/demo').status_code == 201


def test_missing_or_changed_cookie_does_not_restore_access(tmp_path: Path):
    app = create_app(Settings(data_dir=tmp_path / 'workspaces', demo_only=True))
    with TestClient(app) as browser:
        r = browser.post('/api/datasets/demo')
        dataset_id = r.json()['dataset_id']
        assert browser.get(f'/api/datasets/{dataset_id}/profile').status_code == 200
        browser.cookies.clear()
        assert browser.get(f'/api/datasets/{dataset_id}/profile').status_code == 404


def test_forged_guest_cookie_is_replaced(tmp_path: Path):
    app = create_app(Settings(data_dir=tmp_path / 'workspaces', demo_only=True))
    with TestClient(app) as browser:
        browser.cookies.set('datamendry_guest_local', 'A' * 43 + '.' + 'B' * 43)
        result = browser.get('/api/config')
        assert result.status_code == 200
        assert 'set-cookie' in result.headers
        assert 'A' * 43 not in result.headers['set-cookie']
