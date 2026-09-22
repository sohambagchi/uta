"""SQLite schema and connection helpers.

Static GTFS tables are replaced wholesale on each import. Realtime history is
append-only and compact (schema v3, see docs/adr/2026-09-21-2300-compact-history.md):
repeated ids become small integer keys, times become small offsets, and trip facts
(route, headsign, block, ...) live once per trip in trip_dim so history stays
meaningful after the GTFS changes. Views reconstruct the old stop_events rows.
"""

import logging
import os
import shutil
import sqlite3
import time
from compression import zstd
from datetime import date
from pathlib import Path

log = logging.getLogger(__name__)

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
# A visit (or a trip's vehicle) is written once it has been out of the feed this long.
FINAL_AFTER_S = 60
# Live views only show vehicles that reported within this window.
LIVE_MAX_AGE_S = 180
# Pre-migration backups kept (zstd-compressed) next to the database.
KEEP_BACKUPS = 3

SCHEMA_VERSION = 3
EPOCH = date(1970, 1, 1)

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

-- ---------- realtime history (schema v3) ----------
-- Small integer keys for ids repeated in every history row.
CREATE TABLE IF NOT EXISTS stop_keys    (key INTEGER PRIMARY KEY, stop_id TEXT);
CREATE TABLE IF NOT EXISTS route_keys   (key INTEGER PRIMARY KEY, route_id TEXT);
CREATE TABLE IF NOT EXISTS vehicle_keys (key INTEGER PRIMARY KEY, vehicle_id TEXT);
CREATE INDEX IF NOT EXISTS stop_keys_id ON stop_keys(stop_id);
CREATE INDEX IF NOT EXISTS route_keys_id ON route_keys(route_id);
-- One row per distinct trip as it was when observed (the static trips table is replaced
-- on every GTFS import). block_id is UTA's planned vehicle schedule.
CREATE TABLE IF NOT EXISTS trip_dim (
    key              INTEGER PRIMARY KEY,
    feed_version     TEXT,
    trip_id          TEXT,
    route_id         TEXT,
    route_short_name TEXT,
    direction_id     INTEGER,
    trip_headsign    TEXT,
    block_id         TEXT,
    shape_id         TEXT,
    service_id       TEXT
);
CREATE INDEX IF NOT EXISTS trip_dim_trip ON trip_dim(trip_id);
-- (trip_id, route_id) as the vehicle feed named them, for GPS pings.
CREATE TABLE IF NOT EXISTS gps_trips (key INTEGER PRIMARY KEY, trip_id TEXT, route_id TEXT);

-- Service days: day = days since 1970-01-01; origin = epoch of GTFS "midnight" (noon - 12 h).
CREATE TABLE IF NOT EXISTS days (
    day          INTEGER PRIMARY KEY,
    service_date TEXT,          -- YYYY-MM-DD
    origin       INTEGER
);

-- One row per trip-stop visit, written once it has left the feed (FINAL_AFTER_S).
-- The stored time is the last prediction seen, so it is the observed time only when
-- lead_s is inside the observed window (see OBSERVED); visits outside it are kept too.
-- Clustered for the segment query (route, stop, day); visits_at serves "what passed
-- this stop between t0 and t1". stop_events (view) rebuilds the v2 columns.
CREATE TABLE IF NOT EXISTS visits (
    route       INTEGER NOT NULL,   -- route_keys
    stop        INTEGER NOT NULL,   -- stop_keys
    day         INTEGER NOT NULL,   -- days
    trip        INTEGER NOT NULL,   -- trip_dim
    seq         INTEGER NOT NULL,   -- stop_sequence
    vehicle     INTEGER,            -- vehicle_keys
    arr         INTEGER,            -- observed arrival, seconds after days.origin
    dwell       INTEGER,            -- observed departure - arrival
    delay       INTEGER,            -- observed - scheduled arrival (NULL: no schedule)
    sched_dwell INTEGER,            -- scheduled departure - arrival
    lead_s      INTEGER,            -- observed arrival - last sighting
    span        INTEGER,            -- last - first sighting
    n_updates   INTEGER,
    PRIMARY KEY (route, stop, day, trip, seq)
) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS visits_at ON visits(stop, day, arr);

