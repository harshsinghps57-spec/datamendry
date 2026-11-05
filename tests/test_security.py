"""Regression tests for public-demo security controls and resource bounds."""
from __future__ import annotations

import csv
import io
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from datamendry.api import Settings, create_app
from datamendry.engine import DatasetError, import_csv


@pytest.fixture
def demo_client(tmp_path: Path):
    settings = Settings(data_dir=tmp_path / 'data', demo_only=True,
                        max_upload_bytes=1024 * 1024, max_active_datasets=3,
                        demo_creates_per_minute=2, ttl_hours=1)
    with TestClient(create_app(settings)) as client:
        yield client


def test_public_demo_rejects_anonymous_uploads(demo_client):
    response = demo_client.post('/api/datasets', files={'file': ('private.csv', b'id\nsecret\n', 'text/csv')})
    assert response.status_code == 403


def test_sample_only_exploration_still_works(demo_client):
    config = demo_client.get('/api/config')
    assert config.json()['demo_only'] is True
    sample = demo_client.post('/api/datasets/demo')
    assert sample.status_code == 201
    dataset_id = sample.json()['dataset_id']
    assert sample.json()['profile']['rows'] > 0
    assert demo_client.get(f'/api/datasets/{dataset_id}/preview').status_code == 200
    recipe = {'trim_whitespace': True}
    assert demo_client.post(f'/api/datasets/{dataset_id}/simulate', json=recipe).status_code == 200
    assert demo_client.post(f'/api/datasets/{dataset_id}/rules', json={
        'rules': [{'column': sample.json()['profile']['columns'][0], 'kind':'not_empty'}]
    }).status_code == 200
    export = demo_client.get(f'/api/datasets/{dataset_id}/export.csv', params=recipe)
    assert export.status_code == 200
    assert export.content.startswith(b'\xef\xbb\xbf')
    assert demo_client.delete(f'/api/datasets/{dataset_id}').status_code == 200


def test_capacity_and_request_rate_limit(demo_client):
    assert demo_client.post('/api/datasets/demo').status_code == 201
    assert demo_client.post('/api/datasets/demo').status_code == 201
    assert demo_client.post('/api/datasets/demo').status_code == 429


def test_cross_site_post_rejected(demo_client):
    assert demo_client.post('/api/datasets/demo', headers={'Origin': 'https://unrelated.example'}).status_code == 403
    assert demo_client.post('/api/datasets/demo', headers={'Sec-Fetch-Site': 'cross-site'}).status_code == 403
    assert demo_client.post('/api/datasets/demo', headers={'Origin': 'http://testserver'}).status_code == 201


def test_request_body_limit(demo_client):
    assert demo_client.post('/api/datasets/demo', content=b'x' * 70_000).status_code == 413
    assert demo_client.post('/api/datasets/demo', content=b'x' * 10).status_code != 413


def test_csv_rejection_and_limits(tmp_path):
    csv_file = tmp_path / 'input.csv'
    csv_file.write_text('id,name\n1,A\n2,B\n', encoding='utf-8')
    with pytest.raises(DatasetError, match='Row limit exceeded'):
        import_csv(csv_file, tmp_path / 'limit.sqlite', max_rows=1)


def test_spreadsheet_formula_export(tmp_path):
    from datamendry.engine import RepairOptions, export_csv_chunks
    data = tmp_path / 'formula.csv'
    data.write_text('name,description\n1,=HYPERLINK(""https://invalid.example"")\n2,+SUM(1)\n3,@evil\n4,-42\n', encoding='utf-8')
    db = tmp_path / 'formula.sqlite'
    meta = import_csv(data, db)
    output = b''.join(export_csv_chunks(db, meta['columns'], RepairOptions())).decode('utf-8-sig')
    assert output.splitlines()[0].startswith('"name","description"')
    rows = list(csv.reader(io.StringIO(output)))
    assert all(row[1].startswith('\t') for row in rows[1:])


def test_security_headers(demo_client):
    res = demo_client.get('/')
    assert res.status_code == 200
    csp = res.headers['content-security-policy']
    assert "default-src 'self'" in csp
    assert "object-src 'none'" in csp
    assert 'https://static.cloudflareinsights.com/beacon.min.js' in csp
    assert 'https://cloudflareinsights.com' in csp
    assert res.headers['x-frame-options'] == 'DENY'


def test_upload_binary_and_confinement(tmp_path):
    with TestClient(create_app(Settings(data_dir=tmp_path / 'private', max_upload_bytes=3000))) as client:
        res = client.post('/api/datasets', files={'file': ('bad.csv', b'a,b\n\0,2\n', 'text/csv')})
        assert res.status_code == 422
        assert list((tmp_path / 'private').iterdir()) == []
        good = client.post('/api/datasets', files={'file': ('good.csv', b'a,b\n1,2\n', 'text/csv')})
        assert good.status_code == 201
        token = good.json()['dataset_id']
        assert client.get('/api/datasets/' + 'a' * 32 + '/profile').status_code == 404
        assert client.get(f'/api/datasets/{token}/preview').status_code == 200
