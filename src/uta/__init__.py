"""UTA transit explorer: GTFS/GTFS-rt collector, SQLite history, dashboard."""

import os
import time

# All analysis is in Salt Lake City local time; SQLite's 'localtime' modifier
# (used in views and ad-hoc SQL) follows the process TZ.
os.environ["TZ"] = "America/Denver"
time.tzset()
