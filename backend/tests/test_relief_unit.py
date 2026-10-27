"""What to donate for each disaster type, without a database: priorities, season, time, quantities."""

from datetime import date

from app.models.enums import AlertSeverity as S, AlertType as T
from app.services.relief import RULES, alert_slugs, recommend

ALL_12 = {"food", "grocery_ration", "clothes", "blankets", "winter_support", "hygiene", "baby", "household",
          "school_supplies", "books", "mobility_aids", "emergency_relief"}


def test_every_rule_uses_our_categories_and_has_a_reason():
    for kind, rules in RULES.items():
        assert rules, kind
        for r in rules:
            assert r.slug in ALL_12 and r.when in ("now", "soon", "later") and len(r.why) > 15


def test_flood_in_autumn_with_families():
    advice, notes = recommend(T.flood, S.severe, date(2026, 10, 1), date(2026, 9, 28), families=100)
    assert [a.slug for a in advice if a.when == "now"] == ["emergency_relief", "food", "hygiene", "grocery_ration"]
    by = {a.slug: a for a in advice}
    assert by["grocery_ration"].quantity == 100 and by["blankets"].quantity == 200 and by["blankets"].when == "soon"
    assert by["school_supplies"].when == "later" and notes == []


def test_winter_earthquake_needs_warm_items_now_and_wheelchairs():
    advice, notes = recommend(T.earthquake, S.severe, date(2026, 12, 10), date(2026, 12, 9))
    by = {a.slug: a for a in advice}
    assert by["winter_support"].when == "now" and by["blankets"].when == "now" and by["mobility_aids"].when == "now"
    assert any("winter" in n for n in notes) and by["blankets"].quantity is None   # no figures: no quantities


def test_winter_adds_warm_items_to_a_flood_and_recovery_later():
    advice, notes = recommend(T.flood, S.moderate, date(2027, 1, 30), date(2027, 1, 2), families=10)
    by = {a.slug: a for a in advice}
    assert by["winter_support"].when == "now" and by["winter_support"].quantity == 10
    assert by["food"].when == "soon" and by["grocery_ration"].when == "now" and by["school_supplies"].when == "soon"
    assert len(notes) == 2


def test_watch_alert_says_get_ready_and_map_weights():
    _, notes = recommend(T.heatwave, S.watch, date(2026, 6, 1))
    assert any("get these items ready" in n for n in notes)
    w = alert_slugs(T.flood, date(2026, 10, 1), date(2026, 9, 30))
    assert w["emergency_relief"] == 1.0 and w["blankets"] == 0.8 and "school_supplies" not in w
