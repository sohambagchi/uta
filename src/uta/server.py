"""FastAPI app: JSON API + the built dashboard (web/ -> static/)."""

import sqlite3
import threading
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from . import analytics, db

STATIC_DIR = Path(__file__).parent / "static"

NOT_BUILT = """<!doctype html><title>UTA Transit Explorer</title>
<body style="font:14px system-ui;padding:40px">
<p>The dashboard hasn't been built. Run <code>npm --prefix web run build</code> in the dev shell,
or use <code>npm --prefix web run dev</code> for a live-reloading dev server.</p>
<p>The API is up: <a href="/docs">/docs</a>.</p>"""


def _csv(v: str | None) -> list[str] | None:
    if not v:
        return None
    return [x.strip() for x in v.split(",") if x.strip()]


def create_app(db_path: str | None = None, migrate: bool = False) -> FastAPI:
    """migrate: allow bringing an older database up to date (see db.init). Off by default so a
    dev server can't migrate the live database; the collector owns migrations."""
    app = FastAPI(title="UTA Transit Explorer")
    local = threading.local()
    network_cache: dict = {}

    def conn() -> sqlite3.Connection:
        # one connection per worker thread; FastAPI runs sync endpoints in a pool.
        # Read-only: nothing served here writes, so query code can't touch collected data.
        c = getattr(local, "conn", None)
        if c is None:
            c = local.conn = db.connect(db_path, readonly=True)
        return c

    init_conn = db.connect(db_path)
    try:
        db.init(init_conn, allow_migrate=migrate)
    finally:
        init_conn.close()

    @app.get("/api/status")
    def status():
        c = conn()
        last = c.execute("SELECT * FROM polls ORDER BY ts DESC LIMIT 1").fetchone()
        last_ok = c.execute("SELECT ts FROM polls WHERE error IS NULL ORDER BY ts DESC LIMIT 1").fetchone()
        span = c.execute(
            "SELECT MIN(service_date) AS first, MAX(service_date) AS last, COUNT(*) AS n, "
            f"COUNT(DISTINCT service_date || trip_id) AS trips FROM stop_events WHERE {db.OBSERVED}"
        ).fetchone()
        return {
            "gtfs_feed_version": db.get_meta(c, "gtfs_feed_version"),
            "gtfs_imported_at": db.get_meta(c, "gtfs_imported_at"),
            "observed": dict(span),
            "active_vehicles": c.execute(
                "SELECT COUNT(*) FROM vehicle_state WHERE ts >= ?",
                (int(time.time()) - db.LIVE_MAX_AGE_S,)).fetchone()[0],
            "last_poll": dict(last) if last else None,
            "last_ok_poll_age_s": int(time.time() - last_ok[0]) if last_ok else None,
        }

    @app.get("/api/routes")
    def routes():
        """All routes with their directions (headsign, number of stations)."""
        return analytics.list_routes(conn())

    @app.get("/api/routes/{route_id}")
    def route(route_id: str):
        """Ordered stations and main shape for each direction of a route."""
        detail = analytics.route_detail(conn(), route_id)
        if detail is None:
            raise HTTPException(404, "unknown route")
        return detail

    @app.get("/api/network")
    def network():
        """Simplified main shape of every route direction (map context)."""
        c = conn()
        version = db.get_meta(c, "gtfs_feed_version")
        if network_cache.get("version") != version:
            network_cache.update(version=version, data=analytics.network(c))
        return network_cache["data"]

    @app.get("/api/segment")
    def segment(
        route_id: str,
        from_: str = Query(..., alias="from", description="station_id"),
        to: str = Query(..., description="station_id"),
        date_from: str | None = Query(None, description="YYYY-MM-DD, service date"),
        date_to: str | None = None,
    ):
        """Observed and scheduled trips on one route between two stations."""
        res = analytics.segment(conn(), route_id, from_, to, date_from, date_to)
        if res is None:
            raise HTTPException(404, "unknown station")
        return res

    @app.get("/api/vehicles/live")
    def vehicles_live(routes: str | None = Query(None, description="comma-separated route_ids")):
        """Vehicles currently on a trip, from the collector's latest poll only."""
        where = ["v.ts >= ?"]
        params: list = [int(time.time()) - db.LIVE_MAX_AGE_S]
        route_ids = _csv(routes)
        if route_ids:
            where.append(f"v.route_id IN ({','.join('?' * len(route_ids))})")
            params += route_ids
        rows = conn().execute(
            f"""
            SELECT v.vehicle_id, v.ts, v.trip_id, v.route_id, v.direction_id, v.lat, v.lon,
                   v.bearing, v.speed, v.delay_s, v.next_stop_id, v.headsign AS trip_headsign,
                   r.route_short_name, r.route_long_name, r.route_color, r.route_type,
                   s.stop_name AS next_stop_name
            FROM vehicle_state v
            LEFT JOIN routes r ON r.route_id = v.route_id
            LEFT JOIN stops s ON s.stop_id = v.next_stop_id
            WHERE {" AND ".join(where)}
            """,
            params,
        ).fetchall()
        as_of = max((r["ts"] for r in rows), default=None)
        return {"as_of": as_of, "vehicles": [dict(r) for r in rows]}

    if (STATIC_DIR / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="assets")

    @app.get("/", include_in_schema=False)
    def index():
        page = STATIC_DIR / "index.html"
        return FileResponse(page) if page.exists() else HTMLResponse(NOT_BUILT)

    return app
