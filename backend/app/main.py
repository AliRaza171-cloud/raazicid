from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import (admin_donations, admin_riders, ai, alerts, appeals, auth, deprivation, donations, health, me, needs, ngos, reference,
                            reports, rider)
from app.core.config import settings
from app.scheduler import start as start_scheduler
from app.services.rag.embed import warm_up as warm_up_embeddings


@asynccontextmanager
async def lifespan(_: FastAPI):
    scheduler = start_scheduler()   # Phase 6: fetch GDACS / HDX data and refresh need levels in the background
    warm_up_embeddings()            # Phase 6B: load the vector-search model in the background
    yield
    if scheduler:
        scheduler.shutdown(wait=False)


app = FastAPI(
    lifespan=lifespan,
    title=settings.APP_NAME,
    version="0.1.0",
    description="Backend for RAAZICID: AI-guided donation collection and distribution in Pakistan.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Everything lives under /api/v1 so a future v2 can sit alongside it
API_PREFIX = "/api/v1"
app.include_router(health.router, prefix=API_PREFIX)
app.include_router(reference.router, prefix=API_PREFIX)
app.include_router(auth.router, prefix=API_PREFIX)
app.include_router(me.router, prefix=API_PREFIX)
app.include_router(admin_riders.router, prefix=API_PREFIX)
app.include_router(donations.router, prefix=API_PREFIX)
app.include_router(admin_donations.router, prefix=API_PREFIX)
app.include_router(ngos.router, prefix=API_PREFIX)
app.include_router(rider.router, prefix=API_PREFIX)
app.include_router(ai.router, prefix=API_PREFIX)
app.include_router(admin_donations.tracking_router, prefix=API_PREFIX)
app.include_router(needs.router, prefix=API_PREFIX)
app.include_router(alerts.router, prefix=API_PREFIX)
app.include_router(reports.router, prefix=API_PREFIX)
app.include_router(appeals.router, prefix=API_PREFIX)
app.include_router(deprivation.router, prefix=API_PREFIX)

# Phase 3+: donations, NGOs
# Phase 4+: jobs, tracking, notifications
# Phase 5-8: classify, needs, need-finder, alerts, appeals, seasonal, flags, analytics
