"""Phase 6B without a database: chunking, web page text, keyword extraction, rank fusion, prompts, citations."""

import uuid
from datetime import datetime, timezone

from app.services.rag.finder import _cited, build_prompt, tidy
from app.services.rag.search import Hit, keywords, rrf
from app.services.rag.text import chunk_pages, clean, html_text


def test_chunks_keep_pages_and_overlap():
    words = " ".join(f"w{i}" for i in range(800))
    chunks = chunk_pages([(1, "Cover page"), (2, words), (3, "a short last page")])
    assert [c["page"] for c in chunks] == [1, 1, 1]                 # the cover joins page 2, so the chunk starts on page 1
    first, second = chunks[0]["text"].split(), chunks[1]["text"].split()
    assert len(first) == 350 and first[-60:] == second[:60]         # 60 words of overlap
    assert chunks[-1]["text"].endswith("a short last page")         # a tiny last page is not lost


def test_chunks_separate_pages():
    a = " ".join(["alpha"] * 100)
    b = " ".join(["beta"] * 100)
    chunks = chunk_pages([(4, a), (5, b)])
    assert [(c["page"], c["text"].split()[0]) for c in chunks] == [(4, "alpha"), (5, "beta")]
    assert chunk_pages([]) == [] and chunk_pages([(1, "   ")]) == []


def test_clean_and_html():
    assert clean("assess-\nment   of\n\n\n\nneeds") == "assessment of\n\nneeds"
    html = ("<html><head><title>Floods in Swat | Dawn</title><script>var a = 1;</script></head><body>"
            "<nav>Home News Sport Business Opinion More menu items</nav><article>"
            + "<p>Heavy rains caused flash floods in Swat district on Monday, PDMA said in a statement.</p>" * 5
            + "<p>Share</p></article><footer>Copyright Dawn all rights reserved here today</footer></body></html>")
    title, text = html_text(html)
    assert title == "Floods in Swat | Dawn"
    assert "flash floods in Swat" in text and "var a" not in text and "menu" not in text and "Copyright" not in text


def test_keywords_drop_question_words():
    assert keywords("Where in Karachi are blankets needed most this winter?") == ["karachi", "blankets", "winter"]
    assert keywords("?? !!") == []


def test_rank_fusion_rewards_both_lists():
    a, b, c = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    fused = rrf({"meaning": [a, b], "words": [c, b]})
    order = sorted(fused, key=lambda k: -fused[k][0])
    assert order[0] == b and sorted(fused[b][1]) == ["meaning", "words"]   # found by both: first
    assert fused[a][0] == fused[c][0]                                      # same rank in one list each: tie


def test_prompt_numbers_sources_and_facts():
    hit = Hit(chunk_id=uuid.uuid4(), report_id=uuid.uuid4(), title="Sindh drought assessment", publisher="PDMA Sindh", url=None,
              page=4, published_at=datetime(2026, 9, 1, tzinfo=timezone.utc), source="Manual upload",
              text="Tharparkar: 40% of families need food rations.", places=["Tharparkar"])
    facts = [{"id": "D1", "place": "Sindh › Tharparkar", "category": "Food", "level": "urgent", "score": 85, "why": "IPC 3+ for 34%"}]
    p = build_prompt("Where is food needed?", "Sindh", "Food", [hit], facts, web=True)
    assert "[S1] Sindh drought assessment (PDMA Sindh, 01 Sep 2026, page 4) · places: Tharparkar" in p
    assert "[D1] Sindh › Tharparkar: Food need is urgent (score 85)" in p
    assert "search the web" in p and "```json" in p
    empty = build_prompt("Where?", None, None, [], [], web=False)
    assert "(no matching passages in the library)" in empty and "search the web" not in empty


def test_citations_found():
    assert _cited("Tharparkar needs food [S1] and blankets [D2][S3]. Not [X1] or [S].") == {"S1", "D2", "S3"}


def test_web_cite_tags_become_plain_markers():
    raw = "<cite index='2-1,2-10'>Rawalpindi had a 40% shortage of textbooks.</cite> <cite index='7-1'>Lahore too</cite>."
    assert tidy(raw) == "Rawalpindi had a 40% shortage of textbooks. [Web] Lahore too. [Web]"
    assert tidy("<cite index='8-1'>Free textbooks were late</cite>, so parents paid more.") == "Free textbooks were late, [Web] so parents paid more."
    assert tidy("Lyari needs blankets [S1]. <b>bold</b>  text") == "Lyari needs blankets [S1]. bold text"
    assert "<" not in tidy("<cite index='5-3'>Prices up to 300%</cite><cite index='5-4'> higher</cite> in Islamabad [S2].")
