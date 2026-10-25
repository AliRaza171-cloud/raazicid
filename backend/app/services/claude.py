"""Small helper for the Claude Messages API (web scan, need finder). Uses httpx, no extra SDK."""

import json
import re
from typing import Any

import httpx

from app.core.config import settings

API_URL = "https://api.anthropic.com/v1/messages"


class ClaudeError(Exception):
    pass


def ask(messages: list[dict[str, Any]], *, system: str | None = None, tools: list[dict] | None = None,
        max_tokens: int = 2000, timeout: float = 120) -> dict[str, Any]:
    """Send one request; returns the raw response JSON. Raises ClaudeError with a readable message."""
    if not settings.ANTHROPIC_API_KEY:
        raise ClaudeError("Claude is not set up. Add ANTHROPIC_API_KEY to backend/.env and restart the backend.")
    body: dict[str, Any] = {"model": settings.CLAUDE_MODEL, "max_tokens": max_tokens, "messages": messages}
    if system:
        body["system"] = system
    if tools:
        body["tools"] = tools
    try:
        res = httpx.post(API_URL, json=body, timeout=timeout, headers={
            "x-api-key": settings.ANTHROPIC_API_KEY, "anthropic-version": "2023-06-01", "content-type": "application/json"})
    except httpx.HTTPError:
        raise ClaudeError("Could not reach the Claude API. Check the internet connection.")
    if res.status_code != 200:
        try:
            msg = res.json().get("error", {}).get("message", "")
        except ValueError:
            msg = ""
        raise ClaudeError(f"Claude API error {res.status_code}. {msg}".strip())
    return res.json()


def text_and_citations(response: dict[str, Any]) -> tuple[str, list[dict[str, str]]]:
    """All answer text, plus the web pages Claude cited (url, title), without duplicates."""
    parts, cites, seen = [], [], set()
    for block in response.get("content", []):
        if block.get("type") != "text":
            continue
        parts.append(block.get("text", ""))
        for c in block.get("citations") or []:
            url = c.get("url")
            if url and url not in seen:
                seen.add(url)
                cites.append({"url": url, "title": c.get("title") or url, "cited_text": c.get("cited_text", "")})
    return "".join(parts), cites


def extract_json(text: str) -> Any:
    """The JSON object in a reply that may have words or a ```json fence around it."""
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    raw = fence.group(1) if fence else (re.search(r"\{.*\}", text, re.S) or [None])[0]
    if not raw:
        raise ValueError("no JSON in the answer")
    return json.loads(raw)
