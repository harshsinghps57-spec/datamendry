"""Regression: the dashboard script must be served from the explicit static allowlist."""
from pathlib import Path
from fastapi.testclient import TestClient
from datamendry.api import Settings, create_app


def test_analytics_asset_is_served_and_does_not_expand_static_allowlist(tmp_path: Path):
    app = create_app(Settings(data_dir=tmp_path / "datasets"))
    with TestClient(app) as client:
        page = client.get("/")
        assert page.status_code == 200
        assert 'src="/static/analytics.js"' in page.text
        script = client.get("/static/analytics.js")
        assert script.status_code == 200, script.text
        assert "javascript" in script.headers.get("content-type", "").lower()
        assert "datamendry:page" in script.text
        assert "datamendry:dataset" in script.text
        assert client.get("/static/not-listed.js").status_code == 404
