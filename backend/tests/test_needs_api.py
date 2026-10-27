"""Phase 6 end-to-end: disaster alerts, what is needed, relief camp, needs by area, data sources.
Skipped without TEST_DATABASE_URL. Nothing here calls the internet."""

from datetime import datetime, timezone

from sqlalchemy import select

from app.models import DisasterAlert, Location, Source
from app.models.enums import AlertSeverity, AlertType, SourceKind
from app.services.sources import gdacs
from tests.test_auth_api import API, auth, register
from tests.test_donations_api import admin_headers, area


def province_row(rows, name):
    return next(r for r in rows["children"] if r["name"] == name)


def need(row, category_id):
    return next((n for n in row["needs"] if n["category_id"] == category_id), None)


def test_alert_flow_and_needs_by_area(client, db):
    admin_h = admin_headers(client, db)
    donor_h = auth(register(client).json()["access_token"])

    # Donors cannot use admin alert pages
    assert client.get(f"{API}/admin/alerts", headers=donor_h).status_code == 403

    # Admin adds a flood in Lyari reported by the field team: confirmed, needs suggested from figures
    body = {"type": "flood", "severity": "severe", "title": "Urban flooding in Lyari", "location_ids": [area(db, "Lyari")],
            "figures": {"families_affected": 100, "deaths": 0}}
    r = client.post(f"{API}/admin/alerts", headers=admin_h, json=body)
    assert r.status_code == 201, r.text
    alert = r.json()
    assert alert["status"] == "confirmed" and alert["figures"] == {"families_affected": 100}
    assert alert["places"][0]["path"][-1] == "Lyari"
    qty = {n["category_id"]: n["quantity_needed"] for n in alert["needs"]}
    assert qty[2] == 100 and qty[4] == 200 and 12 in qty          # 1 ration and 2 blankets per family
    # Recommended donations for a flood: life-saving items first, each with a reason; recovery items advised for later
    rec = {x["name"]: x for x in alert["recommended"]}
    assert alert["recommended"][0]["when"] == "now" and rec["Hygiene items"]["when"] == "now" and rec["Hygiene items"]["listed"]
    assert rec["School supplies"]["when"] == "later" and not rec["School supplies"]["listed"] and alert["families"] == 100

    # Donors see it
    assert any(a["id"] == alert["id"] for a in client.get(f"{API}/alerts", headers=donor_h).json())

    # Needs by area: Sindh shows urgent emergency relief, and the reason names the alert
    top = client.get(f"{API}/needs", headers=donor_h).json()
    sindh = province_row(top, "Sindh")
    assert sindh["max_level"] == 3 and sindh["has_children"]
    relief = need(sindh, 12)
    assert relief["level_name"] == "urgent" and "Lyari" in relief["reasons"][0]["why"]
    # Drill down: Sindh -> Karachi
    inside = client.get(f"{API}/needs", headers=donor_h, params={"parent_id": sindh["id"]}).json()
    assert inside["place"]["name"] == "Sindh" and province_row(inside, "Karachi")["max_level"] == 3
    assert client.get(f"{API}/needs", headers=donor_h, params={"parent_id": "00000000-0000-0000-0000-000000000000"}).status_code == 404

    # Admin edits what is needed: only rations and blankets
    r = client.put(f"{API}/admin/alerts/{alert['id']}/needs", headers=admin_h,
                   json=[{"category_id": 2, "quantity_needed": 150}, {"category_id": 4, "quantity_needed": None}])
    assert r.status_code == 200 and [(n["category_id"], n["quantity_needed"]) for n in r.json()["needs"]] == [(2, 150), (4, None)]
    assert client.put(f"{API}/admin/alerts/{alert['id']}/needs", headers=admin_h, json=[{"category_id": 99}]).status_code == 422

    # Open a relief camp: a temporary point that takes what the alert needs
    camp = {"name": "Lyari Relief Camp", "location_id": area(db, "Lyari"), "address": "Govt school ground, Chakiwara",
            "lat": 24.867, "lng": 67.0, "open_days": 14}
    assert client.post(f"{API}/admin/alerts/{alert['id']}/camp", headers=admin_h, json={**camp, "lat": 67.0, "lng": 24.867}).status_code == 422
    r = client.post(f"{API}/admin/alerts/{alert['id']}/camp", headers=admin_h, json=camp)
    assert r.status_code == 201, r.text
    p = r.json()
    assert p["type"] == "relief_camp" and p["same_day_food"] and p["closes_at"] and sorted(c["id"] for c in p["categories"]) == [2, 4]
    assert client.get(f"{API}/admin/alerts/{alert['id']}", headers=admin_h).json()["camps"][0]["name"] == "Lyari Relief Camp"

    # Confirming again keeps the admin's edits
    r = client.post(f"{API}/admin/alerts/{alert['id']}/status", headers=admin_h, json={"status": "confirmed"})
    assert [n["category_id"] for n in r.json()["needs"]] == [2, 4]

    # Handled: it leaves the donor list and the needs map
    r = client.post(f"{API}/admin/alerts/{alert['id']}/status", headers=admin_h, json={"status": "handled"})
    assert r.status_code == 200 and r.json()["status"] == "handled"
    assert all(a["id"] != alert["id"] for a in client.get(f"{API}/alerts", headers=donor_h).json())
    sindh = province_row(client.get(f"{API}/needs", headers=donor_h).json(), "Sindh")
    assert need(sindh, 12) is None
    assert client.post(f"{API}/admin/alerts/{alert['id']}/camp", headers=admin_h, json=camp).status_code == 409


