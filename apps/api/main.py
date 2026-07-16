"""
Uvicorn entry point.
Run with: uvicorn main:app --reload --port 8000

Deploy marker: skilled_pro backend (v2) — forces Railway to build latest main.
"""
from app.main import app  # noqa: F401
