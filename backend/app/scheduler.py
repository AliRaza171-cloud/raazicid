"""Background jobs (Phase 6): fetch disaster and need data and refresh need levels while the backend runs.

Turned off with ENABLE_SCHEDULER=false (tests do this). Admins can also run each source by hand.
"""

import logging
from datetime import datetime, timedelta, timezone

from app.core.config import settings
from app.services import llm
from app.db.session import SessionLocal
from app.models.enums import SourceKind

log = logging.getLogger("raazicid.scheduler")


def _job(kind: SourceKind, every: timedelta):
    def run():
        from sqlalchemy import select

        from app.models import Source
        from app.services.sources.runner import run_source
        with SessionLocal() as db:
            src = db.scalar(select(Source).where(Source.kind == kind))
            if src is None or not src.is_enabled:
                return
            # A restart (e.g. uvicorn --reload) should not fetch again if this source ran recently
            if src.last_run_at and datetime.now(timezone.utc) - src.last_run_at < every * 0.9:
                return
            ok, status = run_source(db, kind)
            log.info("%s: %s", kind.value, status)
    return run


def _report_reader_job():
    """Every 2 hours: the AI reads up to 10 library reports it has not read yet, then refreshes need levels."""
    from app.services.needs import recompute
    from app.services.rag.report_needs import read_waiting, waiting
    with SessionLocal() as db:
        if not waiting(db):
            return
        log.info("report reader: %s", read_waiting(db, 10))
        recompute(db)


def _needs_job():
    from app.services.needs import recompute
    with SessionLocal() as db:
        recompute(db)


def start():
    if not settings.ENABLE_SCHEDULER:
        return None
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
    except ImportError:
        log.warning("apscheduler is not installed: run pip install -r requirements.txt to fetch data automatically")
        return None
    now = datetime.now(timezone.utc)
    s = BackgroundScheduler(timezone="UTC", job_defaults={"coalesce": True, "max_instances": 1, "misfire_grace_time": 600})
    s.add_job(_job(SourceKind.gdacs, timedelta(minutes=30)), "interval", minutes=30, next_run_time=now + timedelta(seconds=20), id="gdacs")
    s.add_job(_job(SourceKind.hdx_hapi, timedelta(hours=24)), "interval", hours=24, next_run_time=now + timedelta(seconds=60), id="hdx")
    s.add_job(_needs_job, "interval", minutes=60, id="needs")
    if settings.RELIEFWEB_APPNAME:   # Phase 6B: reports into the library every 6 hours
        s.add_job(_job(SourceKind.reliefweb, timedelta(hours=6)), "interval", hours=6, next_run_time=now + timedelta(seconds=90), id="reliefweb")
    if llm.available():
        s.add_job(_report_reader_job, "interval", hours=2, next_run_time=now + timedelta(minutes=3), id="report_reader")
    if settings.AI_NEEDS_EVERY_DAYS > 0 and llm.available():   # AI web scan for current needs (all Pakistan)
        every = timedelta(days=settings.AI_NEEDS_EVERY_DAYS)
        s.add_job(_job(SourceKind.ai_needs, every), "interval", days=settings.AI_NEEDS_EVERY_DAYS, id="ai_needs")
    if settings.NGO_FINDER_EVERY_HOURS > 0:   # NGOs where places in need have none (free sources first)
        every = timedelta(hours=settings.NGO_FINDER_EVERY_HOURS)
        s.add_job(_job(SourceKind.ngo_finder, every), "interval", hours=settings.NGO_FINDER_EVERY_HOURS,
                  next_run_time=now + timedelta(minutes=5), id="ngo_finder")
    if settings.WEB_SCAN_EVERY_HOURS > 0 and llm.available():
        every = timedelta(hours=settings.WEB_SCAN_EVERY_HOURS)
        s.add_job(_job(SourceKind.web_search, every), "interval", hours=settings.WEB_SCAN_EVERY_HOURS, id="webscan")
    s.start()
    log.info("scheduler started")
    return s
