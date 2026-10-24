"""Phase 5 rules without a database: rider score, food urgency, classifier status, AI review parsing."""

from datetime import datetime, timedelta, timezone

from app.models.enums import FoodType
from app.services.classifier import Classifier
from app.services.doc_review import _parse
from app.services.recommend import RiderFacts, load_size, score_rider
from app.services.urgency import food_urgency

NOW = datetime(2026, 10, 24, 12, 0, tzinfo=timezone.utc)


def facts(**kw):
    base = dict(distance_km=None, area_match="other", active_jobs=0, is_available=True, rating_avg=None, vehicle="motorbike")
    return RiderFacts(**{**base, **kw})


def test_rider_score_prefers_near_free_available():
    near, _ = score_rider(facts(distance_km=1.0), 3, "clothes")
    far, _ = score_rider(facts(distance_km=12.0), 3, "clothes")
    busy, _ = score_rider(facts(distance_km=1.0, active_jobs=3), 3, "clothes")
    off, _ = score_rider(facts(distance_km=1.0, is_available=False), 3, "clothes")
    assert near > far and near > busy and near > off
    assert 0 <= far <= near <= 100


def test_rider_score_parts_add_up():
    score, reasons = score_rider(facts(distance_km=0.0, rating_avg=5.0), 2, "books")
    assert score == sum(p for _, p in reasons) == 100   # 40 + 20 + 15 + 15 + 10


def test_area_used_without_gps():
    same_area, r = score_rider(facts(area_match="same_area"), 2, "books")
    other, _ = score_rider(facts(area_match="other"), 2, "books")
    assert same_area - other == 30 and "same area" in r[0][0]


def test_vehicle_fit():
    assert load_size(40, "clothes") == "large" and load_size(10, "blankets") == "large"
    assert load_size(8, "clothes") == "medium" and load_size(2, "books") == "small"
    pickup, _ = score_rider(facts(vehicle="pickup"), 30, "blankets")
    bike, _ = score_rider(facts(vehicle="motorbike"), 30, "blankets")
    assert pickup > bike


def test_food_urgency_rules():
    assert food_urgency(False, None, None, 10, NOW) == (None, [])
    score, reasons = food_urgency(True, FoodType.cooked, NOW - timedelta(hours=2), 40, NOW, point_distance_km=1.8)
    assert [p for _, p in reasons] == [35, 25, 14, 12] and score == 86
    dry, _ = food_urgency(True, FoodType.dry, None, 5, NOW, point_distance_km=1.0)
    assert dry == 7   # no distance points for dry food


def test_food_urgency_warning_and_cap():
    score, reasons = food_urgency(True, FoodType.cooked, NOW - timedelta(hours=9), 200, NOW, point_distance_km=0.5)
    assert score == 100   # capped
    assert any("Warning" in label for label, _ in reasons)
    _, no_point = food_urgency(True, FoodType.cooked, NOW, 5, NOW, point_distance_km=None)
    assert no_point[-1] == ("No open point for cooked food yet", 0)


def test_classifier_without_model(tmp_path):
    status = Classifier(str(tmp_path)).status()
    assert status["classifier"] in ("not_installed", "no_model") and status["version"] is None


def test_review_parsing_handles_extra_text():
    out = _parse('Here you go:\n{"summary": "Looks fine", "checks": [{"label": "Readable", "ok": true, "detail": ""},'
                 ' {"label": "Name", "ok": "maybe", "detail": "unclear"}]}')
    assert out["summary"] == "Looks fine"
    assert [c["ok"] for c in out["checks"]] == [True, None]
