# DataMendry animations update

This is **DataMendry v0.2.1**, a visual-only refinement of the v0.2 codebase.

To upgrade an existing Windows VS Code installation without reinstalling libraries:

1. Keep your original folder and `.venv` directory. Don't delete your `data` folder if you need its locally uploaded datasets.
2. Copy these **three files** from the update's `static` folder into your current `DataMendry_v0.2/static` folder, replacing the existing files: `index.html`, `app.css`, `app.js`.
3. In the VS Code terminal where Uvicorn is running, leave it running. Browser static assets refresh on reload.
4. In Edge, press **Ctrl+F5** on `http://127.0.0.1:8000/`.
5. Confirm the DataMendry logo appears, hover over the feature cards, switch between tabs, drag a CSV over the upload panel, and open the sample dataset.

No additional Python or JavaScript libraries are required. The application works without an internet connection, and reduced-motion settings are supported. Animations are intentionally subtle and do not process data. This update does not address large-data processing speed, concurrent users, or production security.

To check automated tests in the project folder:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```
