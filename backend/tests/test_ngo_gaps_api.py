"""NGO finder for places in need, end-to-end. Skipped without TEST_DATABASE_URL. Never calls the internet or the AI."""

import uuid
from datetime import date

from sqlalchemy import delete, select

from app.models import NeedIndicator, NeedLevel, Ngo, Source
from app.models.enums import SourceKind
from app.services import ngo_sources
from tests.test_auth_api import API
from tests.test_donations_api import admin_headers, area


def test_fill_gaps_with_openstreetmap_and_3w(client, db, monkeypatch):
    admin_h = admin_headers(client, db)
    sukkur = uuid.UUID(area(db, "Sukkur"))
    sid = db.scalar(select(Source.id).where(Source.kind == SourceKind.hdx_hapi))
    need = NeedLevel(location_id=sukkur, category_id=4, level=2, score=62, reasons=[])
    w3 = NeedIndicator(location_id=sukkur, indicator="orgs_present", value=3, source_id=sid, period_end=date(2025, 12, 31),
                       meta={"sectors": {"Shelter and NFI": ["NRC", "UNHCR"], "Education": ["AKF"]},
                             "names": {"NRC": "Norwegian Refugee Council"}})
    db.add_all([need, w3])
    db.commit()
    monkeypatch.setattr(ngo_sources, "osm_offices", lambda lat, lng, radius: [
        {"name": "Sukkur Welfare Society", "lat": 27.70, "lng": 68.86, "address": "Barrage Road", "phone": None,
         "website": None, "kind": "ngo", "url": "https://www.openstreetmap.org/node/9"}])
    try:
        r = client.post(f"{API}/admin/ngos/fill-gaps", headers=admin_h, json={"location_id": str(sukkur), "use_ai": False})
        assert r.status_code == 200 and r.json()["ok"], r.text
        assert "OpenStreetMap added 1" in r.json()["status"] and "OCHA 3W added 1" in r.json()["status"]
        ngos = {n.name: n for n in db.scalars(select(Ngo).where(Ngo.location_id == sukkur))}
        assert ngos["Sukkur Welfare Society"].found_by == "openstreetmap"
        nrc = ngos["Norwegian Refugee Council"]
        assert nrc.found_by == "ocha_3w" and nrc.location_approx and "blankets" in {c.slug for c in nrc.categories}
        assert "UNHCR" not in ngos and "AKF" not in ngos            # UN agency left out; education does not serve blankets
        # The source shows in the data sources list and can be run from there
        src = next(s for s in client.get(f"{API}/admin/sources", headers=admin_h).json() if s["kind"] == "ngo_finder")
        assert src["can_run"] and "OpenStreetMap" in src["last_status"]
    finally:
        db.execute(delete(Ngo).where(Ngo.location_id == sukkur))
        db.execute(delete(NeedIndicator).where(NeedIndicator.id == w3.id))
        db.commit()
