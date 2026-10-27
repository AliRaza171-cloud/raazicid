"""Phase 1 checks. Run from backend/:  pytest

The first tests need no database. The last one runs only if TEST_DATABASE_URL is set
(point it at an EMPTY Neon branch or a local Postgres with pgvector, never your real data).
"""

from fastapi.testclient import TestClient

import app.models as _models  # noqa: F401  (registers all tables; "as" keeps `app` below pointing at FastAPI)
from app.db.base import Base
from app.main import app

EXPECTED_TABLES = {
    "users", "rider_profiles", "rider_documents", "document_reviews", "refresh_tokens",
    "locations", "categories",
    "donations", "donation_images", "status_changes", "ratings",
    "ngos", "ngo_categories", "jobs", "rider_pings",
    "sources", "reports", "report_chunks", "chunk_locations",
    "need_indicators", "need_levels", "seasonal_rules",
    "disaster_alerts", "alert_locations", "alert_reports", "alert_needs", "appeals",
    "notifications", "fraud_flags",
}


def test_health():
    r = TestClient(app).get("/api/v1/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_all_tables_are_defined():
    assert EXPECTED_TABLES <= set(Base.metadata.tables), EXPECTED_TABLES - set(Base.metadata.tables)


def test_docs_page_loads():
    assert TestClient(app).get("/docs").status_code == 200


def test_seed_is_idempotent(engine, db):
    """Seeding ran once in the session fixture; running again must add nothing."""
    from app.models import Category, Location
    from app.seed.run import seed

    assert seed(db) == {"categories": 0, "sources": 0, "locations": 0, "seasonal_rules": 0}
    assert db.query(Category).count() == 12
    assert db.query(Location).filter_by(name="Lyari").count() == 1
