"""Import every model here so Alembic and `Base.metadata` see all tables."""

from app.models.alerts import AlertNeed, Appeal, DisasterAlert, alert_locations, alert_reports  # noqa: F401
from app.models.donations import Donation, DonationImage, HandOut, Rating, StatusChange  # noqa: F401
from app.models.locations import Category, Location  # noqa: F401
from app.models.logistics import DistributionPoint, Job, PointRequest, RiderPing, point_categories  # noqa: F401
from app.models.needs import NeedIndicator, NeedLevel, SeasonalRule  # noqa: F401
from app.models.rag import ChunkLocation, Report, ReportChunk, Source  # noqa: F401
from app.models.trust import FraudFlag, Notification  # noqa: F401
from app.models.users import DocumentReview, RefreshToken, RiderDocument, RiderProfile, User  # noqa: F401
