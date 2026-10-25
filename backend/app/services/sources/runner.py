"""Run one data source, record how it went on the sources table, then refresh need levels."""

import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import DisasterAlert, Source
from app.models.enums import AlertStatus, SourceKind
from app.services import needs
from app.services.sources import gdacs, hdx, reliefweb, webscan

log = logging.getLogger("raazicid.sources")


def _gdacs(db: Session, source_id: int) -> str:
    return gdacs.sync(db, gdacs.fetch(), source_id)


def _hdx(db: Session, source_id: int) -> str:
    return hdx.fetch_and_sync(db, source_id)


def _webscan(db: Session, source_id: int) -> str:
    events, _ = webscan.scan()
    return webscan.sync(db, events, source_id)


RUNNERS = {SourceKind.gdacs: _gdacs, SourceKind.hdx_hapi: _hdx, SourceKind.web_search: _webscan,
           SourceKind.reliefweb: reliefweb.fetch_and_sync}


def fill_alert_needs(db: Session) -> None:
    """Suggest 'what is needed' for open alerts that have none yet (an admin's edits are never overwritten)."""
    for a in db.scalars(select(DisasterAlert).where(DisasterAlert.status.in_([AlertStatus.unconfirmed, AlertStatus.confirmed]))):
        if not a.needs:
            needs.suggest_alert_needs(db, a)
    db.commit()


def run_source(db: Session, kind: SourceKind) -> tuple[bool, str]:
    """Returns (ok, status line). Never raises: the error is saved as the source's status."""
    source = db.scalar(select(Source).where(Source.kind == kind))
    if source is None or kind not in RUNNERS:
        return False, "This source cannot be run yet"
    try:
        status = RUNNERS[kind](db, source.id)
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
