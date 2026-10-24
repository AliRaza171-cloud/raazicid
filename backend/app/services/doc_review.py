"""Claude reviews a rider's verification photos (Phase 5). Advisory only: the admin always decides.

Sends the CNIC, licence and vehicle registration photos (Cloudinary URLs) with the rider's name and vehicle
number to the Claude Messages API, and asks for a JSON checklist. Needs ANTHROPIC_API_KEY in backend/.env.
"""

import json
import re
from typing import Any

import httpx

from app.core.config import settings

API_URL = "https://api.anthropic.com/v1/messages"
DOC_LABELS = {
    "cnic_front": "CNIC front",
    "cnic_back": "CNIC back",
    "driving_licence": "Driving licence",
    "vehicle_registration": "Vehicle registration",
}

PROMPT = """You help RAAZICID, a donation service in Pakistan, check a new delivery rider's documents.
An admin makes the final decision; you only point out what to look at.

Rider details given at sign-up:
- Full name: {name}
- Vehicle: {vehicle_type}, number {vehicle_number}

The photos above are labelled in order: {labels}.

Check each of these and reply with JSON only, no other text:
{{
  "summary": "one or two plain sentences for the admin",
  "checks": [
    {{"label": "All four documents are present and readable", "ok": true, "detail": "..."}},
    {{"label": "CNIC looks like a Pakistani CNIC (front and back)", "ok": true, "detail": "..."}},
    {{"label": "Name on CNIC matches the sign-up name", "ok": true, "detail": "..."}},
    {{"label": "Driving licence matches the vehicle type and is not visibly expired", "ok": true, "detail": "..."}},
    {{"label": "Vehicle registration number matches the sign-up vehicle number", "ok": true, "detail": "..."}},
    {{"label": "No signs of editing, screenshots of screens or photos of photos", "ok": true, "detail": "..."}}
  ]
}}
Use "ok": null when you cannot tell from the photos. Do not repeat full CNIC numbers in your answer."""


class ReviewError(Exception):
    pass


def _parse(text: str) -> dict[str, Any]:
    match = re.search(r"\{.*\}", text, re.S)
    if not match:
        raise ReviewError("The AI answer was not in the expected format. Try again.")
    data = json.loads(match.group(0))
    checks = [
        {"label": str(c.get("label", ""))[:200], "ok": c.get("ok") if c.get("ok") in (True, False, None) else None,
         "detail": str(c.get("detail", ""))[:500]}
        for c in data.get("checks", []) if isinstance(c, dict)
    ]
    return {"summary": str(data.get("summary", ""))[:1000], "checks": checks}


def review_documents(name: str, vehicle_type: str, vehicle_number: str, docs: list[tuple[str, str]]) -> dict[str, Any]:
    """docs = [(doc_type, https url)]. Returns {"summary", "checks", "model"}."""
    if not settings.ANTHROPIC_API_KEY:
        raise ReviewError("AI review is not set up. Add ANTHROPIC_API_KEY to backend/.env and restart the backend.")
    if not docs:
        raise ReviewError("The rider has not uploaded any documents yet.")
    content: list[dict[str, Any]] = [{"type": "image", "source": {"type": "url", "url": url}} for _, url in docs]
    content.append({"type": "text", "text": PROMPT.format(
        name=name, vehicle_type=vehicle_type, vehicle_number=vehicle_number,
        labels=", ".join(f"{i + 1}. {DOC_LABELS.get(t, t)}" for i, (t, _) in enumerate(docs)),
    )})
    try:
        res = httpx.post(
            API_URL,
            headers={"x-api-key": settings.ANTHROPIC_API_KEY, "anthropic-version": "2023-06-01", "content-type": "application/json"},
            json={"model": settings.CLAUDE_MODEL, "max_tokens": 1200, "messages": [{"role": "user", "content": content}]},
            timeout=90,
        )
    except httpx.HTTPError:
        raise ReviewError("Could not reach the AI service. Check the internet connection and try again.")
    if res.status_code != 200:
        try:
            msg = res.json().get("error", {}).get("message", "")
        except ValueError:
            msg = ""
        raise ReviewError(f"AI service error ({res.status_code}). {msg}".strip())
    text = "".join(b.get("text", "") for b in res.json().get("content", []) if b.get("type") == "text")
    try:
        out = _parse(text)
    except (ValueError, json.JSONDecodeError):
        raise ReviewError("The AI answer was not in the expected format. Try again.")
    out["model"] = settings.CLAUDE_MODEL
    return out
