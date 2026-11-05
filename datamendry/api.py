"""FastAPI application factory. Anonymous, short-lived datasets are deliberately
isolated by a cryptographically random bearer dataset ID, not a guessable number.
Not a replacement for authenticated multi-tenant production infrastructure.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, File, HTTPException, Path as ApiPath, Query, UploadFile
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from datamendry.engine import DatasetError, RepairOptions, export_csv_chunks, fetch_preview, import_csv, make_connection, simulate

PROJECT_DIR = Path(__file__).resolve().parent.parent
DATASET_ID_PATTERN = re.compile(r"^[a-f0-9]{32}$")


@dataclass
class Settings:
    data_dir: Path
    max_upload_bytes: int = 200 * 1024 * 1024
    ttl_hours: int = 24


class Recipe(BaseModel):
    trim_whitespace: bool = False
    normalize_blanks: bool = False
    remove_exact_duplicates: bool = False

    def to_options(self) -> RepairOptions:
        return RepairOptions(**self.model_dump())


class Rule(BaseModel):
    column: str = Field(min_length=1)
    kind: Literal["not_empty", "unique", "numeric", "minimum", "maximum"]
    threshold: float | None = None


class RulesRequest(BaseModel):
    rules: list[Rule] = Field(min_length=1, max_length=20)


def create_app(settings: Settings | None = None) -> FastAPI:
    config = settings or Settings(
        data_dir=Path(os.getenv("DATAMENDRY_DATA_DIR", str(PROJECT_DIR / "data"))),
        max_upload_bytes=int(os.getenv("DATAMENDRY_MAX_UPLOAD_MB", "200")) * 1024 * 1024,
        ttl_hours=int(os.getenv("DATAMENDRY_TTL_HOURS", "24")),
    )
    config.data_dir.mkdir(parents=True, exist_ok=True)
    app = FastAPI(title="DataMendry API", version="0.2.0", docs_url="/api/docs", redoc_url=None)

    @app.middleware("http")
    async def add_security_headers(request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Content-Security-Policy"] = (
    "default-src 'self'; "
    "script-src 'self' https://static.cloudflareinsights.com/beacon.min.js; "
    "style-src 'self'; "
    "img-src 'self' data:; "
    "connect-src 'self' https://cloudflareinsights.com; "
    "form-action 'self'; "
    "base-uri 'none'"
)
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/")
    def index():
        return FileResponse(PROJECT_DIR / "static" / "index.html")

    @app.get("/static/{filename}")
    def asset(filename: str):
        if filename not in {"app.js", "app.css"}:
            raise HTTPException(404, "Asset not found")
        return FileResponse(PROJECT_DIR / "static" / filename)

    @app.get("/api/demo.csv")
    def demo_csv():
        return FileResponse(PROJECT_DIR / "examples" / "sample_sales.csv", media_type="text/csv")

    @app.get("/api/health")
    def health():
        return {"status": "ok", "version": "0.2.0"}

    def dataset_path(dataset_id: str) -> Path:
        if not DATASET_ID_PATTERN.fullmatch(dataset_id):
            raise HTTPException(404, "Dataset not found")
        workspace = config.data_dir / dataset_id
        if not workspace.is_dir():
            raise HTTPException(404, "Dataset not found or expired")
        return workspace

    def get_dataset(dataset_id: str) -> tuple[Path, dict]:
        workspace = dataset_path(dataset_id)
        meta_file = workspace / "metadata.json"
        if not meta_file.exists():
            raise HTTPException(404, "Dataset not found or expired")
        meta = json.loads(meta_file.read_text(encoding="utf-8"))
        if time.time() - meta["created_at"] > config.ttl_hours * 3600:
            shutil.rmtree(workspace, ignore_errors=True)
            raise HTTPException(410, "Dataset expired; please upload again")
        return workspace / "dataset.sqlite", meta

    def remove_expired() -> None:
        # Invoked before new upload. For high traffic use a scheduled cleanup worker.
        now = time.time()
        for folder in config.data_dir.iterdir():
            if not folder.is_dir() or not DATASET_ID_PATTERN.fullmatch(folder.name):
                continue
            try:
                meta = json.loads((folder / "metadata.json").read_text(encoding="utf-8"))
                expired = now - meta["created_at"] > config.ttl_hours * 3600
            except (OSError, KeyError, ValueError):
                expired = now - folder.stat().st_mtime > config.ttl_hours * 3600
            if expired:
                shutil.rmtree(folder, ignore_errors=True)

    @app.post("/api/datasets", status_code=201)
    def upload_dataset(file: UploadFile = File(...)):
        if not file.filename or Path(file.filename).suffix.lower() != ".csv":
            raise HTTPException(415, "This version supports UTF-8 CSV files only")
        remove_expired()
        dataset_id = secrets.token_hex(16)
        workspace = config.data_dir / dataset_id
        workspace.mkdir(mode=0o700, parents=True, exist_ok=False)
        upload_file = workspace / "source.upload"
        count = 0
        digest = hashlib.sha256()
        try:
            with upload_file.open("wb") as dest:
                while chunk := file.file.read(1024 * 1024):
                    count += len(chunk)
                    if count > config.max_upload_bytes:
                        raise HTTPException(413, f"Upload limit is {config.max_upload_bytes // (1024 * 1024)} MiB")
                    digest.update(chunk)
                    dest.write(chunk)
            if count == 0:
                raise HTTPException(422, "The uploaded file is empty")
            summary = import_csv(upload_file, workspace / "dataset.sqlite")
            summary.update({
                "dataset_id": dataset_id,
                "filename": Path(file.filename.replace("\\", "/")).name[:120],
                "bytes_uploaded": count,
                "created_at": time.time(),
                "expires_at": time.time() + config.ttl_hours * 3600,
                "source_sha256": digest.hexdigest(),
            })
            (workspace / "metadata.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
            upload_file.unlink(missing_ok=True)
            return {"dataset_id": dataset_id, "profile": public_profile(summary)}
        except HTTPException:
            shutil.rmtree(workspace, ignore_errors=True)
            raise
        except DatasetError as error:
            shutil.rmtree(workspace, ignore_errors=True)
            raise HTTPException(422, str(error)) from error
        except Exception:
            shutil.rmtree(workspace, ignore_errors=True)
            raise
        finally:
            file.file.close()

    def public_profile(meta: dict) -> dict:
        total = meta["rows"] * len(meta["columns"])
        return {
            "filename": meta["filename"], "columns": meta["columns"], "rows": meta["rows"],
            "column_count": len(meta["columns"]), "missing_cells": meta["missing_cells"],
            "missing_pct": round(meta["missing_cells"] * 100 / total, 2) if total else 0,
            "duplicate_rows": meta["duplicate_rows"],
            "column_missing": [{"name": name, "missing": count} for name, count in zip(meta["columns"], meta["missing_by_column"])],
            "source_sha256": meta["source_sha256"], "expires_at": meta["expires_at"],
        }

    @app.get("/api/datasets/{dataset_id}/profile")
    def profile(dataset_id: str):
        _, meta = get_dataset(dataset_id)
        return public_profile(meta)

    @app.get("/api/datasets/{dataset_id}/preview")
    def preview(dataset_id: str, limit: int = Query(default=20, ge=1, le=100), offset: int = Query(default=0, ge=0)):
        db, meta = get_dataset(dataset_id)
        return fetch_preview(db, meta["columns"], limit=limit, offset=offset)

    @app.post("/api/datasets/{dataset_id}/simulate")
    def run_simulation(dataset_id: str, recipe: Recipe):
        db, meta = get_dataset(dataset_id)
        return simulate(db, meta, recipe.to_options())

    @app.get("/api/datasets/{dataset_id}/export.csv")
    def download(dataset_id: str, trim_whitespace: bool = False,
                 normalize_blanks: bool = False, remove_exact_duplicates: bool = False):
        db, meta = get_dataset(dataset_id)
        options = RepairOptions(trim_whitespace, normalize_blanks, remove_exact_duplicates)
        return StreamingResponse(export_csv_chunks(db, meta["columns"], options), media_type="text/csv; charset=utf-8",
                                 headers={"Content-Disposition": 'attachment; filename="datamendry-cleaned.csv"'})

    @app.post("/api/datasets/{dataset_id}/rules")
    def evaluate_rules(dataset_id: str, request: RulesRequest):
        db, meta = get_dataset(dataset_id)
        columns = meta["columns"]
        results = []
        con = make_connection(db)
        try:
            for rule in request.rules:
                if rule.column not in columns:
                    raise HTTPException(422, f"Unknown column: {rule.column}")
                if rule.kind in {"minimum", "maximum"} and rule.threshold is None:
                    raise HTTPException(422, "Minimum and maximum rules need a threshold")
                col = f"c{columns.index(rule.column)}"  # trusted index, never user-supplied SQL
                if rule.kind == "not_empty":
                    violations = con.execute(f"SELECT COUNT(*) FROM records WHERE TRIM({col}) = ''").fetchone()[0]
                elif rule.kind == "unique":
                    # NULL-like empty strings count as duplicates if repeated.
                    violations = con.execute(f"SELECT COALESCE(SUM(n - 1), 0) FROM (SELECT COUNT(*) AS n FROM records GROUP BY {col} HAVING n > 1)").fetchone()[0]
                else:
                    # Strict decimal parsing: SQLite CAST alone accepts partial numeric strings.
                    # Stream rows from SQLite cursor, keeping memory bounded.
                    from decimal import Decimal, InvalidOperation
                    violations = 0
                    for (value,) in con.execute(f"SELECT {col} FROM records"):
                        try:
                            if not value.strip():
                                raise InvalidOperation
                            number = Decimal(value.strip())
                            if not number.is_finite():
                                raise InvalidOperation
                            if rule.kind == "minimum" and number < Decimal(str(rule.threshold)):
                                violations += 1
                            if rule.kind == "maximum" and number > Decimal(str(rule.threshold)):
                                violations += 1
                        except (InvalidOperation, ValueError):
                            violations += 1
                results.append({"column": rule.column, "kind": rule.kind,
                                "threshold": rule.threshold, "violations": violations,
                                "passed": violations == 0})
            return {"source_sha256": meta["source_sha256"], "results": results}
        finally:
            con.close()

    @app.delete("/api/datasets/{dataset_id}")
    def delete_dataset(dataset_id: str):
        path = dataset_path(dataset_id)
        shutil.rmtree(path)
        return {"deleted": True}

    return app


app = create_app()
