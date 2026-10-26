"""AI needs scan and data age, without a database or network."""

from datetime import date

from app.services.needs import age_factor, score_ai
from app.services.sources.ai_needs import parse

TODAY = date(2026, 10, 25)

REPLY = """I searched recent reports.
```json
{"needs": [
  {"area": "Tharparkar", "province": "Sindh", "categories": ["food", "Grocery_Ration", "toys"], "level": "Urgent",
   "why": "WFP says 40% of families eat one meal a day.", "date": "2026-10-02",
   "sources": [{"url": "https://www.wfp.org/news/x", "title": "WFP Pakistan update"}, {"url": "not a link"}]},
  {"area": "Swat", "province": "KP", "categories": ["blankets"], "level": "high", "why": "Cold wave.", "date": "2025-12-01",
   "sources": []},
  {"area": "", "categories": ["food"]},
  {"area": "Quetta", "province": "Balochistan", "categories": ["unknown"], "level": "some", "date": "2026-10-20"},
  {"area": "Gilgit", "province": "GB", "categories": ["winter_support"], "level": "whatever", "date": "not a date"}
]}
```"""


def test_parse_keeps_recent_known_needs():
    items = parse(REPLY, TODAY)
    assert [i["area"] for i in items] == ["Tharparkar", "Gilgit"]       # old Swat news, empty area, unknown category dropped
    thar, gilgit = items
    assert thar["categories"] == ["food", "grocery_ration"] and thar["level"] == 3 and thar["date"] == date(2026, 10, 2)
    assert thar["sources"] == [{"url": "https://www.wfp.org/news/x", "title": "WFP Pakistan update"}]
    assert gilgit["level"] == 1 and gilgit["date"] == TODAY             # unknown level: "some"; no date: today
    assert parse("no json here", TODAY) == [] and parse('{"needs": []}', TODAY) == []


def test_old_data_counts_less():
    assert age_factor(date(2026, 3, 1), TODAY) == (1.0, None)
    assert age_factor(date(2025, 6, 30), TODAY) == (0.75, "2025")
    assert age_factor(date(2022, 12, 31), TODAY) == (0.5, "2022")
    assert age_factor(None, TODAY) == (1.0, None)


def test_ai_points():
    assert score_ai(3) == 70 and score_ai(2) == 55 and score_ai(1) == 35 and score_ai(0) == 0