-- Per trip and day: visits written and how many are observed. Feeds day_stats.
CREATE TABLE IF NOT EXISTS trip_days (
    day        INTEGER,
    trip       INTEGER,
    n_visits   INTEGER,
    n_observed INTEGER,
    PRIMARY KEY (day, trip)
) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS day_stats (
    day        INTEGER PRIMARY KEY,
    n_visits   INTEGER,
    n_observed INTEGER,
    n_trips    INTEGER          -- trips with at least one observed visit
);

-- Which vehicle ran a trip, from TripUpdates (the vehicle feed can name a vehicle's next
-- trip early). One row per stretch with the same vehicle; seq_* is the trip's next stop
-- at the start and end of the stretch. A trip with two rows changed vehicles.
CREATE TABLE IF NOT EXISTS trip_vehicle (
    day       INTEGER,
    trip      INTEGER,          -- trip_dim
    t_first   INTEGER,          -- epoch
    t_last    INTEGER,
    vehicle   INTEGER,          -- vehicle_keys
    seq_first INTEGER,
    seq_last  INTEGER,
    PRIMARY KEY (day, trip, t_first)
) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS trip_vehicle_vehicle ON trip_vehicle(vehicle, day);

-- GPS pings (one per vehicle per POSITION_EVERY_S). Appended here, then whole days are
-- sealed into gps_blocks (see gps.py). trip is the vehicle feed's trip, tu_trip the
-- trip TripUpdates assigns the vehicle (both gps_trips).
CREATE TABLE IF NOT EXISTS gps_recent (
    ts      INTEGER NOT NULL,
    vehicle INTEGER NOT NULL,
    trip    INTEGER,
    tu_trip INTEGER,
    lat     REAL,
    lon     REAL,
    bearing REAL,
    speed   REAL,               -- m/s
    PRIMARY KEY (ts, vehicle)
) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS gps_blocks (
    day     INTEGER,            -- gps.gps_day
    vehicle INTEGER,
    n       INTEGER,
    t_first INTEGER,
    t_last  INTEGER,
    data    BLOB,
    PRIMARY KEY (day, vehicle)  -- a rowid table: packs KB-sized blobs better than WITHOUT ROWID
);

-- Visits written since the last merge into visits (every 6 h, collector.MERGE_EVERY_S).
-- Appending here and merging in key order touches far fewer pages than inserting each
-- visit into the clustered table as it finishes. Readers see both (visits_all).
CREATE TABLE IF NOT EXISTS visits_new (
    route INTEGER, stop INTEGER, day INTEGER, trip INTEGER, seq INTEGER, vehicle INTEGER,
    arr INTEGER, dwell INTEGER, delay INTEGER, sched_dwell INTEGER, lead_s INTEGER, span INTEGER,
    n_updates INTEGER
);

-- Collector state that must survive a restart (in-flight visits and trips), zstd JSON.
CREATE TABLE IF NOT EXISTS collector_state (
    name TEXT PRIMARY KEY,
    data BLOB
);

-- Poll log (written in batches; the latest poll is in the live database).
CREATE TABLE IF NOT EXISTS polls (
    ts            INTEGER PRIMARY KEY,   -- wall clock of poll
    feed_ts       INTEGER,
    n_vehicles    INTEGER,
    n_trip_updates INTEGER,
    n_stop_updates INTEGER,
    error         TEXT
);

"""

# The v2 stop_events columns, rebuilt from visits (also used to verify the v3 migration).
STOP_EVENTS_VIEW = """
SELECT d.service_date, t.trip_id, v.seq AS stop_sequence, sk.stop_id, t.route_id, t.route_short_name,
       t.direction_id, t.trip_headsign, vk.vehicle_id,
       d.origin + v.arr - v.delay AS sched_arrival,
       d.origin + v.arr - v.delay + v.sched_dwell AS sched_departure,
       d.origin + v.arr AS obs_arrival,
       d.origin + v.arr + v.dwell AS obs_departure,
       d.origin + v.arr - v.lead_s - v.span AS first_seen,
       d.origin + v.arr - v.lead_s AS last_seen,
       v.lead_s, v.n_updates
