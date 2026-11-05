"""Browser UI asset regression guards (not a substitute for visual QA)."""
from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from datamendry.api import Settings, create_app


def test_animation_assets_and_reduced_motion(tmp_path: Path):
    with TestClient(create_app(Settings(data_dir=tmp_path / "uploads"))) as client:
        homepage = client.get("/")
        assert homepage.status_code == 200
        assert 'aria-label="DataMendry home"' in homepage.text
        assert "trace<span" not in homepage.text
        assert 'rel="icon"' in homepage.text

        css = client.get("/static/app.css")
        assert css.status_code == 200
        assert "@media (prefers-reduced-motion: reduce)" in css.text
        assert "dm-fade-up" in css.text
        assert "dm-bar-reveal" in css.text

        js = client.get("/static/app.js")
        assert js.status_code == 200
        assert "prefersReducedMotion.matches" in js.text
        assert "scrollBehavior()" in js.text
