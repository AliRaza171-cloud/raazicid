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


def test_earthquake_finds_ngos_and_needs_show_where_to_drop(client, db, monkeypatch):
    from app.services.sources import ngo_gaps
    from tests.test_donations_api import make_ngo

    admin_h = admin_headers(client, db)
    khuzdar = uuid.UUID(area(db, "Khuzdar"))
    sid = db.scalar(select(Source.id).where(Source.kind == SourceKind.hdx_hapi))
    w3 = NeedIndicator(location_id=khuzdar, indicator="orgs_present", value=2, source_id=sid, period_end=date(2025, 12, 31),
                       meta={"sectors": {"Emergency Shelter and NFI": ["NRC", "UNHCR"]}, "names": {"NRC": "Norwegian Refugee Council"}})
    db.add(w3)
    db.commit()
    monkeypatch.setattr(ngo_sources, "osm_offices", lambda lat, lng, radius: [
        {"name": "Khuzdar Welfare Trust", "lat": 27.81, "lng": 66.61, "address": "Main Bazaar", "phone": "0848-1",
         "website": None, "kind": "ngo", "url": "https://www.openstreetmap.org/node/7"}])
    alert = client.post(f"{API}/admin/alerts", headers=admin_h, json={
        "type": "earthquake", "severity": "moderate", "title": "Earthquake near Khuzdar", "location_ids": [str(khuzdar)],
        "figures": {}}).json()
    try:
        # What runs in the background when an alert is added or confirmed (turned off in tests: run it here)
        status = ngo_gaps.for_alerts(db, uuid.UUID(alert["id"]), use_ai=False)
        assert "Earthquake near Khuzdar" in status and "2 added" in status
        near = {n["name"]: n for n in client.get(f"{API}/admin/alerts/{alert['id']}", headers=admin_h).json()["ngos"]}
        nrc, trust = near["Norwegian Refugee Council"], near["Khuzdar Welfare Trust"]
        assert nrc["active_here"] and "Blankets" in nrc["takes"] and "Winter support" in nrc["takes"]
        assert trust["takes_everything"] and trust["address"] == "Main Bazaar" and "UNHCR" not in near

        # Needs by area: NGOs that take blankets for Khuzdar; one that takes only food is left out
        make_ngo(client, admin_h, db, name="Khuzdar Food Bank", where="Khuzdar", lat=27.80, lng=66.62, category_ids=[1])
        drop = client.get(f"{API}/admin/ngos/for-need", headers=admin_h, params={"location_id": str(khuzdar), "category_id": 4}).json()
        names = [n["name"] for n in drop]
        assert "Khuzdar Food Bank" not in names and set(names) >= {"Norwegian Refugee Council", "Khuzdar Welfare Trust"}
        assert drop[0]["name"] == "Norwegian Refugee Council" and drop[0]["active_here"]   # works there (3W), lists blankets
        # Asked for one place and item, whatever the need level
        r = client.post(f"{API}/admin/ngos/fill-gaps", headers=admin_h,
                        json={"location_id": str(khuzdar), "category_id": 4, "use_ai": False}).json()
        assert r["ok"] and "Khuzdar" in r["status"] and "take blankets" in r["status"]
    finally:
        client.post(f"{API}/admin/alerts/{alert['id']}/status", headers=admin_h, json={"status": "handled"})
        db.execute(delete(Ngo).where(Ngo.location_id == khuzdar))
        db.execute(delete(NeedIndicator).where(NeedIndicator.id == w3.id))
        db.commit()


