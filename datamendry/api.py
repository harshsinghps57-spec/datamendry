"""FastAPI application factory with short-lived browser-scoped guest datasets.
Not a replacement for authenticated accounts, durable storage, or security review.
"""
from __future__ import annotations

import hashlib
import hmac
import base64
import asyncio
import json
import os
import re
import secrets
import shutil
import time
import threading
from contextlib import asynccontextmanager, contextmanager, suppress
from collections import deque
from typing import BinaryIO
from urllib.parse import urlsplit
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field
from starlette.responses import PlainTextResponse

from datamendry.engine import DatasetError, RepairOptions, export_csv_chunks, fetch_preview, import_csv, make_connection, simulate

PROJECT_DIR = Path(__file__).resolve().parent.parent
DATASET_ID_PATTERN = re.compile(r"^[a-f0-9]{32}$")
GUEST_TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9_-]{43}\.[A-Za-z0-9_-]{43}$")


def guest_fingerprint(token: str) -> str:
    """Hash browser bearer secret before recording ownership on disk."""
    return hashlib.sha256(("datamendry-guest-owner:v1:" + token).encode("ascii")).hexdigest()



@dataclass
class Settings:
    data_dir: Path
    max_upload_bytes: int = 200 * 1024 * 1024
    ttl_hours: int = 24
    demo_only: bool = False
    max_rows: int = 2_000_000
    max_import_seconds: int = 120
    max_db_bytes: int = 256 * 1024 * 1024
    max_active_datasets: int = 40
    max_parallel_jobs: int = 3
    demo_creates_per_minute: int = 20
    max_datasets_per_guest: int = 3
    upload_creates_per_minute: int = 8
    secure_cookie: bool = False


class Recipe(BaseModel):
    trim_whitespace: bool = False
    normalize_blanks: bool = False
    remove_exact_duplicates: bool = False

    def to_options(self) -> RepairOptions:
        return RepairOptions(**self.model_dump())


class Rule(BaseModel):
    column: str = Field(min_length=1, max_length=200)
    kind: Literal["not_empty", "unique", "numeric", "minimum", "maximum"]
    threshold: float | None = Field(default=None, allow_inf_nan=False)


class RulesRequest(BaseModel):
    rules: list[Rule] = Field(min_length=1, max_length=20)


class RequestBodyLimit:
    """ASGI-level body limit, including requests without Content-Length.

    Rejects anonymous uploads *before* Starlette parses multipart in demo mode.
    Does not trust client-provided forwarded headers.
    """
    def __init__(self, app, *, config: Settings):
        self.app = app
        self.config = config

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        path = scope.get("path", "")
        method = scope.get("method", "")
        if self.config.demo_only and method == "POST" and path.rstrip("/") == "/api/datasets":
            await PlainTextResponse("Public demo accepts only the built-in sample dataset", status_code=403)(scope, receive, send)
            return
        maximum = (self.config.max_upload_bytes + 128 * 1024) if method == "POST" and path.rstrip("/") == "/api/datasets" else 64 * 1024
        if method not in {"POST", "PUT", "PATCH"}:
            await self.app(scope, receive, send)
            return
        headers = dict(scope.get("headers", []))
        # Browser-origin protection for state-changing requests; not an identity
        # or anti-bot mechanism. Clients can forge headers, so resource quotas
        # and demo-only mode remain the primary public controls.
        host = headers.get(b"host", b"").decode("latin-1").lower()
        origin = headers.get(b"origin", b"").decode("latin-1").lower()
        fetch_site = headers.get(b"sec-fetch-site", b"").decode("latin-1").lower()
        if fetch_site == "cross-site" or (origin and urlsplit(origin).netloc != host):
            await PlainTextResponse("Cross-site requests are not allowed", status_code=403)(scope, receive, send)
            return
        raw = headers.get(b"content-length", b"")
        try:
            if raw and int(raw) > maximum:
                await PlainTextResponse("Request too large", status_code=413)(scope, receive, send)
                return
        except ValueError:
            await PlainTextResponse("Invalid Content-Length", status_code=400)(scope, receive, send)
            return
        received = 0
        response_started = False

        async def limited_receive():
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > maximum:
                    raise BodyTooLarge()
            return message

        async def track_send(message):
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, limited_receive, track_send)
        except BodyTooLarge:
            if not response_started:
                await PlainTextResponse("Request too large", status_code=413)(scope, receive, send)