FROM visits_all v
JOIN days d USING (day)
JOIN trip_dim t ON t.key = v.trip
JOIN stop_keys sk ON sk.key = v.stop
LEFT JOIN vehicle_keys vk ON vk.key = v.vehicle
"""

# Indexes on migrated columns and views: run after migrate(). Views are always
# recreated so definition changes apply to existing databases.
POST_SCHEMA = f"""
CREATE INDEX IF NOT EXISTS stops_station ON stops(station_id);

DROP VIEW IF EXISTS observed_stop_events;
DROP VIEW IF EXISTS stop_events;
DROP VIEW IF EXISTS visits_all;
CREATE VIEW visits_all AS SELECT * FROM visits UNION ALL SELECT * FROM visits_new;

-- The v2 stop_events columns, rebuilt from visits.
CREATE VIEW stop_events AS
{STOP_EVENTS_VIEW};

-- Stop visits we consider actually observed (see OBSERVED).
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


# Live state, rewritten on every poll. It lives in its own small database on tmpfs
# ($XDG_RUNTIME_DIR) so the 10 s rewrites never reach the disk; it is lost on reboot,
# which is fine because it is only the current poll.
LIVE_SCHEMA = """
-- Vehicles in the latest poll that are on a trip and reported recently.
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
-- The latest poll (same columns as polls) and the latest one without an error.
CREATE TABLE IF NOT EXISTS last_poll (
    kind TEXT PRIMARY KEY,      -- 'last' | 'ok'
    ts INTEGER, feed_ts INTEGER, n_vehicles INTEGER, n_trip_updates INTEGER, n_stop_updates INTEGER, error TEXT
);
"""


def live_path(path: str | None = None) -> str:
    """Live-state database for the history database at path ($UTA_LIVE_DIR, else $XDG_RUNTIME_DIR)."""
    import hashlib
    import tempfile
    base = os.environ.get("UTA_LIVE_DIR") or os.environ.get("XDG_RUNTIME_DIR") or tempfile.gettempdir()
    digest = hashlib.sha1(os.path.realpath(path or DEFAULT_DB).encode()).hexdigest()[:12]
    return os.path.join(base, f"uta-live-{digest}.db")


def connect_live(path: str | None = None, readonly: bool = False) -> sqlite3.Connection | None:
    """The live database; None when reading and the collector hasn't created it."""
    lp = live_path(path)
    if readonly and not os.path.exists(lp):
        return None
    conn = connect(lp, readonly=readonly)
    if not readonly:
        conn.executescript(LIVE_SCHEMA)
    return conn


def connect(path: str | None = None, readonly: bool = False) -> sqlite3.Connection:
    path = path or DEFAULT_DB
    if readonly:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, check_same_thread=False, timeout=30)
    else:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(path, check_same_thread=False, timeout=30)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
    conn.row_factory = sqlite3.Row
    return conn


class SchemaMismatch(RuntimeError):
    """The database's schema version doesn't match this code and it won't migrate it."""


def schema_version(conn: sqlite3.Connection) -> int | None:
    """Schema version of the database, or None for an empty (new) one."""
    if not conn.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'meta'").fetchone():
        return None
    return int(get_meta(conn, "schema_version") or 1)


def backup(conn: sqlite3.Connection, dest: str) -> None:
    """Consistent copy of the database, safe while the collector writes (SQLite online backup)."""
    Path(dest).parent.mkdir(parents=True, exist_ok=True)
    out = sqlite3.connect(dest)
    try:
        conn.backup(out)
    finally:
        out.close()


def backup_compressed(conn: sqlite3.Connection, dest: str) -> str:
    """Online backup to dest + '.zst' (zstd); returns that path. Restore with restore_backup."""
    tmp, out = dest + ".tmp", dest + ".zst"
    backup(conn, tmp)
    try:
        with open(tmp, "rb") as src, zstd.open(out, "wb") as dst:
            shutil.copyfileobj(src, dst, 1 << 20)
    finally:
        os.remove(tmp)
    return out


