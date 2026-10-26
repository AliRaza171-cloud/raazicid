"""The AI (OpenAI or Claude) reviews a rider's verification photos (Phase 5). Advisory only: the admin always decides.

Sends the CNIC, licence and vehicle registration photos (Cloudinary URLs) with the rider's name and vehicle
number to the AI, and asks for a JSON checklist. Set up in backend/.env (see services/llm.py).
"""

import json
import re
from typing import Any

from app.services import llm

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
    if not llm.available():
        raise ReviewError(llm.not_set_up())
    if not docs:
        raise ReviewError("The rider has not uploaded any documents yet.")
    prompt = PROMPT.format(name=name, vehicle_type=vehicle_type, vehicle_number=vehicle_number,
                           labels=", ".join(f"{i + 1}. {DOC_LABELS.get(t, t)}" for i, (t, _) in enumerate(docs)))
    try:
        res = llm.complete(prompt, images=[url for _, url in docs], max_tokens=1200, timeout=90)
    except llm.LLMError as e:
        raise ReviewError(str(e))
    try:
        out = _parse(res.text)
    except (ValueError, json.JSONDecodeError):
        raise ReviewError("The AI answer was not in the expected format. Try again.")
    out["model"] = llm.label()
    return out
