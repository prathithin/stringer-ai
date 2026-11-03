"""Live GT TransLoc client, reused from stinger-delay Analysis scrapers.

Primary: https://gatech.transloc.com/Services/JSONPRelay.svc
Fallback: saved snapshot CSV in data/transloc_snapshot.csv when no vehicles
are reporting (nights, outages). The API then sets using_recent_data=True.
"""

from __future__ import annotations

import csv
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx

BASE_URL = "https://gatech.transloc.com/Services/JSONPRelay.svc"
EP_VEHICLES = "GetMapVehiclePoints"
EP_ARRIVALS = "GetRouteStopArrivals"
EP_ROUTES = "GetRoutes"
# GetStops is the live stop list (Description, RouteStopID). GetMapStopPoints
# from the original scraper often drops the connection; GetStops is the same feed
# used on the public map and includes the fields we need.
EP_STOPS = "GetStops"

# Public map key from the original green_bus_scraper.py
DEFAULT_API_KEY = "8882812681"

# CONFIGURED_DEFAULT — not a trained model. Override with ETA_UNCERTAINTY_MINUTES.
DEFAULT_UNCERTAINTY_MINUTES = 4

SNAPSHOT_PATH = Path(__file__).parent / "data" / "transloc_snapshot.csv"

ROUTE_NAMES = {
    17: "Green",
    18: "Emory",
    20: "Red",
    21: "Blue",
    22: "NARA / Science Square",
    23: "Weekend Atlantic Station",
    24: "Weekend Midtown",
    26: "Northside / Atlantic Station",
    28: "Clough",
    29: "Gold",
    30: "Night Gold/Clough",
}

_STOPS_CACHE: list[dict] | None = None
_STOPS_CACHE_AT: datetime | None = None


def _api_key() -> str:
    return os.getenv("TRANSLOC_API_KEY", DEFAULT_API_KEY)


def _uncertainty_minutes() -> int:
    try:
        return int(os.getenv("ETA_UNCERTAINTY_MINUTES", DEFAULT_UNCERTAINTY_MINUTES))
    except ValueError:
        return DEFAULT_UNCERTAINTY_MINUTES


def _get(endpoint: str, timeout: float = 12.0) -> Any:
    url = f"{BASE_URL}/{endpoint}"
    with httpx.Client(timeout=timeout, headers={"User-Agent": "StingerAssistant/1.0"}) as client:
        resp = client.get(url, params={"apiKey": _api_key(), "isPublicMap": "true"})
        resp.raise_for_status()
        return resp.json()


def load_stops(force: bool = False) -> list[dict]:
    global _STOPS_CACHE, _STOPS_CACHE_AT
    now = datetime.now(timezone.utc)
    if (
        not force
        and _STOPS_CACHE is not None
        and _STOPS_CACHE_AT is not None
        and (now - _STOPS_CACHE_AT) < timedelta(minutes=30)
    ):
        return _STOPS_CACHE
    data = _get(EP_STOPS)
    _STOPS_CACHE = data if isinstance(data, list) else []
    _STOPS_CACHE_AT = now
    return _STOPS_CACHE


def _normalize(name: str) -> str:
    return " ".join((name or "").lower().replace("\xa0", " ").split())


def find_stops(stop_name: str) -> list[dict]:
    needle = _normalize(stop_name)
    matches = []
    for s in load_stops():
        desc = s.get("Description") or ""
        if needle and needle in _normalize(desc):
            matches.append(s)
    if matches:
        return matches
    # token overlap fallback
    tokens = set(needle.split())
    for s in load_stops():
        desc = _normalize(s.get("Description") or "")
        if tokens and tokens <= set(desc.split()):
            matches.append(s)
    return matches


def _parse_snapshot_rows() -> list[dict]:
    if not SNAPSHOT_PATH.exists():
        return []
    rows = []
    with SNAPSHOT_PATH.open(newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)
    return rows


def _latest_snapshot_slice() -> tuple[str, list[dict]]:
    rows = _parse_snapshot_rows()
    if not rows:
        return "", []
    latest = max(r.get("snapshot_time") or "" for r in rows)
    return latest, [r for r in rows if r.get("snapshot_time") == latest]


