# Dashboard motion design — v0.2.1

This is a front-end polish update on top of DataMendry v0.2. Backend, upload limits, processing logic and API endpoints are unchanged.

## Motion

- Intro headings and new section fade up in about 0.35–0.45 seconds.
- Navigation, upload panel, buttons, metric cards and feature tiles respond gently on hover.
- Column quality progress bars animate in once when rendered.
- Repaired-data impact cards and status notices reveal once after results arrive.
- All animation uses CSS opacity and transform where possible, rather than JavaScript animation loops.
- Browser `prefers-reduced-motion` is respected, including programmatic scroll behavior.
- No endless decorative animations on large data tables. Existing loading spinner continues to spin while work is active.
- Brand text and icon now say DataMendry (instead of the earlier TraceTidy name); favicon is embedded locally.

## Copy just the UI changes into your local project

Stop server if you prefer (Ctrl+C), then copy `static/index.html`, `static/app.css`, and `static/app.js` over the files with the same names in your original project. Restart the server and refresh the browser with Ctrl+F5. If using `uvicorn --reload`, it may not reload for static file changes, but refreshing in the browser will retrieve them. Keep your project `data/` and `.venv/` folders unchanged.

## Test

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Enjoy the transitions. Reduce Motion in Windows accessibility settings will suppress the animations.
