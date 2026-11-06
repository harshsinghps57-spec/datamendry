"""M9: chart legend and reusable workflow recipe non-regression."""
from pathlib import Path

from fastapi.testclient import TestClient
from datamendry.api import Settings, create_app

ROOT = Path(__file__).resolve().parents[1]

def source(path):
    return (ROOT / path).read_text(encoding='utf-8')


def test_category_stacks_reuse_exact_legend_palette():
    js = source('static/smart_analytics.js')
    assert "const CATEGORY_COLORS = ['#50dcc2', '#38bdf8', '#fbbf24', '#c4b5fd', '#fb7185'];" in js
    assert "panel.append(colorLegend(payload.categories));" in js
    assert "segment.style.backgroundColor = categoryColor(i);" in js
    assert "swatch.style.backgroundColor = categoryColor(index);" in js
    assert "segment.setAttribute('aria-label'" in js
    assert "list.setAttribute('aria-label', 'Chart color legend')" in js


def test_numeric_plots_have_plain_language_scale_legend():
    js = source('static/smart_analytics.js')
    assert "Darker teal indicates a larger count" in js
    assert "Teal bar length represents the mean" in js
    assert "Teal bar length represents the monthly mean" in js


def test_css_has_responsive_legend_and_styled_recipe_button():
    css = source('static/experience.css')
    for selector in ['.analytics-smart-legend', '.analytics-smart-legend-item', '.analytics-smart-swatch',
                     '.analytics-smart-gradient-legend', '.assistant-recipe-import:focus-visible']:
        assert selector in css
    assert 'max-width:500px' in css


def test_recipe_ui_preserves_existing_assistant_controls():
    html = source('static/index.html')
    for selector in ['assistant-toggle', 'assistant-expand', 'assistant-messages', 'assistant-form',
                     'assistant-recipe-file', 'assistant-recipe-import']:
        assert f'id="{selector}"' in html
    assert 'accept=".json,application/json"' in html


def test_recipe_import_checks_schema_header_match_and_size():
    js = source('static/experience.js')
    for check in ["raw.type !== 'datamendry-cleaning-recipe'", 'raw.version !== 1',
                  'raw.columns.some((name,i) => name !== current[i])',
                  'file.size > 32768', "'filter','exclude_column'", 'RECIPE_FILTERS.has(kind)',
                  'value.length > 500', 'Imported cleaning recipe. Review all steps',
                  "saveBtn.textContent = 'Save recipe ↓'", "link.download='datamendry-cleaning-recipe.json'"]:
        assert check in js


def test_recipe_import_does_not_export_or_auto_preview():
    js = source('static/experience.js')
    piece = js[js.index("$('assistant-recipe-file').addEventListener"): js.index('function offerWorkflowProposal(proposal)')]
    assert 'offerWorkflowProposal(' in piece
    assert '/workflows/preview' not in piece
    assert '/workflows/export' not in piece


def test_existing_smart_and_workflow_endpoints_still_work(tmp_path):
    app = create_app(Settings(data_dir=tmp_path/'data',demo_only=False))
    with TestClient(app) as client:
        assert client.get('/static/smart_analytics.js').status_code == 200
        assert client.get('/static/experience.js').status_code == 200
        result = client.post('/api/datasets',files={'file':('test.csv',b'Date,Sex,Score\n2024-01-01,F,1\n2024-02-01,M,2\n2024-03-01,F,3\n','text/csv')})
        assert result.status_code == 201
        ds=result.json()['dataset_id']
        assert client.get(f'/api/datasets/{ds}/smart/overview').status_code == 200
        assert client.get(f'/api/datasets/{ds}/smart/pair?x=Sex&y=Date').json()['mode'] == 'date_category'
        steps=[{'action':'trim_whitespace','column':'','kind':'all','value':''},{'action':'deduplicate','column':'','kind':'all','value':''}]
        preview=client.post(f'/api/datasets/{ds}/workflows/preview',json={'steps':steps})
        assert preview.status_code == 200
        assert preview.json()['matching_rows']==3
        assert client.get(f'/api/datasets/{ds}/profile').json()['rows']==3
