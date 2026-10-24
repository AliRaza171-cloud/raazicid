"""The logged-in user's own profile and rider documents, plus upload signing."""

from fastapi import APIRouter, Depends, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.deps import get_current_user, require_roles
from app.core.errors import api_error
from app.db.session import get_db
from app.models import Location, RiderDocument, User
from app.models.enums import RiderStatus, Role
from app.schemas.auth import MeUpdate, RiderDocIn, RiderDocOut, UploadSignIn, UploadSignOut, UserOut
from app.services.accounts import user_out
from app.services.uploads import upload_signature

router = APIRouter(tags=["me"])


@router.get("/me", response_model=UserOut)
def get_me(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return user_out(db, user)


@router.patch("/me", response_model=UserOut)
def update_me(body: MeUpdate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    data = body.model_dump(exclude_unset=True)
    if "email" in data and data["email"]:
        email = data["email"].lower()
        taken = db.scalar(select(User).where(func.lower(User.email) == email, User.id != user.id))
        if taken:
            raise api_error(409, "email_taken", "An account with this email already exists")
        data["email"] = email
    if data.get("location_id") and db.get(Location, data["location_id"]) is None:
        raise api_error(422, "bad_location", "Choose your area from the list")
    if "full_name" in data and data["full_name"]:
        data["full_name"] = " ".join(data["full_name"].split())
    for key, value in data.items():
        setattr(user, key, value)
    db.commit()
    db.refresh(user)
    return user_out(db, user)


@router.get("/me/rider-documents", response_model=list[RiderDocOut])
def my_documents(user: User = Depends(require_roles(Role.rider)), db: Session = Depends(get_db)):
    rows = db.scalars(select(RiderDocument).where(RiderDocument.rider_id == user.id).order_by(RiderDocument.created_at))
    return [RiderDocOut(id=d.id, doc_type=d.doc_type, file_url=d.file_url, created_at=d.created_at) for d in rows]


@router.post("/me/rider-documents", response_model=RiderDocOut, status_code=status.HTTP_201_CREATED)
def add_document(body: RiderDocIn, user: User = Depends(require_roles(Role.rider)), db: Session = Depends(get_db)):
    """Add or replace one document. Re-uploading after a rejection sends the rider back to review."""
    rp = user.rider_profile
    if rp is None:
        raise api_error(409, "no_rider_profile", "Rider profile missing")
    if rp.status == RiderStatus.suspended:
        raise api_error(403, "rider_suspended", "Your rider account is suspended. Contact RAAZICID")

    for old in db.scalars(
        select(RiderDocument).where(RiderDocument.rider_id == user.id, RiderDocument.doc_type == body.doc_type)
    ):
        db.delete(old)
    doc = RiderDocument(rider_id=user.id, doc_type=body.doc_type, file_url=body.file_url)
    db.add(doc)
    if rp.status == RiderStatus.rejected:
        rp.status = RiderStatus.pending
    db.commit()
    db.refresh(doc)
    return RiderDocOut(id=doc.id, doc_type=doc.doc_type, file_url=doc.file_url, created_at=doc.created_at)


@router.post("/uploads/sign", response_model=UploadSignOut)
def sign_upload(body: UploadSignIn, user: User = Depends(get_current_user)):
    if not (settings.CLOUDINARY_CLOUD_NAME and settings.CLOUDINARY_API_KEY and settings.CLOUDINARY_API_SECRET):
        raise api_error(503, "uploads_not_configured", "Photo uploads are not set up on the server yet")
    folder = f"raazicid/{body.purpose}/{user.id}"
    return upload_signature(
        settings.CLOUDINARY_CLOUD_NAME, settings.CLOUDINARY_API_KEY, settings.CLOUDINARY_API_SECRET, folder
    )
