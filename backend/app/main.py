from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import admin_donations, admin_riders, auth, donations, health, me, points, reference, rider
from app.core.config import settings

app = FastAPI(
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
app.include_router(points.router, prefix=API_PREFIX)
app.include_router(rider.router, prefix=API_PREFIX)
app.include_router(admin_donations.tracking_router, prefix=API_PREFIX)

# Phase 3+: donations, points
# Phase 4+: jobs, tracking, notifications
# Phase 5-8: classify, needs, need-finder, alerts, appeals, seasonal, flags, analytics
