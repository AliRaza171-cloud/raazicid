"""One door to the AI model, whichever provider is set: OpenAI (Responses API) or Claude (Messages API).

Used by the need finder, the disaster news scan and the rider document check. Choose in backend/.env:
    AI_PROVIDER=openai   with OPENAI_API_KEY and OPENAI_MODEL
    AI_PROVIDER=claude   with ANTHROPIC_API_KEY and CLAUDE_MODEL
Both support web search with citations and reading images. No SDK: plain HTTPS with httpx.
"""

from dataclasses import dataclass, field
from typing import Any, Optional

import httpx

from app.core.config import settings

OPENAI_URL = "https://api.openai.com/v1/responses"


class LLMError(Exception):
    """A readable problem: not set up, no internet, the API refused, the credits ran out..."""

    def __init__(self, message: str, out_of_credit: bool = False):
        super().__init__(message)
        self.out_of_credit = out_of_credit


BILLING = {"openai": "platform.openai.com (Settings, Billing)", "claude": "console.anthropic.com (Settings, Billing)"}
NAME = {"openai": "OpenAI", "claude": "Claude"}
_last_used: dict[str, str] = {}


def is_out_of_credit(p: str, status: int, message: str, code: str = "") -> bool:
    """True when the API refused because the account has no credit left (not a passing rate limit)."""
    m = message.lower()
    if p == "openai":
        return code == "insufficient_quota" or "exceeded your current quota" in m or "billing" in m and status in (402, 429)
    return "credit balance is too low" in m or (status == 402)


def out_of_credit_message(p: str, other_tried: bool = False) -> str:
    if other_tried:
        return ("The AI credits have run out for both OpenAI and Claude, so no new search was done. Add credits at "
                f"{BILLING['openai']} or {BILLING['claude']}. The need levels shown come from the last scan and the other data sources.")
    other = "claude" if p == "openai" else "openai"
    key = "ANTHROPIC_API_KEY" if other == "claude" else "OPENAI_API_KEY"
    return (f"Your {NAME[p]} credits have run out, so no new search was done. Add credits at {BILLING[p]}, "
            f"or add {key} to backend/.env and restart the backend to use {NAME[other]} instead. "
            "The need levels shown come from the last scan and the other data sources.")


@dataclass
class Answer:
    text: str
    citations: list[dict[str, str]] = field(default_factory=list)   # pages quoted in the answer: url, title, cited_text
    searched: list[dict[str, str]] = field(default_factory=list)    # every page the web search looked at: url, title
    model: str = ""
    provider: str = ""


def provider() -> str:
    """"openai" or "claude": the one chosen in AI_PROVIDER, or whichever has a key."""
    p = (settings.AI_PROVIDER or "").strip().lower()
    if p in ("openai", "claude"):
        return p
    if settings.OPENAI_API_KEY and not settings.ANTHROPIC_API_KEY:
        return "openai"
    return "claude"


def available() -> bool:
    return bool(settings.OPENAI_API_KEY if provider() == "openai" else settings.ANTHROPIC_API_KEY)


def model_name() -> str:
    return settings.OPENAI_MODEL if provider() == "openai" else settings.CLAUDE_MODEL


def label() -> str:
    """For the admin pages, e.g. "OpenAI gpt-5.5"."""
    return f"{'OpenAI' if provider() == 'openai' else 'Claude'} {model_name()}"


def not_set_up() -> str:
    if provider() == "openai":
        return "AI is not set up. Add OPENAI_API_KEY to backend/.env and restart the backend."
    return "AI is not set up. Add ANTHROPIC_API_KEY (or AI_PROVIDER=openai with OPENAI_API_KEY) to backend/.env and restart the backend."


def complete(prompt: str, *, system: Optional[str] = None, web: Optional[dict[str, Any]] = None, images: Optional[list[str]] = None,
             max_tokens: int = 2000, timeout: float = 150) -> Answer:
    """Ask the model. web = {"max_uses": 4, "allowed_domains": [...] or "blocked_domains": [...]} turns on web search.
    images = public https URLs shown before the prompt (document check)."""
    if not available():
        raise LLMError(not_set_up())
    first = provider()
    try:
        answer = _call(first, prompt, system, web, images, max_tokens, timeout)
    except LLMError as e:
        if not e.out_of_credit:
            raise
        other = "claude" if first == "openai" else "openai"
        if not has_key(other):
            raise LLMError(out_of_credit_message(first), out_of_credit=True)
        try:   # credits gone on one provider: use the other one if its key is set
            answer = _call(other, prompt, system, web, images, max_tokens, timeout)
        except LLMError as e2:
            if e2.out_of_credit:
                raise LLMError(out_of_credit_message(first, other_tried=True), out_of_credit=True)
            raise
    _last_used.update(provider=answer.provider, model=answer.model)
    return answer


def has_key(p: str) -> bool:
    return bool(settings.OPENAI_API_KEY if p == "openai" else settings.ANTHROPIC_API_KEY)


def used_label() -> str:
    """The provider that actually answered last (it differs from label() after a switch for lack of credit)."""
    if not _last_used:
        return label()
    switched = " (switched: the other provider had no credit)" if _last_used["provider"] != provider() else ""
    return f"{NAME[_last_used['provider']]} {_last_used['model']}{switched}"


