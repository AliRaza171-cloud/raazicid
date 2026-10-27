"""Phase 4 end-to-end: assign rider, accept, GPS, pickup proof, delivery to the NGO, decline, cancel.
Skipped without TEST_DATABASE_URL."""

import uuid

from sqlalchemy import select

from app.models import FraudFlag, Notification, RiderProfile
from app.models.enums import RiderStatus
from tests.test_auth_api import API, auth, register
from app.models import Ngo
from tests.test_donations_api import admin_headers, donation_body, make_ngo

PHOTO = "https://res.cloudinary.com/demo/proof.jpg"


def approved_rider(client, db) -> tuple[dict, str]:
    data = register(client, role="rider").json()
    rp = db.get(RiderProfile, uuid.UUID(data["user"]["id"]))
    rp.status = RiderStatus.approved
    db.commit()
    return auth(data["access_token"]), data["user"]["id"]


def accepted_donation(client, db, admin_h) -> tuple[dict, dict, dict]:
    ngo = make_ngo(client, admin_h, db, name=f"Trust {uuid.uuid4().hex[:4]}", where="Saddar", lat=24.86, lng=67.03)
    donor_h = auth(register(client).json()["access_token"])
    d = client.post(f"{API}/donations", headers=donor_h, json=donation_body(db)).json()
    ok = client.post(f"{API}/admin/donations/{d['id']}/accept", headers=admin_h, json={"ngo_id": ngo["id"]})
    assert ok.status_code == 200, ok.text
    return d, donor_h, ngo


def test_full_delivery_flow(client, db):
    admin_h = admin_headers(client, db)
    d, donor_h, ngo = accepted_donation(client, db, admin_h)
    rider_h, rider_id = approved_rider(client, db)
    other_h, _ = approved_rider(client, db)

    # Unapproved riders cannot be assigned or use the rider app
    pending = register(client, role="rider").json()
    assert client.get(f"{API}/rider/jobs", headers=auth(pending["access_token"])).status_code == 403
    bad = client.post(f"{API}/admin/donations/{d['id']}/assign", headers=admin_h, json={"rider_id": pending["user"]["id"]})
    assert bad.status_code == 422

    # Rider goes available and shows up first in the options
    assert client.patch(f"{API}/rider/availability", headers=rider_h, json={"is_available": True}).json()["is_available"]
    opts = client.get(f"{API}/admin/donations/{d['id']}/rider-options", headers=admin_h).json()
    assert opts[0]["is_available"] and any(o["id"] == rider_id for o in opts)

    r = client.post(f"{API}/admin/donations/{d['id']}/assign", headers=admin_h, json={"rider_id": rider_id})
    assert r.status_code == 200 and r.json()["status"] == "rider_assigned" and r.json()["job"]["rider_id"] == rider_id

    jobs = client.get(f"{API}/rider/jobs", headers=rider_h).json()
    assert jobs["total"] == 1
    job = jobs["items"][0]
    assert job["status"] == "assigned" and job["donor_phone"] is None and job["ngo"]["name"] == ngo["name"]
    jid = job["id"]

    # Another rider cannot touch this job; nothing before accepting
    assert client.post(f"{API}/rider/jobs/{jid}/accept", headers=other_h).status_code == 404
    assert client.post(f"{API}/rider/jobs/{jid}/pickup", headers=rider_h, json={"photo_url": PHOTO, "lat": 24.855, "lng": 67.02}).status_code == 409

    acc = client.post(f"{API}/rider/jobs/{jid}/accept", headers=rider_h).json()
    assert acc["status"] == "accepted" and acc["donor_phone"]

    assert client.post(f"{API}/rider/jobs/{jid}/ping", headers=rider_h, json={"lat": 24.85, "lng": 67.01}).status_code == 204
    t = client.get(f"{API}/donations/{d['id']}/tracking", headers=donor_h).json()
    assert t["heading_to"] == "pickup" and t["last"]["lat"] == 24.85 and t["rider"]["vehicle_type"] == "motorbike"
    assert not t["stalled"]
    live = client.get(f"{API}/admin/tracking", headers=admin_h).json()
    assert any(i["job_id"] == jid for i in live)

    # Pickup proof 3+ km from the donor's address -> fraud flag, but the step still goes through
    up = client.post(f"{API}/rider/jobs/{jid}/pickup", headers=rider_h, json={"photo_url": PHOTO, "lat": 24.88, "lng": 67.05})
    assert up.status_code == 200 and up.json()["status"] == "picked_up"
    flags = db.scalars(select(FraudFlag).where(FraudFlag.entity_id == uuid.UUID(jid))).all()
    assert [f.rule_code for f in flags] == ["far_from_pickup"]

    # Delivery at the NGO: the last step, no flag
    t = client.get(f"{API}/donations/{d['id']}/tracking", headers=donor_h).json()
    assert t["heading_to"] == "ngo" and t["ngo"]["name"] == ngo["name"]
    dl = client.post(f"{API}/rider/jobs/{jid}/deliver", headers=rider_h, json={"photo_url": PHOTO, "lat": 24.8601, "lng": 67.0301})
    assert dl.status_code == 200 and dl.json()["status"] == "delivered" and dl.json()["donation_status"] == "delivered"
    assert client.post(f"{API}/rider/jobs/{jid}/ping", headers=rider_h, json={"lat": 24.86, "lng": 67.03}).status_code == 409
    assert client.get(f"{API}/rider/jobs", headers=rider_h).json()["total"] == 0

    out = client.get(f"{API}/donations/{d['id']}", headers=donor_h).json()
    assert out["status"] == "delivered" and out["ngo"]["name"] == ngo["name"]
    assert {p["kind"] for p in out["proofs"]} == {"pickup_proof", "delivery_proof"}
    pickup_proof = next(p for p in out["proofs"] if p["kind"] == "pickup_proof")
    assert pickup_proof["distance_km"] > 1
    assert [h["to_status"] for h in out["history"]][-3:] == ["rider_assigned", "picked_up", "delivered"]

    summary = client.get(f"{API}/rider/summary", headers=rider_h).json()
    assert summary["done_today"] == 1 and summary["active_jobs"] == 0
    assert client.get(f"{API}/rider/jobs", headers=rider_h, params={"filter": "history"}).json()["total"] == 1

    # Donor was told at each step
    donor_id = client.get(f"{API}/me", headers=donor_h).json()["id"]
    types = {n.type for n in db.scalars(select(Notification).where(Notification.user_id == uuid.UUID(donor_id)))}
    assert {"donation_rider_assigned", "donation_picked_up", "donation_delivered"} <= types


