# DataMendry v0.3 security update — instructions

## What changed

- **Safe by default:** public demo uses sample datasets only and rejects arbitrary uploaded files.
- Server-side request-size checks (including streamed requests without Content-Length), bounded concurrent operations, capped active datasets, demo creation limits and periodic expiry cleanup.
- UTF-8 CSV validation plus row, processing-time and disk-backed SQLite page limits.
- Spreadsheet-oriented formula-safe quoted CSV exports, with a documented data-preservation tradeoff.
- CSP retained for the working Cloudflare Analytics installation, plus cross-site request origin checks.
- Updated JavaScript UI switches between public sample-only mode and trusted-laptop mode using `/api/config`.
- New security regression tests, guidance and a scheduled dependency-audit workflow.

**Important:** This is a hardened public *demo*, not a security-certified platform for confidential records. Public user uploads are intentionally disabled until real accounts, isolated storage and external security review are ready.

## Apply to your existing project (Windows / VS Code)

1. **Back up** your current `DataMendry_Animated_v0.2.1` folder. Your real project is inside `DataMendry_v0.2.1_Animated_Full_Project/DataMendry_Animated_v0.2.1`.
2. Extract `DataMendry_v0.3_Security_Update.zip` and open its `DataMendry_v0.3_Update` folder.
3. Copy these files into the *matching paths* in your existing INNER project folder, approving replacements:
   - `datamendry/api.py`
   - `datamendry/engine.py`
   - `static/app.js`
   - `tests/test_engine.py`
   - `tests/test_security.py` (new)
   - `render.yaml`
   - `SECURITY.md`
   - `.github/workflows/dependency-audit.yml` (new)
4. **Do not replace `static/index.html` or your `README.md`**: these contain the Cloudflare tracking snippet and live-demo links you already added on GitHub.
5. In VS Code, open a terminal in the INNER project folder, then run:

   ```powershell
   ..\.venv\Scripts\python.exe -m pytest -q
   git diff --check
   git status --short
   ```

   Expect **22 tests passing** when run against the update as packaged; the exact number can change as you add tests. Stop if tests fail.
6. Verify localhost in safe demo mode (optional, start it after stopping any old Uvicorn instance):

   ```powershell
   $env:DATAMENDRY_DEMO_ONLY = '1'
   ..\.venv\Scripts\python.exe -m uvicorn datamendry.api:app --reload
   ```

   Open `http://127.0.0.1:8000`, click **Try sample dataset**, test the features. Your own-file upload control should be hidden, and POST `/api/datasets` should return 403.
7. To test private CSV uploads on your OWN laptop, stop Uvicorn, run `$env:DATAMENDRY_DEMO_ONLY = '0'`, then start it again. **Never set the public Render service to 0.**
8. When tests pass, commit and push from the INNER project directory:

   ```powershell
   git add datamendry/api.py datamendry/engine.py static/app.js tests/test_engine.py tests/test_security.py render.yaml SECURITY.md .github/workflows/dependency-audit.yml
   git commit -m "Security hardening: sample-only public beta and resource limits"
   git push origin main
   ```
9. In Render, open `datamendry-demo` and manually deploy the latest commit if auto-deploy is still disabled. **Additionally sync the Blueprint `Datamendry-blueprint` so the `render.yaml` environment values are applied.** Verify the service has `DATAMENDRY_DEMO_ONLY=1` in its Environment settings. Since the server defaults to demo-only, a delayed Blueprint sync does not enable real uploads.
10. Check `https://datamendry-demo.onrender.com/api/config` — the result should include `"demo_only": true`. Test the sample button and other features. Check the latest GitHub Actions **Tests** and **Dependency audit** jobs. Keep Cloudflare Analytics in place.

## Limitations and next phases

The hosted demo does not accept visitors' own CSV files. To support this responsibly, the next architecture milestone is authenticated workspaces and privately controlled object storage, followed by a separate worker queue and load/security testing. A free Render instance is not a production large-data platform.
