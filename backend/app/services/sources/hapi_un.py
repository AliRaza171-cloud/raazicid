"""UN data for Pakistan from HDX HAPI (OCHA's Humanitarian API), fetched with the IPC / prices / poverty data.

  3W, operational presence (OCHA): which UN agencies and NGOs work in each district, per sector.
       Used to flag "neglected" places: high need, but nobody working on that need there.
  Humanitarian needs (OCHA response plans): people in need per district and sector. A need signal.
  Rainfall (WFP / CHIRPS): 3-month rainfall against the long-term average per district. Flood / drought risk.
  Refugees (UNHCR): national totals only (HAPI has no district breakdown). A fact for the need finder.
  Displaced people (IOM DTM): internally displaced people per district from DTM's assessments. A need signal
       while recent; older figures (Pakistan's are from the 2022 floods) show in the long-term deprivation layer.

HAPI does not have every subject for every country: whatever is missing for Pakistan is skipped and named in
the source status ("Humanitarian needs: none published for Pakistan").
"""

from collections import defaultdict
from datetime import date, timedelta
from typing import Any, Callable, Optional

from app.services.sources.hdx import ROOT, _d, get_all

# HAPI sector names -> RAAZICID category slugs. Matched on words, because sector codes vary between countries.
SECTOR_WORDS: list[tuple[tuple[str, ...], list[str]]] = [
    (("education",), ["school_supplies", "books"]),
    (("food", "livelihood", "agricultur"), ["food", "grocery_ration"]),
    (("nutrition",), ["food", "baby"]),
    (("health",), ["hygiene", "mobility_aids"]),
    (("water", "sanitation", "hygiene", "wash"), ["hygiene"]),
    (("shelter", "non-food", "nfi"), ["blankets", "household", "winter_support"]),
    (("protection", "child"), ["baby", "clothes"]),
    (("recovery",), ["household"]),
    (("multi", "cash", "intersector"), ["emergency_relief"]),
]
SKIP_SECTORS = ("coordination", "logistics", "telecom", "camp")


def sector_categories(sector: str) -> list[str]:
    """Our category slugs for a HAPI sector name ("Water Sanitation Hygiene" -> ["hygiene"])."""
    s = (sector or "").lower()
    if any(w in s for w in SKIP_SECTORS):
        return []
    out: list[str] = []
    for words, slugs in SECTOR_WORDS:
        if any(w in s for w in words):
            out += [x for x in slugs if x not in out]
    return out


def category_sectors(slug: str, sectors: list[str]) -> list[str]:
    """Which of these sector names serve a category (the reverse of sector_categories)."""
    return [s for s in sectors if slug in sector_categories(s)]


def _place(r: dict[str, Any]) -> tuple[str, str, str]:
    return (str(r.get("admin1_name") or ""), str(r.get("admin2_name") or ""), str(r.get("admin2_code") or ""))


# ---------- pure parsers (unit-tested) ----------

