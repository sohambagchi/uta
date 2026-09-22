# Analytics dashboard

- New pages: Network, Routes (index + route/direction with Marey diagram, delay by station, dwell, headways, running time), Compare (the segment explorer, restyled), Stations (search, hubs, station page with routes, arrivals by hour, past board, transfer check), Trips & vehicles (trip and vehicle pages), Data health, Live.
- Hash router (`web/src/lib/router.svelte.ts`) and a global scope bar; state lives in the URL.
- API: `/api/days`, `/api/insights/{network,route/{id}/{dir},station/{id},trip/{id},vehicle/{id},vehicles,health,stations}`, `/api/search` (`src/uta/insights.py`).
- Design tokens, fonts (Archivo + IBM Plex Mono) and shared components (`web/src/lib/ui/`); `?theme=dark|light` URL parameter.
- Tests: `tests/test_insights.py`.
- Rationale: [2026-09-22-0025-analytics-dashboard](../adr/2026-09-22-0025-analytics-dashboard.md)
- Rendering fixes from an adversarial visual sweep (all pages × light/dark × 1440/1280/1024/834/390):
  - Layout: chart rows no longer collide with the global `.row` layout class; panels scroll wide tables instead of spilling out; no horizontal page scroll on phones.
  - Route page: the time-space diagram folds to the delay column on phones; the hour scope now applies to the time-space diagram and the headways; timetable relief points are dropped.
  - Scales and theme: nice integer ticks; a feed-lag zero line; dark `--sunk` is lifted so bands and tracks show; tooltips are clamped to the viewport.
  - Dates and states: dates without data are selectable and labelled; an empty state on Network.
  - Compare: 24-hour times and no signed zero.
- Compare rebuilt in the new system (`web/src/lib/compare/`): slot cards with segment strips, strip-map stop picker, chip filter bar, m:ss stats table with n badges, hand-drawn time-of-day small multiples, ECDF, box + strip, predictability and vs-timetable by hour, weekday progress meter, day by day, recent trips. Every earlier function and URL kept; legacy components and `@observablehq/plot` removed.
- Time of day replaces the hour selects everywhere: presets (All day, AM peak, Midday, PM peak, Evening, Night) and a service-day slider, 03:00 → 03:00 +1. Every panel follows it (fleet curve, station board and transfer check too); Compare filters by departure on the same scale.
- Route tabs (Overview, Stops, Trips, Headways, Timetable changes), timetable line on running time, carets on clamped outliers; Trip/Vehicle date pickers, vehicle GPS for the day (`/api/insights/vehicle/{id}/gps`), readable Gantt labels; Station mode filter; hub labels on the delay map; aligned Routes columns; phone nav menu.
- Calendar date picker (`web/src/lib/ui/DateRange.svelte`): two months, days with data marked by volume, click start then end, presets (All data, Latest day, Last 7 / 30 days). With no dates in the URL every page covers the whole span of history (`insights.Insights.scope`); single-day panels (fleet curve, station board, transfers, Marey) name their day when the range is wider. Compare uses the same picker (`from`/`to` in its URL; old `range=N` links still work) and fetches with both ends.