def test_first_delivery_fixes_an_approximate_ngo_location(client, db):
    admin_h = admin_headers(client, db)
    d, donor_h, ngo = accepted_donation(client, db, admin_h)
    row = db.get(Ngo, uuid.UUID(ngo["id"]))
    row.location_approx = True   # found on the web with only the city centre
    db.commit()
    rider_h, rider_id = approved_rider(client, db)
    client.post(f"{API}/admin/donations/{d['id']}/assign", headers=admin_h, json={"rider_id": rider_id})
    jid = client.get(f"{API}/rider/jobs", headers=rider_h).json()["items"][0]["id"]
    assert client.get(f"{API}/rider/jobs/{jid}", headers=rider_h).json()["ngo"]["approx"]
    client.post(f"{API}/rider/jobs/{jid}/accept", headers=rider_h)
    client.post(f"{API}/rider/jobs/{jid}/pickup", headers=rider_h, json={"photo_url": PHOTO, "lat": 24.855, "lng": 67.02})
    far = client.post(f"{API}/rider/jobs/{jid}/deliver", headers=rider_h, json={"photo_url": PHOTO, "lat": 24.9, "lng": 67.1})
    assert far.status_code == 200
    db.expire_all()
    row = db.get(Ngo, uuid.UUID(ngo["id"]))
    assert not row.location_approx and (row.lat, row.lng) == (24.9, 67.1)
    assert not db.scalars(select(FraudFlag).where(FraudFlag.entity_id == uuid.UUID(jid), FraudFlag.rule_code == "far_from_ngo")).all()


def test_decline_and_cancel_job(client, db):
    admin_h = admin_headers(client, db)
    d, donor_h, _ = accepted_donation(client, db, admin_h)
    rider_h, rider_id = approved_rider(client, db)

    client.post(f"{API}/admin/donations/{d['id']}/assign", headers=admin_h, json={"rider_id": rider_id})
    # Cannot assign twice
    assert client.post(f"{API}/admin/donations/{d['id']}/assign", headers=admin_h, json={"rider_id": rider_id}).status_code == 409
    jid = client.get(f"{API}/rider/jobs", headers=rider_h).json()["items"][0]["id"]

    dec = client.post(f"{API}/rider/jobs/{jid}/decline", headers=rider_h, json={"reason": "Bike broke down"})
    assert dec.status_code == 200 and dec.json()["status"] == "declined"
    detail = client.get(f"{API}/donations/{d['id']}", headers=admin_h).json()
    assert detail["status"] == "accepted" and detail["job"] is None
    assert detail["history"][-1]["note"] == "Rider declined: Bike broke down"

    # Reassign, then the admin cancels it
    client.post(f"{API}/admin/donations/{d['id']}/assign", headers=admin_h, json={"rider_id": rider_id})
    c = client.post(f"{API}/admin/donations/{d['id']}/cancel-job", headers=admin_h, json={"reason": "Not moving for an hour"})
    assert c.status_code == 200 and c.json()["status"] == "accepted"
    assert client.get(f"{API}/rider/jobs", headers=rider_h).json()["total"] == 0
    # The donor can still cancel now
    assert client.post(f"{API}/donations/{d['id']}/cancel", headers=donor_h).json()["status"] == "cancelled"
