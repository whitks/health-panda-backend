# Health Panda Backend (Flask)

Simple Flask starter app with SQLite-backed user authentication.

Quick start

1. Create a virtual environment and activate it:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Run the app:

```bash
python app.py
```

The app listens on port 5000. On first run it will create `data.db` in the repository root with a `users` table.

Notes
- Default secret is `dev-secret-key`. Set `FLASK_SECRET` env var in production.
# health-panda-backend