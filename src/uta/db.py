"""SQLite schema and connection helpers.

Static GTFS tables are replaced wholesale on each import. The realtime-derived
tables (stop_events, vehicle_positions) are append/upsert-only and denormalize
route/stop/schedule info so history stays meaningful after the GTFS changes.
"""

import os
import sqlite3
from pathlib import Path

DEFAULT_DB = os.environ.get("UTA_DB", str(Path.cwd() / "data" / "uta.db"))

# A stop visit counts as observed when, at our last sighting, its predicted
# arrival was between OBS_LEAD_MIN and OBS_LEAD_MAX seconds from that sighting.
# Checked against GPS: inside this window the vehicle is a median ~90 m from the
# stop at the recorded time; outside it the record is a stale or early-dropped
# prediction. Finalized visits outside the window are deleted by the collector.
OBS_LEAD_MIN = -120
OBS_LEAD_MAX = 15


def observed(alias: str = "") -> str:
    """SQL condition selecting observed stop visits, optionally for a table alias."""
    col = f"{alias}.lead_s" if alias else "lead_s"
    return f"{col} BETWEEN {OBS_LEAD_MIN} AND {OBS_LEAD_MAX}"


OBSERVED = observed()
# A visit is final once it has been out of the feed this long.
FINAL_AFTER_S = 600
# Live views only show vehicles that reported within this window.
LIVE_MAX_AGE_S = 180

SCHEMA_VERSION = 2

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);

-- ---------- static GTFS (current feed) ----------
CREATE TABLE IF NOT EXISTS routes (
    route_id         TEXT PRIMARY KEY,
    route_short_name TEXT,
    route_long_name  TEXT,
    route_type       INTEGER,   -- 0 light rail, 2 rail, 3 bus, ...
    route_color      TEXT,
    route_text_color TEXT
);

CREATE TABLE IF NOT EXISTS stops (
    stop_id        TEXT PRIMARY KEY,
    stop_code      TEXT,
    stop_name      TEXT,
    stop_desc      TEXT,
    stop_lat       REAL,
    stop_lon       REAL,
    location_type  INTEGER,
    parent_station TEXT,
    station_id     TEXT         -- derived grouping, see stations
);
CREATE INDEX IF NOT EXISTS stops_code ON stops(stop_code);

-- Stops merged into stations: platforms/bays of one hub, and both sides of a
-- street for the same named stop. Derived at import (gtfs_static.derive).
CREATE TABLE IF NOT EXISTS stations (
    station_id TEXT PRIMARY KEY,
    name       TEXT,
    lat        REAL,
    lon        REAL,
    n_stops    INTEGER
);

-- Ordered stations along each route direction, merged across trip patterns.
CREATE TABLE IF NOT EXISTS route_stops (
    route_id     TEXT,
    direction_id INTEGER,
    seq          INTEGER,
    station_id   TEXT,
    stop_ids     TEXT,          -- space-separated stop_ids this route uses here
    n_trips      INTEGER,       -- trips in this direction that serve the station
    PRIMARY KEY (route_id, direction_id, seq)
) WITHOUT ROWID;

CREATE TABLE IF NOT EXISTS trips (
    trip_id       TEXT PRIMARY KEY,
    route_id      TEXT,
    service_id    TEXT,
    trip_headsign TEXT,
    direction_id  INTEGER,
    block_id      TEXT,
    shape_id      TEXT
);
CREATE INDEX IF NOT EXISTS trips_route ON trips(route_id);

CREATE TABLE IF NOT EXISTS stop_times (
    trip_id       TEXT,
    stop_sequence INTEGER,
    stop_id       TEXT,
    arrival_s     INTEGER,      -- seconds after service-day midnight (may exceed 86400)
    departure_s   INTEGER,
    timepoint     INTEGER,
    PRIMARY KEY (trip_id, stop_sequence)
) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS stop_times_stop ON stop_times(stop_id, trip_id);

-- one row per (service_id, date) the service actually runs, from calendar + calendar_dates
CREATE TABLE IF NOT EXISTS service_dates (
    service_id TEXT,
    date       TEXT,            -- YYYY-MM-DD
    dow        INTEGER,         -- 0=Mon .. 6=Sun
    PRIMARY KEY (service_id, date)
) WITHOUT ROWID;

-- which routes/directions serve each stop (derived at import)
CREATE TABLE IF NOT EXISTS stop_routes (
    stop_id          TEXT,
    route_id         TEXT,
    route_short_name TEXT,
    direction_id     INTEGER,
    trip_headsign    TEXT,
    n_trips          INTEGER
);
CREATE INDEX IF NOT EXISTS stop_routes_stop ON stop_routes(stop_id);

CREATE TABLE IF NOT EXISTS shapes (
    shape_id TEXT,
    seq      INTEGER,
    lat      REAL,
    lon      REAL,
    PRIMARY KEY (shape_id, seq)
) WITHOUT ROWID;

