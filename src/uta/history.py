"""Writes realtime history in the compact v3 layout (schema in db.py).

Used by the collector for every write and by the v2 -> v3 migration, so migrated
history goes through the same encoding as new history.
"""

import logging
import sqlite3
import time
from dataclasses import astuple, dataclass
from datetime import date

from . import db, gps
from .timeutil import service_day_origin

log = logging.getLogger(__name__)

# trip_dim columns, in order; a trip "version" is a tuple of these.
TRIP_COLS = ("feed_version", "trip_id", "route_id", "route_short_name", "direction_id",
             "trip_headsign", "block_id", "shape_id", "service_id")
KEY_TABLES = {
    "stop": ("stop_keys", ("stop_id",)),
    "route": ("route_keys", ("route_id",)),
    "vehicle": ("vehicle_keys", ("vehicle_id",)),
    "gps_trip": ("gps_trips", ("trip_id", "route_id")),
    "trip": ("trip_dim", TRIP_COLS),
}


@dataclass
class Visit:
    """One trip-stop visit as the collector tracks it (epoch seconds throughout)."""
    service_date: str
    trip: tuple                 # TRIP_COLS values
    seq: int
    stop_id: str | None
    vehicle_id: str | None
    sched_arrival: int | None
    sched_departure: int | None
    obs_arrival: int | None
    obs_departure: int | None
    first_seen: int
    last_seen: int
    n_updates: int = 1


@dataclass
class TripRun:
    """A stretch of a trip run by one vehicle, per TripUpdates."""
    service_date: str
    trip: tuple
    vehicle_id: str | None
    t_first: int
    t_last: int
    seq_first: int
    seq_last: int


def to_json(obj) -> list:
    return list(astuple(obj))


def visit_from_json(row: list) -> Visit:
    return Visit(row[0], tuple(row[1]), *row[2:])


def run_from_json(row: list) -> TripRun:
    return TripRun(row[0], tuple(row[1]), *row[2:])


def day_number(service_date: str) -> int:
    return (date.fromisoformat(service_date) - db.EPOCH).days


def is_observed(lead_s: int | None) -> bool:
    return lead_s is not None and db.OBS_LEAD_MIN <= lead_s <= db.OBS_LEAD_MAX


UPSERT_VISIT = """
INSERT INTO visits VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
ON CONFLICT (route, stop, day, trip, seq) DO UPDATE SET
    vehicle     = COALESCE(excluded.vehicle, vehicle),
    span        = (excluded.arr - excluded.lead_s)
                  - MIN(arr - lead_s - span, excluded.arr - excluded.lead_s - excluded.span),
    arr         = excluded.arr,
    dwell       = excluded.dwell,
    delay       = excluded.delay,
    lead_s      = excluded.lead_s,
    n_updates   = n_updates + excluded.n_updates
WHERE excluded.arr - excluded.lead_s > arr - lead_s
"""