def restore_backup(src: str, dest: str) -> None:
    with zstd.open(src, "rb") as fh, open(dest, "wb") as out:
        shutil.copyfileobj(fh, out, 1 << 20)


def prune_backups(path: str, keep: int = KEEP_BACKUPS) -> list[Path]:
    """Delete all but the newest `keep` pre-migration backups of the database at path."""
    p = Path(path)
    baks = sorted(p.parent.glob(p.name + ".pre-v*.bak*"), key=lambda f: f.stat().st_mtime, reverse=True)
    for f in baks[keep:]:
        log.warning("deleting old backup %s", f)
        f.unlink()
    return baks[keep:]


def init(conn: sqlite3.Connection, allow_migrate: bool = True) -> None:
    """Create the schema and bring the database up to SCHEMA_VERSION.

    Refuses a database newer than this code. With allow_migrate=False, also refuses one that
    needs migrating, so a dev server can't migrate the live database under the collector.
    Before migrating, the database is backed up next to itself (zstd; the newest
    KEEP_BACKUPS are kept), since migrations can purge or rewrite data.
    """
    version = schema_version(conn)
    if version is not None and version > SCHEMA_VERSION:
        raise SchemaMismatch(
            f"database is schema v{version} but this code only knows v{SCHEMA_VERSION}; "
            "run a newer build or point --db at another database")
    if version is not None and version < SCHEMA_VERSION:
        if not allow_migrate:
            raise SchemaMismatch(
                f"database is schema v{version} and this code would migrate it to v{SCHEMA_VERSION}. "
                "Migrations are left to the collector. For development, snapshot the database "
                "(`uta snapshot data/dev.db`) and serve that with --db, or pass --migrate.")
        path = conn.execute("PRAGMA database_list").fetchone()[2]
        if path:
            stamp = time.strftime("%Y%m%d-%H%M%S")
            dest = f"{path}.pre-v{SCHEMA_VERSION}-{stamp}.bak"
            log.warning("backing up schema v%d database to %s.zst before migrating", version, dest)
            backup_compressed(conn, dest)
            prune_backups(path)
    conn.executescript(SCHEMA)
    rewritten = migrate(conn)
    conn.executescript(POST_SCHEMA)
    conn.commit()
    if rewritten:
        log.warning("reclaiming space after migration (VACUUM)")
        conn.execute("VACUUM")


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}


def _is_table(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (name,)).fetchone() is not None


def migrate(conn: sqlite3.Connection) -> bool:
    """Bring an existing database up to SCHEMA_VERSION, atomically.
    Returns True if history was rewritten (worth a VACUUM)."""
    version = int(get_meta(conn, "schema_version") or 1)
    if version >= SCHEMA_VERSION:
        return False
    rewritten = False
    if conn.in_transaction:
        conn.commit()
    conn.execute("BEGIN")
    try:
        if version < 2:
            if "station_id" not in _columns(conn, "stops"):
                conn.execute("ALTER TABLE stops ADD COLUMN station_id TEXT")
            conn.execute("DROP INDEX IF EXISTS stop_events_route")
            if _is_table(conn, "stop_events"):
                _purge_v2(conn)
            if conn.execute("SELECT 1 FROM stops LIMIT 1").fetchone():
                from . import gtfs_static
                gtfs_static.derive(conn)
        if version < 3:
            conn.execute("DROP TABLE IF EXISTS vehicle_state")    # moved to the live database
            if _is_table(conn, "stop_events"):
                from . import history
                history.migrate_v2(conn)
                rewritten = True
        set_meta(conn, "schema_version", str(SCHEMA_VERSION))
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    return rewritten


def _purge_v2(conn: sqlite3.Connection) -> int:
    """The v2 migration's cleanup: delete finalized stop visits outside the observed window."""
    cutoff = int(time.time()) - 600
    return conn.execute(f"DELETE FROM stop_events WHERE last_seen < ? AND NOT ({OBSERVED})", (cutoff,)).rowcount


def get_meta(conn: sqlite3.Connection, key: str) -> str | None:
    row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return row[0] if row else None


def set_meta(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO meta(key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )
