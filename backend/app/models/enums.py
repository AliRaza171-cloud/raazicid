"""All fixed value lists used by the database. Stored as text, so adding a value needs no migration of existing rows."""

from enum import Enum


class Role(str, Enum):
    donor = "donor"
    rider = "rider"
    admin = "admin"


class LocationLevel(str, Enum):
    province = "province"
    city = "city"
    region = "region"   # district / town, e.g. Karachi South
    area = "area"       # neighbourhood, e.g. Lyari


class RiderStatus(str, Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"
    suspended = "suspended"


class DocType(str, Enum):
    cnic_front = "cnic_front"
    cnic_back = "cnic_back"
    driving_licence = "driving_licence"
    vehicle_registration = "vehicle_registration"


class VehicleType(str, Enum):
    motorbike = "motorbike"
    rickshaw = "rickshaw"
    pickup = "pickup"


class Condition(str, Enum):
    new = "new"
    good = "good"
    used = "used"


class FoodType(str, Enum):
    cooked = "cooked"
    dry = "dry"


class DonationStatus(str, Enum):
    """Donation life-cycle. Each step can only move forward (see docs/status-flow.md)."""
    in_review = "in_review"
    accepted = "accepted"
    rejected = "rejected"
    rider_assigned = "rider_assigned"
    picked_up = "picked_up"
    delivered = "delivered"          # our rider dropped it at the NGO (the last step: the NGO gives it out)
    cancelled = "cancelled"


class ImageKind(str, Enum):
    donor_photo = "donor_photo"
    pickup_proof = "pickup_proof"
    delivery_proof = "delivery_proof"




class JobStatus(str, Enum):
    assigned = "assigned"
    accepted = "accepted"
    declined = "declined"
    picked_up = "picked_up"
    delivered = "delivered"
    cancelled = "cancelled"


class SourceKind(str, Enum):
    reliefweb = "reliefweb"
    gdacs = "gdacs"
    hdx_hapi = "hdx_hapi"
    pbs_spi = "pbs_spi"
    pmd = "pmd"
    web_search = "web_search"
    upload = "upload"
    ai_needs = "ai_needs"     # AI web scan for current needs (Phase 6)


class ReportStatus(str, Enum):
    new = "new"
    tagged = "tagged"
    needs_review = "needs_review"
    archived = "archived"


class AlertType(str, Enum):
    flood = "flood"
    earthquake = "earthquake"
    cyclone = "cyclone"
    drought = "drought"
    heatwave = "heatwave"
    cold_wave = "cold_wave"
    heavy_rain = "heavy_rain"
    other = "other"


class AlertSeverity(str, Enum):
    watch = "watch"
    moderate = "moderate"
    severe = "severe"


class AlertStatus(str, Enum):
    unconfirmed = "unconfirmed"   # found by web search / news only
    confirmed = "confirmed"
    handled = "handled"
    dismissed = "dismissed"


class FlagStatus(str, Enum):
    open = "open"
    dismissed = "dismissed"
    action_taken = "action_taken"


class Severity(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"