-- ---------- realtime history ----------
-- One row per trip-stop visit. Updated on every poll with the latest prediction;
-- once the bus passes the stop it leaves the feed and the last value is the
-- observed time. lead_s = obs_arrival - last_seen at the final sighting: small
-- (or negative) means the arrival had essentially happened when we last saw it.
CREATE TABLE IF NOT EXISTS stop_events (
    service_date    TEXT,       -- YYYY-MM-DD (GTFS service day, local)
    trip_id         TEXT,
    stop_sequence   INTEGER,
    stop_id         TEXT,
    route_id        TEXT,
    route_short_name TEXT,
    direction_id    INTEGER,
    trip_headsign   TEXT,
    vehicle_id      TEXT,
    sched_arrival   INTEGER,    -- epoch seconds
    sched_departure INTEGER,
    obs_arrival     INTEGER,    -- epoch seconds (last prediction seen)
    obs_departure   INTEGER,
    first_seen      INTEGER,
    last_seen       INTEGER,    -- feed timestamp of last sighting
    lead_s          INTEGER,
    n_updates       INTEGER DEFAULT 1,
    PRIMARY KEY (service_date, trip_id, stop_sequence)
) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS stop_events_stop ON stop_events(stop_id, service_date);
CREATE INDEX IF NOT EXISTS stop_events_route_stop ON stop_events(route_id, stop_id, service_date);

CREATE TABLE IF NOT EXISTS vehicle_positions (
    vehicle_id TEXT,
    ts         INTEGER,         -- epoch seconds (vehicle timestamp)
    trip_id    TEXT,
    route_id   TEXT,
    lat        REAL,
    lon        REAL,
    bearing    REAL,
    speed      REAL,            -- m/s
    PRIMARY KEY (vehicle_id, ts)
) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS vehicle_positions_ts ON vehicle_positions(ts);

-- Vehicles in the latest poll that are on a trip and reported recently.
-- Replaced wholesale on every poll; live views read only this table.
CREATE TABLE IF NOT EXISTS vehicle_state (
    vehicle_id   TEXT PRIMARY KEY,
    ts           INTEGER,       -- vehicle timestamp
    trip_id      TEXT,
    route_id     TEXT,
    direction_id INTEGER,
    headsign     TEXT,
    lat          REAL,
    lon          REAL,
    bearing      REAL,
    speed        REAL,          -- m/s
    delay_s      INTEGER,       -- predicted - scheduled arrival at next stop
    next_stop_id TEXT
);

CREATE TABLE IF NOT EXISTS polls (
    ts            INTEGER PRIMARY KEY,   -- wall clock of poll
    feed_ts       INTEGER,
    n_vehicles    INTEGER,
    n_trip_updates INTEGER,
    n_stop_updates INTEGER,
    error         TEXT
);

"""

# Indexes on migrated columns and views: run after migrate(). Views are always
# recreated so definition changes apply to existing databases.
POST_SCHEMA = f"""
CREATE INDEX IF NOT EXISTS stops_station ON stops(station_id);

-- Stop visits we consider actually observed (see OBSERVED).
DROP VIEW IF EXISTS observed_stop_events;
CREATE VIEW observed_stop_events AS
SELECT e.*,
       s.stop_name,
       obs_arrival - sched_arrival AS delay_s,
       datetime(obs_arrival, 'unixepoch', 'localtime') AS obs_arrival_local,
       CAST(strftime('%H', obs_arrival, 'unixepoch', 'localtime') AS INTEGER) AS hour,
       (CAST(strftime('%w', service_date) AS INTEGER) + 6) % 7 AS dow   -- 0=Mon
FROM stop_events e
LEFT JOIN stops s USING (stop_id)
WHERE {OBSERVED};

DROP VIEW IF EXISTS scheduled_stop_times;
CREATE VIEW scheduled_stop_times AS
SELECT st.trip_id, st.stop_sequence, st.stop_id, s.stop_name,
       t.route_id, r.route_short_name, t.direction_id, t.trip_headsign, t.service_id,
       st.arrival_s, st.departure_s,
       printf('%02d:%02d', st.arrival_s / 3600, (st.arrival_s % 3600) / 60) AS arrival_hhmm
FROM stop_times st
JOIN trips t USING (trip_id)
JOIN routes r USING (route_id)
JOIN stops s USING (stop_id);
"""


def connect(path: str | None = None, readonly: bool = False) -> sqlite3.Connection:
    path = path or DEFAULT_DB
    if readonly:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, check_same_thread=False)
    else:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(path, check_same_thread=False, timeout=30)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
    conn.row_factory = sqlite3.Row
    return conn


def init(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    migrate(conn)
    conn.executescript(POST_SCHEMA)
    conn.commit()


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}


def migrate(conn: sqlite3.Connection) -> None:
    """Bring an existing database up to SCHEMA_VERSION."""
    version = int(get_meta(conn, "schema_version") or 1)
    if version >= SCHEMA_VERSION:
        return
    if version < 2:
        if "station_id" not in _columns(conn, "stops"):
            conn.execute("ALTER TABLE stops ADD COLUMN station_id TEXT")
        conn.execute("DROP INDEX IF EXISTS stop_events_route")
        purge_stale_events(conn, since=None)
        if conn.execute("SELECT 1 FROM stops LIMIT 1").fetchone():
            from . import gtfs_static
            gtfs_static.derive(conn)
    set_meta(conn, "schema_version", str(SCHEMA_VERSION))
    conn.commit()


def purge_stale_events(conn: sqlite3.Connection, since: str | None, now: int | None = None) -> int:
    """Delete finalized stop visits that fall outside the observed window.

    since: only look at service dates >= this (YYYY-MM-DD); None scans everything.
    """
    import time
    cutoff = (now or int(time.time())) - FINAL_AFTER_S
    where = f"last_seen < ? AND NOT ({OBSERVED})"
    params: list = [cutoff]
    if since:
        where = "service_date >= ? AND " + where
        params.insert(0, since)
    return conn.execute(f"DELETE FROM stop_events WHERE {where}", params).rowcount


def get_meta(conn: sqlite3.Connection, key: str) -> str | None:
    row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return row[0] if row else None


def set_meta(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO meta(key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )
