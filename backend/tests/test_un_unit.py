"""UN data without a database: 3W, people in need, rainfall, refugees (HDX HAPI), scoring and ReliefWeb queries."""

from datetime import date

from app.services.needs import score_pin, score_rain
from app.services.sources import reliefweb
from app.services.sources.hapi_un import (baseline_population, category_sectors, people_in_need, presence, rainfall, refugee_text,
                                          refugees, sector_categories)


def test_sectors_map_to_our_categories():
    assert sector_categories("Education") == ["school_supplies", "books"]
    assert sector_categories("Water Sanitation Hygiene") == ["hygiene"]
    assert sector_categories("Emergency Shelter and NFI") == ["blankets", "household", "winter_support"]
    assert "food" in sector_categories("Food Security") and "baby" in sector_categories("Nutrition")
    assert sector_categories("Logistics") == [] and sector_categories("Coordination") == []
    assert category_sectors("books", ["Education", "Health", "Food Security"]) == ["Education"]
    assert category_sectors("hygiene", ["Health", "WASH"]) == ["Health", "WASH"]


W3 = [
    {"admin1_name": "Sindh", "admin2_name": "Tharparkar", "admin2_code": "PK604", "sector_name": "Education", "org_acronym": "UNICEF", "reference_period_end": "2026-06-30"},
    {"admin1_name": "Sindh", "admin2_name": "Tharparkar", "admin2_code": "PK604", "sector_name": "Education", "org_acronym": "NRSP", "reference_period_end": "2026-06-30"},
    {"admin1_name": "Sindh", "admin2_name": "Tharparkar", "admin2_code": "PK604", "sector_name": "Food Security", "org_acronym": "WFP", "reference_period_end": "2026-06-30"},
    {"admin1_name": "Sindh", "admin2_name": "Tharparkar", "admin2_code": "PK604", "sector_name": "Food Security", "org_acronym": "UNICEF"},
    {"admin1_name": "Balochistan", "admin2_name": "", "sector_name": "Health", "org_name": "World Health Organization"},
    {"admin1_name": "Sindh", "admin2_name": "Badin", "sector_name": "", "org_acronym": "X"},          # no sector: skipped
]


def test_presence_counts_organisations_per_place():
    out = {(r["admin1_name"], r["admin2_name"]): r for r in presence(W3)}
    thar = out[("Sindh", "Tharparkar")]
    assert thar["orgs"] == 3 and thar["sectors"] == {"Education": ["NRSP", "UNICEF"], "Food Security": ["UNICEF", "WFP"]}
    assert thar["period_end"] == date(2026, 6, 30) and thar["admin2_code"] == "PK604"
    assert out[("Balochistan", None)]["sectors"] == {"Health": ["World Health Organization"]}   # province-level row
    assert ("Sindh", "Badin") not in out


def test_people_in_need_whole_population_only_and_share():
    rows = [
        {"admin1_name": "Sindh", "admin2_name": "Dadu", "admin2_code": "PK605", "sector_name": "Education", "population_status": "INN",
         "category": "", "population": 120000, "reference_period_end": "2025-12-31"},
        {"admin1_name": "Sindh", "admin2_name": "Dadu", "admin2_code": "PK605", "sector_name": "Education", "population_status": "INN",
         "category": "Children - Girls", "population": 50000, "reference_period_end": "2025-12-31"},             # breakdown: skipped
        {"admin1_name": "Sindh", "admin2_name": "Dadu", "admin2_code": "PK605", "sector_name": "Education", "population_status": "TGT",
         "category": "", "population": 60000, "reference_period_end": "2025-12-31"},                           # target, not need
        {"admin1_name": "Sindh", "admin2_name": "Dadu", "admin2_code": "PK605", "sector_name": "Education", "population_status": "INN",
         "category": "total", "population": 90000, "reference_period_end": "2024-12-31"},                      # older
    ]
    pop = baseline_population([{"admin2_code": "PK605", "admin2_name": "Dadu", "gender": "all", "age_range": "all", "population": 400000},
                               {"admin2_code": "PK605", "gender": "f", "age_range": "all", "population": 1}])
    out = people_in_need(rows, pop)
    assert len(out) == 1 and out[0]["people"] == 120000 and out[0]["share"] == 0.3 and out[0]["sector"] == "Education"
    assert people_in_need(rows)[0]["share"] is None


