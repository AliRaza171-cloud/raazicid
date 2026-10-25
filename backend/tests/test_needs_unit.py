"""Phase 6 rules without a database: need scoring, GDACS parsing, Claude web-scan parsing."""

from app.models.enums import AlertSeverity, AlertType
from app.services.claude import extract_json, text_and_citations
from app.services.needs import (combine, families, level_of, score_alert, score_ipc, score_poverty, score_price,
                                score_requests)
from app.services.sources import gdacs, webscan


# ---------- need levels ----------

def test_level_bands():
    assert [level_of(s) for s in (0, 29, 30, 54, 55, 79, 80, 100)] == [0, 0, 1, 1, 2, 2, 3, 3]


def test_signal_scores():
    assert score_ipc(0.34) == 85 and score_ipc(0.22) == 65 and score_ipc(0.12) == 40 and score_ipc(0.05) == 0
    assert score_price(0.25) == 60 and score_price(0.12) == 45 and score_price(0.04) == 0
    assert score_poverty(0.45) == 40 and score_poverty(0.30) == 25 and score_poverty(0.1) == 0
    assert score_alert(AlertSeverity.severe, True) == 90
    assert score_alert(AlertSeverity.severe, False) == 63      # not confirmed yet counts less
    assert score_requests(10) == 40 and score_requests(80) == 60


def test_combine_takes_highest_plus_bonus():
    score, level, reasons = combine([(65, {"why": "IPC"}), (45, {"why": "prices"}), (25, {"why": "poverty"}), (10, {"why": "x"})])
    assert score == 65 + 5 + 5 and level == 2                  # only signals of 25+ add the bonus
    assert [r["why"] for r in reasons] == ["IPC", "prices", "poverty", "x"] and reasons[0]["points"] == 65


def test_combine_caps_and_empty():
    assert combine([(90, {}), (85, {}), (80, {}), (60, {})])[0] == 100
    assert combine([]) == (0, 0, []) and combine([(0, {})]) == (0, 0, [])


def test_two_medium_signals_reach_high():
    # Prices up 12% (45) and many open requests (60): "high", not just "some"
    assert combine([(45, {}), (60, {})])[1] == 2


def test_families_from_figures():
    assert families({"families_affected": 300}) == 300
    assert families({"people_affected": 1200}) == 200          # 6 people per family
    assert families({"houses_damaged": 40}) == 40
    assert families({"deaths": 3}) is None and families({}) is None


# ---------- GDACS ----------

def feature(iso3="PAK", etype="FL", level="Orange", name="Flood in Pakistan", lng=68.4, lat=26.2, eid=1001):
    return {"type": "Feature", "geometry": {"type": "Point", "coordinates": [lng, lat]},
            "properties": {"eventtype": etype, "eventid": eid, "name": name, "description": "Flood in Sindh", "iso3": iso3,
                           "country": "Pakistan" if iso3 == "PAK" else "India", "alertlevel": level,
                           "fromdate": "2026-08-20T00:00:00", "url": {"report": "https://www.gdacs.org/report.aspx?eventid=1001"}}}


def test_gdacs_keeps_pakistan_only():
    events = gdacs.parse({"features": [feature(), feature(iso3="IND", eid=2), feature(etype="WF", eid=3)]})
    assert len(events) == 1
    e = events[0]
    assert e["key"] == "FL1001" and e["type"] == AlertType.flood and e["severity"] == AlertSeverity.moderate
    assert (e["lat"], e["lng"]) == (26.2, 68.4)                 # GeoJSON is [lng, lat]
    assert e["url"].startswith("https://www.gdacs.org/") and e["started_at"].year == 2026


def test_gdacs_affected_countries_and_levels():
    f = feature(iso3="AFG", etype="EQ", level="Red", eid=7)
    f["properties"]["country"] = "Afghanistan"
    f["properties"]["affectedcountries"] = [{"iso3": "AFG"}, {"iso3": "PAK"}]
    e = gdacs.parse({"features": [f]})[0]
    assert e["type"] == AlertType.earthquake and e["severity"] == AlertSeverity.severe
    assert gdacs.parse({}) == [] and gdacs.parse({"features": [{"properties": {}}]}) == []


# ---------- Claude web scan ----------

REPLY = """Here is what I found:
```json
{"events": [
  {"type": "flood", "title": "Flash floods in Swat", "areas": ["Swat", "Khyber Pakhtunkhwa"], "severity": "SEVERE",
   "summary": "PDMA KP reports flash floods.", "figures": {"families_affected": 450, "deaths": 0, "made_up": 9, "injured": "12"},
   "started_at": "2026-08-21", "sources": [{"url": "https://www.dawn.com/news/1", "title": "Floods in Swat"}, {"url": "not-a-link"}]},
  {"type": "landslide", "title": "Landslide on KKH", "areas": [], "severity": "unknown"},
  {"title": ""}
]}
```"""


def test_webscan_parse_cleans_events():
    events = webscan.parse(REPLY)
    assert len(events) == 2
    swat, other = events
    assert swat["type"] == AlertType.flood and swat["severity"] == AlertSeverity.severe
    assert swat["figures"] == {"families_affected": 450}       # zero, unknown keys and text numbers dropped
    assert swat["started_at"].day == 21 and swat["sources"] == [{"url": "https://www.dawn.com/news/1", "title": "Floods in Swat"}]
    assert other["type"] == AlertType.other and other["severity"] == AlertSeverity.watch and other["started_at"] is None


def test_webscan_parse_bad_replies():
    assert webscan.parse("Sorry, nothing found.") == []
    assert webscan.parse('{"events": []}') == []
    assert webscan.parse('{"events": "none"}') == []
    assert webscan.parse("[1, 2]") == []


def test_claude_helpers():
    res = {"content": [{"type": "server_tool_use"}, {"type": "text", "text": "A ", "citations": [{"url": "https://a", "title": "A"}]},
                       {"type": "text", "text": "B", "citations": [{"url": "https://a"}, {"url": "https://b"}]}]}
    text, cites = text_and_citations(res)
    assert text == "A B" and [c["url"] for c in cites] == ["https://a", "https://b"]
    assert extract_json('words {"x": 1} words') == {"x": 1}
