"""Regression tests for the safe no-missing state and all-columns chart gallery."""
from pathlib import Path
from fastapi.testclient import TestClient
from datamendry.api import create_app, Settings


ROOT = Path(__file__).resolve().parents[1]


def new_csv(client, blob):
    result = client.post('/api/datasets', files={'file': ('m4.csv', blob, 'text/csv')})
    assert result.status_code == 201, result.text
    return result.json()['dataset_id']


def test_profile_and_chart_aggregate_on_clean_csv(tmp_path):
    app = create_app(Settings(data_dir=tmp_path/'data', demo_only=False))
    with TestClient(app) as client:
        ds = new_csv(client, b'CGPA,Placement,Name\n7.2,Yes,A\n8.9,No,B\n8.2,Yes,C\n')
        profile = client.get(f'/api/datasets/{ds}/profile')
        assert profile.status_code == 200
        assert profile.json()['missing_cells'] == 0
        assert all(row['missing'] == 0 for row in profile.json()['column_missing'])
        for column in profile.json()['columns']:
            result = client.get(f'/api/datasets/{ds}/analytics', params={'column': column})
            assert result.status_code == 200
            assert result.json()['column'] == column


def test_mixed_missing_and_safe_chart_categories(tmp_path):
    app = create_app(Settings(data_dir=tmp_path/'data', demo_only=False))
    with TestClient(app) as client:
        ds = new_csv(client, b'Value,Name\n1,<svg onload=alert(1)>\n,Two\n4,Three\n')
        profile = client.get(f'/api/datasets/{ds}/profile').json()
        assert profile['missing_cells'] == 1
        j = client.get(f'/api/datasets/{ds}/analytics?column=Name').json()
        assert j['mode'] == 'categorical'
        assert any('<svg' in x['label'] for x in j['bars'])
    js = (ROOT/'static/analytics.js').read_text(encoding='utf-8')
    assert 'textContent' in js
    assert 'innerHTML' not in js


def test_gallery_markup_controls_and_delivery(tmp_path):
    page = (ROOT/'static/index.html').read_text(encoding='utf-8')
    js = (ROOT/'static/analytics.js').read_text(encoding='utf-8')
    css = (ROOT/'static/experience.css').read_text(encoding='utf-8')
    for selector in ['analytics-all-charts', 'analytics-gallery-more', 'analytics-gallery-status',
                     'analytics-missing-heading', 'analytics-missing-caption',
                     'analytics-column-chart', 'assistant-expand']:
        assert f'id="{selector}"' in page
    for term in ['No missing values found', '100% complete', 'GALLERY_BATCH = 8',
                 'GALLERY_CONCURRENCY = 3', 'galleryVersion', 'loadGalleryBatch',
                 'analytics-mini-hist', 'analytics-mini-category', 'encodeURIComponent(tile.column)']:
        assert term in js
    assert '.analytics-gallery' in css
    app = create_app(Settings(data_dir=tmp_path/'data', demo_only=False))
    with TestClient(app) as client:
        result = client.get('/static/analytics.js')
        assert result.status_code == 200
        assert b'loadGalleryBatch' in result.content
