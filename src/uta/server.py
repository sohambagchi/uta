"""FastAPI app: JSON API + static dashboard."""

import sqlite3
import threading
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import analytics, db

STATIC_DIR = Path(__file__).parent / "static"
SQL_ROW_LIMIT = 5000
SQL_TIMEOUT_S = 15


def _csv(v: str | None) -> list[str] | None:
    if not v:
        return None
    return [x.strip() for x in v.split(",") if x.strip()]


def _ints(v: str | None) -> list[int] | None:
    items = _csv(v)
    return [int(x) for x in items] if items else None


def create_app(db_path: str | None = None) -> FastAPI:
    app = FastAPI(title="UTA Transit Explorer")
    local = threading.local()

    def conn() -> sqlite3.Connection:
        # one connection per worker thread; FastAPI runs sync endpoints in a pool
        c = getattr(local, "conn", None)
        if c is None:
            c = local.conn = db.connect(db_path)
        return c

    init_conn = db.connect(db_path)
    db.init(init_conn)
    init_conn.close()

    @app.get("/api/status")
    def status():
        c = conn()
        last = c.execute("SELECT * FROM polls ORDER BY ts DESC LIMIT 1").fetchone()
        last_ok = c.execute("SELECT ts FROM polls WHERE error IS NULL ORDER BY ts DESC LIMIT 1").fetchone()
        span = c.execute(
            "SELECT MIN(service_date) AS first, MAX(service_date) AS last, COUNT(*) AS n, "
            "COUNT(DISTINCT service_date || trip_id) AS trips FROM stop_events WHERE lead_s <= ?",
            (analytics.MAX_LEAD_S,),
        ).fetchone()
        return {
            "gtfs_feed_version": db.get_meta(c, "gtfs_feed_version"),
            "gtfs_imported_at": db.get_meta(c, "gtfs_imported_at"),
            "counts": {
                t: c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                for t in ("routes", "stops", "trips", "polls")
            },
            "observed": dict(span),
            "vehicle_positions": c.execute("SELECT COUNT(*) FROM vehicle_positions").fetchone()[0],
            "last_poll": dict(last) if last else None,
            "last_ok_poll_age_s": int(time.time() - last_ok[0]) if last_ok else None,
        }

    @app.get("/api/routes")
    def routes():
        rows = conn().execute(
            "SELECT route_id, route_short_name, route_long_name, route_type, route_color, route_text_color "
            "FROM routes ORDER BY route_type, CAST(route_short_name AS INTEGER), route_short_name"
        ).fetchall()
        return [dict(r) for r in rows]

    @app.get("/api/routes/{route_id}/shapes")
    def route_shapes(route_id: str):
        c = conn()
        shape_ids = [r[0] for r in c.execute(
            "SELECT DISTINCT shape_id FROM trips WHERE route_id = ?", (route_id,))]
        return {
            sid: [[r[0], r[1]] for r in c.execute(
                "SELECT lat, lon FROM shapes WHERE shape_id = ? ORDER BY seq", (sid,))]
            for sid in shape_ids
        }

    @app.get("/api/stops")
    def stops(q: str = "", downstream_of: str | None = None, limit: int = 30):
        return analytics.search_stops(conn(), q, _csv(downstream_of), limit=min(limit, 200))

    @app.get("/api/travel-time")
    def travel_time(
        from_: str = Query(..., alias="from", description="comma-separated stop_ids"),
        to: str = Query(..., description="comma-separated stop_ids"),
        radius_m: float = 0,
        routes: str | None = None,
        dows: str | None = Query(None, description="0=Mon..6=Sun, comma-separated"),
        hour_from: int | None = None,
        hour_to: int | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
    ):
        return analytics.travel_time(
            conn(), _csv(from_), _csv(to), radius_m=min(radius_m, 1000), routes=_csv(routes),
            dows=_ints(dows), hour_from=hour_from, hour_to=hour_to,
            date_from=date_from, date_to=date_to,
        )

    @app.get("/api/route-performance")
    def route_performance(routes: str | None = None, date_from: str | None = None,
                          date_to: str | None = None, route_type: int | None = None):
        return analytics.route_performance(conn(), _csv(routes), date_from, date_to, route_type)

    @app.get("/api/vehicles/live")
    def vehicles_live(max_age_s: int = 300):
        c = conn()
        latest = c.execute("SELECT MAX(ts) FROM vehicle_positions").fetchone()[0]
        if latest is None:
            return {"as_of": None, "vehicles": []}
        rows = c.execute(
            """
            WITH last AS (
                SELECT vehicle_id, MAX(ts) AS ts FROM vehicle_positions
                WHERE ts >= ? GROUP BY vehicle_id
            )
            SELECT v.vehicle_id, v.ts, v.trip_id, v.route_id, v.lat, v.lon, v.bearing, v.speed,
                   r.route_short_name, r.route_long_name, r.route_color, r.route_type, t.trip_headsign,
                   (SELECT obs_arrival - sched_arrival FROM stop_events e
                     WHERE e.trip_id = v.trip_id AND e.last_seen >= v.ts - 120
                     ORDER BY e.stop_sequence LIMIT 1) AS delay_s
            FROM last JOIN vehicle_positions v USING (vehicle_id, ts)
            LEFT JOIN routes r ON r.route_id = v.route_id
            LEFT JOIN trips t ON t.trip_id = v.trip_id
            """,
            (latest - max_age_s,),
        ).fetchall()
        return {"as_of": latest, "vehicles": [dict(r) for r in rows]}

    class SqlRequest(BaseModel):
        sql: str

    @app.post("/api/sql")
    def run_sql(req: SqlRequest):
        c = db.connect(db_path, readonly=True)
        c.execute("PRAGMA query_only = ON")
        deadline = time.time() + SQL_TIMEOUT_S
        c.set_progress_handler(lambda: 1 if time.time() > deadline else 0, 10000)
        try:
            cur = c.execute(req.sql)
            cols = [d[0] for d in cur.description] if cur.description else []
            rows = cur.fetchmany(SQL_ROW_LIMIT + 1)
        except sqlite3.Error as exc:
            raise HTTPException(400, str(exc))
        finally:
            c.close()
        return {
            "columns": cols,
            "rows": [list(r) for r in rows[:SQL_ROW_LIMIT]],
            "truncated": len(rows) > SQL_ROW_LIMIT,
        }

    @app.get("/api/schema")
    def schema():
        c = conn()
        return [
            {"name": r["name"], "type": r["type"], "sql": r["sql"]}
            for r in c.execute(
                "SELECT name, type, sql FROM sqlite_master WHERE type IN ('table','view') "
                "AND name NOT LIKE 'sqlite_%' ORDER BY type, name")
        ]

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/")
    def index():
        return FileResponse(STATIC_DIR / "index.html")

    return app
