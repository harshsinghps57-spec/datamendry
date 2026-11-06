"""Milestone 6: exploratory correlations and HTML report integration contracts."""
from __future__ import annotations

import math
from pathlib import Path

from fastapi.testclient import TestClient

from datamendry.api import Settings, create_app
from datamendry.analytics_relationships import relationship_overview, MAX_SCANNED_ROWS

ROOT = Path(__file__).resolve().parents[1]


def upload(client, content):
    response = client.post('/api/datasets', files={'file': ('relationships.csv', content, 'text/csv')})
    assert response.status_code == 201, response.text
    return response.json()['dataset_id']


def test_positive_and_negative_correlations_with_complete_pairs(tmp_path):
    app = create_app(Settings(data_dir=tmp_path/'data', demo_only=False))
    with TestClient(app) as client:
        identifier = upload(client, b'X,Y,Z,Label\n1,10,4,A\n2,20,3,B\n3,30,2,C\n4,40,1,D\n')
        payload = client.get(f'/api/datasets/{identifier}/relationships')
        assert payload.status_code == 200
        j = payload.json()
        assert j['sampled_rows'] == 4 and j['data_sent_externally'] is False
        assert j['columns'] == ['X','Y','Z']
        xy = next(row for row in j['pairs'] if row['x'] == 'X' and row['y'] == 'Y')
        xz = next(row for row in j['pairs'] if row['x'] == 'X' and row['y'] == 'Z')
        assert math.isclose(xy['r'], 1.0, abs_tol=1e-12)
        assert math.isclose(xz['r'], -1.0, abs_tol=1e-12)
        assert xy['paired_rows'] == 4


def test_pair_density_contains_only_aggregates_and_matches_counts(tmp_path):
    app = create_app(Settings(data_dir=tmp_path/'data', demo_only=False))
    with TestClient(app) as client:
        identifier = upload(client, b'X,Y\n1,2\n2,3\n3,4\n4,5\n5,6\n')
        response = client.get(f'/api/datasets/{identifier}/relationships/pair', params={'x':'X','y':'Y'})
        assert response.status_code == 200
        payload = response.json()
        assert len(payload['bins']) == 10
        assert all(len(row) == 10 for row in payload['bins'])
        assert sum(sum(row) for row in payload['bins']) == payload['paired_rows'] == 5
        assert all(isinstance(value, int) for row in payload['bins'] for value in row)
        assert 'rows' not in payload and 'raw_data' not in payload
        assert math.isclose(payload['r'], 1.0)


def test_missing_pair_values_and_non_numeric_fields(tmp_path):
    app = create_app(Settings(data_dir=tmp_path/'data', demo_only=False))
    with TestClient(app) as client:
        identifier = upload(client, b'A,B,Description\n1,2,west\n2,3,east\n,5,east\n4,,west\n5,6,west\n')
        response = client.get(f'/api/datasets/{identifier}/relationships')
        assert response.status_code == 200
        assert response.json()['columns'] == ['A','B']
        result = client.get(f'/api/datasets/{identifier}/relationships/pair',params={'x':'A','y':'B'}).json()
        assert result['paired_rows'] == 3
        assert sum(map(sum,result['bins'])) == 3


def test_constant_columns_report_undefined_and_pair_fails_safely(tmp_path):
    app = create_app(Settings(data_dir=tmp_path/'data', demo_only=False))
    with TestClient(app) as client:
        identifier = upload(client, b'A,B\n5,1\n5,2\n5,3\n5,4\n')
        matrix = client.get(f'/api/datasets/{identifier}/relationships').json()
        pair = next(item for item in matrix['pairs'] if item['x'] == 'A' and item['y'] == 'B')
        assert pair['r'] is None
        detail = client.get(f'/api/datasets/{identifier}/relationships/pair?x=A&y=B')
        assert detail.status_code == 200
        assert detail.json()['r'] is None


def test_invalid_column_inputs_do_not_leak_data(tmp_path):
    app = create_app(Settings(data_dir=tmp_path/'data', demo_only=False))
    with TestClient(app) as client:
        identifier = upload(client, b'A,B,Title\n1,2,A\n3,4,B\n5,6,C\n')
        for params in [{'x':'Title','y':'A'},{'x':'A','y':'A'},{'x':'nonexistent','y':'B'}]:
            response = client.get(f'/api/datasets/{identifier}/relationships/pair', params=params)
            assert response.status_code == 422
        assert client.get(f'/api/datasets/{identifier}/relationships/pair?x=A').status_code == 422


