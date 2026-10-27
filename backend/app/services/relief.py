"""What to donate for a disaster (Phase 6): our 12 categories ranked for each disaster type, with a plain reason.

Each disaster type lists the categories that help, when they help and how many per affected family:
  now    the first days: life-saving items (shelter, ready food, clean water and hygiene)
  soon   the next weeks: rations, bedding, clothes, baby items
  later  recovery: household items, school supplies, books
The list is then adjusted for:
  season    winter (Nov-Feb) moves blankets and winter support to "now"; summer (May-Aug) raises hygiene for floods
  time      3 weeks after the start, ready food gives way to rations and recovery items move up
  severity  a "watch" alert is advice to get items ready, not to send them yet
Quantities = affected families x items per family (6 people per family), when the alert has figures.
Pure functions, unit-tested; used for an alert's "what is needed" and for its need signals on the map.
"""

from dataclasses import dataclass
from datetime import date
from typing import Optional

from app.models.enums import AlertSeverity, AlertType

ORDER = {"now": 0, "soon": 1, "later": 2}
WINTER = {11, 12, 1, 2}
SUMMER = {5, 6, 7, 8}
RECOVERY_DAYS = 21


@dataclass(frozen=True)
class Rule:
    slug: str
    when: str            # now / soon / later
    per_family: float    # items per affected family (0 = do not estimate)
    why: str


R = Rule
RULES: dict[AlertType, list[Rule]] = {
    AlertType.flood: [
        R("emergency_relief", "now", 0.5, "Tents, tarpaulins and torches for families whose homes are under water."),
        R("food", "now", 1, "Ready-to-eat food: kitchens and stored food are under water."),
        R("hygiene", "now", 1, "Soap, water-cleaning tablets and sanitary items: dirty flood water spreads diarrhoea and skin disease."),
        R("grocery_ration", "now", 1, "A month of flour, rice, lentils and oil for when families can cook again."),
        R("blankets", "soon", 2, "Bedding is soaked, and nights in camps are cold."),
        R("clothes", "soon", 1, "Families leave with only the clothes they wear."),
        R("baby", "soon", 0.3, "Nappies, milk powder and baby food for infants in camps."),
        R("household", "later", 0.5, "Pots, water cans and mats to start again at home."),
        R("school_supplies", "later", 0.5, "School bags and stationery are lost; schools reopen when the water goes down."),
        R("books", "later", 0.3, "Textbooks for children when schools reopen."),
    ],
    AlertType.earthquake: [
        R("emergency_relief", "now", 1, "Tents and tarpaulins: houses are damaged and aftershocks keep people outside."),
        R("blankets", "now", 3, "People sleep outside, and nights are cold in the mountains."),
        R("food", "now", 1, "Ready-to-eat food for the first days, while kitchens are broken."),
        R("mobility_aids", "now", 0.05, "Wheelchairs, crutches and walkers for people injured by falling walls."),
        R("grocery_ration", "soon", 1, "Rations once families have a place to cook."),
        R("hygiene", "soon", 1, "Soap and water-cleaning tablets: water pipes and toilets are often broken."),
        R("winter_support", "soon", 1, "Warm jackets, shawls and heaters for families living in tents."),
        R("clothes", "soon", 1, "Clothes lost under the rubble."),
        R("household", "soon", 1, "Cooking pots and stoves lost under the rubble."),
        R("baby", "soon", 0.3, "Baby items for young families in tents."),
        R("school_supplies", "later", 0.5, "Children restart school in tents or repaired buildings."),
        R("books", "later", 0.3, "Textbooks lost with the houses."),
    ],
    AlertType.cyclone: [
        R("emergency_relief", "now", 0.5, "Tarpaulins and tents for roofs blown away."),
        R("food", "now", 1, "Ready-to-eat food while roads and markets are closed."),
        R("hygiene", "now", 1, "Soap and water-cleaning tablets: storm water mixes with sewage."),
        R("grocery_ration", "now", 1, "Rations for the weeks before fishing and farming restart."),
        R("blankets", "soon", 1, "Bedding soaked by rain and sea water."),
        R("clothes", "soon", 1, "Clothes lost to wind and water."),
        R("household", "soon", 0.5, "Pots, water cans and mats."),
        R("baby", "soon", 0.3, "Baby items for families in shelters."),
        R("school_supplies", "later", 0.5, "School items for when classes restart."),
    ],
    AlertType.drought: [
        R("grocery_ration", "now", 1, "Crops and animals die, so families slowly run out of food."),
        R("hygiene", "now", 1, "Water is short: water cans, water-cleaning tablets and soap."),
        R("baby", "now", 0.3, "Young children become malnourished first: baby food and milk powder."),
        R("food", "soon", 0.5, "Ready food for the weakest families."),
        R("household", "soon", 0.5, "Water containers to carry and store water."),
        R("clothes", "later", 0.5, "Families spend everything on food and water."),
        R("school_supplies", "later", 0.5, "Children leave school to fetch water or work; school items help them stay."),
    ],
    AlertType.heatwave: [
        R("hygiene", "now", 1, "Drinking water, oral rehydration salts (ORS) and soap."),
        R("baby", "now", 0.2, "Babies dehydrate fastest: ORS and baby items."),
        R("food", "soon", 0.5, "Food that needs no cooking in the heat."),
        R("household", "soon", 0.3, "Water coolers and containers."),
        R("emergency_relief", "soon", 0.2, "Shade sheets for camps and street cooling points."),
    ],
    AlertType.cold_wave: [
        R("blankets", "now", 2, "Blankets for families without heating."),
        R("winter_support", "now", 1, "Warm jackets, shawls, gloves and heaters."),
        R("clothes", "now", 1, "Warm clothes, especially for children."),
        R("baby", "soon", 0.3, "Warm baby clothes and blankets."),
        R("food", "soon", 0.5, "Hot meals for people living outside."),
        R("grocery_ration", "later", 0.5, "Rations when work stops in the cold."),
    ],
    AlertType.heavy_rain: [
        R("emergency_relief", "now", 0.5, "Tarpaulins for leaking and broken roofs."),
        R("hygiene", "now", 1, "Soap and water-cleaning tablets: standing water spreads disease."),
        R("blankets", "soon", 1, "Bedding soaked by rain."),
        R("food", "soon", 0.5, "Ready food where kitchens are flooded."),
        R("household", "soon", 0.5, "Pots, water cans and mats."),
        R("clothes", "later", 0.5, "Clothes ruined by water."),
    ],
    AlertType.other: [
        R("emergency_relief", "now", 1, "Shelter and basic relief items."),
        R("food", "now", 0.5, "Ready-to-eat food."),
        R("hygiene", "soon", 1, "Soap and clean water."),
        R("blankets", "soon", 1, "Bedding for people away from home."),
    ],
}
COLD_HITS = {AlertType.flood, AlertType.earthquake, AlertType.cyclone, AlertType.heavy_rain, AlertType.other}
RECOVERY_UP = {"household", "school_supplies", "books", "grocery_ration", "clothes"}


