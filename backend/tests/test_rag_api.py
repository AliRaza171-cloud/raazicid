"""Phase 6B end-to-end: report library, keyword search, need finder (Claude stubbed), appeals, notifications.
Skipped without TEST_DATABASE_URL. Nothing here calls the internet or Claude."""

import uuid

from app.core.config import settings
from app.models import User
from app.services import llm
from app.services.rag import finder
from app.services.rag.search import search
from tests.test_auth_api import API, auth, register
from tests.test_donations_api import admin_headers, area

REPORT = ("Winter needs assessment, Karachi.\n"
          + "In Lyari many families sleep without blankets and warm clothes as temperatures fall at night. " * 12
          + "\nIn Saddar the main need is hygiene kits for street children. " * 8)


def upload(client, admin_h, text=REPORT, name="winter-needs.txt", **form):
    return client.post(f"{API}/admin/reports/upload", headers=admin_h, files={"file": (name, text.encode(), "text/plain")}, data=form)


def test_library_search_and_need_finder(client, db, monkeypatch):
    monkeypatch.setattr(settings, "ENABLE_EMBEDDINGS", False)   # keyword search only: no model download in tests
    admin_h = admin_headers(client, db)
    donor_h = auth(register(client).json()["access_token"])
    assert client.get(f"{API}/admin/reports", headers=donor_h).status_code == 403

    r = upload(client, admin_h, publisher="RAAZICID field team", published_at="2026-10-20")
    assert r.status_code == 201, r.text
    rep = r.json()
    assert rep["chunks"] >= 1 and rep["status"] == "tagged" and rep["publisher"] == "RAAZICID field team"
    tagged = {p["name"] for c in rep["chunk_list"] for p in c["places"]}
    assert {"Lyari", "Saddar"} <= tagged

    # Same text again is refused; wrong file type too
    assert upload(client, admin_h).status_code == 409
    assert upload(client, admin_h, name="photo.jpg").status_code == 422

    # Keyword search, with and without a place filter
    hits = search(db, "Where are blankets needed?", None)
    assert hits and "blankets" in hits[0].text and hits[0].how == ["words"]
    assert search(db, "blankets", uuid.UUID(area(db, "Lyari")))
    assert client.get(f"{API}/admin/rag/status", headers=admin_h).json()["search"] == "keyword"

    # Fix a passage's places by hand
    chunk = rep["chunk_list"][0]
    fixed = client.put(f"{API}/admin/chunks/{chunk['id']}/places", headers=admin_h, json={"location_ids": [area(db, "Lyari")]}).json()
    assert [p["name"] for p in fixed["places"]] == ["Lyari"] and fixed["places"][0]["confirmed"]

    # Need finder without an AI key: passages and need levels only
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "")
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "")
    monkeypatch.setattr(settings, "AI_PROVIDER", "")
    out = client.post(f"{API}/admin/need-finder/ask", headers=admin_h, json={"question": "Where are blankets needed in Karachi?", "category_id": 4}).json()
    assert out["ai"] is False and out["sources"] and out["sources"][0]["id"] == "S1"

    # Need finder with Claude stubbed: answer, citations and areas matched to our places
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "test-key")
    sent = {}

    def fake_complete(prompt, **kw):
        sent["prompt"] = prompt
        sent["web"] = kw.get("web")
        return llm.Answer(text='```json\n{"summary": "Lyari needs blankets [S1].", "areas": [{"name": "Lyari", '
                               '"need": "urgent", "categories": ["Blankets"], "reason": "Families sleep without blankets [S1].", '
                               '"sources": ["S1"]}], "confidence": "medium"}\n```')

    monkeypatch.setattr(finder.llm, "complete", fake_complete)
    out = client.post(f"{API}/admin/need-finder/ask", headers=admin_h,
                      json={"question": "Where are blankets needed in Karachi?", "location_id": area(db, "Karachi"), "category_id": 4,
                            "web_search": True}).json()
    assert out["ai"] and out["answer"] == "Lyari needs blankets [S1]." and out["sources"][0]["cited"]
    assert out["areas"][0]["path"][-1] == "Lyari" and out["areas"][0]["location_id"] == area(db, "Lyari")
    assert "[S1]" in sent["prompt"] and "Focus on: Sindh › Karachi" in sent["prompt"] and sent["web"]["max_uses"] == 4

    # Archive: the need finder stops using it
    assert client.post(f"{API}/admin/reports/{rep['id']}/archive", headers=admin_h).json()["status"] == "archived"
    assert not search(db, "blankets Lyari", None)
    assert client.post(f"{API}/admin/reports/{rep['id']}/restore", headers=admin_h).json()["status"] == "tagged"


def test_appeal_reaches_donors_in_the_province(client, db):
    admin_h = admin_headers(client, db)
    sindh_donor = register(client).json()
    punjab_donor = register(client).json()
    for data, place in ((sindh_donor, "Lyari"), (punjab_donor, "Lahore")):
        u = db.get(User, uuid.UUID(data["user"]["id"]))
        u.location_id = uuid.UUID(area(db, place))
    db.commit()
    sindh_h, punjab_h = auth(sindh_donor["access_token"]), auth(punjab_donor["access_token"])

    body = {"title": "Blankets for Lyari", "message": "Nights are cold and many families have no blankets.",
            "location_id": area(db, "Lyari"), "category_ids": [4, 5], "days": 7}
    r = client.post(f"{API}/admin/appeals", headers=admin_h, json=body)
    assert r.status_code == 201, r.text
    appeal = r.json()
    assert appeal["provinces"] == ["Sindh"] and appeal["live"] and appeal["reached"] >= 1
    assert [c["name"] for c in appeal["categories"]] == ["Blankets", "Winter support"]

    # Only the Sindh donor sees it and gets a notification
    assert any(a["id"] == appeal["id"] for a in client.get(f"{API}/appeals/active", headers=sindh_h).json())
    assert all(a["id"] != appeal["id"] for a in client.get(f"{API}/appeals/active", headers=punjab_h).json())
    inbox = client.get(f"{API}/me/notifications", headers=sindh_h).json()
    note = next(n for n in inbox["items"] if n["type"] == "appeal")
    assert inbox["unread"] >= 1 and note["data"]["appeal_id"] == appeal["id"] and "Blankets" in note["body"]
    assert all(n["type"] != "appeal" or n["data"]["appeal_id"] != appeal["id"] for n in client.get(f"{API}/me/notifications", headers=punjab_h).json()["items"])
    assert client.post(f"{API}/me/notifications/read", headers=sindh_h).json()["unread"] == 0
    assert client.get(f"{API}/me/notifications", headers=sindh_h).json()["unread"] == 0

    # A province must be a province; ending stops it
    bad = client.post(f"{API}/admin/appeals", headers=admin_h, json={**body, "province_ids": [area(db, "Karachi")]})
    assert bad.status_code == 422
    ended = client.post(f"{API}/admin/appeals/{appeal['id']}/end", headers=admin_h).json()
    assert not ended["live"]
    assert all(a["id"] != appeal["id"] for a in client.get(f"{API}/appeals/active", headers=sindh_h).json())
    assert any(a["id"] == appeal["id"] for a in client.get(f"{API}/admin/appeals", headers=admin_h).json())

    # All Pakistan reaches the Punjab donor too
    everyone = client.post(f"{API}/admin/appeals", headers=admin_h, json={**body, "title": "Winter appeal", "all_pakistan": True}).json()
    assert everyone["provinces"] == ["All Pakistan"]
    assert any(a["id"] == everyone["id"] for a in client.get(f"{API}/appeals/active", headers=punjab_h).json())
    client.post(f"{API}/admin/appeals/{everyone['id']}/end", headers=admin_h)
