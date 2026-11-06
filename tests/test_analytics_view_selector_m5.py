"""Milestone 5: analytics view selector and lazy gallery contract."""
from pathlib import Path

from fastapi.testclient import TestClient

from datamendry.api import Settings, create_app


ROOT = Path(__file__).resolve().parents[1]


def test_analytics_mode_select_contains_both_views_and_defaults_single():
    html = (ROOT / 'static/index.html').read_text(encoding='utf-8')
    assert '<select id="analytics-view-mode"' in html
    assert '<option value="single" selected>Explore a column</option>' in html
    assert '<option value="all">All columns — chart overview</option>' in html
    assert 'id="analytics-single-panel"' in html
    assert 'id="analytics-gallery-panel"' in html
    assert html.index('id="analytics-view-mode"') < html.index('id="analytics-single-panel"')
    assert html.index('id="analytics-single-panel"') < html.index('id="analytics-gallery-panel"')
    assert 'analytics-gallery-panel analytics-view-panel" hidden>' in html


def test_gallery_is_lazy_and_detail_links_restore_single_view():
    js = (ROOT / 'static/analytics.js').read_text(encoding='utf-8')
    assert "function setAnalyticsView(mode)" in js
    assert "setAnalyticsView('single');" in js
    assert "analyticsView === 'all'" in js
    assert 'galleryLoading' in js
    assert "if (analyticsView === 'all') void loadGalleryBatch();" in js
    assert "$('analytics-view-mode').addEventListener('change'" in js
    assert "$('analytics-gallery-panel').hidden = analyticsView !== 'all';" in js
    css = (ROOT / 'static/experience.css').read_text(encoding='utf-8')
    assert '.analytics-view-panel[hidden]' in css


def test_analytics_script_still_served_and_api_unchanged(tmp_path):
    app = create_app(Settings(data_dir=tmp_path / 'data', demo_only=False))
    with TestClient(app) as client:
        js = client.get('/static/analytics.js')
        assert js.status_code == 200
        assert b'setAnalyticsView' in js.content
        created = client.post('/api/datasets', files={'file': ('check.csv', b'ID,Score\nx,4\ny,5\n', 'text/csv')})
        assert created.status_code == 201
        dataset_id = created.json()['dataset_id']
        result = client.get(f'/api/datasets/{dataset_id}/analytics?column=Score')
        assert result.status_code == 200
        assert result.json()['column'] == 'Score'