def presence(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Per district (or province when that is all there is): {sector: [organisations]} from the latest 3W."""
    by: dict[tuple, dict[str, set]] = defaultdict(lambda: defaultdict(set))
    names: dict[tuple, dict[str, str]] = defaultdict(dict)   # short name shown -> full name (to match NGOs we know)
    period: dict[tuple, Optional[date]] = {}
    for r in rows:
        if not r.get("admin1_name") or not r.get("sector_name"):
            continue
        org = r.get("org_acronym") or r.get("org_name")
        if not org:
            continue
        key = _place(r)
        by[key][str(r["sector_name"])].add(str(org)[:60])
        if r.get("org_name"):
            names[key][str(org)[:60]] = str(r["org_name"])[:160]
        end = _d(r.get("reference_period_end")) or _d(r.get("reference_period_start"))
        if end and (period.get(key) is None or end > period[key]):
            period[key] = end
    out = []
    for (a1, a2, code), sectors in by.items():
        orgs = set().union(*sectors.values())
        out.append({"admin1_name": a1, "admin2_name": a2 or None, "admin2_code": code or None, "orgs": len(orgs),
                    "sectors": {s: sorted(o) for s, o in sorted(sectors.items())}, "period_end": period.get((a1, a2, code)),
                    "names": names.get((a1, a2, code), {})})
    return out


def people_in_need(rows: list[dict[str, Any]], population: Optional[dict[str, int]] = None) -> list[dict[str, Any]]:
    """Latest people-in-need figure per district and sector (whole population rows only, not by age or sex)."""
    best: dict[tuple, dict] = {}
    for r in rows:
        if str(r.get("population_status") or "").upper() != "INN" or not r.get("admin1_name"):
            continue
        cat = str(r.get("category") or "").strip().lower()
        if cat not in ("", "total", "all"):
            continue   # breakdowns (women, children, disability) would double count
        sector = str(r.get("sector_name") or r.get("sector_code") or "")
        try:
            pop = int(float(r.get("population") or 0))
        except (TypeError, ValueError):
            continue
        if pop <= 0:
            continue
        end = _d(r.get("reference_period_end")) or date.min
        key = (*_place(r), sector)
        if key not in best or end > best[key]["period_end"]:
            a1, a2, code = _place(r)
            best[key] = {"admin1_name": a1, "admin2_name": a2 or None, "admin2_code": code or None, "sector": sector,
                         "people": pop, "period_end": end, "period_start": _d(r.get("reference_period_start"))}
    out = list(best.values())
    for r in out:
        base = (population or {}).get(r["admin2_code"] or "") or (population or {}).get((r["admin2_name"] or r["admin1_name"]).lower())
        r["share"] = round(r["people"] / base, 4) if base else None
    return out


def baseline_population(rows: list[dict[str, Any]]) -> dict[str, int]:
    """Total population per admin2 code and per lower-case place name (all ages, all sexes)."""
    out: dict[str, int] = {}
    for r in rows:
        if str(r.get("gender") or "all").lower() not in ("all", "") or str(r.get("age_range") or "all").lower() not in ("all", ""):
            continue
        try:
            pop = int(float(r.get("population") or 0))
        except (TypeError, ValueError):
            continue
        if pop <= 0:
            continue
        name = r.get("admin2_name") or r.get("admin1_name")
        if r.get("admin2_code"):
            out[str(r["admin2_code"])] = pop
        if name:
            out[str(name).lower()] = pop
    return out


def rainfall(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Latest 3-month rainfall anomaly per district (final or preliminary data, not forecasts)."""
    best: dict[tuple, dict] = {}
    for r in rows:
        if str(r.get("version") or "").lower() == "forecast" or not r.get("admin1_name"):
            continue
        if r.get("rainfall_anomaly_pct") is None:
            continue
        end = _d(r.get("reference_period_end"))
        if end is None:
            continue
        key = _place(r)
        if key not in best or end > best[key]["period_end"]:
            a1, a2, code = key
            best[key] = {"admin1_name": a1, "admin2_name": a2 or None, "admin2_code": code or None,
                         "anomaly_pct": round(float(r["rainfall_anomaly_pct"]), 1), "rainfall": r.get("rainfall"),
                         "average": r.get("rainfall_long_term_average"), "period_end": end,
                         "period_start": _d(r.get("reference_period_start")), "period": r.get("aggregation_period")}
    return list(best.values())


def refugees(rows: list[dict[str, Any]]) -> Optional[dict[str, Any]]:
    """UNHCR totals for people hosted by Pakistan in the latest year: by group, and the main countries of origin."""
    latest = None
    for r in rows:
        end = _d(r.get("reference_period_end"))
        if end and (latest is None or end > latest):
            latest = end
    if latest is None:
        return None
    groups: dict[str, int] = defaultdict(int)
    origins: dict[str, int] = defaultdict(int)
    for r in rows:
        if _d(r.get("reference_period_end")) != latest:
            continue
        if str(r.get("gender") or "all").lower() not in ("all", "") or str(r.get("age_range") or "all").lower() not in ("all", ""):
            continue
        try:
            pop = int(float(r.get("population") or 0))
        except (TypeError, ValueError):
            continue
        groups[str(r.get("population_group") or "?")] += pop
        origins[str(r.get("origin_location_name") or r.get("origin_location_code") or "?")] += pop
    if not groups:
        return None
    return {"period_end": latest, "groups": dict(groups), "origins": sorted(origins.items(), key=lambda x: -x[1])[:5]}


def displacement(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Displaced people per place from IOM DTM: each operation's latest round, at the most detailed admin level it
    reports, summed per place (rows split by origin or assessment type add up)."""
    latest: dict[str, date] = {}
    for r in rows:
        end = _d(r.get("reference_period_end"))
        op = str(r.get("operation") or "?")
        if end and (op not in latest or end > latest[op]):
            latest[op] = end
    detail: dict[str, int] = {}   # per operation: 2 if its latest round has district rows, else 1
    for r in rows:
        op = str(r.get("operation") or "?")
        if _d(r.get("reference_period_end")) == latest.get(op) and r.get("admin2_name"):
            detail[op] = 2
    places: dict[tuple, dict] = {}
    for r in rows:
        op = str(r.get("operation") or "?")
        end = _d(r.get("reference_period_end"))
        if end is None or end != latest.get(op) or not r.get("admin1_name"):
            continue
        if detail.get(op) == 2 and not r.get("admin2_name"):
            continue   # the province total of an operation that also gives districts would count people twice
        try:
            people = int(float(r.get("population") or 0))
        except (TypeError, ValueError):
            continue
        if people <= 0:
            continue
        key = _place(r) if detail.get(op) == 2 else (str(r["admin1_name"]), "", "")
        a1, a2, code = key
        row = places.setdefault(key, {"admin1_name": a1, "admin2_name": a2 or None, "admin2_code": code or None, "people": 0,
                                      "operations": [], "round": None, "period_end": end,
                                      "period_start": _d(r.get("reference_period_start"))})
        row["people"] += people
        if op not in row["operations"]:
            row["operations"].append(op)
        row["round"] = r.get("reporting_round") or row["round"]
        row["period_end"] = max(row["period_end"], end)
    return list(places.values())


GROUP_NAMES = {"REF": "refugees", "ASY": "asylum-seekers", "ROC": "people in a refugee-like situation", "OIP": "others in need of protection",
               "STA": "stateless people", "IDP": "internally displaced people", "RET": "returned refugees", "OOC": "others of concern"}


def refugee_text(r: dict[str, Any]) -> str:
    total = sum(r["groups"].values())
    parts = [f"{n:,} {GROUP_NAMES.get(g, g)}" for g, n in sorted(r["groups"].items(), key=lambda x: -x[1]) if n > 0]
    origins = ", ".join(f"{name} ({n:,})" for name, n in r["origins"] if n > 0)
    return (f"UNHCR figures for Pakistan (reference period ending {r['period_end']:%d %B %Y}), via HDX HAPI.\n"
            f"Pakistan hosts {total:,} people of concern to UNHCR: {', '.join(parts)}.\n"
            f"Main countries of origin: {origins}.\n"
            "Refugee families commonly need food, rations, blankets and winter items, hygiene kits, clothes and school "
            "supplies. UNHCR publishes these totals for the whole country, not per district.")


# ---------- fetching ----------

def fetch_all(app_id: str, log: Callable[[str], None]) -> dict[str, Any]:
    """Everything above for Pakistan. A part that fails or has no data is left empty and noted in `log`."""
    out: dict[str, Any] = {"presence": [], "pin": [], "rain": [], "refugees": None, "idps": []}

    def part(name: str, fn):
        try:
            return fn()
        except Exception as e:  # one missing dataset must not stop the others
            log(f"{name}: {str(e)[:80]}")
            return None

    out["presence"] = part("3W", lambda: presence(get_all("coordination-context/operational-presence", app_id, root=ROOT))) or []
    pop = part("population", lambda: baseline_population(get_all("geography-infrastructure/baseline-population", app_id, root=ROOT, admin_level=2))) or {}
    out["pin"] = part("people in need", lambda: people_in_need(get_all("affected-people/humanitarian-needs", app_id, root=ROOT), pop)) or []
    since = (date.today() - timedelta(days=150)).isoformat()
    out["rain"] = part("rainfall", lambda: rainfall(get_all("climate/rainfall", app_id, root=ROOT, admin_level=2,
                                                            aggregation_period="3-month", start_date=since))) or []
    out["refugees"] = part("refugees", lambda: refugees(get_all("affected-people/refugees-persons-of-concern", app_id, root=ROOT,
                                                                 pakistan=False, asylum_location_code="PAK")))
    out["idps"] = part("displaced people (IOM DTM)", lambda: displacement(get_all("affected-people/idps", app_id, root=ROOT))) or []
    return out
