"""Read-only DataMendry v1 release preflight. No uploads, deletions or secrets printed.

Usage:
  python tools/release_preflight.py
  python tools/release_preflight.py --url http://127.0.0.1:8002
  python tools/release_preflight.py --skip-tests --url http://127.0.0.1:8002
"""
from __future__ import annotations

import argparse
import ast
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request

REQUIRED = [
    "datamendry/api.py",
    "datamendry/advanced_cleaning.py",
    "datamendry/smart_relationships.py",
    "datamendry/analytics_v1.py",
    "datamendry/analytics_relationships.py",
    "datamendry/assistant_planner.py",
    "static/index.html",
    "static/app.js",
    "static/account.js",
    "static/analytics.js",
    "static/smart_analytics.js",
    "static/advanced_cleaning.js",
    "static/experience.js",
    "static/experience.css",
]
PUBLIC_ASSETS = ["analytics.js", "smart_analytics.js", "advanced_cleaning.js", "experience.js", "account.js"]


def cli(args=None):
    p = argparse.ArgumentParser(description="Non-destructive DataMendry v1 preflight audit")
    p.add_argument("--url", default="", help="Optional LOCAL running server URL, e.g. http://127.0.0.1:8002")
    p.add_argument("--skip-tests", action="store_true", help="Skip pytest for a quick second pass")
    p.add_argument("--project", default=".", help="Project root containing datamendry/ and static/")
    p.add_argument("--output", default="DATAMENDRY_PREFLIGHT_RESULT.md", help="Markdown report path")
    return p.parse_args(args)


def command(cmd, cwd, timeout=180):
    try:
        p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=timeout,
                           env={**os.environ, "PYTHONIOENCODING": "utf-8"})
        return p.returncode, (p.stdout or "") + "\n" + (p.stderr or "")
    except (OSError, subprocess.TimeoutExpired) as ex:
        return 999, type(ex).__name__


def url_status(base_url: str, path: str):
    url = base_url.rstrip("/") + path
    req = urllib.request.Request(url, method="GET", headers={"User-Agent": "DataMendry-local-preflight/1"})
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            if path == "/api/health":
                try:
                    obj = json.load(resp)
                    return resp.status, str(obj.get("version", "unknown"))[:40]
                except (json.JSONDecodeError, UnicodeError, ValueError):
                    return resp.status, "unparseable health JSON"
            return resp.status, ""
    except urllib.error.HTTPError as ex:
        return ex.code, "HTTP error"
    except (urllib.error.URLError, TimeoutError, OSError):
        return None, "server unreachable"


def audit(project: Path, url: str, skip_tests: bool):
    checks = []
    def add(label, status, detail):
        checks.append((label, status, detail))

    missing = [p for p in REQUIRED if not (project / p).is_file()]
    add("Expected Milestone 10 source files", "FAIL" if missing else "PASS",
        ", ".join(missing) if missing else "All expected backend and frontend files are present")

    python_sources = list((project / "datamendry").rglob("*.py")) if (project / "datamendry").exists() else []
    bad = []
    for file in python_sources:
        try:
            ast.parse(file.read_text(encoding="utf-8"), filename=str(file))
        except (SyntaxError, UnicodeError, OSError) as e:
            bad.append(f"{file.relative_to(project)} ({type(e).__name__})")
    add("Python source parsing", "FAIL" if not python_sources or bad else "PASS",
        ", ".join(bad) if bad else f"{len(python_sources)} source files parsed")

    api = (project / "datamendry/api.py")
    if api.is_file():
        code = api.read_text(encoding="utf-8", errors="replace")
        absent = [p for p in PUBLIC_ASSETS if f'"{p}"' not in code and f"'{p}'" not in code]
        add("Approved frontend asset routes", "FAIL" if absent else "PASS",
            ", ".join(absent) if absent else "All five expected JavaScript filenames found in backend")
        match = re.search(r'FastAPI\([^\n]*version=["\']([^"\']+)', code)
        if not match:
            match = re.search(r'\"version\":\s*\"([^\"]+)\"', code)
        version = match.group(1) if match else "not detected"
        add("v1.0.0 API version alignment", "PASS" if version == "1.0.0" else "WARN",
            f"Source reports {version}. Align the API/health version when preparing v1.0 release")

    code, out = command(["git", "branch", "--show-current"], project, timeout=12)
    if code == 0:
        branch = out.strip().splitlines()[0] if out.strip() else "(detached)"
        add("Development branch isolation", "PASS" if branch == "feature/v1-ai-analytics" else "WARN",
            f"Current branch: {branch}; do not deploy directly from an unverified branch")
        code2, tracked = command(["git", "ls-files"], project, timeout=12)
        if code2 == 0:
            risky = [p for p in tracked.splitlines() if re.search(r'(^|/)(\.env(\..+)?|.*\.(pem|p12|pfx|key)|credentials\.json)$', p, flags=re.I)
                     and not p.endswith(".env.example")]
            add("Secret-like files tracked by Git", "FAIL" if risky else "PASS",
                "Tracked sensitive-looking filenames: " + ", ".join(risky) if risky else "No obvious secret filenames tracked")
        else:
            add("Git tracked-secret scan", "WARN", "Unable to list tracked files")
    else:
        add("Git repository", "WARN", "No readable Git checkout; check current branch manually")

    if shutil.which("node"):
        failed = []
        count = 0
        for file in sorted((project / "static").glob("*.js")):
            count += 1
            rc, _ = command(["node", "--check", str(file)], project, timeout=20)
            if rc != 0:
                failed.append(file.name)
        add("JavaScript syntax", "FAIL" if failed else ("PASS" if count else "SKIP"), ", ".join(failed) if failed else (f"{count} JS files passed syntax check" if count else "No JavaScript files found"))
    else:
        add("JavaScript syntax", "WARN", "Node.js not installed; skip only this optional static check")

    if skip_tests:
        add("Automated test suite", "SKIP", "Skipped by --skip-tests")
    else:
        rc, log = command([sys.executable, "-m", "pytest", "-q"], project, timeout=180)
        final_line = next((line.strip() for line in reversed(log.splitlines()) if re.search(r'\b(?:passed|failed|errors?)\b', line)), "no readable test summary")
        add("Automated test suite", "PASS" if rc == 0 else "FAIL", final_line[:260])

    if url:
        parsed = urllib.parse.urlparse(url)
        if parsed.hostname not in ("localhost", "127.0.0.1", "::1") or parsed.scheme != "http":
            add("Live local server", "FAIL", "Only http://127.0.0.1 or localhost is allowed for this preflight")
        else:
            for path in ["/", "/api/health", "/api/config", "/api/account-config"] + ["/static/" + a for a in PUBLIC_ASSETS]:
                status, hint = url_status(url, path)
                add("GET " + path, "PASS" if status == 200 else "FAIL",
                    f"HTTP {status if status is not None else 'unreachable'}" + (f"; reported API version {hint}" if path == "/api/health" else ""))
    else:
        add("Local HTTP route checks", "SKIP", "Start Uvicorn and rerun with --url http://127.0.0.1:8002")
    return checks


