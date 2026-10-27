"""Phase 3 end-to-end checks: NGOs, donations, accept / reject / cancel. Skipped without TEST_DATABASE_URL."""

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.models import Location, Notification
from tests.test_auth_api import API, auth, make_admin, register


def area(db, name: str) -> str:
    return str(db.scalar(select(Location.id).where(Location.name == name)))


def admin_headers(client, db) -> dict:
    email, pw = make_admin(db)
    return auth(client.post(f"{API}/auth/login", json={"login": email, "password": pw}).json()["access_token"])


def donation_body(db, **extra) -> dict:
    now = datetime.now(timezone.utc)
    return {
        "category_id": 4, "title": "10 blankets", "quantity": 10, "condition": "good",
        "pickup": {"address": "House 14, Block 7, Saddar", "lat": 24.855, "lng": 67.02,
                   "location_id": area(db, "Saddar"),
                   "from": (now + timedelta(hours=1)).isoformat(), "to": (now + timedelta(hours=4)).isoformat()},
        "photo_urls": ["https://res.cloudinary.com/demo/blankets.jpg"],
        **extra,
    }


def make_ngo(client, admin_h, db, name="Noor Welfare Trust", where="Lyari", **extra) -> dict:
    body = {"name": name, "location_id": area(db, where), "address": "Near Chakiwara", "lat": 24.866, "lng": 67.0,
            "phone": "021-111-222", **extra}
    r = client.post(f"{API}/admin/ngos", headers=admin_h, json=body)
    assert r.status_code == 201, r.text
    return r.json()


def test_ngos_crud_access_and_web_search(client, db, monkeypatch):
    admin_h = admin_headers(client, db)
    n = make_ngo(client, admin_h, db, category_ids=[3, 4], website="noortrust.org")
    assert n["location_path"][-1] == "Lyari" and [c["id"] for c in n["categories"]] == [3, 4]
    assert n["found_by"] == "admin" and n["website"] == "https://noortrust.org" and not n["location_approx"]

    # Swapped coordinates are refused
    bad = client.post(f"{API}/admin/ngos", headers=admin_h, json={"name": "X", "location_id": n["location_id"],
                                                                  "address": "Somewhere", "lat": 67.0, "lng": 24.86})
    assert bad.status_code == 422

    upd = client.patch(f"{API}/admin/ngos/{n['id']}", headers=admin_h, json={"takes_cooked_food": True, "category_ids": []})
    assert upd.status_code == 200 and upd.json()["takes_cooked_food"] and upd.json()["categories"] == []

    # Filter by city includes NGOs in its areas; hidden ones only on request
    karachi = area(db, "Karachi")
    assert any(x["id"] == n["id"] for x in client.get(f"{API}/admin/ngos", headers=admin_h, params={"location_id": karachi}).json())
    hidden = make_ngo(client, admin_h, db, name="Closed Trust")
    client.patch(f"{API}/admin/ngos/{hidden['id']}", headers=admin_h, json={"is_active": False})
    assert all(x["id"] != hidden["id"] for x in client.get(f"{API}/admin/ngos", headers=admin_h).json())
    assert any(x["id"] == hidden["id"] for x in client.get(f"{API}/admin/ngos", headers=admin_h, params={"include_hidden": True}).json())

    # Donors and riders cannot see the NGO list
    donor_h = auth(register(client).json()["access_token"])
    assert client.get(f"{API}/admin/ngos", headers=donor_h).status_code == 403
    rider_h = auth(register(client, role="rider").json()["access_token"])
    assert client.get(f"{API}/admin/ngos", headers=rider_h).status_code == 403

    # Web search for NGOs in Hyderabad (the AI and the map lookup are stand-ins: tests never call paid APIs)
    from app.services import llm, ngo_finder
    answer = """```json
{"ngos": [{"name": "Hyderabad Welfare Trust", "address": "Latifabad Unit 7", "phone": "022-1234567",
  "website": "hwt.org.pk", "accepts": ["clothes", "blankets", "spaceships"], "cooked_food": false,
  "about": "Helps poor families.", "source_url": "https://hwt.org.pk/about"},
 {"name": "Sindh Food Bank", "address": "", "accepts": ["food"], "cooked_food": true, "source_url": "https://x.pk"}]}
```"""
    monkeypatch.setattr(llm, "available", lambda: True)
    monkeypatch.setattr(llm, "complete", lambda *a, **k: llm.Answer(text=answer, provider="openai", model="test"))
    monkeypatch.setattr(ngo_finder, "geocode", lambda address, city, centre: (25.39, 68.37) if "Latifabad" in address else None)
    r = client.post(f"{API}/admin/ngos/search", headers=admin_h, json={"location_id": area(db, "Hyderabad")})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["place"] == "Hyderabad" and body["found"] == 2 and body["added"] == 2
    by = {x["name"]: x for x in body["ngos"]}
    trust, bank = by["Hyderabad Welfare Trust"], by["Sindh Food Bank"]
    assert trust["found_by"] == "web_search" and not trust["location_approx"] and [c["id"] for c in trust["categories"]] == [3, 4]
    assert bank["location_approx"] and bank["takes_cooked_food"] and "call first" in bank["address"]
    # Searching again does not add the same NGOs twice
    again = client.post(f"{API}/admin/ngos/search", headers=admin_h, json={"location_id": area(db, "Hyderabad")}).json()
    assert again["added"] == 0 and len([x for x in again["ngos"] if x["name"] == "Hyderabad Welfare Trust"]) == 1


