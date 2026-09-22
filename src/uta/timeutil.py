"""GTFS time helpers. All wall-clock times are America/Denver."""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

TZ = ZoneInfo("America/Denver")


def parse_gtfs_time(s: str) -> int | None:
    """' 4:15:00' / '25:10:00' -> seconds after service-day midnight."""
    s = s.strip()
    if not s:
        return None
    h, m, sec = s.split(":")
    return int(h) * 3600 + int(m) * 60 + int(sec)


def service_day_origin(service_date: date) -> int:
    """Epoch seconds of GTFS 'midnight' for a service day: noon minus 12h (DST-safe per spec)."""
    noon = datetime(service_date.year, service_date.month, service_date.day, 12, tzinfo=TZ)
    return int(noon.timestamp()) - 12 * 3600


def infer_service_date(epoch: int, sched_s: int | None) -> date:
    """Service day a realtime event belongs to, given its scheduled offset.

    noon_of_service_day ~= epoch - sched_s + 12h, which tolerates +/-12h of delay.
    Without a schedule, fall back to the local calendar date shifted by 3h so
    after-midnight owl trips stay on the previous day.
    """
    if sched_s is None:
        return datetime.fromtimestamp(epoch - 3 * 3600, TZ).date()
    return datetime.fromtimestamp(epoch - sched_s + 12 * 3600, TZ).date()


def local(epoch: int) -> datetime:
    return datetime.fromtimestamp(epoch, TZ)


def daterange(start: date, end: date):
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)
