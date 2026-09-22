"""Download and import the UTA static GTFS feed."""

import csv
import io
import logging
import sqlite3
import zipfile
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
        for table in ("routes", "stops", "trips", "stop_times", "service_dates", "shapes", "stop_routes"):
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
            "INSERT INTO stops VALUES (?,?,?,?,?,?,?,?)",
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

        conn.execute(
            "INSERT INTO stop_routes "
            "SELECT st.stop_id, t.route_id, r.route_short_name, t.direction_id, "
            "       max(t.trip_headsign), COUNT(*) "
            "FROM stop_times st JOIN trips t USING (trip_id) JOIN routes r USING (route_id) "
            "GROUP BY st.stop_id, t.route_id, t.direction_id"
        )

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


def refresh(conn: sqlite3.Connection, force: bool = False) -> bool:
    return import_zip(conn, download(), force=force)
