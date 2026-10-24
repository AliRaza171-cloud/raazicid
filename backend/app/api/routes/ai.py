"""AI helpers (Phase 5): photo category suggestion, classifier status, how often the AI was right."""

from typing import Optional

import httpx
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.deps import get_current_user, require_roles
from app.core.errors import api_error
from app.db.session import get_db
from app.models import Category, Donation, User
from app.models.enums import Role
from app.services.classifier import classifier

router = APIRouter(tags=["ai"])
MAX_IMAGE_BYTES = 10 * 1024 * 1024


class ClassifyIn(BaseModel):
    image_url: str


class Suggestion(BaseModel):
    category_id: int
    name: str
    p: float


class ClassifyOut(BaseModel):
    model_version: Optional[str]
    suggestions: list[Suggestion]


class StatusOut(BaseModel):
    classifier: str            # ready | not_installed | no_model
    version: Optional[str]
    accuracy: Optional[float]  # on the Open Images test split
    own_photo_accuracy: Optional[float]
    document_review: bool      # ANTHROPIC_API_KEY set


def _download(url: str) -> bytes:
    prefix = f"https://res.cloudinary.com/{settings.CLOUDINARY_CLOUD_NAME}/"
    if not settings.CLOUDINARY_CLOUD_NAME or not url.startswith(prefix):
        # Only our own uploads: the server must not fetch arbitrary links
        raise api_error(422, "bad_image_url", "Upload the photo first")
    try:
        with httpx.stream("GET", url, timeout=20, follow_redirects=False) as r:
            if r.status_code != 200:
                raise api_error(502, "image_download_failed", "Could not read the photo. Try again")
            data = bytearray()
            for chunk in r.iter_bytes():
                data.extend(chunk)
                if len(data) > MAX_IMAGE_BYTES:
                    raise api_error(422, "image_too_big", "The photo is too big")
            return bytes(data)
    except httpx.HTTPError:
        raise api_error(502, "image_download_failed", "Could not read the photo. Try again")


@router.get("/ai/status", response_model=StatusOut)
def status(_: User = Depends(get_current_user)):
    return StatusOut(**classifier.status(), document_review=bool(settings.ANTHROPIC_API_KEY))


@router.post("/ai/classify", response_model=ClassifyOut)
def classify(body: ClassifyIn, _: User = Depends(require_roles(Role.donor, Role.admin)), db: Session = Depends(get_db)):
    """Suggest a category for an uploaded donation photo. The donor confirms or changes it."""
    if not classifier.ready:
        raise api_error(503, "classifier_not_ready", "Photo suggestions are not set up yet. Choose the category yourself")
    image = _download(body.image_url)
    try:
        top = classifier.predict(image)
    except Exception:
        raise api_error(422, "bad_image", "Could not read that photo. Try another one")
    names = {c.id: c.name for c in db.scalars(select(Category))}
    return ClassifyOut(
        model_version=classifier.version,
        suggestions=[Suggestion(category_id=t["category_id"], name=names.get(t["category_id"], "?"), p=t["p"]) for t in top],
    )


class CategoryStat(BaseModel):
    category_id: int
    name: str
    suggested: int
    kept: int


class AiStats(BaseModel):
    donations_with_ai: int
    top1_kept: int             # donor kept the AI's first choice
    top3_hit: int              # donor's category was in the AI's top 3
    top1_rate: Optional[float]
    top3_rate: Optional[float]
    by_category: list[CategoryStat]


@router.get("/admin/ai/stats", response_model=AiStats)
def stats(_: User = Depends(require_roles(Role.admin)), db: Session = Depends(get_db)):
    """How often real donors agreed with the AI. Good evidence for the thesis next to the test-set accuracy."""
    rows = list(db.scalars(select(Donation).where(Donation.ai_category_id.is_not(None))))
    names = {c.id: c.name for c in db.scalars(select(Category))}
    top1 = sum(1 for d in rows if d.category_id == d.ai_category_id)
    top3 = sum(1 for d in rows if d.category_id in {t.get("category_id") for t in (d.ai_top3 or [])} or d.category_id == d.ai_category_id)
    per: dict[int, list[int]] = {}
    for d in rows:
        s = per.setdefault(d.ai_category_id, [0, 0])
        s[0] += 1
        s[1] += int(d.category_id == d.ai_category_id)
    n = len(rows)
    return AiStats(
        donations_with_ai=n, top1_kept=top1, top3_hit=top3,
        top1_rate=round(top1 / n, 3) if n else None, top3_rate=round(top3 / n, 3) if n else None,
        by_category=[CategoryStat(category_id=c, name=names.get(c, "?"), suggested=v[0], kept=v[1])
                     for c, v in sorted(per.items())],
    )
