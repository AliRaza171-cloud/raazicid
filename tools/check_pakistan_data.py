"""
RAAZICID - Phase 1 data check
================================
Checks how much Pakistan data three sources really return, before we build
the RAG / need-finder on top of them:

  1. ReliefWeb API v2   - reports (NDMA, PDMA, IPC, UN...) and disasters for Pakistan
  2. GDACS API          - disaster alerts (floods, earthquakes, cyclones...) in Pakistan
  3. HDX HAPI v2        - food security (IPC), food prices, poverty rate for PAK

Usage (run on your own laptop, needs internet):

    pip install requests
    python check_pakistan_data.py --reliefweb-appname YOUR_APPROVED_APPNAME --email you@example.com

    # skip a source if you don't have its key yet:
    python check_pakistan_data.py --email you@example.com --skip reliefweb

Output:
    - a summary printed to the terminal
    - pakistan_data_check.md  (same summary, to paste into your FYP notes)
    - pakistan_data_check.json (raw numbers and samples)

Notes:
    - ReliefWeb needs a PRE-APPROVED appname. Request one at https://apidoc.reliefweb.int/
    - HDX HAPI needs an app identifier; this script creates it from --email automatically.
    - GDACS needs no key.
"""

import argparse
import base64
import json
import time
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone

try:
    import requests
except ImportError:
    sys.exit("Please install requests first:  pip install requests")

# ---------------------------------------------------------------------------
# FILL THESE IN, then just press Run in VS Code (no command-line needed)
# ---------------------------------------------------------------------------
MY_EMAIL = ""              # e.g. "yourname@gmail.com"  (needed for HDX HAPI)
RELIEFWEB_APPNAME = ""     # leave empty until ReliefWeb approves your app name
# ---------------------------------------------------------------------------

TIMEOUT = 30
APP_NAME = "RAAZICID-FYP"
NOW = datetime.now(timezone.utc)
ONE_YEAR_AGO = NOW - timedelta(days=365)

results = {"checked_at": NOW.isoformat(), "sources": {}}
summary_lines = []


def say(line=""):
    print(line, flush=True)
    summary_lines.append(line)


def progress(msg):
    """Shown in the terminal only, not saved to the report."""
    print(f"   ... {msg}", flush=True)


def iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%S+00:00")


# ---------------------------------------------------------------------------
# 1. ReliefWeb
# ---------------------------------------------------------------------------
def reliefweb_post(resource, appname, body):
    url = f"https://api.reliefweb.int/v2/{resource}"
    resp = requests.post(url, params={"appname": appname}, json=body, timeout=TIMEOUT)
    if resp.status_code in (401, 403):
        raise RuntimeError(
            f"ReliefWeb refused the request ({resp.status_code}). Your appname is probably "
            "not approved yet. Request one at https://apidoc.reliefweb.int/"
        )
    resp.raise_for_status()
    return resp.json()


