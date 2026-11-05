# DataMendry v0.4 — Security and privacy

**Status: limited public demonstration, NOT an independently audited production application.** No security setting can guarantee that a visitor or device is safe. Do not upload sensitive, regulated, personal, or confidential records.

## Public Render deployment (default)

- `DATAMENDRY_DEMO_ONLY=1` is the default (fail closed). Arbitrary CSV uploads are rejected with HTTP 403 **before multipart parsing**.
- The website creates sample-only workspaces using the included, non-sensitive `sample_sales.csv`. This permits demonstration of profiling, validation, repair previews and spreadsheet-oriented export.
- Global demo request cap, active-workspace cap and processing-concurrency semaphore reduce accidental overload. **These are per-process controls, not a substitute for edge rate limiting or bot mitigation.**
- Workspaces are identified by cryptographically random dataset IDs **and** private, time-limited guest-browser session cookies. Each dataset is bound to the SHA-256 fingerprint of the creating browser’s server-signed session secret; the server checks ownership for profile, preview, simulation, rules, download, and deletion. A copied dataset URL alone no longer grants access. Guest cookies are NOT user accounts or a replacement for persistent authentication.
- Dataset workspaces expire and a cleanup task runs periodically. Disk removal is *not secure erasure*. Render's free instance disk is ephemeral, and all workspaces may disappear on restart.
- Only defined CSS and JS assets are served. Security headers include CSP, `nosniff`, frame denial and referrer restrictions. CSP permits the separately installed Cloudflare Web Analytics beacon and its collection endpoint.
- The API refuses cross-site browser mutations using `Origin` / `Sec-Fetch-Site` checks. Host-only HttpOnly SameSite=Lax cookies add browser-side CSRF resistance; Render requires Secure cookies through `DATAMENDRY_SECURE_COOKIE=1`. Headers are forgeable by non-browser clients; these controls do not constitute full identity verification.

## Local development mode (not for internet exposure)

To enable your own CSV files **only on your trusted laptop**, set `DATAMENDRY_DEMO_ONLY=0` in your local terminal before running Uvicorn. Do NOT enable this on the public Render instance until further abuse/penetration tests, secure storage and privacy review are completed. v0.4 isolates temporary guest-browser workspaces, but does not provide real accounts.

- Files are limited by input bytes, rows, SQLite page budget and import wall time. These controls reduce, not eliminate, resource-exhaustion risk.
- Only UTF-8 CSV parsing is supported. NUL bytes, malformed rows, too many columns and over-limit files are rejected. Untrusted CSV cells are always rendered with `textContent` in the browser.
- Spreadsheet-oriented CSV exports neutralize likely formula-starting cells using a leading TAB inside quoted CSV fields. This **changes the exported cell contents** and is not universal across spreadsheet software; verify in your target spreadsheet before opening untrusted exports. The CSV is not suitable as an exact byte-for-byte roundtrip representation.

## Remaining production blockers

Do not advertise DataMendry as safe for confidential real-world uploads until the following are implemented and reviewed:

1. Proper authenticated user accounts and session lifecycle, beyond temporary per-browser guest workspace isolation.
2. External private object storage with enforced retention, encryption at rest and deletion controls.
3. Separate task workers with memory/CPU/time limits, queueing, cancellation and per-user quotas.
4. Edge-level WAF/rate limiting/abuse protection; logging without PII, alerting and incident response.
5. Malware and dependency monitoring appropriate to new file types, and independent security testing.
6. HTTPS/custom domain and backups/disaster recovery for any persistent state.

## Reporting security issues

Use GitHub's **Report a vulnerability** / private security advisory feature when enabled. Do not paste real user data, credentials, or exploit details into public issues. Until a private channel exists, do not submit sensitive information via public comments.

References: OWASP File Upload Cheat Sheet; OWASP CSV Injection testing guide; Render free service limitations.
