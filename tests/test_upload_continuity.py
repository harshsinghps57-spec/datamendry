"""Public upload availability and private-workspace regression tests.

The rendering config is under version control. A future intentional production
policy change requires also intentionally changing this test.
"""
from pathlib import Path
import re

from fastapi.testclient import TestClient
from datamendry.api import Settings, create_app

ROOT = Path(__file__).resolve().parents[1]


def _render_value(text: str, key: str) -> str:
    match = re.search(r"(?m)^\s*- key: " + re.escape(key)
                      + r"\s*\n\s*value: [\"']?([^\s\"']+)", text)
    assert match, f"{key} missing from render.yaml"
    return match.group(1)


def test_render_keeps_public_uploads_and_cookie_protection():
    config = (ROOT / 'render.yaml').read_text(encoding='utf-8')
    assert _render_value(config, 'DATAMENDRY_DEMO_ONLY') == '0', 'CSV uploads must remain enabled'
    assert _render_value(config, 'DATAMENDRY_SECURE_COOKIE') == '1'
    assert int(_render_value(config, 'DATAMENDRY_MAX_UPLOAD_MB')) > 0
    assert int(_render_value(config, 'DATAMENDRY_UPLOADS_PER_MINUTE')) > 0
    assert int(_render_value(config, 'DATAMENDRY_MAX_DATASETS')) > 0


def test_frontend_keeps_upload_button_when_enabled_and_remembers_dataset():
    js = (ROOT / 'static' / 'app.js').read_text(encoding='utf-8')
    assert 'uploadButton.hidden = false' in js
    assert 'configureDemoMode().then(restoreDataset)' in js
    assert "sessionStorage.setItem(CURRENT_DATASET_KEY, id)" in js
    assert "sessionStorage.removeItem(CURRENT_DATASET_KEY)" in js


def test_uploaded_csv_can_be_reopened_but_not_read_by_other_guest(tmp_path):
    app = create_app(Settings(data_dir=tmp_path / 'workspaces', demo_only=False,
                              secure_cookie=True, max_upload_bytes=1024*1024))
    with (TestClient(app, base_url='https://testserver') as a,
          TestClient(app, base_url='https://testserver') as b):
        config = a.get('/api/config')
        assert config.status_code == 200
        assert config.json()['demo_only'] is False
        assert config.json()['private_guest_workspace'] is True
        response = a.post('/api/datasets', files={'file': ('sample.csv', b'city,value\nPune,1\n', 'text/csv')})
        assert response.status_code == 201, response.text
        id_ = response.json()['dataset_id']
        assert a.get(f'/api/datasets/{id_}/profile').status_code == 200
        assert a.get(f'/api/datasets/{id_}/preview').status_code == 200
        assert b.get(f'/api/datasets/{id_}/profile').status_code == 404
        assert b.get(f'/api/datasets/{id_}/export.csv').status_code == 404
        assert b.delete(f'/api/datasets/{id_}').status_code == 404
        assert a.delete(f'/api/datasets/{id_}').status_code == 200
        assert a.get(f'/api/datasets/{id_}/profile').status_code == 404


def test_server_rejects_oversize_upload(tmp_path):
    app = create_app(Settings(data_dir=tmp_path / 'workspaces',
                              demo_only=False, max_upload_bytes=100))
    with TestClient(app) as client:
        response = client.post('/api/datasets', files={'file': ('oversized.csv', b'a\n' + b'1'*110 + b'\n', 'text/csv')})
        assert response.status_code == 413, response.text
