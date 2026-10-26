"""UN data end-to-end: people in need and rainfall raise need levels; 3W marks neglected places; need finder facts.
Skipped without TEST_DATABASE_URL. Nothing here calls the internet."""

import uuid
from datetime import date

from sqlalchemy import delete, select

from app.models import NeedIndicator, Source
from app.models.enums import SourceKind
from app.services.needs import recompute
from app.services.rag.finder import un_facts
from tests.test_auth_api import API, auth, register
from tests.test_donations_api import area


def test_un_signals_and_neglected_places(client, db):
    sid = db.scalar(select(Source.id).where(Source.kind == SourceKind.hdx_hapi))
    lyari, saddar = uuid.UUID(area(db, "Lyari")), uuid.UUID(area(db, "Saddar"))
    db.add_all([
        # 30% of Lyari needs shelter help -> blankets / household / winter: high (65)
        NeedIndicator(location_id=lyari, indicator="people_in_need", value=90000, source_id=sid, period_end=date.today(),
                      meta={"sector": "Emergency Shelter and NFI", "share": 0.3}),
        # Saddar: 70% less rain than normal -> drought risk for food (50, some)
        NeedIndicator(location_id=saddar, indicator="rainfall_anomaly_pct", value=-70, source_id=sid, period_end=date.today(),
                      meta={"period": "3-month"}),
        # Only health organisations work in Lyari
        NeedIndicator(location_id=lyari, indicator="orgs_present", value=2, source_id=sid, period_end=date.today(),
                      meta={"sectors": {"Health": ["WHO", "MSF"]}}),
    ])
    db.commit()
    try:
        recompute(db)
        donor_h = auth(register(client).json()["access_token"])
        sindh = next(r for r in client.get(f"{API}/needs", headers=donor_h).json()["children"] if r["name"] == "Sindh")
        karachi_level = client.get(f"{API}/needs", headers=donor_h, params={"parent_id": sindh["id"]}).json()
        assert karachi_level["has_3w"]
        south = client.get(f"{API}/needs", headers=donor_h, params={"parent_id": area(db, "Karachi")}).json()
        row = next(r for r in south["children"] if r["name"] == "Karachi South")
        blankets = next(n for n in row["needs"] if n["category_id"] == 4)
        assert blankets["level"] >= 2 and any("people" in r["why"] and "OCHA" in r["source"] for r in blankets["reasons"])
        food = next(n for n in row["needs"] if n["category_id"] == 1)
        assert any("less than normal" in r["why"] for r in food["reasons"])
        # High need for blankets, but only health organisations there: neglected
        assert "Blankets" in row["neglected"] and row["who_works"] == {"Health": ["MSF", "WHO"]} and row["orgs"] == 2

        facts = un_facts(db, uuid.UUID(area(db, "Karachi")), 4, start=5)
        assert facts and facts[0]["id"] == "D5" and "no organisation reported working on blankets" in facts[0]["text"]
        assert "WHO" in un_facts(db, None, None, start=1)[0]["text"]
    finally:
        db.execute(delete(NeedIndicator).where(NeedIndicator.location_id.in_([lyari, saddar]), NeedIndicator.source_id == sid))
        db.commit()
        recompute(db)


def test_ai_scan_adds_fresh_linked_needs(client, db, monkeypatch):
    from app.services.sources import ai_needs
    from app.services.sources.runner import run_source
    from tests.test_donations_api import admin_headers

    admin_h = admin_headers(client, db)
    sindh = area(db, "Sindh")
    assert client.post(f"{API}/admin/needs/ai-scan", headers=admin_h, json={"location_id": area(db, "Karachi")}).status_code in (422,)

    items = [{"area": "Lyari", "province": "Sindh", "categories": ["hygiene"], "level": 3, "why": "Hygiene kits ran out at camps.",
              "date": date.today(), "sources": [{"url": "https://www.unicef.org/pakistan/x", "title": "UNICEF update"}]},
             {"area": "Lahore", "province": "Punjab", "categories": ["food"], "level": 2, "why": "Outside Sindh.", "date": date.today(),
              "sources": []}]
    monkeypatch.setattr(ai_needs, "scan", lambda scope: items)
    ok, status = run_source(db, SourceKind.ai_needs, {"province_id": uuid.UUID(sindh)})
    assert ok and "2 needs found" in status and "1 added" in status and "not matched" in status   # Lahore is not in Sindh
    try:
        donor_h = auth(register(client).json()["access_token"])
        south = client.get(f"{API}/needs", headers=donor_h, params={"parent_id": area(db, "Karachi")}).json()
        row = next(r for r in south["children"] if r["name"] == "Karachi South")
        hygiene = next(n for n in row["needs"] if n["category_id"] == 6)
        r = next(r for r in hygiene["reasons"] if r["source"].startswith("AI web scan"))
        assert hygiene["level"] >= 2 and r["url"] == "https://www.unicef.org/pakistan/x" and "Hygiene kits" in r["why"]
        # A new scan of Sindh replaces the old one
        monkeypatch.setattr(ai_needs, "scan", lambda scope: [])
        assert "0 needs found" in run_source(db, SourceKind.ai_needs, {"province_id": uuid.UUID(sindh)})[1]
        assert not db.scalars(select(NeedIndicator).where(NeedIndicator.indicator == "ai_need")).first()
    finally:
        db.execute(delete(NeedIndicator).where(NeedIndicator.indicator == "ai_need"))
        db.commit()
        recompute(db)
