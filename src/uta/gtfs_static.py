"""Download and import the UTA static GTFS feed."""

import csv
import io
import logging
import math
import re
import sqlite3
import zipfile
from collections import Counter, defaultdict
from datetime import date, datetime

import requests

from . import db
from .timeutil import daterange, parse_gtfs_time

log = logging.getLogger(__name__)

STATIC_URL = "https://apps.rideuta.com/tms/gtfs/Static"


def download(url: str = STATIC_URL) -> bytes:
    resp = requests.get(url, timeout=120)
    resp.raise_for_status()
    return resp.content


def _rows(zf: zipfile.ZipFile, name: str):
    if name not in zf.namelist():
        return
    with zf.open(name) as fh:
        reader = csv.DictReader(io.TextIOWrapper(fh, encoding="utf-8-sig"))
        for row in reader:
            yield {k.strip(): (v.strip() if v is not None else "") for k, v in row.items()}


def _int(v: str) -> int | None:
    return int(v) if v not in ("", None) else None


def _float(v: str) -> float | None:
    return float(v) if v not in ("", None) else None


def _ymd(s: str) -> date:
    return datetime.strptime(s, "%Y%m%d").date()


def feed_version(zf: zipfile.ZipFile) -> str:
    for row in _rows(zf, "feed_info.txt"):
        return row.get("feed_version") or ""
    return ""


def import_zip(conn: sqlite3.Connection, data: bytes, force: bool = False) -> bool:
    """Import a GTFS zip. Returns False if this feed version is already loaded."""
    zf = zipfile.ZipFile(io.BytesIO(data))
    version = feed_version(zf)
    if not force and version and db.get_meta(conn, "gtfs_feed_version") == version:
        log.info("GTFS %s already imported", version)
        return False

    log.info("importing GTFS %s", version)
    with conn:
        for table in ("routes", "stops", "trips", "stop_times", "service_dates", "shapes"):
            conn.execute(f"DELETE FROM {table}")

        conn.executemany(
            "INSERT INTO routes VALUES (?,?,?,?,?,?)",
            (
                (r["route_id"], r.get("route_short_name"), r.get("route_long_name"),
                 _int(r.get("route_type", "")), r.get("route_color"), r.get("route_text_color"))
                for r in _rows(zf, "routes.txt")
            ),
        )
        conn.executemany(
            "INSERT INTO stops (stop_id, stop_code, stop_name, stop_desc, stop_lat, stop_lon, "
            "location_type, parent_station) VALUES (?,?,?,?,?,?,?,?)",
            (
                (r["stop_id"], r.get("stop_code"), r.get("stop_name"), r.get("stop_desc"),
                 _float(r.get("stop_lat", "")), _float(r.get("stop_lon", "")),
                 _int(r.get("location_type", "")), r.get("parent_station") or None)
                for r in _rows(zf, "stops.txt")
            ),
        )
        conn.executemany(
            "INSERT INTO trips VALUES (?,?,?,?,?,?,?)",
            (
                (r["trip_id"], r["route_id"], r["service_id"], r.get("trip_headsign"),
                 _int(r.get("direction_id", "")), r.get("block_id"), r.get("shape_id"))
                for r in _rows(zf, "trips.txt")
            ),
        )
        conn.executemany(
            "INSERT INTO stop_times VALUES (?,?,?,?,?,?)",
            (
                (r["trip_id"], int(r["stop_sequence"]), r["stop_id"],
                 parse_gtfs_time(r.get("arrival_time", "")),
                 parse_gtfs_time(r.get("departure_time", "")),
                 _int(r.get("timepoint", "")))
                for r in _rows(zf, "stop_times.txt")
            ),
        )
        conn.executemany(
            "INSERT OR IGNORE INTO shapes VALUES (?,?,?,?)",
            (
                (r["shape_id"], int(r["shape_pt_sequence"]),
                 float(r["shape_pt_lat"]), float(r["shape_pt_lon"]))
                for r in _rows(zf, "shapes.txt")
            ),
        )
        conn.executemany("INSERT OR IGNORE INTO service_dates VALUES (?,?,?)", _service_dates(zf))
        derive(conn)
        db.set_meta(conn, "gtfs_feed_version", version)
        db.set_meta(conn, "gtfs_imported_at", datetime.now().isoformat(timespec="seconds"))
    conn.execute("ANALYZE")
    return True


def _service_dates(zf: zipfile.ZipFile):
    days = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
    active: dict[tuple[str, date], bool] = {}
    for r in _rows(zf, "calendar.txt"):
        for d in daterange(_ymd(r["start_date"]), _ymd(r["end_date"])):
            if r[days[d.weekday()]] == "1":
                active[(r["service_id"], d)] = True
    for r in _rows(zf, "calendar_dates.txt"):
        active[(r["service_id"], _ymd(r["date"]))] = r["exception_type"] == "1"
    for (sid, d), on in active.items():
        if on:
            yield sid, d.isoformat(), d.weekday()


# ---------------------------------------------------------------- derived tables

# Stops with the same normalized name this close together are one station
# (bays of a hub, both sides of a street).
STATION_RADIUS_M = 250
_ABBR = {"west": "w", "east": "e", "north": "n", "south": "s", "street": "st",
         "avenue": "ave", "boulevard": "blvd", "road": "rd", "drive": "dr"}