def check_reliefweb(appname):
    say("## 1. ReliefWeb (reports + disasters)")
    out = {}

    # Reports about Pakistan created in the last 12 months
    body = {
        "filter": {
            "operator": "AND",
            "conditions": [
                {"field": "primary_country", "value": "Pakistan"},
                {"field": "date.created", "value": {"from": iso(ONE_YEAR_AGO), "to": iso(NOW)}},
            ],
        },
        "fields": {"include": ["title", "date.created", "source.shortname", "source.name", "url_alias", "file.url"]},
        "sort": ["date:desc"],
        "limit": 1000,
    }
    data = reliefweb_post("reports", appname, body)
    reports = data.get("data", [])
    total = data.get("totalCount", len(reports))

    sources = Counter()
    official = 0
    with_files = 0
    for r in reports:
        f = r.get("fields", {})
        names = [s.get("shortname") or s.get("name", "") for s in f.get("source", [])]
        sources.update(names)
        if any(n and ("NDMA" in n or "PDMA" in n or "Govt" in n) for n in names):
            official += 1
        if f.get("file"):
            with_files += 1

    say(f"- Reports about Pakistan in the last 12 months: **{total}**")
    say(f"- From NDMA / PDMA / Government of Pakistan: **{official}** (of the {len(reports)} downloaded)")
    say(f"- With a PDF/file attached: **{with_files}**")
    say("- Top publishers: " + ", ".join(f"{n} ({c})" for n, c in sources.most_common(8)))
    say("- Latest 5:")
    for r in reports[:5]:
        f = r.get("fields", {})
        say(f"  - {f.get('date', {}).get('created', '')[:10]}  {f.get('title', '')[:110]}")

    out["reports_last_12_months"] = total
    out["official_ndma_pdma_govt"] = official
    out["with_files"] = with_files
    out["top_sources"] = sources.most_common(15)

    # Current / alert disasters in Pakistan
    body = {
        "filter": {
            "operator": "AND",
            "conditions": [
                {"field": "primary_country", "value": "Pakistan"},
                {"field": "status", "value": ["current", "alert"], "operator": "OR"},
            ],
        },
        "fields": {"include": ["name", "status", "date.event", "type.name"]},
        "sort": ["date:desc"],
        "limit": 50,
    }
    data = reliefweb_post("disasters", appname, body)
    disasters = data.get("data", [])
    say(f"- Disasters listed as current or alert for Pakistan: **{len(disasters)}**")
    for d in disasters[:10]:
        f = d.get("fields", {})
        types = ", ".join(t.get("name", "") for t in f.get("type", []))
        say(f"  - [{f.get('status')}] {f.get('name')} ({types})")
    out["current_disasters"] = [d.get("fields", {}).get("name") for d in disasters]
    say()
    return out


# ---------------------------------------------------------------------------
# 2. GDACS
# ---------------------------------------------------------------------------
def gdacs_is_pakistan(props):
    if str(props.get("iso3", "")).upper() == "PAK":
        return True
    if "pakistan" in str(props.get("country", "")).lower():
        return True
    for c in props.get("affectedcountries") or []:
        if isinstance(c, dict) and str(c.get("iso3", "")).upper() == "PAK":
            return True
    return False


def check_gdacs():
    say("## 2. GDACS (disaster alerts)")
    url = "https://www.gdacs.org/gdacsapi/api/events/geteventlist/SEARCH"
    all_events, seen, skipped = [], set(), []

    def fetch(params):
        """GDACS can be slow: wait up to 60 s and retry 3 times before giving up."""
        for attempt in range(3):
            try:
                return requests.get(url, params=params, timeout=60)
            except requests.exceptions.RequestException:
                time.sleep(5 * (attempt + 1))
        return None

    # Ask week by week (wildfires and volcanoes left out: they are most of the
    # worldwide volume and rarely matter for Pakistan)
    for w in range(52, 0, -1):
        start = NOW - timedelta(days=7 * w)
        end = NOW - timedelta(days=7 * (w - 1))
        week_count, page, failed = 0, 1, False
        while page <= 20:  # safety stop per week
            params = {
                "eventlist": "EQ;TC;FL;DR",
                "alertlevel": "Green;Orange;Red",
                "fromDate": start.strftime("%Y-%m-%d"),
                "toDate": end.strftime("%Y-%m-%d"),
                "pageSize": 100,
                "pageNumber": page,
            }
            resp = fetch(params)
            if resp is None or resp.status_code >= 500:
                failed = True
                break
            if resp.status_code == 204:
                break
            resp.raise_for_status()
            feats = resp.json().get("features", [])
            for e in feats:
                p = e.get("properties", {})
                key = (p.get("eventtype"), p.get("eventid"))
                if key not in seen:
                    seen.add(key)
                    all_events.append(e)
                    week_count += 1
            if len(feats) < 100:
                break
            page += 1
        if failed:
            skipped.append(f"{start:%d %b}")
            progress(f"GDACS week of {start:%d %b %Y}: no answer, skipped")
        else:
            progress(f"GDACS week of {start:%d %b %Y}: {week_count} events worldwide")

    if skipped:
        say(f"- Weeks skipped (GDACS did not answer): {len(skipped)} ({', '.join(skipped[:8])}{' ...' if len(skipped) > 8 else ''})")

    dates = sorted(str(e.get("properties", {}).get("fromdate", ""))[:10] for e in all_events
                   if e.get("properties", {}).get("fromdate"))
    if dates:
        say(f"- Dates covered: {dates[0]} to {dates[-1]}")

    pak = [e.get("properties", {}) for e in all_events if gdacs_is_pakistan(e.get("properties", {}))]
    by_type = Counter(p.get("eventtype") for p in pak)
    by_level = Counter(p.get("alertlevel") for p in pak)

    say(f"- Events worldwide in the last 12 months (downloaded): {len(all_events)}")
    say(f"- Events in Pakistan: **{len(pak)}**")
    say("- By type (EQ quake, FL flood, TC cyclone, DR drought, WF fire): "
        + (", ".join(f"{t} {c}" for t, c in by_type.items()) or "none"))
    say("- By alert level: " + (", ".join(f"{l} {c}" for l, c in by_level.items()) or "none"))
    for p in pak[:10]:
        say(f"  - {str(p.get('fromdate', ''))[:10]}  {p.get('eventtype')}  {p.get('alertlevel')}  {p.get('name', '')}")
    say()
    return {
        "events_worldwide": len(all_events),
        "events_pakistan": len(pak),
        "by_type": dict(by_type),
        "by_alert_level": dict(by_level),
        "sample": pak[:10],
    }


