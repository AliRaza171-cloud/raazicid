"""Phase 5 endpoints against the test database. Skipped without TEST_DATABASE_URL."""

from app.services.classifier import classifier
from tests.test_auth_api import API, auth, register
from tests.test_donations_api import admin_headers, donation_body
from tests.test_jobs_api import accepted_donation, approved_rider


def test_classify_and_ai_stats(client, db):
    admin_h = admin_headers(client, db)
    donor_h = auth(register(client).json()["access_token"])

    status = client.get(f"{API}/ai/status", headers=donor_h).json()
    assert status["classifier"] in ("ready", "not_installed", "no_model")

    r = client.post(f"{API}/ai/classify", headers=donor_h, json={"image_url": "https://example.com/x.jpg"})
    if not classifier.ready:
        assert r.status_code == 503
    else:
        assert r.status_code == 422   # only our own Cloudinary uploads are fetched

    # Donor kept the AI's first choice on one donation and changed it on another
    ai_kept = {"category_id": 4, "confidence": 0.9, "top3": [{"category_id": 4, "p": 0.9}, {"category_id": 5, "p": 0.07}]}
    ai_changed = {"category_id": 3, "confidence": 0.6, "top3": [{"category_id": 3, "p": 0.6}, {"category_id": 4, "p": 0.3}]}
    assert client.post(f"{API}/donations", headers=donor_h, json=donation_body(db, ai=ai_kept)).status_code == 201
    assert client.post(f"{API}/donations", headers=donor_h, json=donation_body(db, ai=ai_changed)).status_code == 201

    s = client.get(f"{API}/admin/ai/stats", headers=admin_h).json()
    assert s["donations_with_ai"] >= 2 and s["top1_kept"] >= 1 and s["top3_hit"] >= 2
    assert client.get(f"{API}/admin/ai/stats", headers=donor_h).status_code == 403


def test_rider_options_have_scores_and_job_keeps_it(client, db):
    admin_h = admin_headers(client, db)
    d, _, _ = accepted_donation(client, db, admin_h)
    rider_h, rider_id = approved_rider(client, db)
    client.patch(f"{API}/rider/availability", headers=rider_h, json={"is_available": True})

    opts = client.get(f"{API}/admin/donations/{d['id']}/rider-options", headers=admin_h).json()
    scores = [o["score"] for o in opts]
    assert scores == sorted(scores, reverse=True)
    mine = next(o for o in opts if o["id"] == rider_id)
    assert mine["score"] == min(100, sum(r["points"] for r in mine["reasons"]))

    client.post(f"{API}/admin/donations/{d['id']}/assign", headers=admin_h, json={"rider_id": rider_id})
    from app.models import Job
    from sqlalchemy import select
    import uuid
    job = db.scalars(select(Job).where(Job.donation_id == uuid.UUID(d["id"]))).first()
    db.refresh(job)
    assert job.recommendation_score == mine["score"]


def test_ai_review_needs_key(client, db):
    from app.core.config import settings
    admin_h = admin_headers(client, db)
    rider = register(client, role="rider").json()
    r = client.post(f"{API}/admin/riders/{rider['user']['id']}/ai-review", headers=admin_h)
    # Without a key, or without documents, the admin gets a clear message instead of a crash
    if not settings.ANTHROPIC_API_KEY:
        assert r.status_code == 503 and "ANTHROPIC_API_KEY" in r.json()["detail"]["message"]
    else:
        assert r.status_code == 503 and "documents" in r.json()["detail"]["message"]