def test_rainfall_latest_real_reading():
    rows = [
        {"admin1_name": "Sindh", "admin2_name": "Dadu", "rainfall_anomaly_pct": 40, "reference_period_end": "2026-08-31", "version": "final"},
        {"admin1_name": "Sindh", "admin2_name": "Dadu", "rainfall_anomaly_pct": 140.25, "reference_period_end": "2026-09-30", "version": "preliminary"},
        {"admin1_name": "Sindh", "admin2_name": "Dadu", "rainfall_anomaly_pct": 300, "reference_period_end": "2026-10-31", "version": "forecast"},
    ]
    out = rainfall(rows)
    assert len(out) == 1 and out[0]["anomaly_pct"] == 140.2 and out[0]["period_end"] == date(2026, 9, 30)


def test_refugees_latest_year_totals():
    rows = [
        {"population_group": "REF", "origin_location_name": "Afghanistan", "gender": "all", "age_range": "all", "population": 1500000, "reference_period_end": "2025-12-31"},
        {"population_group": "ASY", "origin_location_name": "Afghanistan", "gender": "all", "age_range": "all", "population": 20000, "reference_period_end": "2025-12-31"},
        {"population_group": "REF", "origin_location_name": "Somalia", "gender": "all", "age_range": "all", "population": 500, "reference_period_end": "2025-12-31"},
        {"population_group": "REF", "origin_location_name": "Afghanistan", "gender": "f", "age_range": "all", "population": 700000, "reference_period_end": "2025-12-31"},
        {"population_group": "REF", "origin_location_name": "Afghanistan", "gender": "all", "age_range": "all", "population": 1300000, "reference_period_end": "2024-12-31"},
    ]
    r = refugees(rows)
    assert r["groups"] == {"REF": 1500500, "ASY": 20000} and r["origins"][0] == ("Afghanistan", 1520000)
    text = refugee_text(r)
    assert "1,520,500 people of concern" in text and "1,500,500 refugees" in text and "not per district" in text
    assert refugees([]) is None


def test_un_signal_scores():
    assert score_pin(10, 0.45) == 85 and score_pin(10, 0.3) == 65 and score_pin(10, 0.12) == 45 and score_pin(10, 0.05) == 0
    assert score_pin(600_000, None) == 75 and score_pin(150_000, None) == 60 and score_pin(25_000, None) == 40
    assert score_rain(140) == (25, "wet") and score_rain(70) == (0, None) and score_rain(-65) == (25, "dry")
    assert score_rain(-45) == (0, None) and score_rain(10) == (0, None)
    # Dry places: a big percentage of very little rain is no flood risk; no usual rain means no drought either
    assert score_rain(115, rainfall=30, average=14) == (0, None) and score_rain(115, rainfall=320, average=150) == (25, "wet")
    assert score_rain(-70, rainfall=3, average=10) == (0, None) and score_rain(-70, rainfall=20, average=70) == (25, "dry")


def test_reliefweb_queries():
    body = reliefweb.query_body(14, 60, un_only=True)
    conds = body["filter"]["conditions"]
    assert {"field": "primary_country.iso3", "value": "pak"} in conds
    assert any(c["field"] == "source.shortname" and "UNICEF" in c["value"] and c["operator"] == "OR" for c in conds)
    live = reliefweb.query_body(365, 5, un_only=False, words="school books Rawalpindi")
    assert live["query"]["value"] == "school books Rawalpindi" and live["sort"][0] == "score:desc"
    assert not any(c["field"] == "source.shortname" for c in live["filter"]["conditions"])
