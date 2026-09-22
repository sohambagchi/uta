"""FastAPI app: JSON API + the built dashboard (web/ -> static/)."""

import sqlite3
import threading
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from . import analytics, db, insights

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

    def live():
        """Read-only connection to the collector's live database, or None if it isn't running."""
        c = getattr(local, "live", None)
        if c is None:
            c = local.live = db.connect_live(db_path, readonly=True)
        return c

    init_conn = db.connect(db_path)
    try:
        db.init(init_conn, allow_migrate=migrate)
    finally:
        init_conn.close()

    @app.get("/api/status")
    def status():
        c, lc = conn(), live()
        polls = {r["kind"]: r for r in lc.execute("SELECT * FROM last_poll")} if lc else {}
        last, last_ok = polls.get("last"), polls.get("ok")
        # Constant-time however much history there is: day_stats is kept by the collector
        # for merged visits; staged visits (<= 6 h) are counted here.
        merged = c.execute(
            "SELECT MIN(d.service_date) AS first, MAX(d.service_date) AS last, "
            "COALESCE(SUM(s.n_observed), 0) AS n, COALESCE(SUM(s.n_trips), 0) AS trips "
            "FROM day_stats s JOIN days d USING (day) WHERE s.n_observed > 0").fetchone()
        staged = c.execute(
            f"""SELECT MIN(d.service_date) AS first, MAX(d.service_date) AS last, COUNT(*) AS n,
                       COUNT(DISTINCT CASE WHEN NOT EXISTS (
                           SELECT 1 FROM trip_days td WHERE td.day = v.day AND td.trip = v.trip AND td.n_observed > 0)
                       THEN v.day || ':' || v.trip END) AS trips
                FROM visits_new v JOIN days d USING (day) WHERE {db.observed("v")}""").fetchone()
        firsts = [x for x in (merged["first"], staged["first"]) if x]
        lasts = [x for x in (merged["last"], staged["last"]) if x]
        span = {"first": min(firsts, default=None), "last": max(lasts, default=None),
                "n": merged["n"] + staged["n"], "trips": merged["trips"] + staged["trips"]}
        return {
            "gtfs_feed_version": db.get_meta(c, "gtfs_feed_version"),
            "gtfs_imported_at": db.get_meta(c, "gtfs_imported_at"),
            "observed": span,
            "active_vehicles": lc.execute(
                "SELECT COUNT(*) FROM vehicle_state WHERE ts >= ?",
                (int(time.time()) - db.LIVE_MAX_AGE_S,)).fetchone()[0] if lc else 0,
            "last_poll": {k: last[k] for k in last.keys() if k != "kind"} if last else None,
            "last_ok_poll_age_s": int(time.time() - last_ok["ts"]) if last_ok else None,
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
        lc = live()
        if lc is None:
            return {"as_of": None, "vehicles": []}
        rows = [dict(r) for r in lc.execute(
            f"""
            SELECT v.vehicle_id, v.ts, v.trip_id, v.route_id, v.direction_id, v.lat, v.lon,
                   v.bearing, v.speed, v.delay_s, v.next_stop_id, v.headsign AS trip_headsign
            FROM vehicle_state v
            WHERE {" AND ".join(where)}
            """,
            params,
        )]
        # route and stop names live in the history database
        c = conn()
        route_info = {r["route_id"]: r for r in c.execute(
            "SELECT route_id, route_short_name, route_long_name, route_color, route_type FROM routes")}
        stop_ids = sorted({r["next_stop_id"] for r in rows if r["next_stop_id"]})
        stop_names = dict(c.execute(
            f"SELECT stop_id, stop_name FROM stops WHERE stop_id IN ({','.join('?' * len(stop_ids))})", stop_ids))
        for r in rows:
            info = route_info.get(r["route_id"])
            for k in ("route_short_name", "route_long_name", "route_color", "route_type"):
                r[k] = info[k] if info else None
            r["next_stop_name"] = stop_names.get(r["next_stop_id"])
        as_of = max((r["ts"] for r in rows), default=None)
        return {"as_of": as_of, "vehicles": rows}

    ins = insights.Insights(conn)

    def scope(date_from, date_to, dows, h, modes):
        return ins.scope(date_from, date_to, dows, h, modes)

    Scope = dict(
        date_from=Query(None, alias="from", description="first service date, YYYY-MM-DD (default: latest)"),
        date_to=Query(None, alias="to", description="last service date (default: latest with data)"),
        dows=Query(None, description="weekdays to keep, e.g. 01234 (0=Mon)"),
        h=Query(None, description="service-day hours, e.g. 5-29"),
        modes=Query(None, description="comma-separated: bus,lrt,streetcar,rail"),
    )

    @app.get("/api/days")
    def days():
        """Service days with observed visits."""
        return ins.days_with_data()

    @app.get("/api/insights/network")
    def insights_network(date_from: str | None = Scope["date_from"], date_to: str | None = Scope["date_to"],
                         dows: str | None = Scope["dows"], h: str | None = Scope["h"], modes: str | None = Scope["modes"]):
        """KPIs, modes, hours, route ranking, fleet curve and station delays over a scope."""
        sc = scope(date_from, date_to, dows, h, modes)
        return insights.network_summary(ins, sc)

    @app.get("/api/insights/route/{route_id}/{direction_id}")
    def insights_route(route_id: str, direction_id: int, at: str | None = Query(None, description="headway station_id"),
                       date_from: str | None = Scope["date_from"], date_to: str | None = Scope["date_to"],
                       dows: str | None = Scope["dows"], h: str | None = Scope["h"]):
        """One route direction: delay by station, running time, and the last day's Marey diagram and headways."""
        res = insights.route_day(ins, scope(date_from, date_to, dows, h, None), route_id, direction_id, at)
        if res is None:
            raise HTTPException(404, "unknown route")
        return res

    @app.get("/api/insights/station/{station_id}")
    def insights_station(station_id: str, until: int | None = Query(None, description="board end, service-day seconds"),
                         xf: str | None = Query(None, description="transfer from route_id"),
                         xt: str | None = Query(None, description="transfer to route_id"),
                         date_from: str | None = Scope["date_from"], date_to: str | None = Scope["date_to"],
                         dows: str | None = Scope["dows"], h: str | None = Scope["h"], modes: str | None = Scope["modes"]):
        res = insights.station_view(ins, scope(date_from, date_to, dows, h, modes), station_id, until, xf, xt)
        if res is None:
            raise HTTPException(404, "unknown station")
        return res

    @app.get("/api/insights/trip/{trip_id}")
    def insights_trip(trip_id: str, date: str | None = Query(None, description="service date")):
        res = insights.trip_view(ins, trip_id, date)
        if res is None:
            raise HTTPException(404, "unknown trip")
        return res

    @app.get("/api/insights/vehicle/{vehicle_id}")
    def insights_vehicle(vehicle_id: str, date: str | None = Query(None, description="service date")):
        res = insights.vehicle_view(ins, vehicle_id, date)
        if res is None:
            raise HTTPException(404, "unknown vehicle")
        return res

    @app.get("/api/insights/vehicle/{vehicle_id}/gps")
    def insights_vehicle_gps(vehicle_id: str, date: str | None = Query(None, description="service date")):
        """The vehicle's GPS pings over its service day."""
        res = insights.vehicle_gps(ins, vehicle_id, date)
        if res is None:
            raise HTTPException(404, "unknown vehicle")
        return res

    @app.get("/api/insights/vehicles")
    def insights_vehicles(date_to: str | None = Scope["date_to"]):
        """Vehicles that ran trips on a service day."""
        return insights.vehicles_on_day(ins, scope(None, date_to, None, None, None))

    @app.get("/api/insights/health")
    def insights_health(date_from: str | None = Scope["date_from"], date_to: str | None = Scope["date_to"]):
        return insights.health(ins, scope(date_from, date_to, None, None, None))

    @app.get("/api/insights/stations")
    def insights_hubs():
        """Stations served by the most routes."""
        return insights.hubs(ins)

    @app.get("/api/search")
    def search(q: str = ""):
        return insights.search(ins, q)

    # check_dir=False: `npm run watch` may create (and re-create) the directory after startup.
    app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets", check_dir=False), name="assets")

    @app.get("/", include_in_schema=False)
    def index():
        page = STATIC_DIR / "index.html"
        return FileResponse(page) if page.exists() else HTMLResponse(NOT_BUILT)

    return app
