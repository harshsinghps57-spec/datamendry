# DataMendry v0.9.4.1 — Top-right Account Menu Only

This small UI-only patch is built directly on **the working v0.9.4 update**.

## Change

- Removed the duplicate account/profile button and dropdown from the bottom-left sidebar.
- Kept the existing **top-right profile menu** with the same email/Google identity, My Datasets, Set / change password, Log in / Register, and Sign out functions.
- Left the sidebar privacy note in place.
- Did not modify the backend, account.js, authentication settings, CSV storage, AI assistant, filters, navigation, or animations.

## Install (in the existing project, NOT a new project)

1. Back up your existing `static/index.html` and `static/experience.js` files.
2. Stop Uvicorn (Ctrl+C).
3. Copy this ZIP's `static/index.html` and `static/experience.js` into the inner project `static/` directory, replacing only those two files.
4. Copy this ZIP's `tests/test_ui_polish_v094.py` into `tests/`, replacing that single test file. The new assertion expects **only the top-right** account menu.
5. Do not replace `account.js`, `app.js`, `experience.css`, `render.yaml`, `.env`, `.git`, or `data`.
6. Run `python -m pytest -q`.
7. Restart using `python -m uvicorn datamendry.api:app --host 127.0.0.1 --port 8002`.
8. Refresh `http://127.0.0.1:8002/` with Ctrl+F5.

## Check

- No account menu in the bottom-left sidebar.
- Top-right dropdown opens and shows user details, My Datasets, password action, sign-out.
- Google and email/password login still work; saved CSV files are unchanged.

This patch does not deploy to Render or GitHub.