@dataclass
class Advice:
    slug: str
    when: str
    why: str
    per_family: float
    quantity: Optional[int] = None


def recommend(kind: AlertType, severity: AlertSeverity, today: date, started: Optional[date] = None,
              families: Optional[int] = None) -> tuple[list[Advice], list[str]]:
    """(advice per category, notes explaining the adjustments). Highest priority first."""
    items = {r.slug: Advice(r.slug, r.when, r.why, r.per_family) for r in RULES.get(kind, RULES[AlertType.other])}
    notes: list[str] = []
    if today.month in WINTER and kind in COLD_HITS:
        notes.append("It is winter, so warm items are needed right away.")
        for slug, why, per in (("blankets", "It is winter: bedding is needed from the first night.", 2),
                               ("winter_support", "It is winter: warm jackets, shawls and heaters for people without a home.", 1)):
            if slug in items:
                items[slug].when, items[slug].why = "now", why
            else:
                items[slug] = Advice(slug, "now", why, per)
    if today.month in SUMMER and kind in (AlertType.flood, AlertType.heavy_rain) and "hygiene" in items:
        items["hygiene"].why += " Summer heat makes disease spread faster."
    if started and (today - started).days >= RECOVERY_DAYS:
        notes.append(f"It started {(today - started).days} days ago: families are moving from emergency help to recovery.")
        if "food" in items and items["food"].when == "now":
            items["food"].when = "soon"
        for slug in RECOVERY_UP:
            if slug in items and items[slug].when == "later":
                items[slug].when = "soon"
            elif slug in items and items[slug].when == "soon" and slug == "grocery_ration":
                items[slug].when = "now"
    if severity == AlertSeverity.watch:
        notes.append("This is a watch alert: get these items ready, and send them once damage is confirmed.")
    for a in items.values():
        if families and a.per_family:
            a.quantity = max(1, round(families * a.per_family))
    out = sorted(items.values(), key=lambda a: ORDER[a.when])   # stable: keeps the rule order inside each group
    return out, notes


def alert_slugs(kind: AlertType, today: date, started: Optional[date] = None) -> dict[str, float]:
    """Categories an alert raises on the needs map, with their weight: 'now' items count fully, 'soon' items 0.8.
    'Later' (recovery) items are not a need signal yet."""
    advice, _ = recommend(kind, AlertSeverity.severe, today, started)
    return {a.slug: (1.0 if a.when == "now" else 0.8) for a in advice if a.when != "later"}
