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
        NeedIndicator(location_id=lyari, indicator="people_in_need", value=90000, source_id=sid, period_end=date(2026, 6, 30),
                      meta={"sector": "Emergency Shelter and NFI", "share": 0.3}),
        # Saddar: 70% less rain than normal -> drought risk for food (50, some)
        NeedIndicator(location_id=saddar, indicator="rainfall_anomaly_pct", value=-70, source_id=sid, period_end=date(2026, 9, 30),
                      meta={"period": "3-month"}),
        # Only health organisations work in Lyari
        NeedIndicator(location_id=lyari, indicator="orgs_present", value=2, source_id=sid, period_end=date(2026, 6, 30),
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
