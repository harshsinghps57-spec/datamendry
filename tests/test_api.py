from __future__ import annotations

import csv
import io
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from datamendry.api import Settings, create_app


@pytest.fixture
def client(tmp_path: Path):
    with TestClient(create_app(Settings(data_dir=tmp_path / 'uploads', max_upload_bytes=1024 * 1024, ttl_hours=24))) as test_client:
        yield test_client


def upload(client, content: bytes, filename='sales.csv'):
    return client.post('/api/datasets', files={'file': (filename, content, 'text/csv')})


def test_home_and_assets(client):
    assert client.get('/').status_code == 200
    assert 'DataMendry' in client.get('/').text
    assert client.get('/static/app.js').status_code == 200
    assert client.get('/static/app.css').status_code == 200
    assert client.get('/api/demo.csv').status_code == 200
    assert client.get('/static/../../etc/passwd').status_code == 404
    res = client.get('/api/health')
    assert res.json()['status'] == 'ok'
    assert res.headers['x-content-type-options'] == 'nosniff'


def test_end_to_end(client):
    response = upload(client, b'id,value\n001, 7 \n001,7\n002,\n')
    assert response.status_code == 201, response.text
    result = response.json()
    dataset_id = result['dataset_id']
    assert result['profile']['rows'] == 3
    assert result['profile']['column_count'] == 2
    assert result['profile']['missing_cells'] == 1
    preview = client.get(f'/api/datasets/{dataset_id}/preview?limit=2').json()
    assert preview['rows'][0][0] == '001'
    options = {'trim_whitespace': True, 'normalize_blanks': True, 'remove_exact_duplicates': True}
    impact = client.post(f'/api/datasets/{dataset_id}/simulate', json=options)
    assert impact.status_code == 200
    assert impact.json()['after']['rows'] == 2
    output = client.get(f'/api/datasets/{dataset_id}/export.csv', params=options)
    assert output.status_code == 200
    exported = list(csv.reader(io.StringIO(output.content.decode('utf-8-sig'))))
    assert exported == [['id', 'value'], ['001', '7'], ['002', '']]
    assert client.delete(f'/api/datasets/{dataset_id}').json()['deleted']
    assert client.get(f'/api/datasets/{dataset_id}/profile').status_code == 404


def test_validation_rules(client):
    res = upload(client, b'id,score\n001,4\n001,foo\n002,9\n003,\n')
    key = res.json()['dataset_id']
    checks = [
        {'column': 'id', 'kind': 'unique'},
        {'column': 'score', 'kind': 'not_empty'},
        {'column': 'score', 'kind': 'numeric'},
        {'column': 'score', 'kind': 'minimum', 'threshold': 5},
        {'column': 'score', 'kind': 'maximum', 'threshold': 10},
    ]
    results = client.post(f'/api/datasets/{key}/rules', json={'rules': checks})
    assert results.status_code == 200, results.text
    assert [x['violations'] for x in results.json()['results']] == [1, 1, 2, 3, 2]
    assert client.post(f'/api/datasets/{key}/rules', json={'rules': [{'column': 'bad', 'kind': 'unique'}]}).status_code == 422
    assert client.post(f'/api/datasets/{key}/rules', json={'rules': [{'column': 'score', 'kind': 'maximum'}]}).status_code == 422


def test_rejections_cleanup(client):
    assert upload(client, b'id,name\n1,2\n', 'bad.xlsx').status_code == 415
    assert upload(client, b'').status_code == 422
    assert upload(client, b'a,b\n\xff,2\n').status_code == 422
    assert upload(client, b'x,y\n1,2,3\n').status_code == 422
    assert upload(client, b'id,name\n' + b'a,zzz\n' * 300_000).status_code == 413


def test_invalid_id_and_request_limits(client):
    assert client.get('/api/datasets/../profile').status_code == 404
    assert client.get('/api/datasets/' + '0' * 32 + '/profile').status_code == 404
    res = upload(client, b'id,value\n1,5\n')
    key = res.json()['dataset_id']
    assert client.get(f'/api/datasets/{key}/preview?limit=200').status_code == 422
    assert client.post(f'/api/datasets/{key}/rules', json={'rules': []}).status_code == 422