def test_guest_session_owner_isolation(tmp_path):
    app = create_app(Settings(data_dir=tmp_path/'data', demo_only=False))
    with TestClient(app) as owner, TestClient(app) as outsider:
        identifier = upload(owner, b'A,B\n1,2\n2,4\n3,6\n')
        assert owner.get(f'/api/datasets/{identifier}/relationships').status_code == 200
        assert outsider.get(f'/api/datasets/{identifier}/relationships').status_code == 404
        assert outsider.get(f'/api/datasets/{identifier}/relationships/pair?x=A&y=B').status_code == 404


def test_bounded_sample_excludes_rows_beyond_10000(tmp_path):
    # A controlled test fixture ensures this endpoint never silently claims all rows were scanned.
    csv_data = ('A,B\n' + ''.join(f'{i},{2*i}\n' for i in range(MAX_SCANNED_ROWS + 3))).encode()
    app = create_app(Settings(data_dir=tmp_path/'data', demo_only=False))
    with TestClient(app) as client:
        identifier = upload(client, csv_data)
        result = client.get(f'/api/datasets/{identifier}/relationships')
        assert result.status_code == 200
        assert result.json()['truncated'] is True
        assert result.json()['sampled_rows'] == 10000
        assert result.json()['pairs'][1]['paired_rows'] == 10000


def test_numeric_column_limit_is_twelve(tmp_path):
    names = [f'C{i}' for i in range(14)]
    csv = (','.join(names)+'\n'+''.join(','.join(str(x+i) for i in range(14))+'\n' for x in range(5))).encode()
    app = create_app(Settings(data_dir=tmp_path/'data',demo_only=False))
    with TestClient(app) as client:
        identifier = upload(client, csv)
        result = client.get(f'/api/datasets/{identifier}/relationships').json()
        assert len(result['columns']) == 12
        assert len(result['pairs']) == 12*13//2
        pair = client.get(f'/api/datasets/{identifier}/relationships/pair?x=C1&y=C13')
        assert pair.status_code == 422


def test_empty_categories_no_relationships(tmp_path):
    app = create_app(Settings(data_dir=tmp_path/'data',demo_only=False))
    with TestClient(app) as client:
        identifier = upload(client, b'A,B\nfirst,yes\nsecond,no\nthird,yes\n')
        result = client.get(f'/api/datasets/{identifier}/relationships').json()
        assert result['columns'] == []
        assert result['pairs'] == []


def test_browser_controls_accessible_without_modifying_legacy_modes(tmp_path):
    html = (ROOT/'static/index.html').read_text(encoding='utf-8')
    js = (ROOT/'static/analytics.js').read_text(encoding='utf-8')
    css = (ROOT/'static/experience.css').read_text(encoding='utf-8')
    for value in ('value="single" selected','value="all"','value="compare"', 'id="analytics-correlation-matrix"',
                  'id="analytics-pair-x"', 'id="analytics-pair-y"', 'id="analytics-visual-report"'):
        assert value in html
    assert 'function setAnalyticsView(mode)' in js
    assert "analyticsView === 'all'" in js
    assert 'setAnalyticsView(\'single\')' in js
    assert 'function downloadVisualReport()' in js
    assert 'function reportEsc(value)' in js
    assert 'textContent' in js and 'innerHTML' not in js
    assert '.analytics-density-grid' in css and '.analytics-matrix' in css
    app = create_app(Settings(data_dir=tmp_path/'data',demo_only=False))
    with TestClient(app) as client:
        assert client.get('/static/analytics.js').status_code == 200


def test_relationships_never_modify_original_source(tmp_path):
    app = create_app(Settings(data_dir=tmp_path/'data',demo_only=False))
    with TestClient(app) as client:
        identifier = upload(client, b'A,B\n1,5\n2,9\n3,12\n')
        before = client.get(f'/api/datasets/{identifier}/preview').json()
        assert client.get(f'/api/datasets/{identifier}/relationships').status_code == 200
        assert client.get(f'/api/datasets/{identifier}/relationships/pair?x=A&y=B').status_code == 200
        after = client.get(f'/api/datasets/{identifier}/preview').json()
        assert before == after
