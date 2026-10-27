"""NGO web search without the internet: reading the AI's answer, spotting repeats, trusting map lookups."""

from app.services.ngo_finder import close_enough, name_key, parse_ngos

ALLOWED = ["food", "grocery_ration", "clothes", "blankets", "hygiene"]


def test_parse_cleans_rows_and_drops_repeats():
    answer = """Here you go:
```json
{"ngos": [
 {"name": "  Edhi Foundation (Hyderabad) ", "address": "Station Road", "phone": "022-111", "website": "edhi.org",
  "accepts": ["food", "clothes", "rockets", "food"], "cooked_food": true, "about": "Ambulances and shelters.",
  "source_url": "https://edhi.org/centres"},
 {"name": "EDHI FOUNDATION", "address": "Another"},
 {"name": "", "address": "No name"},
 {"name": "Local Trust", "address": "", "source_url": "not a link", "cooked_food": "yes"},
 "junk"
]}
```"""
    rows = parse_ngos(answer, ALLOWED)
    assert [r["name"] for r in rows] == ["Edhi Foundation (Hyderabad)", "Local Trust"]
    edhi, local = rows
    assert edhi["accepts"] == ["food", "clothes"] and edhi["cooked_food"] is True and edhi["website"] == "https://edhi.org"
    assert local["address"] is None and local["source_url"] is None and local["cooked_food"] is False


def test_bad_answers_give_nothing():
    assert parse_ngos("Sorry, I could not search.", ALLOWED) == []
    assert parse_ngos('```json\n{"ngos": "none"}\n```', ALLOWED) == []


def test_name_key_and_map_checks():
    assert name_key("Saylani Welfare (Karachi)") == name_key("SAYLANI WELFARE") == "saylani welfare"
    hyderabad = (25.396, 68.358)
    assert close_enough(25.39, 68.37, hyderabad) and not close_enough(24.86, 67.0, hyderabad)   # Karachi is 150 km away
    assert not close_enough(51.5, -0.12, None) and close_enough(31.5, 74.3, None)