def test_gdacs_event_becomes_unconfirmed_alert(client, db):
    admin_h = admin_headers(client, db)
    source_id = db.scalar(select(Source.id).where(Source.kind == SourceKind.gdacs))
    key = f"FL{int(datetime.now().timestamp())}"
    event = {"key": key, "type": AlertType.flood, "severity": AlertSeverity.moderate, "name": "Flood in Pakistan",
             "description": "", "started_at": datetime.now(timezone.utc), "lat": 24.9, "lng": 67.05,
             "url": f"https://www.gdacs.org/report.aspx?eventid={key}"}
    assert "1 new alerts" in gdacs.sync(db, [event], source_id)
    # Same event again: not duplicated; a higher level updates it
    assert "0 new alerts, 1 updated" in gdacs.sync(db, [{**event, "severity": AlertSeverity.severe}], source_id)

    a = db.scalar(select(DisasterAlert).where(DisasterAlert.gdacs_event_id == key))
    assert a.status.value == "unconfirmed" and a.severity == AlertSeverity.severe
    assert [l.name for l in a.locations] == ["Karachi"]            # placed by its coordinates
    assert len(a.reports) == 1 and a.reports[0].publisher == "GDACS"

    donor_h = auth(register(client).json()["access_token"])
    assert all(x["id"] != str(a.id) for x in client.get(f"{API}/alerts", headers=donor_h).json())   # not confirmed yet
    listed = client.get(f"{API}/admin/alerts", headers=admin_h, params={"status": "unconfirmed"}).json()
    assert any(x["id"] == str(a.id) and x["from_gdacs"] for x in listed)

    r = client.post(f"{API}/admin/alerts/{a.id}/status", headers=admin_h, json={"status": "confirmed"})
    assert r.status_code == 200 and r.json()["needs"]                # suggested on confirm
    assert any(x["id"] == str(a.id) for x in client.get(f"{API}/alerts", headers=donor_h).json())
    client.post(f"{API}/admin/alerts/{a.id}/status", headers=admin_h, json={"status": "dismissed"})


def test_sources_page(client, db):
    admin_h = admin_headers(client, db)
    rows = client.get(f"{API}/admin/sources", headers=admin_h).json()
    kinds = {r["kind"]: r for r in rows}
    assert kinds["gdacs"]["can_run"] and kinds["web_search"]["can_run"] and not kinds["reliefweb"]["can_run"]
    assert client.post(f"{API}/admin/sources/upload/run", headers=admin_h).status_code == 422
    counts = client.get(f"{API}/admin/alerts/counts", headers=admin_h).json()
    assert set(counts) == {"unconfirmed", "confirmed", "handled", "dismissed"}
    assert db.scalar(select(Location).where(Location.name == "Karachi")).lat is not None   # seed filled coordinates
