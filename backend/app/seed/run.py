"""Fill the database with starting data. Run from backend/:  python -m app.seed.run

Safe to run many times: it only inserts rows that are missing.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models import Category, Location, SeasonalRule, Source
from app.models.enums import LocationLevel, SourceKind
from app.seed.data import CATEGORIES, CITY_REGIONS, PROVINCES, SEASONAL_RULES, SOURCES


def get_or_create_location(db: Session, name: str, level: LocationLevel, parent: Location | None) -> Location:
    parent_id = parent.id if parent else None
    stmt = select(Location).where(Location.name == name)
    stmt = stmt.where(Location.parent_id.is_(None)) if parent_id is None else stmt.where(Location.parent_id == parent_id)
    loc = db.scalar(stmt)
    if loc is None:
        loc = Location(name=name, level=level, parent_id=parent_id)
        db.add(loc)
        db.flush()
    return loc


def seed(db: Session) -> dict:
    added = {"categories": 0, "sources": 0, "locations": 0, "seasonal_rules": 0}

    for cid, slug, name, perishable in CATEGORIES:
        if db.get(Category, cid) is None:
            db.add(Category(id=cid, slug=slug, name=name, is_perishable=perishable))
            added["categories"] += 1

    for sid, kind, name, every in SOURCES:
        if db.get(Source, sid) is None:
            db.add(Source(id=sid, kind=SourceKind(kind), name=name, every_minutes=every))
            added["sources"] += 1
    db.flush()

    before = db.query(Location).count()
    for province, cities in PROVINCES.items():
        p = get_or_create_location(db, province, LocationLevel.province, None)
        for city in cities:
            c = get_or_create_location(db, city, LocationLevel.city, p)
            for region, areas in CITY_REGIONS.get(city, {}).items():
                r = get_or_create_location(db, region, LocationLevel.region, c)
                for area in areas:
                    get_or_create_location(db, area, LocationLevel.area, r)
    added["locations"] = db.query(Location).count() - before

    slug_to_id = {slug: cid for cid, slug, _, _ in CATEGORIES}
    for name, slugs, start_m, end_m, hijri, days_before, weight in SEASONAL_RULES:
        for slug in slugs:
            exists = db.scalar(
                select(SeasonalRule).where(SeasonalRule.name == name, SeasonalRule.category_id == slug_to_id[slug])
            )
            if exists is None:
                db.add(SeasonalRule(
                    name=name, category_id=slug_to_id[slug], start_month=start_m, end_month=end_m,
                    hijri_month=hijri, days_before_event=days_before, weight=weight,
                ))
                added["seasonal_rules"] += 1

    db.commit()
    return added


if __name__ == "__main__":
    with SessionLocal() as session:
        print("Seed added:", seed(session))
