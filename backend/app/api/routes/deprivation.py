"""Long-term deprivation layer (PSLM, HIES, IOM DTM tables an admin uploads). Admin only. Never changes need levels."""

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.deps import require_roles
from app.core.errors import api_error
from app.db.session import get_db
from app.models import Location, NeedIndicator, User
from app.models.enums import LocationLevel, Role
from app.services import deprivation

router = APIRouter(tags=["deprivation"])
admin_only = require_roles(Role.admin)
MAX_BYTES = 5 * 1024 * 1024


@router.get("/admin/deprivation")
def get_layer(parent_id: Optional[uuid.UUID] = None, _: User = Depends(admin_only), db: Session = Depends(get_db)):
    if parent_id and db.get(Location, parent_id) is None:
        raise api_error(404, "location_not_found", "Place not found")
    return deprivation.area_deprivation(db, parent_id)


@router.post("/admin/deprivation/upload")
def upload_table(file: UploadFile = File(...), measure: str = Form(...), source: str = Form(..., min_length=2, max_length=120),
                 year: int = Form(..., ge=1998, le=2100), place_column: str = Form(""), value_column: str = Form(""),
                 invert: bool = Form(False), add_missing: bool = Form(True),
                 _: User = Depends(admin_only), db: Session = Depends(get_db)):
    """A CSV or Excel table with a place column and a number column. Replaces the earlier table of that measure."""
    info = deprivation.MEASURES.get(measure)
    if info is None:
        raise api_error(422, "bad_measure", "Choose what the table measures")
    name = file.filename or "table.csv"
    if not name.lower().endswith((".csv", ".txt", ".xlsx", ".xlsm")):
        raise api_error(422, "bad_file", "Upload a CSV or an Excel (.xlsx) file")
    raw = file.file.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise api_error(413, "too_big", "Tables up to 5 MB")
    try:
        rows = deprivation.read_rows(raw, name)
    except Exception:
        raise api_error(422, "unreadable", "Could not read this file. Save it as .xlsx or .csv and try again.")
    t = deprivation.parse_table(rows, info["share"], place_column.strip() or None, value_column.strip() or None, invert)
    if not t["rows"]:
        found = f". Columns found: {', '.join(c for c in t['columns'] if c)}"[:300] if t["columns"] else ""
        raise api_error(422, "no_rows", ("; ".join(t["problems"][:3]) or "No rows with a place and a number") + found)
    result = deprivation.save_table(db, measure, t["rows"], source.strip(), year, add_missing)
    return {**result, "problems": t["problems"][:10], "used": t["used"], "columns": [c for c in t["columns"] if c][:40]}


@router.delete("/admin/deprivation/{measure}")
def remove_table(measure: str, _: User = Depends(admin_only), db: Session = Depends(get_db)):
    if measure not in deprivation.MEASURES:
        raise api_error(404, "bad_measure", "Unknown table")
    db.execute(delete(NeedIndicator).where(NeedIndicator.indicator == f"dep:{measure}"))
    db.commit()
    return {"removed": measure}


@router.get("/admin/deprivation/template")
def template(_: User = Depends(admin_only), db: Session = Depends(get_db)):
    """A CSV to fill in: province, place and an empty value for every province, city and district we know."""
    locs = {l.id: l for l in db.scalars(select(Location))}

    def province(l: Location) -> str:
        guard = 0
        while l.parent_id and guard < 6:
            l = locs[l.parent_id]
            guard += 1
        return l.name

    rows = sorted((province(l), l.name) for l in locs.values() if l.level != LocationLevel.area)
    lines = ["province,place,value"] + [f'"{p}","{n}",' for p, n in rows]
    return {"filename": "raazicid-places-template.csv", "csv": "\n".join(lines) + "\n"}
