"""GPS history: a small append-only table for recent pings, sealed into compressed blocks.

The app never reads GPS history interactively, so closed days are stored as one
zstd-compressed columnar block per (day, vehicle): about 6 bytes per ping instead of ~90.

Lossless: the feed's floats are float32. Each float column is stored as an integer code
(value * scale) when float32(code / scale) reproduces the value exactly (lat/lon at 2^-18
degrees, bearing in centidegrees, speed in 0.01 mph: 99.8-100% of pings on 2026-09-21);
anything else, including NULL, is kept verbatim as an exception.
"""

import sqlite3
import struct
from collections import defaultdict
from compression import zstd
from datetime import date, datetime, timedelta

from .timeutil import TZ

VERSION = 1
# (column, scale) for float columns; code = round(value * scale)
FLOAT_COLS = (("lat", 1 << 18), ("lon", 1 << 18), ("bearing", 100), ("speed", 1 / 0.0044704))
EPOCH = date(1970, 1, 1)


def _f32(x: float) -> float:
    return struct.unpack("<f", struct.pack("<f", x))[0]


def gps_day(ts: int) -> int:
    """Day a ping belongs to: local date 3 h earlier (so owl service stays with its evening),
    as days since 1970-01-01."""
    return (datetime.fromtimestamp(ts - 3 * 3600, TZ).date() - EPOCH).days


def day_start(day: int) -> int:
    """First epoch second of a gps_day."""
    d = EPOCH + timedelta(days=day)
    return int(datetime(d.year, d.month, d.day, 3, tzinfo=TZ).timestamp())


def _varints(out: bytearray, xs) -> None:
    prev = 0
    for x in xs:
        d, prev = x - prev, x
        v = (d << 1) ^ (d >> 63)          # zigzag
        while v >= 0x80:
            out.append((v & 0x7F) | 0x80)
            v >>= 7
        out.append(v)


def _read_varints(buf: bytes, pos: int, n: int) -> tuple[list[int], int]:
    out, prev = [], 0
    for _ in range(n):
        shift = v = 0
        while True:
            b = buf[pos]
            pos += 1
            v |= (b & 0x7F) << shift
            if b < 0x80:
                break
            shift += 7
        prev += (v >> 1) ^ -(v & 1)
        out.append(prev)
    return out, pos


def encode(rows: list[tuple]) -> bytes:
    """rows: (ts, trip, tu_trip, lat, lon, bearing, speed) for one vehicle, any order."""
    rows = sorted(rows, key=lambda r: r[0])
    n = len(rows)
    # trip keys start at 1, so 0 stands for NULL
    cols = [[r[i] if r[i] is not None else 0 for r in rows] for i in range(3)]
    exceptions = []
    for c, (_, scale) in enumerate(FLOAT_COLS):
        codes, prev = [], 0
        for i, r in enumerate(rows):
            v = r[3 + c]
            code = round(v * scale) if v is not None and abs(v) < 1e12 else None  # NaN/inf -> exception
            if code is None or _f32(code / scale) != v:
                exceptions.append((i, c, v))
                code = prev                      # keep the delta stream smooth
            codes.append(code)
            prev = code
        cols.append(codes)
    out = bytearray()
    _varints(out, [n, len(exceptions)])
    for col in cols:
        _varints(out, col)
    for i, c, v in exceptions:
        _varints(out, [i, c, v is not None])
        if v is not None:
            out += struct.pack("<d", v)
    return bytes([VERSION]) + zstd.compress(bytes(out), 9)


def decode(blob: bytes) -> list[tuple]:
    """Inverse of encode: [(ts, trip, tu_trip, lat, lon, bearing, speed)] sorted by ts."""
    if blob[0] != VERSION:
        raise ValueError(f"unknown GPS block version {blob[0]}")
    buf = zstd.decompress(blob[1:])
    (n, n_exc), pos = _read_varints(buf, 0, 2)
    cols = []
    for _ in range(3 + len(FLOAT_COLS)):
        col, pos = _read_varints(buf, pos, n)
        cols.append(col)
    for c, (_, scale) in enumerate(FLOAT_COLS):
        cols[3 + c] = [_f32(x / scale) for x in cols[3 + c]]
    for c in (1, 2):
        cols[c] = [k or None for k in cols[c]]
    for _ in range(n_exc):
        (i, c, has), pos = _read_varints(buf, pos, 3)
        v = None
        if has:
            v = struct.unpack_from("<d", buf, pos)[0]
            pos += 8
        cols[3 + c][i] = v
    return list(zip(*cols))


def seal(conn: sqlite3.Connection, before: int) -> int:
    """Move recent pings with ts < before into blocks (only whole days are sealed by callers).
    Merges into an existing block if late pings arrive for a sealed day. Returns pings moved."""
    rows = conn.execute(
        "SELECT ts, vehicle, trip, tu_trip, lat, lon, bearing, speed FROM gps_recent WHERE ts < ?",
        (before,)).fetchall()
    if not rows:
        return 0
    groups = defaultdict(list)
    for ts, vehicle, *rest in rows:
        groups[(gps_day(ts), vehicle)].append((ts, *rest))
    for (day, vehicle), pts in groups.items():
        old = conn.execute("SELECT data FROM gps_blocks WHERE day = ? AND vehicle = ?", (day, vehicle)).fetchone()
        if old:
            seen = {p[0] for p in pts}
            pts += [p for p in decode(old[0]) if p[0] not in seen]
        pts.sort(key=lambda p: p[0])
        conn.execute("INSERT OR REPLACE INTO gps_blocks VALUES (?,?,?,?,?,?)",
                     (day, vehicle, len(pts), pts[0][0], pts[-1][0], encode(pts)))
    conn.execute("DELETE FROM gps_recent WHERE ts < ?", (before,))
    return len(rows)


def read(conn: sqlite3.Connection, t0: int | None = None, t1: int | None = None):
    """Pings with t0 <= ts < t1 from blocks and the recent table, as
    (vehicle_id, ts, trip_id, route_id, lat, lon, bearing, speed, tu_trip_id), by vehicle then ts."""
    vehicles = dict(conn.execute("SELECT key, vehicle_id FROM vehicle_keys"))
    trips = {k: (t, r) for k, t, r in conn.execute("SELECT key, trip_id, route_id FROM gps_trips")}
    lo, hi = (t0 if t0 is not None else 0), (t1 if t1 is not None else 1 << 62)
    pts = defaultdict(list)
    for vehicle, data in conn.execute(
            "SELECT vehicle, data FROM gps_blocks WHERE t_last >= ? AND t_first < ?", (lo, hi)):
        pts[vehicle] += [p for p in decode(data) if lo <= p[0] < hi]
    for ts, vehicle, *rest in conn.execute(
            "SELECT ts, vehicle, trip, tu_trip, lat, lon, bearing, speed FROM gps_recent WHERE ts >= ? AND ts < ?",
            (lo, hi)):
        pts[vehicle].append((ts, *rest))
    for vehicle in sorted(pts, key=lambda k: vehicles[k]):
        for ts, trip, tu_trip, lat, lon, bearing, speed in sorted(pts[vehicle], key=lambda p: p[0]):
            trip_id, route_id = trips.get(trip, (None, None))
            yield (vehicles[vehicle], ts, trip_id, route_id, lat, lon, bearing, speed,
                   trips.get(tu_trip, (None,))[0])
