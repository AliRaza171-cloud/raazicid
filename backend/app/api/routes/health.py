from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict:
    """Is the API running? (no database call)"""
    return {"status": "ok", "app": settings.APP_NAME}


@router.get("/health/db")
def health_db(db: Session = Depends(get_db)) -> dict:
    """Can the API reach PostgreSQL, and is pgvector installed?"""
    db.execute(text("SELECT 1"))
    has_vector = db.execute(text("SELECT 1 FROM pg_extension WHERE extname = 'vector'")).first() is not None
    return {"status": "ok", "database": "reachable", "pgvector": has_vector}