def test_donation_flow_accept(client, db):
    admin_h = admin_headers(client, db)
    near = make_ngo(client, admin_h, db, name="Saddar Trust", where="Saddar", lat=24.856, lng=67.021)
    far = make_ngo(client, admin_h, db, name="Lahore Trust", where="Lahore", lat=31.52, lng=74.35)
    food_only = make_ngo(client, admin_h, db, name="Food Only", where="Saddar", category_ids=[1])

    donor = register(client).json()
    donor_h = auth(donor["access_token"])
    r = client.post(f"{API}/donations", headers=donor_h, json=donation_body(db))
    assert r.status_code == 201, r.text
    d = r.json()
    assert d["status"] == "in_review" and d["ref"].startswith("D-") and d["can_cancel"]
    assert d["pickup"]["location_path"][-1] == "Saddar" and len(d["photos"]) == 1
    assert d["urgency_score"] is None   # not food
    assert d["history"][0]["to_status"] == "in_review"

    # Only donors create; riders cannot see someone else's donation
    rider_h = auth(register(client, role="rider").json()["access_token"])
    assert client.post(f"{API}/donations", headers=rider_h, json=donation_body(db)).status_code == 403
    other_h = auth(register(client).json()["access_token"])
    assert client.get(f"{API}/donations/{d['id']}", headers=other_h).status_code == 404

    mine = client.get(f"{API}/donations/mine", headers=donor_h, params={"filter": "active"}).json()
    assert mine["total"] == 1 and mine["items"][0]["id"] == d["id"]

    # Admin sees it, NGO options are ranked: same area first, the food-only NGO left out
    listed = client.get(f"{API}/admin/donations", headers=admin_h, params={"status": "in_review", "q": "blankets"}).json()
    assert any(i["id"] == d["id"] and i["donor_name"] == "Test User" for i in listed["items"])
    opts = client.get(f"{API}/admin/donations/{d['id']}/ngo-options", headers=admin_h).json()
    ids = [o["id"] for o in opts]
    assert ids.index(near["id"]) < ids.index(far["id"]) and food_only["id"] not in ids
    assert opts[0]["match"] == "same_area"

    # Wrong NGO refused, right one accepted
    assert client.post(f"{API}/admin/donations/{d['id']}/accept", headers=admin_h, json={"ngo_id": food_only["id"]}).status_code == 409
    ok = client.post(f"{API}/admin/donations/{d['id']}/accept", headers=admin_h, json={"ngo_id": near["id"]})
    assert ok.status_code == 200 and ok.json()["status"] == "accepted" and ok.json()["ngo"]["name"] == "Saddar Trust"
    assert ok.json()["ngo_name"] == "Saddar Trust"
    assert ok.json()["history"][-1]["by_name"] == "Admin"

    # Donor was told; cannot reject an accepted donation; donor can still cancel
    notes = db.scalars(select(Notification).where(Notification.user_id == uuid.UUID(donor["user"]["id"]))).all()
    assert any(n.type == "donation_accepted" for n in notes)
    assert client.post(f"{API}/admin/donations/{d['id']}/reject", headers=admin_h, json={"reason": "Too late"}).status_code == 409
    c = client.post(f"{API}/donations/{d['id']}/cancel", headers=donor_h)
    assert c.status_code == 200 and c.json()["status"] == "cancelled" and not c.json()["can_cancel"]
    assert client.post(f"{API}/donations/{d['id']}/cancel", headers=donor_h).status_code == 409

    counts = client.get(f"{API}/admin/donations/counts", headers=admin_h).json()
    assert counts["cancelled"] >= 1


def test_food_urgency_reject_and_validation(client, db):
    admin_h = admin_headers(client, db)
    donor_h = auth(register(client).json()["access_token"])
    prepared = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    food = donation_body(db, category_id=1, title="Cooked rice, 40 plates", quantity=40, is_food=True,
                         food_type="cooked", prepared_at=prepared)
    r = client.post(f"{API}/donations", headers=donor_h, json=food)
    assert r.status_code == 201, r.text
    d = r.json()
    # cooked 35 + 1-3 h 25 + 40 plates 14 (+ distance to the nearest NGO for cooked food, if any)
    assert d["condition"] is None and [x["points"] for x in d["urgency_reasons"]][:3] == [35, 25, 14]
    assert d["urgency_score"] == min(100, sum(x["points"] for x in d["urgency_reasons"]))

    # Food sorts first by urgency
    first = client.get(f"{API}/admin/donations", headers=admin_h, params={"sort": "urgency", "status": "in_review"}).json()["items"][0]
    assert first["urgency_score"] is not None

    # Cooked food cannot go to an NGO that does not take cooked food
    no_food = make_ngo(client, admin_h, db, name="No Food Trust", where="Saddar")
    assert client.post(f"{API}/admin/donations/{d['id']}/accept", headers=admin_h, json={"ngo_id": no_food["id"]}).status_code == 409

    rej = client.post(f"{API}/admin/donations/{d['id']}/reject", headers=admin_h, json={"reason": "Pickup too far for cooked food"})
    assert rej.status_code == 200 and rej.json()["status"] == "rejected"
    assert rej.json()["reject_reason"] == "Pickup too far for cooked food"
    assert client.get(f"{API}/donations/mine", headers=donor_h, params={"filter": "done"}).json()["total"] == 1

    # Validation: food category without type, location outside Pakistan, unknown area
    assert client.post(f"{API}/donations", headers=donor_h, json=donation_body(db, category_id=1)).status_code == 422
    outside = donation_body(db)
    outside["pickup"] = {**outside["pickup"], "lat": 51.5, "lng": -0.12}
    assert client.post(f"{API}/donations", headers=donor_h, json=outside).status_code == 422
    unknown = donation_body(db)
    unknown["pickup"] = {**unknown["pickup"], "location_id": "00000000-0000-4000-8000-000000000000"}
    assert client.post(f"{API}/donations", headers=donor_h, json=unknown).status_code == 422