def normalize_stop_name(name: str) -> str:
    """'1940. W North Temple Station (EB)' -> '1940 w north temple station'."""
    name = re.sub(r"\([^)]*(\)|$)", " ", name or "")   # (NB), (Bay E), (Ogden), truncated '(Riverda'
    toks = re.split(r"[^a-z0-9]+", name.lower())
    return " ".join(_ABBR.get(t, t) for t in toks if t)


def display_name(names: list[str]) -> str:
    cleaned = [re.sub(r"\s*\([^)]*(\)|$)", "", n or "").strip() for n in names]
    return Counter(cleaned).most_common(1)[0][0]


def _haversine_m(lat1, lon1, lat2, lon2) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * 6_371_000 * math.asin(math.sqrt(a))


def derive(conn: sqlite3.Connection) -> None:
    """Rebuild tables derived from the static feed: stations, stop_routes, route_stops."""
    _derive_stations(conn)
    conn.execute("DELETE FROM stop_routes")
    conn.execute(
        "INSERT INTO stop_routes "
        "SELECT st.stop_id, t.route_id, r.route_short_name, t.direction_id, "
        "       max(t.trip_headsign), COUNT(*) "
        "FROM stop_times st JOIN trips t USING (trip_id) JOIN routes r USING (route_id) "
        "GROUP BY st.stop_id, t.route_id, t.direction_id"
    )
    _derive_route_stops(conn)


def _derive_stations(conn: sqlite3.Connection) -> None:
    stops = conn.execute(
        "SELECT stop_id, stop_name, stop_lat, stop_lon FROM stops WHERE stop_lat IS NOT NULL"
    ).fetchall()
    parent = list(range(len(stops)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    norm = [normalize_stop_name(s[1]) for s in stops]
    # ~450 m grid cells; comparing neighbouring cells covers the radius
    cell_lat, cell_lon = 0.004, 0.005
    cells = defaultdict(list)
    for i, s in enumerate(stops):
        cells[(round(s[2] / cell_lat), round(s[3] / cell_lon))].append(i)
    for (cy, cx), members in cells.items():
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                for j in cells.get((cy + dy, cx + dx), ()):
                    for i in members:
                        if i < j and norm[i] == norm[j] and _haversine_m(
                                stops[i][2], stops[i][3], stops[j][2], stops[j][3]) <= STATION_RADIUS_M:
                            parent[find(i)] = find(j)

    groups = defaultdict(list)
    for i in range(len(stops)):
        groups[find(i)].append(i)
    stations, assign = [], []
    for members in groups.values():
        ids = sorted(stops[i][0] for i in members)
        sid = ids[0]
        stations.append((
            sid, display_name([stops[i][1] for i in members]),
            sum(stops[i][2] for i in members) / len(members),
            sum(stops[i][3] for i in members) / len(members),
            len(members),
        ))
        assign += [(sid, stop_id) for stop_id in ids]
    conn.execute("DELETE FROM stations")
    conn.executemany("INSERT INTO stations VALUES (?,?,?,?,?)", stations)
    conn.executemany("UPDATE stops SET station_id = ? WHERE stop_id = ?", assign)


def _derive_route_stops(conn: sqlite3.Connection) -> None:
    """Order each route direction's stations by merging its trip patterns.

    Patterns are merged most-frequent first; a station missing from the list so
    far is inserted right after the nearest station that precedes it in its own
    pattern. A station visited twice (loops) keeps its first position.
    """
    patterns: dict = defaultdict(Counter)   # (route, dir) -> Counter(pattern tuple)
    stop_ids: dict = defaultdict(set)       # (route, dir, station) -> stop_ids
    cur_key, cur_trip, seq = None, None, []
    rows = conn.execute(
        "SELECT t.route_id, COALESCE(t.direction_id, 0), st.trip_id, s.station_id, st.stop_id "
        "FROM stop_times st JOIN trips t USING (trip_id) JOIN stops s USING (stop_id) "
        "ORDER BY st.trip_id, st.stop_sequence"
    )
    for route_id, direction, trip_id, station_id, stop_id in rows:
        if trip_id != cur_trip:
            if seq:
                patterns[cur_key][tuple(seq)] += 1
            cur_key, cur_trip, seq = (route_id, direction), trip_id, []
        if not seq or seq[-1] != station_id:
            seq.append(station_id)
        stop_ids[(route_id, direction, station_id)].add(stop_id)
    if seq:
        patterns[cur_key][tuple(seq)] += 1

    out = []
    for (route_id, direction), counter in patterns.items():
        order: list = []
        n_trips: Counter = Counter()
        for pattern, n in counter.most_common():
            for station in set(pattern):
                n_trips[station] += n
            for k, station in enumerate(pattern):
                if station in order:
                    continue
                prev = next((p for p in reversed(pattern[:k]) if p in order), None)
                order.insert(order.index(prev) + 1 if prev is not None else 0, station)
        for i, station in enumerate(order):
            out.append((route_id, direction, i, station,
                        " ".join(sorted(stop_ids[(route_id, direction, station)])), n_trips[station]))
    conn.execute("DELETE FROM route_stops")
    conn.executemany("INSERT INTO route_stops VALUES (?,?,?,?,?,?)", out)


def refresh(conn: sqlite3.Connection, force: bool = False) -> bool:
    return import_zip(conn, download(), force=force)
