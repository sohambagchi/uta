"""SQLite schema and connection helpers.

Static GTFS tables are replaced wholesale on each import. The realtime-derived
tables (stop_events, vehicle_positions) are append/upsert-only and denormalize
route/stop/schedule info so history stays meaningful after the GTFS changes.
"""

import os
import sqlite3
from pathlib import Path

DEFAULT_DB = os.environ.get("UTA_DB", str(Path.cwd() / "data" / "uta.db"))

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
    parent_station TEXT
);
CREATE INDEX IF NOT EXISTS stops_code ON stops(stop_code);

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
CREATE INDEX IF NOT EXISTS stop_events_route ON stop_events(route_id, service_date);

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

CREATE TABLE IF NOT EXISTS polls (
    ts            INTEGER PRIMARY KEY,   -- wall clock of poll
    feed_ts       INTEGER,
    n_vehicles    INTEGER,
    n_trip_updates INTEGER,
    n_stop_updates INTEGER,
    error         TEXT
);

-- ---------- convenience views for ad-hoc SQL ----------
-- Stop visits we consider actually observed (not stale far-future predictions).
CREATE VIEW IF NOT EXISTS observed_stop_events AS
SELECT e.*,
       s.stop_name,
       obs_arrival - sched_arrival AS delay_s,
       datetime(obs_arrival, 'unixepoch', 'localtime') AS obs_arrival_local,
       CAST(strftime('%H', obs_arrival, 'unixepoch', 'localtime') AS INTEGER) AS hour,
       (CAST(strftime('%w', service_date) AS INTEGER) + 6) % 7 AS dow   -- 0=Mon
FROM stop_events e
LEFT JOIN stops s USING (stop_id)
WHERE lead_s <= 120;

CREATE VIEW IF NOT EXISTS scheduled_stop_times AS
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
    conn.commit()


def get_meta(conn: sqlite3.Connection, key: str) -> str | None:
    row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return row[0] if row else None


def set_meta(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO meta(key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )
