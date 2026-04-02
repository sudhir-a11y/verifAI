# Backend (FastAPI)

This folder contains the FastAPI backend, database bootstrap SQL, and operational scripts.

## Quickstart

Install dependencies:

```bash
python3 -m pip install -r backend/requirements.txt
```

Initialize DB (schema + seeds):

```bash
python3 backend/scripts/create_database.py
```

Run API:

```bash
uvicorn backend.app.main:app --reload
```

