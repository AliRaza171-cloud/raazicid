"""Report reader without a database or network: which text the AI reads, and how its answer is cleaned."""

from datetime import date

from app.services.rag.report_needs import MAX_CHARS, REPORT_MAX_AGE_DAYS, pick_text
from app.services.sources.ai_needs import parse

TODAY = date(2026, 10, 25)


def test_short_report_is_read_whole_with_page_marks():
    text = pick_text([(1, "Cover"), (2, "Families in Dadu still lack blankets."), (None, "Annex")])
    assert text == "[page 1]\nCover\n\n[page 2]\nFamilies in Dadu still lack blankets.\n\nAnnex"


def test_long_report_keeps_the_passages_about_needs_in_page_order():
    filler = [(p, "Acknowledgements and methodology. " * 120) for p in range(1, 30)]
    needs = [(15, "Families are still waiting for food; shortage of hygiene kits; unmet needs in Kech. " * 20)]
    text = pick_text(filler[:14] + needs + filler[14:], limit=12_000)
    assert len(text) <= 12_000 and "[page 15]" in text and "still waiting" in text
    pages = [int(line[6:-1]) for line in text.splitlines() if line.startswith("[page ")]
    assert pages == sorted(pages)
    assert MAX_CHARS >= 30_000


REPLY = """```json
{"needs": [
  {"area": "Kech", "province": "Balochistan", "categories": ["hygiene"], "level": "urgent", "page": 15,
   "why": "4,000 families lack hygiene kits.", "unmet": "shortage of hygiene kits", "reached": "none"},
  {"area": "Dadu", "province": "Sindh", "categories": ["blankets"], "level": "high", "page": "7",
   "why": "WFP distributed 2,000 blankets.", "unmet": ""},
  {"area": "Swat", "province": "KP", "categories": ["school_supplies"], "level": "some", "date": "2023-01-10",
   "why": "Schools need books.", "unmet": "children still need textbooks"}
]}
```"""


def test_report_answer_uses_report_date_and_pages():
    items = parse(REPLY, TODAY, max_age_days=REPORT_MAX_AGE_DAYS, default_date=date(2026, 6, 1))
    assert [i["area"] for i in items] == ["Kech"]          # Dadu: aid handed out; Swat: dated 2023, too old for a report
    kech = items[0]
    assert kech["page"] == 15 and kech["date"] == date(2026, 6, 1) and kech["reached"] == "none" and kech["level"] == 3
