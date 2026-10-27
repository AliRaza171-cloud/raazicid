"""Run one data source, record how it went on the sources table, then refresh need levels."""

import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import DisasterAlert, Source
from app.models.enums import AlertStatus, SourceKind
from app.services import needs
from app.services.sources import ai_needs, gdacs, hdx, ngo_gaps, reliefweb, webscan

log = logging.getLogger("raazicid.sources")


def _gdacs(db: Session, source_id: int) -> str:
    return gdacs.sync(db, gdacs.fetch(), source_id)


def _hdx(db: Session, source_id: int) -> str:
    return hdx.fetch_and_sync(db, source_id)


def _webscan(db: Session, source_id: int) -> str:
    events, _ = webscan.scan()
    return webscan.sync(db, events, source_id)


def _reliefweb(db: Session, source_id: int) -> str:
    """New ReliefWeb reports go into the library, then the AI reads them for unmet needs."""
    from app.services import llm
    from app.services.rag.report_needs import read_waiting
    status = reliefweb.fetch_and_sync(db, source_id)
    return status + ("; " + read_waiting(db, 15) if llm.available() else "")


RUNNERS = {SourceKind.gdacs: _gdacs, SourceKind.hdx_hapi: _hdx, SourceKind.web_search: _webscan,
           SourceKind.reliefweb: _reliefweb, SourceKind.ai_needs: ai_needs.run, SourceKind.ngo_finder: ngo_gaps.run}
NAMES = {SourceKind.ai_needs: "AI web scan for current needs",
         SourceKind.ngo_finder: "NGO finder for places in need (OpenStreetMap, OCHA 3W, web search)"}


def ensure_source(db: Session, kind: SourceKind) -> Source:
    """Sources added after the first seed (e.g. the AI needs scan) are created when first used."""
    source = db.scalar(select(Source).where(Source.kind == kind))
    if source is None:
        source = Source(id=(db.scalar(select(func.max(Source.id))) or 0) + 1, kind=kind, name=NAMES.get(kind, kind.value))
        db.add(source)
        db.commit()
    return source


def fill_alert_needs(db: Session) -> None:
    """Suggest 'what is needed' for open alerts that have none yet (an admin's edits are never overwritten)."""
    for a in db.scalars(select(DisasterAlert).where(DisasterAlert.status.in_([AlertStatus.unconfirmed, AlertStatus.confirmed]))):
        if not a.needs:
            needs.suggest_alert_needs(db, a)
    db.commit()


def run_source(db: Session, kind: SourceKind, options: Optional[dict] = None) -> tuple[bool, str]:
    """Returns (ok, status line). Never raises: the error is saved as the source's status.
    options go to the runner, e.g. {"province_id": ...} for the AI needs scan."""
    source = ensure_source(db, kind) if kind in NAMES else db.scalar(select(Source).where(Source.kind == kind))
    if source is None or kind not in RUNNERS:
        return False, "This source cannot be run yet"
    source_id = source.id
    db.commit()   # no transaction held during slow downloads / the Claude scan
    try:
        status = RUNNERS[kind](db, source_id, **(options or {}))
        fill_alert_needs(db)
        needs.recompute(db)
        ok = True
    except Exception as e:  # network errors, missing keys, bad data: keep the app running
        db.rollback()
        status, ok = f"Error: {e}"[:500], False
        log.warning("source %s failed: %s", kind.value, e)
    source = db.scalar(select(Source).where(Source.kind == kind))
    source.last_run_at = datetime.now(timezone.utc)
    source.last_status = status
    db.commit()
    return ok, status
