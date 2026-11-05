# DataMendry — Data Repair Workspace

[![CI](https://img.shields.io/badge/CI-GitHub_Actions-blue)](.github/workflows/tests.yml) ![Python](https://img.shields.io/badge/Python-3.11%2B-blue) ![License](https://img.shields.io/badge/License-MIT-green) ![Stage](https://img.shields.io/badge/Status-public_preview-orange)

> **Working name**: DataMendry. We renamed the earlier TraceTidy prototype because that name is already used by a different public project. This is not a trademark or domain availability clearance.

**Understand messy CSV data, simulate the impact of fixes, validate rules, and export cleaned datasets with a reproducible audit record.**

Designed for analysts, students, researchers, and small businesses who want explainable, **non-destructive** data cleaning rather than silent auto-fixes.

### Key features available in v0.2 (UI polish in v0.2.1)

- **FastAPI web application** with a responsive dashboard and live sample dataset
- **Lightweight UI animations (v0.2.1)**: staggered page entrance, navigation micro-interactions, upload drag feedback, subtle card hover, and one-time chart reveals; respects `prefers-reduced-motion`
- **Streaming UTF-8 CSV ingest** with disk-backed SQLite rather than a full-data browser or pandas import
- **Exact dataset quality metrics**: rows, columns, missing cells, exact duplicate rows, per-column missing counts
- **Paginated browser preview** (25 rows at a time) with original strings preserved (e.g. `0012` stays `0012`)
- **Repair impact simulator**: preview rows removed, changed values in retained rows, and remaining blanks before exporting
- **Deterministic cleaning recipe**: trim boundary whitespace, normalize blanks, and remove exact duplicates
- **On-demand validation rules**: non-empty, uniqueness, numeric, min, max
- **Streaming cleaned CSV export**, JSON audit from the browser with source SHA-256 fingerprint and the selected recipe
- **Safer CSV export**: formula-like cells are prefixed with a quote to reduce spreadsheet formula injection risk
- **User-managed deletion** and automatic expiry checks (default 24 h) for uploads
- **Automated tests, GitHub Actions, Dockerfile, dependency policies, example data**

**What is different?** DataMendry focuses on a safe *repair preview workflow*: proposed transformations are simulated and reported before you export, with data provenance. This differentiating UX is a goal, **not a claim that no competitors offer similar functionality**.

## Quick start (Windows PowerShell in VS Code)

Install Python 3.11+ and open the project folder:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m uvicorn datamendry.api:app --reload
```

Open **http://127.0.0.1:8000/** and select **Try sample dataset**. The API reference is at **http://127.0.0.1:8000/api/docs**.

Mac/Linux:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/pytest -q
.venv/bin/uvicorn datamendry.api:app --reload
```

## Architecture

```text
Browser (HTML, CSS, vanilla JavaScript)
     │ upload CSV / preview / simulation / validation / downloads
     ▼
FastAPI server ──────── temporary upload workspaces
     │                     ├── metadata.json / SHA-256
     └─ Python engine ─────└── disk-backed SQLite (row strings and indexes)
            │
            ├─ streaming CSV ingest, profiling
            ├─ deterministic simulated recipes
            ├─ rule evaluation
            └─ streaming sanitized CSV export
```

CSV imports and exports stream chunks to limit Python application memory. *This is not a promise of constant resource use overall*: SQLite uses disk, memory and CPU; exact duplicate detection requires an on-disk index. Actual maximum datasets depend on host capacity, execution timeout, disk, and load.

## Configuration

| Environment variable | Default | Purpose |
|---|---:|---|
| `DATAMENDRY_MAX_UPLOAD_MB` | `200` | Maximum uploaded file size in MiB |
| `DATAMENDRY_DATA_DIR` | `./data` | Local upload and SQLite workspace directory |
| `DATAMENDRY_TTL_HOURS` | `24` | Lazy expiration window for uploaded data |

**Do not upload private or confidential information to an unknown public instance.** Uploads are sent to the application server, not processed locally in the browser; the temporary dataset identifier serves as a bearer access token. Expiration is checked on access and the next upload, not a guaranteed background deletion schedule. Local mode is recommended until authenticated production hosting is ready.

## API

| Method | Endpoint | Purpose |
|---|---|---|
| `POST` | `/api/datasets` | Stream-upload a UTF-8 CSV |
| `GET` | `/api/datasets/{id}/profile` | Per-column and full-data report |
| `GET` | `/api/datasets/{id}/preview?limit=25&offset=0` | Read-only paginated preview |
| `POST` | `/api/datasets/{id}/simulate` | Preview cleaning recipe impact |
| `GET` | `/api/datasets/{id}/export.csv` | Stream cleaned CSV download |
| `POST` | `/api/datasets/{id}/rules` | Run validation rules |
| `DELETE` | `/api/datasets/{id}` | Delete dataset workspace |
| `GET` | `/api/health` | Health check |
| `GET` | `/api/docs` | Auto-generated OpenAPI docs |

### Example recipe

```json
{"trim_whitespace":true,"normalize_blanks":true,"remove_exact_duplicates":true}
```

## Development

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
python benchmarks/bench_csv.py --rows 100000
```

The benchmark writes synthetic data to a temporary directory, measures ingest/simulation/export time and peak Python memory; record the actual hardware and repeat under realistic loads before publishing performance claims.

## Deployment

Docker:

```bash
docker build -t datamendry:0.2 .
docker run --rm -p 8000:8000 -e DATAMENDRY_MAX_UPLOAD_MB=200 datamendry:0.2
```

This container is a **test / hobby instance**. Persistent multi-user deployment needs durable object storage, authentication and tenant isolation, rate limiting, disk quotas, reverse-proxy request limits, observability, scheduled cleanup, threat modeling, and load testing. Hosting with an ephemeral filesystem (including free Render hosting) can drop uploaded data on restart; do not market that setup as production ready. A `render.yaml` is included for an **anonymous, small-file hobby demo** (20 MiB max, one-hour lazy retention). Never upload confidential data there. See [SECURITY.md](SECURITY.md) for public deployment gaps.

## Open-source roadmap

- v0.3: dataset schema contracts, reusable versioned recipes, downloadable violations, robust CSV encoding selection, XLSX import adapters
- v0.4: background processing with progress reports and cancellation, benchmarks on 1–10 million rows, memory/disk limits, rate limiting
- v0.5: durable PostgreSQL + object storage, authentication and permissions, observability, user management
- v0.6: optional DuckDB/Parquet analytics, quality changes over time, SQL connectors
- v1.0: security review, multi-user beta, real user feedback, public hosted service with documented SLA targets

ML and LLM components can eventually explain problems and propose rule changes; they are deliberately **not** advertised as present in v0.2.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Open an issue before a large contribution; use only synthetic or approved, non-sensitive datasets for bug reports.

## License

MIT — [LICENSE](LICENSE).
