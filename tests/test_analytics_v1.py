"""Private analytics API and additive interface regression tests."""
import math
from pathlib import Path
from fastapi.testclient import TestClient
from datamendry.api import Settings, create_app


def create_csv(client, content: bytes):
    response = client.post('/api/datasets', files={'file': ('insights.csv', content, 'text/csv')})
    assert response.status_code == 201, response.text
    return response.json()['dataset_id']


def test_numeric_insights_and_original_unchanged(tmp_path: Path):
    app = create_app(Settings(data_dir=tmp_path/'data', demo_only=False))
    with TestClient(app) as client:
        ds = create_csv(client, b'ID,CGPA,Region\n1,1,West\n2,2,East\n3,3,West\n4,4,East\n5,5,West\n6,,North\n')
        result = client.get(f'/api/datasets/{ds}/analytics', params={'column':'CGPA'})
        assert result.status_code == 200, result.text
        j = result.json()
        assert j['mode'] == 'numeric'
        assert (j['rows'],j['missing'],j['present'],j['numeric_count']) == (6,1,5,5)
        assert sum(item['count'] for item in j['bars']) == 5
        assert len(j['bars']) == 12
        assert j['stats']['min'] == 1
        assert j['stats']['max'] == 5
        assert math.isclose(j['stats']['mean'],3)
        assert j['stats']['possible_outliers_3sigma'] == 0
        assert j['data_sent_externally'] is False
        assert client.get(f'/api/datasets/{ds}/profile').json()['rows'] == 6


def test_categorical_mode_and_bounded_top_values(tmp_path: Path):
    app = create_app(Settings(data_dir=tmp_path/'data', demo_only=False))
    with TestClient(app) as c:
        ds = create_csv(c, b'Region\nWest\nEast\nWest\nNorth\n""\n')
        j = c.get(f'/api/datasets/{ds}/analytics?column=Region').json()
        assert j['mode'] == 'categorical'
        assert j['bars'][0] == {'label':'West','count':2}
        assert j['missing'] == 1
        assert len(j['bars']) == 3
        assert j['stats'] is None


def test_mixed_values_not_misleading_numeric(tmp_path: Path):
    app = create_app(Settings(data_dir=tmp_path/'data', demo_only=False))
    with TestClient(app) as c:
        ds = create_csv(c, b'Value\n1\n2\n3\ntext\n')
        j = c.get(f'/api/datasets/{ds}/analytics?column=Value').json()
        assert j['mode'] == 'categorical'
        assert j['numeric_count'] == 3
        assert j['invalid_numeric'] == 1


def test_zero_variance_and_one_numeric(tmp_path: Path):
    app = create_app(Settings(data_dir=tmp_path/'data', demo_only=False))
    with TestClient(app) as c:
        ds = create_csv(c, b'Value\n7\n7\n7\n')
        j = c.get(f'/api/datasets/{ds}/analytics?column=Value').json()
        assert j['mode'] == 'numeric'
        assert j['stats']['std_dev'] == 0
        assert j['bars'][0]['count'] == 3
        assert sum(b['count'] for b in j['bars'][1:]) == 0


def test_empty_column_and_special_text(tmp_path: Path):
    app = create_app(Settings(data_dir=tmp_path/'data', demo_only=False))
    with TestClient(app) as c:
        ds = create_csv(c, b'Blank,Name\n,\"<img src=x onerror=alert(1)>\"\n ,text\n')
        j = c.get(f'/api/datasets/{ds}/analytics?column=Blank').json()
        assert j['mode'] == 'empty'
        assert j['missing'] == 2
        j2 = c.get(f'/api/datasets/{ds}/analytics?column=Name').json()
        assert j2['mode'] == 'categorical'
        assert any('<img' in r['label'] for r in j2['bars'])
        # Frontend must render those as textContent, never as HTML.
        frontend = (Path(__file__).parents[1] / 'static/analytics.js').read_text(encoding='utf-8')
        assert 'textContent' in frontend
        assert 'innerHTML' not in frontend


def test_bad_column_rejected_and_private_guest_isolation(tmp_path: Path):
    app = create_app(Settings(data_dir=tmp_path/'data', demo_only=False))
    with TestClient(app) as alice, TestClient(app) as bob:
        ds = create_csv(alice, b'Value\n3\n4\n')
        assert alice.get(f'/api/datasets/{ds}/analytics?column=NoSuchColumn').status_code == 422
        assert alice.get(f'/api/datasets/{ds}/analytics?column=').status_code == 422
        assert alice.get(f'/api/datasets/{ds}/analytics?column='+ 'x' * 201).status_code == 422
        assert bob.get(f'/api/datasets/{ds}/analytics?column=Value').status_code == 404


def test_large_categories_limited_and_sorted(tmp_path: Path):
    app = create_app(Settings(data_dir=tmp_path/'data', demo_only=False))
    with TestClient(app) as c:
        blob = ('Group\n' + ''.join(f'G{i}\n' for i in range(29)) + 'G0\n').encode()
        ds = create_csv(c, blob)
        j = c.get(f'/api/datasets/{ds}/analytics?column=Group').json()
        assert len(j['bars']) == 10
        assert j['bars'][0]['label'] == 'G0'
        assert j['bars'][0]['count'] == 2
        assert j['rows'] == 30


def test_outliers_and_finite_numeric(tmp_path: Path):
    app = create_app(Settings(data_dir=tmp_path/'data', demo_only=False))
    with TestClient(app) as c:
        blob = ('Score\n' + '1\n' * 49 + '1000\n').encode()
        ds = create_csv(c, blob)
        j = c.get(f'/api/datasets/{ds}/analytics?column=Score').json()
        assert j['mode'] == 'numeric'
        assert j['stats']['possible_outliers_3sigma'] == 1
        assert all(math.isfinite(value) for value in j['stats'].values())


def test_ui_navigation_assistant_and_guide_are_additive():
    root = Path(__file__).parents[1]
    page = (root/'static/index.html').read_text(encoding='utf-8')
    app = (root/'static/app.js').read_text(encoding='utf-8')
    experience = (root/'static/experience.js').read_text(encoding='utf-8')
    analytics = (root/'static/analytics.js').read_text(encoding='utf-8')
    css = (root/'static/experience.css').read_text(encoding='utf-8')
    for fragment in ['data-page="analytics"', 'data-crumb-page="analytics"', 'id="page-analytics"',
                     'id="analytics-column"', 'id="analytics-report"', 'src="/static/analytics.js"',
                     'id="assistant-expand"', 'id="assistant-examples-toggle"',
                     'class="assistant-compose"',
                     'data-page="filter"', 'id="guide-assistant"', 'id="profile-toggle"']:
        assert fragment in page
    assert "analytics: 'Analytics dashboard'" in app
    assert "datamendry:page" in app
    assert "is-expanded" in experience
    assert "assistant-prompts" in experience
    assert '.assistant-panel.is-expanded' in css
    assert 'fetch(`/api/datasets/${encodeURIComponent(id)}/analytics' in analytics
    assert 'innerHTML' not in analytics
