"""Regression checks for opt-in filter/export and account welcome routes."""
from __future__ import annotations
import csv
import io
from pathlib import Path
from fastapi.testclient import TestClient
from datamendry.api import Settings, create_app


def test_filter_preview_export_preserves_source(tmp_path: Path):
    with TestClient(create_app(Settings(data_dir=tmp_path / 'd', demo_only=False))) as client:
        response = client.post('/api/datasets', files={'file': ('sales.csv', b'Name,Region,Formula\nA,West,=HYPERLINK(\nB,East,normal\nC,West,ok\n', 'text/csv')})
        assert response.status_code == 201, response.text
        key = response.json()['dataset_id']
        spec = {'filter_column': 'Region', 'kind': 'equals', 'value': 'West', 'included_columns': ['Name','Formula']}
        res = client.post(f'/api/datasets/{key}/filters/preview', json=spec)
        assert res.status_code == 200, res.text
        assert res.json()['matching_rows'] == 2
        assert res.json()['columns'] == ['Name','Formula']
        result = client.post(f'/api/datasets/{key}/filters/export', json=spec)
        assert result.status_code == 200
        text = result.content.decode('utf-8-sig')
        rows = list(csv.reader(io.StringIO(text)))
        assert rows[0] == ['Name','Formula']
        assert len(rows) == 3
        assert rows[1][1].startswith('\t=')  # Protect spreadsheet formulas
        assert client.get(f'/api/datasets/{key}/profile').json()['rows'] == 3


def test_filter_rejects_unknown_and_injection(tmp_path: Path):
    with TestClient(create_app(Settings(data_dir=tmp_path / 'd'))) as client:
        key = client.post('/api/datasets', files={'file': ('test.csv', b'Name,Value\nA,1\n', 'text/csv')}).json()['dataset_id']
        base = {'filter_column': 'Name', 'kind': 'all', 'value': '', 'included_columns': ['Name']}
        assert client.post(f'/api/datasets/{key}/filters/preview', json={**base, 'included_columns': ['Name; DROP TABLE records']}).status_code == 422
        assert client.post(f'/api/datasets/{key}/filters/preview', json={**base, 'included_columns': []}).status_code == 422
        assert client.post(f'/api/datasets/{key}/filters/preview', json={**base, 'kind':'contains', 'filter_column':'nonexistent'}).status_code == 422
        assert client.get('/verify').status_code == 200
        for name in ['experience.js','experience.css','verify.js']:
            assert client.get('/static/' + name).status_code == 200
        assert client.get('/static/secret.js').status_code == 404


def test_filter_owner_isolation(tmp_path: Path):
    app = create_app(Settings(data_dir=tmp_path / 'd'))
    with TestClient(app) as a, TestClient(app) as b:
        key = a.post('/api/datasets', files={'file': ('x.csv', b'id,name\n1,A\n', 'text/csv')}).json()['dataset_id']
        spec = {'kind':'all','included_columns':['id']}
        assert b.post(f'/api/datasets/{key}/filters/preview', json=spec).status_code == 404
        assert b.post(f'/api/datasets/{key}/filters/export', json=spec).status_code == 404


def test_render_keeps_public_uploads():
    root = Path(__file__).resolve().parents[1]
    cfg = (root / 'render.yaml').read_text()
    assert 'key: DATAMENDRY_DEMO_ONLY\n        value: "0"' in cfg
    assert 'id="file-input"' in (root / 'static/index.html').read_text(encoding='utf-8')


def test_ai_is_opt_in_and_disabled_without_server_key(tmp_path, monkeypatch):
    monkeypatch.delenv('DATAMENDRY_OPENAI_API_KEY', raising=False)
    with TestClient(create_app(Settings(data_dir=tmp_path / 'd'))) as client:
        assert client.get('/api/assistant/config').json() == {'ai_available': False}
        dataset_id = client.post('/api/datasets', files={'file': ('test.csv', b'id,name\n1,Ana\n', 'text/csv')}).json()['dataset_id']
        response = client.post(f'/api/datasets/{dataset_id}/assistant/suggest', json={'message': 'remove duplicates', 'consent_to_column_names': True})
        assert response.status_code == 503