class BodyTooLarge(Exception):
    pass


def create_app(settings: Settings | None = None) -> FastAPI:
    config = settings or Settings(
        data_dir=Path(os.getenv("DATAMENDRY_DATA_DIR", str(PROJECT_DIR / "data"))),
        max_upload_bytes=int(os.getenv("DATAMENDRY_MAX_UPLOAD_MB", "200")) * 1024 * 1024,
        ttl_hours=int(os.getenv("DATAMENDRY_TTL_HOURS", "24")),
        demo_only=os.getenv("DATAMENDRY_DEMO_ONLY", "1").strip().lower() in {"1", "true", "yes"},
        max_rows=int(os.getenv("DATAMENDRY_MAX_ROWS", "2000000")),
        max_db_bytes=int(os.getenv("DATAMENDRY_MAX_DB_MB", "256")) * 1024 * 1024,
        max_active_datasets=int(os.getenv("DATAMENDRY_MAX_DATASETS", "40")),
        max_datasets_per_guest=int(os.getenv("DATAMENDRY_MAX_PER_GUEST", "3")),
        upload_creates_per_minute=int(os.getenv("DATAMENDRY_UPLOADS_PER_MINUTE", "8")),
        secure_cookie=os.getenv("DATAMENDRY_SECURE_COOKIE", "0").strip().lower() in {"1", "true", "yes"},
    )
    if (config.max_upload_bytes <= 0 or config.max_rows <= 0 or config.max_parallel_jobs <= 0
            or config.ttl_hours <= 0 or config.max_datasets_per_guest <= 0
            or config.upload_creates_per_minute <= 0):
        raise ValueError("Invalid resource limits")
    config.data_dir.mkdir(mode=0o700, parents=True, exist_ok=True)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        await asyncio.to_thread(remove_expired)
        async def periodic_cleanup():
            while True:
                await asyncio.sleep(180)
                await asyncio.to_thread(remove_expired)
        task = asyncio.create_task(periodic_cleanup())
        try:
            yield
        finally:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task

    app = FastAPI(title="DataMendry API", version="0.4.0", docs_url="/api/docs", redoc_url=None, lifespan=lifespan)
    app.add_middleware(RequestBodyLimit, config=config)
    jobs = threading.BoundedSemaphore(config.max_parallel_jobs)
    workspace_lock = threading.Lock()
    demo_log: deque[float] = deque()
    upload_log: deque[float] = deque()
    # __Host- cookies reject Domain attributes and must be Secure and Path=/.
    cookie_name = "__Host-datamendry_guest" if config.secure_cookie else "datamendry_guest_local"
    # A per-process signing key prevents accepting client-invented session IDs.
    # On free Render, process restarts also clear temporary uploaded datasets.
    session_signing_key = secrets.token_bytes(32)

    def sign_session(token: str) -> str:
        signature = hmac.new(session_signing_key, token.encode("ascii"), hashlib.sha256).digest()
        return base64.urlsafe_b64encode(signature).decode("ascii").rstrip("=")

    def validate_guest_cookie(cookie: str) -> str | None:
        if not GUEST_TOKEN_PATTERN.fullmatch(cookie):
            return None
        token, signature = cookie.split(".", 1)
        if not hmac.compare_digest(signature, sign_session(token)):
            return None
        return token

    def session_owner(request: Request) -> str:
        token = getattr(request.state, "guest_token", None)
        if not token:
            raise HTTPException(404, "Dataset not found")
        return guest_fingerprint(token)


    @contextmanager
    def job_slot():
        if not jobs.acquire(blocking=False):
            raise HTTPException(429, "Server is busy; try again later")
        try:
            yield
        finally:
            jobs.release()

    @app.middleware("http")
    async def add_security_headers(request: Request, call_next):
        # A random HttpOnly, host-only session cookie scopes every dataset
        # operation to the browser that created it. Never exposed to JS.
        token = validate_guest_cookie(request.cookies.get(cookie_name, ""))
        new_cookie = token is None
        if new_cookie:
            token = secrets.token_urlsafe(32)
        request.state.guest_token = token
        response = await call_next(request)
        if new_cookie:
            response.set_cookie(
                key=cookie_name, value=f"{token}.{sign_session(token)}", path="/", httponly=True,
                secure=config.secure_cookie, samesite="lax",
                max_age=config.ttl_hours * 3600,
            )
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' https://static.cloudflareinsights.com/beacon.min.js; "
            "style-src 'self'; "
            "img-src 'self' data:; "
            "connect-src 'self' https://cloudflareinsights.com; "
            "form-action 'self'; base-uri 'none'; object-src 'none'; frame-ancestors 'none'"
        )
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
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
        return {"status": "ok", "version": "0.4.0"}

    @app.get("/api/config")
    def public_config():
        return {"demo_only": config.demo_only,
                "private_guest_workspace": True,
                "max_upload_mb": config.max_upload_bytes // (1024 * 1024),
                "ttl_hours": config.ttl_hours}

    def dataset_path(dataset_id: str, request: Request) -> Path:
        if not DATASET_ID_PATTERN.fullmatch(dataset_id):
            raise HTTPException(404, "Dataset not found")
        workspace = config.data_dir / dataset_id
        if not workspace.is_dir():
            raise HTTPException(404, "Dataset not found")
        # Check authorization on *every* endpoint, including export/delete.
        try:
            meta = json.loads((workspace / "metadata.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            raise HTTPException(404, "Dataset not found") from None
        owner = meta.get("guest_owner", "")
        if not isinstance(owner, str) or not secrets.compare_digest(owner, session_owner(request)):
            # Do not reveal that another guest's dataset exists.
            raise HTTPException(404, "Dataset not found")
        return workspace

    def get_dataset(dataset_id: str, request: Request) -> tuple[Path, dict]:
        workspace = dataset_path(dataset_id, request)
        meta = json.loads((workspace / "metadata.json").read_text(encoding="utf-8"))
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

    def create_workspace(owner: str) -> tuple[str, Path]:
        # Bound number of active workspaces under concurrent requests.
        remove_expired()
        with workspace_lock:
            active = sum(1 for folder in config.data_dir.iterdir()
                         if folder.is_dir() and DATASET_ID_PATTERN.fullmatch(folder.name))
            if active >= config.max_active_datasets:
                raise HTTPException(429, "Demo capacity reached; try again later")
            guest_active = 0
            for folder in config.data_dir.iterdir():
                if not folder.is_dir() or not DATASET_ID_PATTERN.fullmatch(folder.name):
                    continue
                try:
                    meta = json.loads((folder / "metadata.json").read_text(encoding="utf-8"))
                    if secrets.compare_digest(str(meta.get("guest_owner", "")), owner):
                        guest_active += 1
                except (OSError, ValueError):
                    pass
            if guest_active >= config.max_datasets_per_guest:
                raise HTTPException(429, "Guest workspace is full; delete a dataset before importing another")
            dataset_id = secrets.token_hex(16)
            workspace = config.data_dir / dataset_id
            workspace.mkdir(mode=0o700, parents=True, exist_ok=False)
        return dataset_id, workspace

    def ingest(stream: BinaryIO, filename: str, owner: str) -> dict:
        if not filename or not filename.lower().endswith(".csv") or len(filename) > 200:
            raise HTTPException(415, "Only UTF-8 CSV files are supported")
        dataset_id, workspace = create_workspace(owner)
        source = workspace / "source.upload"
        count = 0
        digest = hashlib.sha256()
        try:
            with source.open("wb") as dest:
                while chunk := stream.read(256 * 1024):
                    count += len(chunk)
                    if count > config.max_upload_bytes:
                        raise HTTPException(413, "Upload size limit exceeded")
                    if b"\x00" in chunk:
                        raise HTTPException(422, "Binary files are not supported")
                    digest.update(chunk)
                    dest.write(chunk)
            if not count:
                raise HTTPException(422, "The uploaded file is empty")
            summary = import_csv(source, workspace / "dataset.sqlite",
                                 max_rows=config.max_rows,
                                 max_seconds=config.max_import_seconds,
                                 max_db_bytes=config.max_db_bytes)
            created = time.time()
            summary.update({
                "dataset_id": dataset_id, "filename": Path(filename.replace("\\", "/")).name[:120],
                "bytes_uploaded": count, "created_at": created,
                "expires_at": created + config.ttl_hours * 3600,
                "source_sha256": digest.hexdigest(),
                "guest_owner": owner,
            })
            (workspace / "metadata.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
            source.unlink(missing_ok=True)
            return {"dataset_id": dataset_id, "profile": public_profile(summary)}
        except (HTTPException, DatasetError) as error:
            shutil.rmtree(workspace, ignore_errors=True)
            if isinstance(error, DatasetError):
                raise HTTPException(422, str(error)) from error
            raise
        except Exception:
            shutil.rmtree(workspace, ignore_errors=True)
            raise

    @app.post("/api/datasets", status_code=201)
    def upload_dataset(request: Request, file: UploadFile = File(...)):
        if config.demo_only:
            raise HTTPException(403, "Public demo accepts only the built-in sample dataset")
        with job_slot():
            with workspace_lock:
                now = time.monotonic()
                while upload_log and now - upload_log[0] > 60:
                    upload_log.popleft()
                if len(upload_log) >= config.upload_creates_per_minute:
                    raise HTTPException(429, "Too many uploads; try again later")
                upload_log.append(now)
            try:
                return ingest(file.file, file.filename or "", session_owner(request))
            finally:
                file.file.close()

    @app.post("/api/datasets/demo", status_code=201)
    def create_demo(request: Request):
        with job_slot():
            now = time.monotonic()
            with workspace_lock:
                while demo_log and now - demo_log[0] > 60:
                    demo_log.popleft()
                if len(demo_log) >= config.demo_creates_per_minute:
                    raise HTTPException(429, "Too many demo requests; try again later")
                demo_log.append(now)
            with (PROJECT_DIR / "examples" / "sample_sales.csv").open("rb") as stream:
                return ingest(stream, "sample-sales.csv", session_owner(request))

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
    def profile(dataset_id: str, request: Request):
        _, meta = get_dataset(dataset_id, request)
        return public_profile(meta)

    @app.get("/api/datasets/{dataset_id}/preview")
    def preview(dataset_id: str, request: Request, limit: int = Query(default=20, ge=1, le=100), offset: int = Query(default=0, ge=0)):
        db, meta = get_dataset(dataset_id, request)
        return fetch_preview(db, meta["columns"], limit=limit, offset=offset)

    @app.post("/api/datasets/{dataset_id}/simulate")
    def run_simulation(dataset_id: str, recipe: Recipe, request: Request):
        with job_slot():
            db, meta = get_dataset(dataset_id, request)
            return simulate(db, meta, recipe.to_options())

    @app.get("/api/datasets/{dataset_id}/export.csv")
    def download(dataset_id: str, request: Request, trim_whitespace: bool = False,
                 normalize_blanks: bool = False, remove_exact_duplicates: bool = False):
        db, meta = get_dataset(dataset_id, request)
        options = RepairOptions(trim_whitespace, normalize_blanks, remove_exact_duplicates)
        if not jobs.acquire(blocking=False):
            raise HTTPException(429, "Server is busy; try again later")

        def limited_export():
            try:
                yield from export_csv_chunks(db, meta["columns"], options)
            finally:
                jobs.release()

        return StreamingResponse(limited_export(), media_type="text/csv; charset=utf-8",
                                 headers={"Content-Disposition": 'attachment; filename="datamendry-cleaned.csv"',
                                          "X-Content-Type-Options": "nosniff"})

    @app.post("/api/datasets/{dataset_id}/rules")
    def evaluate_rules(dataset_id: str, request: RulesRequest, browser: Request):
        with job_slot():
            return _evaluate_rules(dataset_id, request, browser)

    def _evaluate_rules(dataset_id: str, rules: RulesRequest, browser: Request):
        db, meta = get_dataset(dataset_id, browser)
        columns = meta["columns"]
        results = []
        con = make_connection(db)
        try:
            for rule in rules.rules:
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
    def delete_dataset(dataset_id: str, request: Request):
        with job_slot():
            path = dataset_path(dataset_id, request)
            shutil.rmtree(path)
            return {"deleted": True}

    return app


app = create_app()
