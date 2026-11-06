"""Check the opt-in account integration and never-regress upload controls."""
from pathlib import Path
from fastapi.testclient import TestClient
from datamendry.api import create_app, Settings
ROOT = Path(__file__).resolve().parents[1]


def test_account_disabled_by_default(tmp_path, monkeypatch):
    monkeypatch.delenv("DATAMENDRY_SUPABASE_URL", raising=False)
    monkeypatch.delenv("DATAMENDRY_SUPABASE_PUBLISHABLE_KEY", raising=False)
    with TestClient(create_app(Settings(data_dir=tmp_path / "d"))) as c:
        response = c.get("/api/account-config")
        assert response.status_code == 200
        assert response.json()["enabled"] is False
        assert response.json()["publishable_key"] == ""


def test_account_public_config_with_url_only(tmp_path, monkeypatch):
    monkeypatch.setenv("DATAMENDRY_SUPABASE_URL", "https://myproject.supabase.co")
    monkeypatch.setenv("DATAMENDRY_SUPABASE_PUBLISHABLE_KEY", "sb_publishable_test")
    with TestClient(create_app(Settings(data_dir=tmp_path / "d"))) as c:
        config = c.get("/api/account-config").json()
        assert config["enabled"] is True
        assert config["bucket"] == "datamendry-files"
        assert config["url"] == "https://myproject.supabase.co"
        assert c.get("/static/account.js").status_code == 200
        assert "script-src 'self'" in c.get("/").headers["content-security-policy"]


def test_malicious_url_rejected(tmp_path, monkeypatch):
    monkeypatch.setenv("DATAMENDRY_SUPABASE_URL", "https://myproject.supabase.co.evil.test")
    monkeypatch.setenv("DATAMENDRY_SUPABASE_PUBLISHABLE_KEY", "sb_publishable_test")
    with TestClient(create_app(Settings(data_dir=tmp_path / "d"))) as c:
        assert c.get("/api/account-config").json()["enabled"] is False


def test_upload_still_enabled_and_auth_panel_optional(tmp_path):
    with TestClient(create_app(Settings(data_dir=tmp_path / "d", demo_only=False))) as c:
        assert c.get("/api/config").json()["demo_only"] is False
        page = c.get("/").text
        assert 'for="file-input"' in page
        assert 'id="account-panel"' in page
        assert 'src="/static/account.js"' in page
        resp = c.post("/api/datasets", files={"file": ("test.csv", b"name,score\nana,5\n", "text/csv")})
        assert resp.status_code == 201


def test_private_bucket_policy_is_present():
    sql = (ROOT / "SUPABASE_SETUP_v0.6.sql").read_text()
    assert "TO authenticated" in sql
    assert sql.count("storage.foldername(name)") == 3
    assert "FOR SELECT" in sql and "FOR INSERT" in sql and "FOR DELETE" in sql
    assert "TO public" not in sql.lower()


def test_live_config_keeps_upload_enabled():
    render = (ROOT / "render.yaml").read_text()
    assert 'key: DATAMENDRY_DEMO_ONLY\n        value: "0"' in render
