"""AI provider switch without a network: OpenAI request body, OpenAI answer parsing, provider choice, link clean-up."""

from app.core.config import settings
from app.services import llm
from app.services.rag.finder import tidy

OPENAI_ANSWER = {
    "model": "gpt-5.5",
    "status": "completed",
    "output": [
        {"type": "web_search_call", "id": "ws_1", "status": "completed",
         "action": {"type": "search", "query": "textbook shortage Pakistan",
                    "sources": [{"type": "url", "url": "https://www.dawn.com/news/1"}, {"type": "url", "url": "https://tribune.com.pk/2"}]}},
        {"type": "message", "role": "assistant", "content": [{
            "type": "output_text",
            "text": "Rawalpindi has a 40% textbook shortage ([dawn.com](https://www.dawn.com/news/1)).",
            "annotations": [{"type": "url_citation", "url": "https://www.dawn.com/news/1", "title": "Textbook shortage", "start_index": 0, "end_index": 41}],
        }]},
    ],
}


def test_openai_answer_parsed():
    a = llm.openai_parse(OPENAI_ANSWER)
    assert a.text.startswith("Rawalpindi has a 40% textbook shortage") and a.provider == "openai" and a.model == "gpt-5.5"
    quoted = OPENAI_ANSWER["output"][1]["content"][0]["text"][0:41]
    assert a.citations == [{"url": "https://www.dawn.com/news/1", "title": "Textbook shortage", "cited_text": quoted}]
    assert [s["url"] for s in a.searched] == ["https://www.dawn.com/news/1", "https://tribune.com.pk/2"]


def test_openai_request_body(monkeypatch):
    monkeypatch.setattr(settings, "OPENAI_MODEL", "gpt-5.5")
    b = llm.openai_body("Where?", "Be brief", {"max_uses": 4, "allowed_domains": ["https://ndma.gov.pk/", "dawn.com"]},
                        ["https://res.cloudinary.com/x/cnic.jpg"], 1200)
    assert b["model"] == "gpt-5.5" and b["instructions"] == "Be brief" and b["max_output_tokens"] >= 3600
    assert b["input"][0]["content"] == [{"type": "input_image", "image_url": "https://res.cloudinary.com/x/cnic.jpg"},
                                        {"type": "input_text", "text": "Where?"}]
    assert b["tools"] == [{"type": "web_search", "search_context_size": "medium", "filters": {"allowed_domains": ["ndma.gov.pk", "dawn.com"]}}]
    assert b["include"] == ["web_search_call.action.sources"]
    plain = llm.openai_body("Hi", None, None, None, 500)
    assert "tools" not in plain and "instructions" not in plain


def test_provider_choice(monkeypatch):
    monkeypatch.setattr(settings, "AI_PROVIDER", "")
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "")
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "sk-test")
    assert llm.provider() == "openai" and llm.available() and llm.label().startswith("OpenAI")
    monkeypatch.setattr(settings, "AI_PROVIDER", "claude")
    assert llm.provider() == "claude" and not llm.available() and "ANTHROPIC_API_KEY" in llm.not_set_up()
    monkeypatch.setattr(settings, "AI_PROVIDER", "OpenAI")
    assert llm.provider() == "openai"


def test_openai_inline_links_become_web_markers():
    assert tidy("Rawalpindi has a 40% textbook shortage ([dawn.com](https://www.dawn.com/news/1)).") == \
        "Rawalpindi has a 40% textbook shortage. [Web]"
    assert tidy("See [the NDMA report](https://ndma.gov.pk/sitrep) for details.") == "See the NDMA report for details."   # link text kept, URL gone
    assert tidy("Floods hit Swat ([geo.tv](https://www.geo.tv/a)), PDMA said.") == "Floods hit Swat, [Web] PDMA said."


class FakeResponse:
    def __init__(self, status, body):
        self.status_code, self._body = status, body

    def json(self):
        return self._body


def test_out_of_credit_is_explained(monkeypatch):
    monkeypatch.setattr(settings, "AI_PROVIDER", "openai")
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "")
    quota = {"error": {"message": "You exceeded your current quota, please check your plan and billing details.",
                       "type": "insufficient_quota", "code": "insufficient_quota"}}
    monkeypatch.setattr(llm.httpx, "post", lambda *a, **k: FakeResponse(429, quota))
    try:
        llm.complete("hello")
        raise AssertionError("should fail")
    except llm.LLMError as e:
        assert e.out_of_credit and "credits have run out" in str(e) and "ANTHROPIC_API_KEY" in str(e)


def test_rate_limit_is_not_out_of_credit():
    assert not llm.is_out_of_credit("openai", 429, "Rate limit reached for requests", "rate_limit_exceeded")
    assert llm.is_out_of_credit("claude", 400, "Your credit balance is too low to access the Anthropic API.")


def test_switches_to_claude_when_openai_has_no_credit(monkeypatch):
    monkeypatch.setattr(settings, "AI_PROVIDER", "openai")
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setattr(llm, "_openai", lambda *a: (_ for _ in ()).throw(llm.LLMError("no credit", out_of_credit=True)))
    monkeypatch.setattr(llm, "_claude", lambda *a: llm.Answer(text="ok", model="claude-x", provider="claude"))
    assert llm.complete("hello").provider == "claude"
    assert "switched" in llm.used_label()