class History:
    """Key caches plus the writers. Only one writer (the collector) at a time."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self.keys = {}
        for kind, (table, cols) in KEY_TABLES.items():
            self.keys[kind] = {tuple(r)[1:]: r[0] for r in conn.execute(
                f"SELECT key, {', '.join(cols)} FROM {table}")}
        self.origins = dict(conn.execute("SELECT day, origin FROM days"))
        self.dirty_days: set[int] = set()

    def key(self, kind: str, *values) -> int:
        k = self.keys[kind].get(values)
        if k is None:
            table, cols = KEY_TABLES[kind]
            k = self.conn.execute(
                f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})",
                values).lastrowid
            self.keys[kind][values] = k
        return k

    def day(self, service_date: str) -> int:
        day = day_number(service_date)
        if day not in self.origins:
            origin = service_day_origin(date.fromisoformat(service_date))
            self.conn.execute("INSERT OR IGNORE INTO days VALUES (?,?,?)", (day, service_date, origin))
            self.origins[day] = origin
        return day

    def encode_visit(self, v: Visit) -> tuple:
        day = self.day(v.service_date)
        origin = self.origins[day]
        oa, od, sa, sd = v.obs_arrival, v.obs_departure, v.sched_arrival, v.sched_departure
        return (
            self.key("route", v.trip[2]), self.key("stop", v.stop_id), day,
            self.key("trip", *v.trip), v.seq,
            self.key("vehicle", v.vehicle_id) if v.vehicle_id is not None else None,
            oa - origin if oa is not None else None,
            od - oa if od is not None and oa is not None else None,
            oa - sa if oa is not None and sa is not None else None,
            sd - sa if sd is not None and sa is not None else None,
            oa - v.last_seen if oa is not None else None,
            v.last_seen - v.first_seen,
            v.n_updates,
        )

    def stage_visits(self, visits) -> None:
        """Append final visits to visits_new (cheap); merge_staged moves them into visits."""
        self.conn.executemany("INSERT INTO visits_new VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                              [self.encode_visit(v) for v in visits])

    def merge_staged(self) -> int:
        """Move visits_new into visits in key order, then refresh day_stats."""
        rows = self.conn.execute(
            "SELECT * FROM visits_new ORDER BY route, stop, day, trip, seq, rowid").fetchall()
        self.upsert_rows(rows)
        self.conn.execute("DELETE FROM visits_new")
        self.refresh_day_stats()
        return len(rows)

    def write_visits(self, visits) -> int:
        """Upsert final visits straight into visits (the migration's path)."""
        return self.upsert_rows([self.encode_visit(v) for v in visits])

    def upsert_rows(self, rows) -> int:
        """Upsert encoded visits. A visit written before (it left the feed and came back)
        keeps the newer prediction, the earliest first sighting and the summed update count."""
        counts: dict[tuple, list] = {}
        for row in rows:
            row = tuple(row)
            old = self.conn.execute(
                "SELECT arr - lead_s, lead_s FROM visits WHERE route=? AND stop=? AND day=? AND trip=? AND seq=?",
                row[:5]).fetchone()
            c = counts.setdefault((row[2], row[3]), [0, 0])
            if old is None:
                c[0] += 1
                c[1] += is_observed(row[10])
            elif row[6] is not None and row[6] - row[10] > old[0]:
                c[1] += is_observed(row[10]) - is_observed(old[1])
            self.conn.execute(UPSERT_VISIT, row)
        self.conn.executemany(
            "INSERT INTO trip_days VALUES (?,?,?,?) ON CONFLICT (day, trip) DO UPDATE SET "
            "n_visits = n_visits + excluded.n_visits, n_observed = n_observed + excluded.n_observed",
            [(day, trip, nv, no) for (day, trip), (nv, no) in counts.items()])
        self.dirty_days.update(day for day, _ in counts)
        return len(rows)

    def write_trip_runs(self, runs) -> None:
        self.conn.executemany(
            "INSERT OR REPLACE INTO trip_vehicle VALUES (?,?,?,?,?,?,?)",
            [(self.day(r.service_date), self.key("trip", *r.trip), r.t_first, r.t_last,
              self.key("vehicle", r.vehicle_id) if r.vehicle_id is not None else None,
              r.seq_first, r.seq_last) for r in runs])

    def write_gps(self, rows) -> None:
        """rows: (vehicle_id, ts, trip_id, route_id, lat, lon, bearing, speed, tu_trip_id, tu_route_id)."""
        self.conn.executemany(
            "INSERT OR IGNORE INTO gps_recent VALUES (?,?,?,?,?,?,?,?)",
            [(ts, self.key("vehicle", vid),
              self.key("gps_trip", trip_id, route_id) if trip_id is not None else None,
              self.key("gps_trip", tu_trip, tu_route) if tu_trip is not None else None,
              lat, lon, bearing, speed)
             for vid, ts, trip_id, route_id, lat, lon, bearing, speed, tu_trip, tu_route in rows])

    def refresh_day_stats(self, days=None) -> None:
        days = sorted(self.dirty_days if days is None else days)
        for i in range(0, len(days), 500):
            chunk = days[i:i + 500]
            self.conn.execute(
                f"INSERT OR REPLACE INTO day_stats SELECT day, SUM(n_visits), SUM(n_observed), "
                f"SUM(n_observed > 0) FROM trip_days WHERE day IN ({','.join('?' * len(chunk))}) GROUP BY day",
                chunk)
        self.dirty_days.clear()


def seal_gps(conn: sqlite3.Connection, now: int | None = None) -> int:
    """Seal every GPS day before the current one into blocks."""
    return gps.seal(conn, gps.day_start(gps.gps_day(now or int(time.time()))))


# ---------------------------------------------------------------- v2 -> v3

class MigrationError(RuntimeError):
    """The converted history doesn't reproduce the original rows; nothing was changed."""


def migrate_v2(conn: sqlite3.Connection) -> None:
    """Convert stop_events and vehicle_positions tables to the v3 layout, verify the
    conversion reproduces every original row, then drop the originals.
    The caller runs this inside a transaction and rolls back on any error."""
    conn.execute("DROP VIEW IF EXISTS observed_stop_events")
    conn.execute("ALTER TABLE stop_events RENAME TO stop_events_v2")
    h = History(conn)
    feed_version = db.get_meta(conn, "gtfs_feed_version")
    static = {r[0]: tuple(r)[1:] for r in conn.execute(
        "SELECT trip_id, route_id, block_id, shape_id, service_id FROM trips")}

    def trip_of(r) -> tuple:
        s = static.get(r["trip_id"])
        extra = s[1:] if s is not None and s[0] == r["route_id"] else (None, None, None)
        return (feed_version, r["trip_id"], r["route_id"], r["route_short_name"], r["direction_id"],
                r["trip_headsign"], *extra)

    n = 0
    cur = conn.execute("SELECT * FROM stop_events_v2")
    while batch := cur.fetchmany(20000):
        h.write_visits(Visit(r["service_date"], trip_of(r), r["stop_sequence"], r["stop_id"], r["vehicle_id"],
                             r["sched_arrival"], r["sched_departure"], r["obs_arrival"], r["obs_departure"],
                             r["first_seen"], r["last_seen"], r["n_updates"]) for r in batch)
        n += len(batch)
    # Pre-v3 trip vehicles are rebuilt from visits: coarser than the collector's own record.
    h.write_trip_runs(
        TripRun(r["service_date"], trip_of(r), r["vehicle_id"], r["t_first"], r["t_last"], r["seq_first"], r["seq_last"])
        for r in conn.execute(
            "SELECT service_date, trip_id, route_id, route_short_name, direction_id, trip_headsign, vehicle_id, "
            "MIN(first_seen) AS t_first, MAX(last_seen) AS t_last, "
            "MIN(stop_sequence) AS seq_first, MAX(stop_sequence) AS seq_last FROM stop_events_v2 "
            "WHERE vehicle_id IS NOT NULL GROUP BY 1, 2, 3, 4, 5, 6, 7"))
    h.refresh_day_stats(list(h.origins))

    conn.execute(f"CREATE TEMP VIEW stop_events_v3 AS {db.STOP_EVENTS_VIEW.replace('visits_all', 'visits')}")
    for a, b in (("stop_events_v2", "stop_events_v3"), ("stop_events_v3", "stop_events_v2")):
        diff = conn.execute(f"SELECT COUNT(*) FROM (SELECT * FROM {a} EXCEPT SELECT * FROM {b})").fetchone()[0]
        if diff:
            raise MigrationError(f"{diff} rows of {a} are not reproduced by {b}")
    if conn.execute("SELECT COUNT(*) FROM visits").fetchone()[0] != n:
        raise MigrationError("visit count differs from stop_events")
    conn.execute("DROP VIEW stop_events_v3")
    log.info("migrated %d stop visits", n)

    if conn.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'vehicle_positions'").fetchone():
        cur = conn.execute("SELECT * FROM vehicle_positions")
        m = 0
        while batch := cur.fetchmany(50000):
            h.write_gps((*tuple(r), None, None) for r in batch)
            m += len(batch)
        seal_gps(conn)
        old = set(map(tuple, conn.execute("SELECT * FROM vehicle_positions")))
        new = {p[:8] for p in gps.read(conn)}
        if old != new:
            raise MigrationError(f"GPS history differs after conversion ({len(old ^ new)} pings)")
        conn.execute("DROP TABLE vehicle_positions")
        log.info("migrated %d GPS pings", m)
    conn.execute("DROP TABLE stop_events_v2")
