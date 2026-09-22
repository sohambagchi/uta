# Analytics model: route segments, client-side statistics, no SQL console

**Status:** accepted

**Context:** The dashboard is for route analytics (trip duration, variance, schedule adherence), not trip planning, and users query with controls rather than SQL. The old travel-time view mixed all routes between two stops and needed a round trip for every filter change.
**Decision:** The unit of analysis is a segment: one route between two of its stations (direction inferred from stop order). Up to 4 segments are compared at once, colored by the first four slots of the dataviz categorical palette, fixed per comparison. `/api/segment` returns per-trip samples (columnar) for the date range. Weekday, hour, outlier, and bin filters and all statistics run in the browser. The SQL console, `/api/sql`, `/api/travel-time`, and `/api/route-performance` are removed.
**Alternatives:** Server-side aggregation per filter change (slower controls, and the statistics would be duplicated in two places).
**Consequences:** Transfers and whole-route pages are out of scope for now. Payload size grows with history (~10k trips per segment over 90 days is fine; revisit with daily rollups if segments get much busier). Ad-hoc SQL is still possible with `sqlite3`.