def live_feed() -> dict:
    """Return arrivals keyed by RouteStopID plus a using_recent_data flag."""
    using_recent = False
    vehicles: list[dict] = []
    arrivals: list[dict] = []
    try:
        vehicles = _get(EP_VEHICLES) or []
        arrivals = _get(EP_ARRIVALS) or []
        if not vehicles:
            using_recent = True
    except Exception:
        using_recent = True
        vehicles = []
        arrivals = []

    if using_recent:
        snapshot_time, snap_rows = _latest_snapshot_slice()
        arrivals = _arrivals_from_snapshot(snap_rows, snapshot_time)
        return {
            "using_recent_data": True,
            "snapshot_time": snapshot_time,
            "vehicles": [],
            "arrivals": arrivals,
        }

    return {
        "using_recent_data": False,
        "snapshot_time": None,
        "vehicles": vehicles,
        "arrivals": arrivals,
    }


def _arrivals_from_snapshot(rows: list[dict], snapshot_time: str) -> list[dict]:
    """Rebuild GetRouteStopArrivals-like records from a historical CSV slice."""
    grouped: dict[tuple[str, str], list[dict]] = {}
    try:
        snap_dt = datetime.fromisoformat(snapshot_time)
    except ValueError:
        snap_dt = datetime.now()

    for row in rows:
        rsid = str(row.get("route_stop_id") or "")
        rid = str(row.get("route_id") or "")
        eta = row.get("estimated_time_arrival") or ""
        vid = row.get("vehicle_id")
        if not rsid or not eta:
            continue
        try:
            eta_dt = datetime.fromisoformat(eta)
            secs = max(0, int((eta_dt - snap_dt).total_seconds()))
        except ValueError:
            continue
        grouped.setdefault((rid, rsid), []).append(
            {"VehicleID": vid, "SecondsToStop": secs, "OnRoute": True}
        )

    out = []
    for (rid, rsid), estimates in grouped.items():
        try:
            route_id = int(rid)
        except ValueError:
            route_id = 0
        try:
            route_stop_id = int(rsid)
        except ValueError:
            route_stop_id = 0
        out.append(
            {
                "RouteID": route_id,
                "RouteStopID": route_stop_id,
                "VehicleEstimates": estimates,
            }
        )
    return out


def get_arrivals(stop_name: str) -> dict:
    feed = live_feed()
    stops = find_stops(stop_name)
    stop_ids = {int(s.get("RouteStopID")) for s in stops if s.get("RouteStopID") is not None}
    stop_by_id = {int(s["RouteStopID"]): s for s in stops if s.get("RouteStopID") is not None}

    results = []
    for entry in feed["arrivals"]:
        rsid = entry.get("RouteStopID")
        if stop_ids and rsid not in stop_ids:
            continue
        if not stop_ids:
            continue
        stop_meta = stop_by_id.get(rsid) or {}
        route_id = entry.get("RouteID")
        for est in entry.get("VehicleEstimates") or []:
            secs = est.get("SecondsToStop")
            if secs is None:
                continue
            eta_min = round(secs / 60, 1)
            results.append(
                {
                    "stop_name": stop_meta.get("Description") or stop_name,
                    "route_id": route_id,
                    "route_name": ROUTE_NAMES.get(route_id, f"Route {route_id}"),
                    "route_stop_id": rsid,
                    "vehicle_id": est.get("VehicleID"),
                    "eta_minutes": eta_min,
                    "seconds_to_stop": secs,
                }
            )

    results.sort(key=lambda r: r["eta_minutes"])
    return {
        "query": stop_name,
        "matched_stops": [
            {
                "name": s.get("Description"),
                "route_id": s.get("RouteID"),
                "route_name": ROUTE_NAMES.get(s.get("RouteID"), str(s.get("RouteID"))),
                "route_stop_id": s.get("RouteStopID"),
            }
            for s in stops[:12]
        ],
        "arrivals": results[:20],
        "using_recent_data": feed["using_recent_data"],
        "snapshot_time": feed["snapshot_time"],
    }


def get_uncertainty(route: str) -> dict:
    """Return the ETA uncertainty range.

    CONFIGURED_DEFAULT: ±ETA_UNCERTAINTY_MINUTES (default 4). Historical CSVs
    exist but we did not fit a per-route variance model in this timebox.
    """
    minutes = _uncertainty_minutes()
    route_label = (route or "").strip()
    return {
        "route": route_label,
        "plus_minus_minutes": minutes,
        "source": "CONFIGURED_DEFAULT",
        "note": (
            f"Using a configured ±{minutes} minute ETA range, not a trained model. "
            "Historical TransLoc snapshots are available in backend/data/."
        ),
    }
