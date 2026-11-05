# DataMendry v0.4 — Private guest workspaces (first security milestone)

**What this adds**

- Each browser receives a cryptographically random, server-signed, HttpOnly, SameSite=Lax, host-only session cookie. On Render the cookie uses the `__Host-` prefix and `Secure` protection.
- Every dataset is bound to the creating browser's secret. Knowing a dataset ID is **not enough** to preview, inspect, simulate, run rules, download, or delete another browser's dataset. Unauthorized requests return HTTP 404.
- Per-browser dataset quota and global upload-create rate limiting limit misuse. Existing upload size/row/database budgets, concurrency limits, 1-hour expiry and automatic cleanup remain.
- **Public uploads stay disabled** because `render.yaml` retains `DATAMENDRY_DEMO_ONLY=1` and limits the free instance. Sample datasets still work and now use isolated guest workspaces.
- The existing Cloudflare analytics script in your `static/index.html` must **not** be replaced.

**Important limits**

This is an anonymous short-lived guest session, **not a login system**. Clearing cookies or opening another browser loses access to previous datasets; data is not portable between devices. Server restarts on Render can erase all workspaces. Cookie theft can grant access to a session. Uploading confidential, personal, regulated or sensitive data is not supported. The app is not independently security audited; it is a public hobby beta. Do not promise that no harm or compromise is possible.

## Apply to your existing Windows project

1. Back up your existing project folder `DataMendry_Animated_v0.2.1` before updating.
2. Extract `DataMendry_v0.4_Private_Workspaces_Update.zip`. Open the **inner** `DataMendry_v0.4_Update` folder.
3. Copy its content into the **inner** `DataMendry_Animated_v0.2.1` Git project folder, merging matching folders. Replace these paths only:
   - `datamendry/api.py`
   - `static/app.js`
   - `tests/test_private_workspaces.py` (new)
   - `SECURITY.md`
   - `render.yaml`
   - `PRIVATE_WORKSPACES_v0.4.md` (new)
4. **Do not replace `static/index.html`, `README.md`, `.git`, `.venv`, or your own datasets.** Your current index file retains the working Cloudflare tracker.
5. In VS Code, open a terminal **inside** `DataMendry_Animated_v0.2.1`. Run:

   ```powershell
   python -m pytest -q
   git diff --check
   git status --short
   ```

   Expected baseline is **27 passing tests** (your environment may differ); stop if tests fail.
6. Test on your laptop before any GitHub push:

   ```powershell
   $env:DATAMENDRY_DEMO_ONLY = "0"
   $env:DATAMENDRY_SECURE_COOKIE = "0"
   python -m uvicorn datamendry.api:app --reload --host 127.0.0.1 --port 8001
   ```

   Open `http://127.0.0.1:8001/`. Test a **small non-sensitive** CSV, then use another browser or Edge InPrivate window and verify that the dataset URL is NOT accessible. The second browser should receive `404` when requesting the first browser's `/api/datasets/<id>/profile`.
7. **After** local tests pass, commit and push the six update paths:

   ```powershell
   git add datamendry/api.py static/app.js tests/test_private_workspaces.py render.yaml SECURITY.md PRIVATE_WORKSPACES_v0.4.md
   git diff --cached --check
   git commit -m "DataMendry v0.4: private guest workspace isolation"
   git push origin main
   ```

8. In Render, **first sync the existing Blueprint** (`Datamendry-blueprint`), confirm `DATAMENDRY_DEMO_ONLY=1` and `DATAMENDRY_SECURE_COOKIE=1`, then deploy commit and check that `/api/config` reports `demo_only: true` and `private_guest_workspace: true`. Do not create another web service.
9. On the public site verify that the sample dataset still works; a custom upload must still yield `403`. Verify Cloudflare Analytics continues to receive `rum` requests (204).

## Later: actual public CSV uploads

Only after separate security review and stress testing should the environment be changed to allow small non-sensitive public CSV uploads. Persistent accounts, external private storage with retention policies, incident handling, WAF/rate limiting, monitoring and resource isolation are required before accepting confidential data or advertising production security. CSV only for now—Excel support needs its own hardened parser and tests.