# ---------------------------------------------------------------------------
# 3. HDX HAPI
# ---------------------------------------------------------------------------
def hapi_identifier(email):
    try:
        resp = requests.get(
            "https://hapi.humdata.org/api/v2/encode_app_identifier",
            params={"application": APP_NAME, "email": email},
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        return resp.json()["encoded_app_identifier"]
    except Exception:
        # Fallback: the identifier is base64("application:email")
        return base64.b64encode(f"{APP_NAME}:{email}".encode()).decode()


def hapi_get(path, app_id, **params):
    rows, offset, limit = [], 0, 1000
    while True:
        resp = requests.get(
            f"https://hapi.humdata.org/api/v2/{path}",
            params={"app_identifier": app_id, "location_code": "PAK", "output_format": "json",
                    "limit": limit, "offset": offset, **params},
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        page = resp.json().get("data", [])
        rows.extend(page)
        if len(page) < limit or offset > 20000:
            return rows
        offset += limit


def describe_rows(rows):
    """Generic description, so it works whatever the exact column names are."""
    if not rows:
        return {"records": 0}
    keys = list(rows[0].keys())
    admin2 = {r.get("admin2_name") for r in rows if r.get("admin2_name")}
    admin1 = {r.get("admin1_name") for r in rows if r.get("admin1_name")}
    date_keys = [k for k in keys if "reference_period" in k or k.endswith("_date")]
    latest = max((str(r.get(k)) for r in rows for k in date_keys if r.get(k)), default="unknown")
    # Districts in the most recent period only (older analyses can cover other districts)
    period_key = "reference_period_end" if "reference_period_end" in keys else (date_keys[0] if date_keys else None)
    # Province/national totals have no district name, so look at district rows when there are any
    district_rows = [r for r in rows if r.get("admin2_name")] or rows
    latest_rows = district_rows
    if period_key:
        newest = max((str(r.get(period_key)) for r in district_rows if r.get(period_key)), default=None)
        latest_rows = [r for r in district_rows if str(r.get(period_key)) == newest]
    phase_key = next((k for k in keys if "phase" in k and "population" not in k and "fraction" not in k), None)
    phase_counts = {}
    if phase_key:
        for r in latest_rows:
            phase_counts[str(r.get(phase_key))] = phase_counts.get(str(r.get(phase_key)), 0) + 1
    latest_admin2 = {r.get("admin2_name") for r in latest_rows if r.get("admin2_name")}
    latest_admin1 = {r.get("admin1_name") for r in latest_rows if r.get("admin1_name")}
    return {
        "records": len(rows),
        "provinces": sorted(admin1),
        "districts_count": len(admin2),
        "latest_period_districts": sorted(latest_admin2),
        "latest_period_provinces": sorted(latest_admin1),
        "latest_period_end": (str(latest_rows[0].get(period_key))[:10] if period_key and latest_rows else "unknown"),
        "phase_column": phase_key,
        "phase_counts_latest": phase_counts,
        "latest_date": latest[:10],
        "columns": keys,
        "sample": rows[0],
    }


def check_hapi(email):
    say("## 3. HDX HAPI (food security, food prices, poverty)")
    app_id = hapi_identifier(email)
    out = {}
    endpoints = {
        "Food security (IPC)": "food-security-nutrition-poverty/food-security",
        "Food prices": "food-security-nutrition-poverty/food-prices-market-monitor",
        "Poverty rate": "food-security-nutrition-poverty/poverty-rate",
    }
    for label, path in endpoints.items():
        progress(f"downloading {label}")
        try:
            info = describe_rows(hapi_get(path, app_id))
        except Exception as exc:  # keep going if one endpoint fails
            info = {"error": str(exc)}
        out[label] = info
        if "error" in info:
            say(f"- {label}: ERROR {info['error']}")
        elif info["records"] == 0:
            say(f"- {label}: **no Pakistan data**")
        else:
            say(f"- {label}: **{info['records']} records**, provinces: {len(info['provinces'])}, "
                f"districts (all years): {info['districts_count']}, latest date: {info['latest_date']}")
            latest_d = info["latest_period_districts"]
            say(f"  - Latest period (ending {info['latest_period_end']}): {len(latest_d)} districts in "
                f"{', '.join(info['latest_period_provinces']) or 'n/a'}")
            if latest_d:
                say(f"  - Districts: {', '.join(latest_d[:50])}{' ...' if len(latest_d) > 50 else ''}")
            if info.get("phase_counts_latest"):
                say(f"  - Rows by {info['phase_column']} (latest period): "
                    + ", ".join(f"{k}: {v}" for k, v in sorted(info['phase_counts_latest'].items())))
            say(f"  - Columns: {', '.join(info['columns'])}")
    say()
    return out


# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description="RAAZICID: check Pakistan data sources")
    ap.add_argument("--reliefweb-appname", help="Your pre-approved ReliefWeb appname")
    ap.add_argument("--email", help="Your email, used for the HDX HAPI app identifier")
    ap.add_argument("--skip", nargs="*", default=[], choices=["reliefweb", "gdacs", "hapi"])
    args = ap.parse_args()
    args.email = args.email or MY_EMAIL.strip() or None
    args.reliefweb_appname = args.reliefweb_appname or RELIEFWEB_APPNAME.strip() or None
    if not args.email and sys.stdin.isatty():
        typed = input("Your email for HDX HAPI (press Enter to skip HDX): ").strip()
        args.email = typed or None

    say(f"# RAAZICID data check · Pakistan · {NOW:%Y-%m-%d %H:%M} UTC")
    say("Period checked: last 12 months\n")

    checks = [
        ("reliefweb", lambda: check_reliefweb(args.reliefweb_appname), args.reliefweb_appname,
         "add --reliefweb-appname (request one at https://apidoc.reliefweb.int/)"),
        ("gdacs", check_gdacs, True, ""),
        ("hapi", lambda: check_hapi(args.email), args.email, "add --email"),
    ]
    for name, fn, ready, hint in checks:
        if name in args.skip:
            continue
        if not ready:
            say(f"## {name}: skipped, {hint}\n")
            continue
        try:
            results["sources"][name] = fn()
        except Exception as exc:
            say(f"**{name} failed:** {exc}\n")
            results["sources"][name] = {"error": str(exc)}

    with open("pakistan_data_check.md", "w", encoding="utf-8") as f:
        f.write("\n".join(summary_lines) + "\n")
    with open("pakistan_data_check.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, default=str)
    print("\nSaved pakistan_data_check.md and pakistan_data_check.json")


if __name__ == "__main__":
    main()
