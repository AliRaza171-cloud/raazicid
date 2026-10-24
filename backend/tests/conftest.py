"""Shared test setup.

Database tests use TEST_DATABASE_URL, which must point at an EMPTY database (e.g. a Neon branch
named "test"). Every test run drops and recreates all tables there. Never use your real database.
"""

import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

import app.models as _models  # noqa: F401
from app.db.base import Base
from app.db.session import get_db
from app.main import app

TEST_DB = os.getenv("TEST_DATABASE_URL")
needs_db = pytest.mark.skipif(not TEST_DB, reason="set TEST_DATABASE_URL to run database tests")


@pytest.fixture(scope="session")
def engine():
    if not TEST_DB:
        pytest.skip("set TEST_DATABASE_URL to run database tests")
    eng = create_engine(TEST_DB, pool_pre_ping=True)
    with eng.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    Base.metadata.drop_all(eng)
    Base.metadata.create_all(eng)
    from app.seed.run import seed
    with sessionmaker(bind=eng)() as db:
        seed(db)
    yield eng
    Base.metadata.drop_all(eng)


@pytest.fixture()
def db(engine):
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def client(engine):
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    def override_get_db():
        s = Session()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
