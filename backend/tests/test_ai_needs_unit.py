"""AI needs scan and data age, without a database or network."""

from datetime import date

from app.services.needs import age_factor, score_ai
from app.services.sources.ai_needs import combine, parse, shows_gap

TODAY = date(2026, 10, 25)

REPLY = """I searched recent reports.
```json
{"needs": [
  {"area": "Tharparkar", "province": "Sindh", "categories": ["food", "Grocery_Ration", "toys"], "level": "Urgent",
   "why": "WFP says 40% of families eat one meal a day.", "unmet": "families still lack enough food", "reached": "partial",
   "date": "2026-10-02",
   "sources": [{"url": "https://www.wfp.org/news/x", "title": "WFP Pakistan update"}, {"url": "not a link"}]},
  {"area": "Swat", "province": "KP", "categories": ["blankets"], "level": "high", "why": "Cold wave.", "date": "2025-12-01",
   "sources": []},
  {"area": "", "categories": ["food"]},
  {"area": "Quetta", "province": "Balochistan", "categories": ["unknown"], "level": "some", "date": "2026-10-20"},
  {"area": "Gilgit", "province": "GB", "categories": ["winter_support"], "level": "whatever", "date": "not a date",
   "why": "Families in high valleys are without warm clothes.", "reached": "none"},
  {"area": "Mohmand", "province": "KP", "categories": ["blankets"], "level": "high", "date": "2026-09-30",
   "why": "NDMA reported 370 tents, 160 blankets and 200 quilts for Mohmand.", "unmet": ""},
  {"area": "Bajaur", "province": "KP", "categories": ["blankets"], "level": "high", "date": "2026-09-30",
   "why": "Displaced families still waiting for blankets.", "sources": [{"url": "https://sitreps.ndma.gov.pk/province-dark/3"}]}
]}
```"""


def test_parse_keeps_recent_known_needs():
    items = parse(REPLY, TODAY)
    # dropped: old Swat news, empty area, unknown category, Mohmand (aid handed out, no gap), Bajaur (only an NDMA sitrep)
    assert [i["area"] for i in items] == ["Tharparkar", "Gilgit"]
    thar, gilgit = items
    assert thar["categories"] == ["food", "grocery_ration"] and thar["date"] == date(2026, 10, 2)
    assert thar["level"] == 2 and thar["reached"] == "partial"          # urgent, but some aid arrives: high
    assert gilgit["reached"] == "none" and thar["unmet"] == "families still lack enough food"
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


def _item(area, cats, level, url, day=20):
    return {"area": area, "province": "Punjab", "categories": cats, "level": level, "why": "x", "date": date(2026, 10, day),
            "sources": [{"url": url, "title": "t"}] if url else []}


def test_one_source_cannot_fill_the_scan():
    sitrep = "https://sitreps.ndma.gov.pk/province-dark/1"
    food = [_item("Sheikhupura", ["food"], 3, sitrep), _item("Muzaffargarh", ["food"], 2, sitrep + "?x=1"),
            _item("Jhang", ["food"], 2, sitrep + "/")]
    other = [_item("Rajanpur", ["blankets"], 2, "https://www.unicef.org/pakistan/a"),
             _item("Sheikhupura", ["food", "hygiene"], 1, "https://www.dawn.com/news/2", day=22)]
    out = combine([food, other], per_source=2)
    areas = [(i["area"], i["categories"]) for i in out]
    assert ("Jhang", ["food"]) not in areas                         # third item from the same sitrep page dropped
    assert ("Sheikhupura", ["food"]) in areas and ("Rajanpur", ["blankets"]) in areas
    assert ("Sheikhupura", ["hygiene"]) in areas                    # food already covered there: only the new category kept


def test_theme_only_keeps_its_categories():
    text = '{"needs": [{"area": "Swat", "categories": ["blankets", "food"], "level": "high", "date": "2026-10-20", "why": "Families need blankets."}]}'
    assert parse(text, TODAY, allowed=["blankets", "winter_support"])[0]["categories"] == ["blankets"]


def test_aid_handed_out_is_not_a_need():
    assert not shows_gap("NDMA reported 370 tents, 160 blankets and 200 quilts for Mohmand on 30 September.")
    assert not shows_gap("WFP distributed 5,000 food packs in Dadu.")
    assert shows_gap("WFP distributed 5,000 food packs, but 12,000 families are still waiting.")
    assert shows_gap("", "no assistance has reached the villages")
    assert shows_gap("Schools in Kech ran out of textbooks.") and shows_gap("300 families need hygiene kits.")
