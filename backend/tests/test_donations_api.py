"""Phase 3 end-to-end checks: points, donations, accept / reject / cancel. Skipped without TEST_DATABASE_URL."""

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


def make_point(client, admin_h, db, name="Noor Community Point", where="Lyari", **extra) -> dict:
    body = {"name": name, "type": "mosque", "location_id": area(db, where), "address": "Near Chakiwara",
            "lat": 24.866, "lng": 67.0, "contact_name": "Bilal", "contact_phone": "0300-1112223", **extra}
    r = client.post(f"{API}/admin/points", headers=admin_h, json=body)
    assert r.status_code == 201, r.text
    return r.json()


def test_points_crud_and_access(client, db):
    admin_h = admin_headers(client, db)
    p = make_point(client, admin_h, db, category_ids=[3, 4])
    assert p["location_path"][-1] == "Lyari" and [c["id"] for c in p["categories"]] == [3, 4]
    assert p["contact_phone"] == "03001112223"

    # Swapped coordinates are refused
    bad = client.post(f"{API}/admin/points", headers=admin_h, json={**{k: p[k] for k in ("name", "type", "location_id", "address")}, "lat": 67.0, "lng": 24.86})
    assert bad.status_code == 422

    upd = client.patch(f"{API}/admin/points/{p['id']}", headers=admin_h, json={"same_day_food": True, "category_ids": []})
    assert upd.status_code == 200 and upd.json()["same_day_food"] and upd.json()["categories"] == []

    # Filter by city includes points in its areas
    karachi = area(db, "Karachi")
    assert any(x["id"] == p["id"] for x in client.get(f"{API}/points", headers=admin_h, params={"location_id": karachi}).json())

    # Donors and unapproved riders cannot see points
    donor_h = auth(register(client).json()["access_token"])
    assert client.get(f"{API}/points", headers=donor_h).status_code == 403
    rider_h = auth(register(client, role="rider").json()["access_token"])
    assert client.get(f"{API}/points", headers=rider_h).status_code == 403

    # Point requests
    req = client.post(f"{API}/points/{p['id']}/requests", headers=admin_h, json={"category_id": 4, "quantity": 50, "note": "Cold nights"})
    assert req.status_code == 201
    detail = client.get(f"{API}/points/{p['id']}", headers=admin_h).json()
    assert detail["open_requests"] == 1 and detail["requests"][0]["category"]["name"] == "Blankets"
    done = client.patch(f"{API}/admin/point-requests/{req.json()['id']}", headers=admin_h, json={"status": "fulfilled"})
    assert done.status_code == 200 and done.json()["status"] == "fulfilled"


def test_donation_flow_accept(client, db):
    admin_h = admin_headers(client, db)
    near = make_point(client, admin_h, db, name="Saddar Hall", where="Saddar", lat=24.856, lng=67.021)
    far = make_point(client, admin_h, db, name="Lahore Hall", where="Lahore", lat=31.52, lng=74.35)
    food_only = make_point(client, admin_h, db, name="Food Only", where="Saddar", category_ids=[1])

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

    # Admin sees it, options are ranked: same area first, food-only point left out
    listed = client.get(f"{API}/admin/donations", headers=admin_h, params={"status": "in_review", "q": "blankets"}).json()
    assert any(i["id"] == d["id"] and i["donor_name"] == "Test User" for i in listed["items"])
    opts = client.get(f"{API}/admin/donations/{d['id']}/point-options", headers=admin_h).json()
    ids = [o["id"] for o in opts]
    assert ids.index(near["id"]) < ids.index(far["id"]) and food_only["id"] not in ids
    assert opts[0]["match"] == "same_area"

    # Wrong point refused, right point accepted
    assert client.post(f"{API}/admin/donations/{d['id']}/accept", headers=admin_h, json={"point_id": food_only["id"]}).status_code == 409
    ok = client.post(f"{API}/admin/donations/{d['id']}/accept", headers=admin_h, json={"point_id": near["id"]})
    assert ok.status_code == 200 and ok.json()["status"] == "accepted" and ok.json()["point"]["name"] == "Saddar Hall"
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
    assert d["urgency_score"] == 74 and d["condition"] is None
    assert [x["points"] for x in d["urgency_reasons"]] == [35, 25, 14]

    # Food sorts first by urgency
    first = client.get(f"{API}/admin/donations", headers=admin_h, params={"sort": "urgency", "status": "in_review"}).json()["items"][0]
    assert first["urgency_score"] is not None

    # Cooked food cannot go to a point without same-day food
    no_food = make_point(client, admin_h, db, name="No Food Point", where="Saddar")
    assert client.post(f"{API}/admin/donations/{d['id']}/accept", headers=admin_h, json={"point_id": no_food["id"]}).status_code == 409

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
