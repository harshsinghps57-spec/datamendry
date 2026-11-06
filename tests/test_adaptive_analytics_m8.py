"""Milestone 8: adaptive Pearson display and honest completeness indicators."""
from pathlib import Path

from fastapi.testclient import TestClient

from datamendry.api import Settings, create_app

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_ui_has_accessible_optional_pearson_section_and_fallback():
    html = read('static/index.html')
    assert 'id="analytics-pearson-section"' in html
    assert 'aria-label="Pearson correlation analysis" hidden' in html
    assert 'id="analytics-pearson-unavailable"' in html
    assert 'id="analytics-quality-next"' in html
    assert html.index('id="analytics-smart-result"') < html.index('id="analytics-pearson-section"')


def test_js_hides_ineligible_pearson_without_removing_smart_comparison():
    js = read('static/analytics.js')
    assert "const supported = names.length >= 2;" in js
    assert 'pearsonSection.hidden = !supported;' in js
    assert 'fallback.hidden = supported;' in js
    assert 'Use Smart comparisons above for this dataset.' in js
    assert "if (relationships) { renderCorrelationMatrix(relationships); return; }" in js
    assert "$('analytics-pearson-section').hidden = true;" in js


def test_data_completeness_progress_tracks_present_not_missing():
    js = read('static/analytics.js')
    assert 'progress.value = Math.max(0, profile.rows - row.missing);' in js
    assert "row.missing > 0) count.classList.add('analytics-count-missing')" in js
    assert 'Exact missing counts appear beside each column' in js
    assert "$('analytics-missing-heading').textContent = 'Data completeness across columns';" in js
    assert 'renderQualityNextSteps(profile);' in js
    assert js.index('if (activeDataset === id) return;') < js.index('const thisProfile = ++profileRequest;')


def test_next_steps_navigate_without_data_mutation():
    js = read('static/analytics.js')
    assert "button.addEventListener('click', () => ui()?.navigate?.(page));" in js
    assert "'quality', 'Open Quality explorer →'" in js
    assert "'repair', 'Open Repair studio →'" in js
    assert "'rules', 'Open Rule checker →'" in js
    # Recommendation area is read-only; no extra mutation API calls added.
    assert 'api/datasets' not in js[js.index('function renderQualityNextSteps('):js.index('function detailButton(')]


def test_report_omits_ineligible_pearson_section_but_keeps_numeric_reports():
    js = read('static/analytics.js')
    assert 'const correlationSection = relation.columns.length > 1' in js
    assert '${correlationSection}<p class="muted">Generated locally by DataMendry.' in js
    assert 'Bars show present values, not missing values.' in js
    assert 'function reportEsc(value)' in js


def test_existing_analytics_and_relationship_endpoints_remain_supported(tmp_path):
    app = create_app(Settings(data_dir=tmp_path / 'data', demo_only=False))
    with TestClient(app) as client:
        assert client.get('/static/analytics.js').status_code == 200
        assert client.get('/static/experience.css').status_code == 200
        first = client.post('/api/datasets', files={'file': ('people.csv', b'Index,Name,Team\n1,Alice,East\n2,Bob,West\n3,,West\n', 'text/csv')})
        assert first.status_code == 201
        first_id = first.json()['dataset_id']
        profile = client.get(f'/api/datasets/{first_id}/profile').json()
        assert profile['rows'] == 3
        assert profile['missing_cells'] == 1
        assert client.get(f'/api/datasets/{first_id}/relationships').json()['columns'] == ['Index']
        smart = client.get(f'/api/datasets/{first_id}/smart/overview')
        assert smart.status_code == 200
        second = client.post('/api/datasets', files={'file': ('scores.csv', b'IQ,CGPA\n110,7\n120,8\n130,9\n', 'text/csv')})
        assert second.status_code == 201
        second_id = second.json()['dataset_id']
        corr = client.get(f'/api/datasets/{second_id}/relationships')
        assert corr.status_code == 200
        assert set(corr.json()['columns']) == {'IQ', 'CGPA'}