def _call(p, prompt, system, web, images, max_tokens, timeout) -> Answer:
    if p == "openai":
        return _openai(prompt, system, web, images, max_tokens, timeout)
    return _claude(prompt, system, web, images, max_tokens, timeout)


# ---------- OpenAI (Responses API) ----------

def openai_body(prompt: str, system: Optional[str], web: Optional[dict], images: Optional[list[str]], max_tokens: int) -> dict[str, Any]:
    content: list[dict[str, Any]] = [{"type": "input_image", "image_url": u} for u in images or []]
    content.append({"type": "input_text", "text": prompt})
    body: dict[str, Any] = {"model": settings.OPENAI_MODEL, "input": [{"role": "user", "content": content}],
                            # reasoning models spend part of the budget thinking: leave room for the answer
                            "max_output_tokens": max(max_tokens * 3, 4000)}
    if system:
        body["instructions"] = system
    if web is not None:
        tool: dict[str, Any] = {"type": "web_search", "search_context_size": "medium"}
        clean = lambda ds: [d.replace("https://", "").replace("http://", "").strip("/") for d in ds][:100]
        if web.get("allowed_domains"):
            tool["filters"] = {"allowed_domains": clean(web["allowed_domains"])}
        elif web.get("blocked_domains"):
            tool["filters"] = {"blocked_domains": clean(web["blocked_domains"])}
        body["tools"] = [tool]
        body["include"] = ["web_search_call.action.sources"]
    return body


def openai_parse(data: dict[str, Any]) -> Answer:
    texts: list[str] = []
    cites: list[dict[str, str]] = []
    searched: list[dict[str, str]] = []
    seen_c, seen_s = set(), set()
    for item in data.get("output") or []:
        kind = item.get("type")
        if kind == "message":
            for part in item.get("content") or []:
                if part.get("type") != "output_text":
                    continue
                t = part.get("text") or ""
                for a in part.get("annotations") or []:
                    if a.get("type") == "url_citation" and a.get("url") and a["url"] not in seen_c:
                        seen_c.add(a["url"])
                        s, e = a.get("start_index"), a.get("end_index")
                        quoted = t[s:e] if isinstance(s, int) and isinstance(e, int) else ""
                        cites.append({"url": a["url"], "title": a.get("title") or a["url"], "cited_text": quoted[:300]})
                texts.append(t)
        elif kind == "web_search_call":
            for src in ((item.get("action") or {}).get("sources") or []):
                url = src.get("url") if isinstance(src, dict) else None
                if url and url not in seen_s:
                    seen_s.add(url)
                    searched.append({"url": url, "title": src.get("title") or url, "page_age": ""})
    text = "".join(texts) or str(data.get("output_text") or "")
    return Answer(text=text, citations=cites, searched=searched, model=str(data.get("model") or settings.OPENAI_MODEL), provider="openai")


def _openai(prompt, system, web, images, max_tokens, timeout) -> Answer:
    try:
        res = httpx.post(OPENAI_URL, json=openai_body(prompt, system, web, images, max_tokens), timeout=timeout,
                         headers={"Authorization": f"Bearer {settings.OPENAI_API_KEY}", "Content-Type": "application/json"})
    except httpx.HTTPError:
        raise LLMError("Could not reach the OpenAI API. Check the internet connection.")
    if res.status_code != 200:
        try:
            err = res.json().get("error", {}) or {}
        except ValueError:
            err = {}
        msg, code = str(err.get("message") or ""), str(err.get("code") or err.get("type") or "")
        if is_out_of_credit("openai", res.status_code, msg, code):
            raise LLMError(out_of_credit_message("openai"), out_of_credit=True)
        raise LLMError(f"OpenAI API error {res.status_code}. {msg}".strip())
    data = res.json()
    if data.get("status") == "incomplete":
        reason = (data.get("incomplete_details") or {}).get("reason", "")
        if not any(i.get("type") == "message" for i in data.get("output") or []):
            raise LLMError(f"OpenAI stopped before answering ({reason or 'incomplete'}). Try again.")
    return openai_parse(data)


# ---------- Claude (Messages API) ----------

def _claude(prompt, system, web, images, max_tokens, timeout) -> Answer:
    from app.services.claude import ClaudeError, ask_complete, search_results, text_and_citations

    content: list[dict[str, Any]] = [{"type": "image", "source": {"type": "url", "url": u}} for u in images or []]
    content.append({"type": "text", "text": prompt})
    tools = None
    if web is not None:
        tool: dict[str, Any] = {"type": "web_search_20250305", "name": "web_search", "max_uses": int(web.get("max_uses") or 4)}
        if web.get("allowed_domains"):
            tool["allowed_domains"] = web["allowed_domains"]
        elif web.get("blocked_domains"):
            tool["blocked_domains"] = web["blocked_domains"]
        tools = [tool]
    try:
        res = ask_complete([{"role": "user", "content": content}], system=system, tools=tools, max_tokens=max_tokens, timeout=timeout)
    except ClaudeError as e:
        if is_out_of_credit("claude", getattr(e, "status", 0), str(e)):
            raise LLMError(out_of_credit_message("claude"), out_of_credit=True)
        raise LLMError(str(e))
    text, cites = text_and_citations(res)
    return Answer(text=text, citations=cites, searched=search_results(res), model=settings.CLAUDE_MODEL, provider="claude")