def test_province_need_shows_ngos_per_place_and_searches_each_place(client, db, monkeypatch):
    """Sindh needs blankets in Sukkur: the NGOs table is per place (not only Karachi), a place with no NGO of its own
    shows the nearest town that has one (Larkana, not Karachi) and how far, and "Find NGOs" for Sindh searches around
    Sukkur itself."""
    from tests.test_donations_api import make_ngo

    admin_h = admin_headers(client, db)
    sindh, sukkur = uuid.UUID(area(db, "Sindh")), uuid.UUID(area(db, "Sukkur"))
    need = NeedLevel(location_id=sukkur, category_id=4, level=1, score=40, reasons=[])
    db.add(need)
    db.commit()
    make_ngo(client, admin_h, db, name="Karachi Blanket Bank", where="Karachi", lat=24.86, lng=67.01, category_ids=[4])
    make_ngo(client, admin_h, db, name="Larkana Blanket Bank", where="Larkana", lat=27.56, lng=68.21, category_ids=[4])
    seen = []
    monkeypatch.setattr(ngo_sources, "osm_offices", lambda lat, lng, radius: seen.append((round(lat), round(lng))) or [
        {"name": "Sukkur Welfare Society", "lat": 27.70, "lng": 68.86, "address": "Barrage Road", "phone": None,
         "website": None, "kind": "ngo", "url": "https://www.openstreetmap.org/node/9"},
        {"name": "World Health Organization", "lat": 27.70, "lng": 68.85, "address": None, "phone": None,
         "website": None, "kind": "ngo", "url": "https://www.openstreetmap.org/node/10"}])
    params = {"location_id": str(sindh), "category_id": 4}
    try:
        rows = {r["place"]: r for r in client.get(f"{API}/admin/ngos/by-place", headers=admin_h, params=params).json()}
        fb = rows["Sukkur"]["fallback"]
        assert rows["Sukkur"]["ngos"] == [] and fb["town"] == "Larkana" and 40 < fb["km"] < 90
        assert [n["name"] for n in fb["ngos"]] == ["Larkana Blanket Bank"]
        assert rows["Sukkur"]["path"][-1] == "Sukkur" and rows["Sukkur"]["works_here"] == []

        r = client.post(f"{API}/admin/ngos/fill-gaps", headers=admin_h, json={**params, "use_ai": False}).json()
        assert r["ok"] and "Sukkur (+1)" in r["status"], r
        assert (28, 69) in seen                                       # searched around Sukkur, not around Karachi
        rows = {r["place"]: r for r in client.get(f"{API}/admin/ngos/by-place", headers=admin_h, params=params).json()}
        assert [n["name"] for n in rows["Sukkur"]["ngos"]] == ["Sukkur Welfare Society"]   # the WHO office is left out
        assert rows["Sukkur"]["fallback"] is None
    finally:
        db.execute(delete(Ngo).where(Ngo.name.in_(["Karachi Blanket Bank", "Larkana Blanket Bank", "Sukkur Welfare Society"])))
        db.execute(delete(NeedLevel).where(NeedLevel.id == need.id))
        db.commit()


def test_import_ngo_list(client, db):
    """An admin's list: one NGO in several cities is saved in each; a new district is added under its province; an
    NGO we already have in a city gets the missing phone instead of a copy."""
    from tests.test_donations_api import make_ngo

    admin_h = admin_headers(client, db)
    make_ngo(client, admin_h, db, name="Saylani Welfare Trust - Test Branch", where="Hyderabad", lat=25.39, lng=68.36, category_ids=[1], phone=None)
    csv_text = ("NGO name,District,Province,Phone,Takes,Lat,Lng\n"
                "Test Rural Support Programme,Hyderabad; Sukkur,Sindh,,Food; Grocery / ration,,\n"
                "Saylani Welfare International Trust,Hyderabad,Sindh,021 111 729 526,,,\n"
                "Testabad Relief Society,Testabad,Sindh,0300-0000000,Blankets,26.73,67.78\n")
    try:
        r = client.post(f"{API}/admin/ngos/import", headers=admin_h,
                        files={"file": ("ngos.csv", csv_text.encode(), "text/csv")})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["added"] == 3 and body["updated"] == 1, body
        trsp = list(db.scalars(select(Ngo).where(Ngo.name == "Test Rural Support Programme")))
        assert len(trsp) == 2 and all(n.location_approx and n.found_by == "import" for n in trsp)
        assert {c.slug for c in trsp[0].categories} == {"food", "grocery_ration"}
        saylani = db.scalar(select(Ngo).where(Ngo.name == "Saylani Welfare Trust - Test Branch"))
        db.refresh(saylani)
        assert saylani.phone == "021 111 729 526"
        new = db.scalar(select(Ngo).where(Ngo.name == "Testabad Relief Society"))
        assert not new.location_approx and new.lat == 26.73
    finally:
        db.execute(delete(Ngo).where(Ngo.name.in_(["Test Rural Support Programme", "Saylani Welfare Trust - Test Branch",
                                                  "Testabad Relief Society"])))
        from app.models import Location
        db.execute(delete(Location).where(Location.name == "Testabad"))
        db.commit()
