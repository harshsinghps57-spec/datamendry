"""Public privacy policy checks for DataMendry."""
from pathlib import Path
from fastapi.testclient import TestClient
from datamendry.api import app

ROOT = Path(__file__).resolve().parents[1]


def test_privacy_link_visible_on_homepage():
    page = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
    assert '<a href="/privacy">Privacy Policy</a>' in page


def test_privacy_page_public_and_discloses_core_services():
    with TestClient(app) as client:
        result = client.get("/privacy")
        assert result.status_code == 200
        for term in ("Google", "Supabase", "CSV", "delete", "Cloudflare", "Render"):
            assert term.lower() in result.text.lower()
        css = client.get("/static/privacy.css")
        assert css.status_code == 200
