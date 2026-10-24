"""Phase 2 end-to-end checks against a real (test) database. Skipped without TEST_DATABASE_URL."""

import uuid

from sqlalchemy import select

from app.core.security import hash_password
from app.models import Location, User
from app.models.enums import Role

API = "/api/v1"


def unique_phone() -> str:
    return "03" + str(uuid.uuid4().int)[:9]


def register(client, role="donor", **extra):
    body = {"role": role, "full_name": "Test User", "phone": unique_phone(), "password": "password123", **extra}
    if role == "rider" and "rider" not in body:
        body["rider"] = {"vehicle_type": "motorbike", "vehicle_number": "khi-4821"}
    return client.post(f"{API}/auth/register", json=body)


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def make_admin(db) -> tuple[str, str]:
    phone, email = unique_phone(), f"admin-{uuid.uuid4().hex[:6]}@raazicid.pk"
    db.add(User(role=Role.admin, full_name="Admin", phone=phone, email=email, password_hash=hash_password("adminpass1")))
    db.commit()
    return email, "adminpass1"


def test_donor_register_login_me(client, db):
    lyari = db.scalar(select(Location).where(Location.name == "Lyari"))
    r = register(client, location_id=str(lyari.id), email="Sana@Example.com")
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["user"]["role"] == "donor"
    assert data["user"]["location_path"] == ["Sindh", "Karachi", "Karachi South", "Lyari"]
    assert data["user"]["email"] == "sana@example.com"

    phone = data["user"]["phone"]
    by_phone = client.post(f"{API}/auth/login", json={"login": phone[:4] + " " + phone[4:], "password": "password123"})
    assert by_phone.status_code == 200
    by_email = client.post(f"{API}/auth/login", json={"login": "SANA@example.com", "password": "password123"})
    assert by_email.status_code == 200

    me = client.get(f"{API}/me", headers=auth(by_email.json()["access_token"]))
    assert me.status_code == 200 and me.json()["phone"] == phone


def test_wrong_password_and_duplicates(client):
    r = register(client)
    phone = r.json()["user"]["phone"]
    bad = client.post(f"{API}/auth/login", json={"login": phone, "password": "nope-nope"})
    assert bad.status_code == 401 and bad.json()["detail"]["code"] == "wrong_login"
    dup = client.post(f"{API}/auth/register", json={"role": "donor", "full_name": "Other", "phone": phone, "password": "password123"})
    assert dup.status_code == 409 and dup.json()["detail"]["code"] == "phone_taken"


def test_refresh_rotates_and_logout_revokes(client):
    tokens = register(client).json()
    first = client.post(f"{API}/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert first.status_code == 200
    again = client.post(f"{API}/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert again.status_code == 401   # old refresh token no longer works
    new_refresh = first.json()["refresh_token"]
    assert client.post(f"{API}/auth/logout", json={"refresh_token": new_refresh}).status_code == 204
    assert client.post(f"{API}/auth/refresh", json={"refresh_token": new_refresh}).status_code == 401


def test_me_requires_login(client):
    assert client.get(f"{API}/me").status_code == 401
    assert client.get(f"{API}/me", headers=auth("garbage")).status_code == 401


def test_update_profile_location(client, db):
    tokens = register(client).json()
    orangi = db.scalar(select(Location).where(Location.name == "Orangi Town"))
    r = client.patch(f"{API}/me", headers=auth(tokens["access_token"]), json={"location_id": str(orangi.id), "full_name": "New  Name"})
    assert r.status_code == 200
    assert r.json()["location_path"][-1] == "Orangi Town" and r.json()["full_name"] == "New Name"


def test_rider_verification_flow(client, db):
    rider = register(client, role="rider").json()
    assert rider["user"]["rider_status"] == "pending"
    rider_h = auth(rider["access_token"])

    # A donor cannot use rider or admin endpoints
    donor_h = auth(register(client).json()["access_token"])
    assert client.get(f"{API}/me/rider-documents", headers=donor_h).status_code == 403
    assert client.get(f"{API}/admin/riders", headers=donor_h).status_code == 403

    admin_email, admin_pw = make_admin(db)
    admin_h = auth(client.post(f"{API}/auth/login", json={"login": admin_email, "password": admin_pw}).json()["access_token"])
    rid = rider["user"]["id"]

    # Cannot approve before any document
    r = client.post(f"{API}/admin/riders/{rid}/decision", headers=admin_h, json={"action": "approve"})
    assert r.status_code == 409

    for doc in ["cnic_front", "cnic_back", "driving_licence", "vehicle_registration"]:
        up = client.post(f"{API}/me/rider-documents", headers=rider_h, json={"doc_type": doc, "file_url": f"https://res.cloudinary.com/demo/{doc}.jpg"})
        assert up.status_code == 201, up.text
    # Re-uploading replaces, not duplicates
    client.post(f"{API}/me/rider-documents", headers=rider_h, json={"doc_type": "cnic_front", "file_url": "https://res.cloudinary.com/demo/new.jpg"})
    assert len(client.get(f"{API}/me/rider-documents", headers=rider_h).json()) == 4

    pending = client.get(f"{API}/admin/riders", headers=admin_h, params={"status": "pending"}).json()
    assert any(item["id"] == rid for item in pending["items"])

    ask = client.post(f"{API}/admin/riders/{rid}/decision", headers=admin_h,
                      json={"action": "request_document", "note": "Licence expired"})
    assert ask.status_code == 200 and ask.json()["review_note"] == "Licence expired"
    assert client.get(f"{API}/me", headers=rider_h).json()["rider_note"] == "Licence expired"

    ok = client.post(f"{API}/admin/riders/{rid}/decision", headers=admin_h, json={"action": "approve"})
    assert ok.status_code == 200 and ok.json()["status"] == "approved"
    assert client.get(f"{API}/me", headers=rider_h).json()["rider_status"] == "approved"

    counts = client.get(f"{API}/admin/riders/counts", headers=admin_h).json()
    assert counts["approved"] >= 1