def report(project: Path, checks):
    count = {s: sum(1 for _, st, _ in checks if st == s) for s in ("PASS", "WARN", "FAIL", "SKIP")}
    header = f"# DataMendry v1 — Read-only local preflight\n\nResults: **{count['PASS']} PASS · {count['WARN']} WARN · {count['FAIL']} FAIL · {count['SKIP']} SKIP**.\n\n"
    header += "This is a preliminary local engineering check, **not a production security certification**.\n\n"
    lines = [header, "| Check | Status | Result |", "|---|---|---|"]
    for name, status, detail in checks:
        safe = detail.replace("|", "/").replace("\n", " ").replace("`", "'")
        lines.append(f"| {name} | **{status}** | {safe} |")
    lines.extend(["", "## Mandatory manual release gates", "",
                  "- Test email/password, Google OAuth, password recovery and session logout/login on local and deployed origins.",
                  "- Test a second account cannot list, preview, export or delete another account's saved datasets.",
                  "- Test Supabase bucket policies, actual deletion, storage quotas and retention with NONSENSITIVE demo CSVs.",
                  "- Test both numeric and employee-style CSVs, multi-step assistant, analytics reports, smart comparisons and repair exports.",
                  "- Test a real phone-sized display and keyboard-only navigation; check labels, focus and loading/error states.",
                  "- Test upload limits, repeated requests, two-browser isolation and malformed/large files; do not use personal data.",
                  "- Check production environment settings and access permissions privately; never paste secret keys into chats or GitHub.",
                  "- Prepare a rollback commit, keep Render manual deploy, and verify live health before expanding access.",
                  "- Review and disclose privacy limitations. Do not invite sensitive or regulated uploads before independent security review.",
                  "", "## Decision", "",
                  "Any FAIL blocks release. WARN/SKIP need a recorded disposition. Manual gates require real-browser evidence before release.", ""])
    return "\n".join(lines)


def main(args=None):
    opts = cli(args)
    project = Path(opts.project).expanduser().resolve()
    if not project.is_dir():
        raise SystemExit("Project directory not found")
    checks = audit(project, opts.url, opts.skip_tests)
    count = {s: sum(st == s for _, st, _ in checks) for s in ("PASS", "WARN", "FAIL", "SKIP")}
    for label, status, detail in checks:
        print(f"[{status:4}] {label}: {detail}")
    output = Path(opts.output)
    if not output.is_absolute():
        output = project / output
    output.write_text(report(project, checks), encoding="utf-8")
    print(f"\nSummary: {count['PASS']} pass, {count['WARN']} warn, {count['FAIL']} fail, {count['SKIP']} skip")
    print(f"Report saved to: {output}")
    return 1 if count["FAIL"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
