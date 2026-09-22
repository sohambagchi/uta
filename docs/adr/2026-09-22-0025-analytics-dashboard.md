# Analytics dashboard: page per level, per-day facts in memory, minimal text

**Status:** accepted (supersedes the layout and copy parts of [2026-09-21-2130-subway-design](2026-09-21-2130-subway-design.md); design brief and canvas: [2026-09-21-2322-claude-design-prompt](../analysis-artifacts/2026-09-21-2322-claude-design-prompt.md))

**Context:** The dashboard was one screen for timing rides between two stops. The data now supports network, route, station, trip, vehicle and data-quality questions, and the product is an analyst's instrument rather than a rider tool.

**Decision:**
- **Pages by level**, each a hash route whose path names the thing and whose query sets the scope: `#/network`, `#/routes/<route_id>/<dir>`, `#/compare?c=…`, `#/stations/<id>`, `#/trip/<id>?date=`, `#/vehicle/<id>?date=`, `#/health`, `#/live`. A global scope bar (dates, weekdays, service hours, modes; on-time window shown) is stored in the query as `from`, `to`, `dows`, `h`, `modes`; a page hides the controls that don't apply. Defaults are omitted, so shared links stay short.
- **Server-side aggregation** in `insights.py`, not per-trip samples in the browser (the segment page keeps its client-side filtering). Each service day's observed visits are read once into compact `array` columns (`DayFacts`) and cached per process (LRU, 60 days); a finished day never changes, the current day is re-read at most every 60 s. Route, trip and vehicle views read their own rows directly.
- **Collector gaps are data**: a poll gap over 120 s is an outage, drawn hatched on every time axis, excluded from "scheduled trips that ran", from headway statistics (a gap spanning an unobserved arrival is dropped: a missing observation is not a missing vehicle) and from coverage.
- **Fleet in service** comes from GPS pings on a trip (±60 s of each 10-minute mark), not `trip_vehicle`, which is written only after a trip ends.
- **Visual system** from the design canvas: Archivo (width axis) + IBM Plex Mono, warm paper / blue-black neutrals, three colour roles that never share a chart (diverging delay blue ↔ grey ↔ amber-to-oxblood; slots A–D; UTA line colours), hand-drawn SVG charts for the new pages (Observable Plot remains in Compare).
- **Minimal text**: question titles, numbers, tags and legends on the page; definitions, method and caveats behind ⓘ tips.

**Consequences:** `visits` has no index on `day`, so reading a day scans the table (≈0.4 s per day today); fine while history is weeks, see TODO. The server stays read-only. The old `#c=…` bookmarks redirect to `#/compare`. `npmDepsHash` changed (Archivo, IBM Plex Mono replace Inter).
