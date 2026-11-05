# DataMendry v0.3 — Security and privacy

**Status: limited public demonstration, NOT an independently audited production application.** No security setting can guarantee that a visitor or device is safe. Do not upload sensitive, regulated, personal, or confidential records.

## Public Render deployment (default)

- `DATAMENDRY_DEMO_ONLY=1` is the default (fail closed). Arbitrary CSV uploads are rejected with HTTP 403 **before multipart parsing**.
- The website creates sample-only workspaces using the included, non-sensitive `sample_sales.csv`. This permits demonstration of profiling, validation, repair previews and spreadsheet-oriented export.
- Global demo request cap, active-workspace cap and processing-concurrency semaphore reduce accidental overload. **These are per-process controls, not a substitute for edge rate limiting or bot mitigation.**
- Workspaces are identified by cryptographically random 128-bit bearer IDs. Anyone with a dataset URL can access its data. URLs are NOT an authentication system.
- Dataset workspaces expire and a cleanup task runs periodically. Disk removal is *not secure erasure*. Render's free instance disk is ephemeral, and all workspaces may disappear on restart.
- Only defined CSS and JS assets are served. Security headers include CSP, `nosniff`, frame denial and referrer restrictions. CSP permits the separately installed Cloudflare Web Analytics beacon and its collection endpoint.
- The API refuses cross-site browser mutations using `Origin` / `Sec-Fetch-Site` checks; these headers are forgeable and are not login credentials.

## Local development mode (not for internet exposure)

To enable your own CSV files **only on your trusted laptop**, set `DATAMENDRY_DEMO_ONLY=0` in your local terminal before running Uvicorn. Do NOT enable this on the public Render instance until account authentication, authorization, isolation and audited abuse protections are built.

- Files are limited by input bytes, rows, SQLite page budget and import wall time. These controls reduce, not eliminate, resource-exhaustion risk.
- Only UTF-8 CSV parsing is supported. NUL bytes, malformed rows, too many columns and over-limit files are rejected. Untrusted CSV cells are always rendered with `textContent` in the browser.
- Spreadsheet-oriented CSV exports neutralize likely formula-starting cells using a leading TAB inside quoted CSV fields. This **changes the exported cell contents** and is not universal across spreadsheet software; verify in your target spreadsheet before opening untrusted exports. The CSV is not suitable as an exact byte-for-byte roundtrip representation.

## Remaining production blockers

Do not advertise DataMendry as safe for confidential real-world uploads until the following are implemented and reviewed:

1. Proper authentication, authorization, isolated accounts/workspaces and secure identity lifecycle.
2. External private object storage with enforced retention, encryption at rest and deletion controls.
3. Separate task workers with memory/CPU/time limits, queueing, cancellation and per-user quotas.
4. Edge-level WAF/rate limiting/abuse protection; logging without PII, alerting and incident response.
5. Malware and dependency monitoring appropriate to new file types, and independent security testing.
6. HTTPS/custom domain and backups/disaster recovery for any persistent state.

## Reporting security issues

Use GitHub's **Report a vulnerability** / private security advisory feature when enabled. Do not paste real user data, credentials, or exploit details into public issues. Until a private channel exists, do not submit sensitive information via public comments.

References: OWASP File Upload Cheat Sheet; OWASP CSV Injection testing guide; Render free service limitations.
