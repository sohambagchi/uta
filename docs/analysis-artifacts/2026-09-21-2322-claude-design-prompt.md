> Question: what should a Claude Design prompt for a full analytics UI contain, given the data, schema and query space? Answer: the prompt below (paste everything under the rule). Data figures are from the first ~7 h of collection (2026-09-21).

---

# Design brief: UTA Transit Explorer, an analytics dashboard for a transit network

## What this is

A local-first web dashboard that builds its own performance history of the Utah Transit Authority (Salt Lake City region) from UTA's public GTFS and GTFS-realtime feeds. It is **not a commuter app**: there is no trip planner and no "when is my bus". It is an analyst's instrument for asking how the network actually performs compared with its timetable: across the network, by mode, by route, along a stretch of a route, at a stop, for a single trip or vehicle, and over time.

Design the complete web UI: information architecture, navigation, every key screen, the component and chart vocabulary, and the empty, sparse, loading and stale states. The audience is a transit-curious power user or planner who reads distributions and percentiles comfortably, but the UI should stay approachable. Every chart should state its question in plain words as a title (e.g. "How late are Red Line trains by hour?"), with the exact statistic available on hover.

## The network (real values, use them in mockups)

- 86 routes: 81 bus routes (e.g. 2, 9, 200, 213, 455, 470, 821, 862, 830X, flex routes F94, F578…), 4 rail lines of type "light rail" (701 **Blue Line** `#004a97`, 703 **Red Line** `#be2036`, 704 **Green Line** `#2eb566`, 720 **S-Line** streetcar `#77777a`), and 1 commuter rail (750 **FrontRunner** `#c227b9`, Ogden to Provo).
- 5,423 stops, merged into 3,291 **stations** (bays of a hub and both sides of a street count as one place). The biggest hubs are Ogden Central, West Valley Central, Provo Central, Murray Central and Sandy Civic Center.
- Timetable: 11,083 trips, 907 vehicle blocks, ~467k scheduled stop times, route shapes, and service calendars that expand to specific dates.
- Live: ~120–250 vehicles in service at any moment (about 470 distinct vehicles over an evening). Vehicle IDs look like `25024` (bus) or `L4` / `CC115` (rail).
- Local time is America/Denver. Service days run past midnight (times like 25:10).

## The data (what is recorded)

A collector polls UTA's feeds every 10 s. Each poll carries about 5,000 stop predictions across about 260 active trips.

1. **Stop visits** (the core fact table), one row per trip × stop × service date, containing:
   - scheduled and observed arrival and departure, which give **delay** and **dwell** (observed and scheduled);
   - route, direction, headsign, vehicle, stop sequence, and vehicle block;
   - quality fields: how many prediction updates were seen, and `lead_s`, which is how far the last prediction was from "now". A visit counts as *observed* only when `lead_s` is between −120 and +15 s. Validated against GPS, that is a median of about 90 m from the stop. About 96% of visits qualify.
   - Roughly 7k observed visits per hour at peak.
2. **Scheduled trips** from the current and past timetables. Each visit keeps its own schedule snapshot, so history survives timetable changes (feed version, e.g. `2026 AUG_20260813`).
3. **GPS pings** per vehicle every 30 s: lat/lon, speed, bearing, and the trip it claims. Older days are archived and compressed.
4. **Trip ↔ vehicle assignment** over time, including mid-trip vehicle swaps.
5. **Live state**: every vehicle currently on a trip, with position, bearing, speed, delay at its next stop, and that next stop.
6. **Collector health**: every poll's timestamp, feed timestamp (which gives feed lag), vehicle, trip and stop-update counts, and any errors.

Known gaps the UI must communicate honestly:
- UTA never publishes realtime data for a trip's **first stop**, so segments that start at a terminal have timetable figures only.
- **History starts when the collector starts.** Timetable figures exist immediately. Observed figures grow from hours, to days (time-of-day patterns become usable), to weeks (day-of-week becomes meaningful). Right now there is roughly one evening of data.
- Sample sizes vary enormously. A frequent light-rail pair gets hundreds of trips a day; a flex route may get a handful.

Illustrative findings from the first evening (for realistic mockup copy only):
- Buses average +140 s late at stops; 57% are more than 1 min late and 15% more than 5 min late.
- Light rail averages +122 s.
- FrontRunner averages +3 s, but 20% of its arrivals are more than 1 min *early*.
- The routes with the most delay were F94, 862, 9 and 200.
- Mean observed dwell was 24 s.

## The question space the design should cover

Organize the product around these levels. Each level has its own summary and links down to the level below and back up to the level above.

**Network / system**
- How much of the scheduled service actually ran today? What share of scheduled trips were observed, missing, or cancelled?
- What is on-time performance (e.g. −1 / +5 min window) by mode, by route, and by hour? Which routes are worst and best, and what are they trending toward?
- How many vehicles are in service over the day, scheduled versus actual (fleet in service curve)?
- Where on the map is delay generated? Show a delay or speed heat along route shapes and at stations.

**Route (one line, one direction)**
- **Delay accumulation along the route**: median and p90 delay at each stop, on a strip-map / stringline axis. Where does the route lose time, and does it recover at timepoints?
- **Headway regularity**: actual versus scheduled gaps between consecutive vehicles at a stop, bunching (gap < ¼ scheduled), gaps (> 1.5×), and excess wait time.
- **Time-space (Marey) diagram**: every trip of a day as a line through stop × time, scheduled versus observed. This is the canonical transit-analytics chart; it shows bunching, holds and slowdowns at a glance.
- **Running time and schedule padding**: observed versus scheduled end-to-end time by hour, and early-running at timepoints.
- **Dwell by stop**, observed versus scheduled.

**Segment (route between stop A and stop B), which the existing product already does well**
- Typical travel time, spread (p10–p90, p95, std dev, CV, **buffer index**), and timetable figure.
- How it varies by departure time of day, day of week, and day by day, plus every trip as a dot.
- Up to **4 comparisons side by side**, slotted A–D: different routes over the same stops (e.g. TRAX Blue versus bus 200 between the same two stations), or different stretches of one route.
- Filters: history window, weekdays, departure-hour range, time-bin size, and far-outlier exclusion.

**Station / stop**
- Which routes serve it, and how is each performing here? Show arrivals by hour, delay distribution, dwell, and a departure/arrival board of *past* events (what actually happened versus what was scheduled).
- For transfer hubs: would a scheduled connection between route X and route Y actually have been made?

**Trip and vehicle / block**
- A single trip's story: scheduled versus observed stop by stop, its GPS trace, and speed along the way.
- A vehicle's day: its blocks and trips in sequence, layover, late departures that propagate into the next trip, and swaps.

**Time**
- Calendar heatmap (day × hour) of on-time share or median delay, per network, route or segment.
- Before and after a timetable change (feed versions).

**Data quality / collector health (a first-class page, not hidden)**
- Poll timeline with errors and feed lag, vehicles and trips per poll, and gaps in collection.
- Observed coverage: for each route and day, the share of scheduled visits that were observed, the share rejected by the lead window, and missing first stops.
- A "data maturity" indicator that says how much history backs each view, and a sample size shown next to every statistic.

**Live (context, not the center)**
- A network map of vehicles in service, colored by delay and pointed along their bearing, animated between polls. The map is a way into routes, trips and vehicles, not a rider tracker.

## Current implementation (to design toward, not to copy)

- Stack: Svelte 5 + Vite SPA; Observable Plot for charts; MapLibre GL with OpenFreeMap vector tiles; FastAPI + SQLite backend. Summary statistics are computed in the browser from per-trip samples, so filters apply instantly.
- Existing layout: a left column of comparison cards A–D, each with a route, a direction, and two stops picked from a vertical strip map of the route's stations or by clicking the map. Above them is a resizable live map. Below are filters, a stats table, a chart grid, and a trips table.
- All state lives in the URL (bookmarkable, shareable views). Keep that property.
- Current visual identity: NYC-subway signage. It has a black sign-band header with a white pinstripe, comparison slots as round colored "bullets" (blue `#0039a6`, orange `#ff6319`, green `#00933c`, purple `#b933ad`) used as direct chart labels, stop lists drawn as strip maps, UTA's own line colors on the map, delay status colors (yellow / lime / orange / red), and Inter. Light by default, with a dark toggle.
- That identity was chosen for a rider-friendly tool. The product is now an analytics dashboard, so feel free to evolve it toward something denser and more instrument-like. Keep what serves analysis: slot bullets as direct labels, strip-map station axes, and real line colors.

## What I want from you

1. **Information architecture**: top-level navigation (Network, Routes, Segments/Compare, Stations, Trips & Vehicles, Data health, Live, or a better split), plus global controls (date range, weekdays, hours, mode filter) and how they scope each page. Include drill-down and breadcrumb patterns, and how a URL encodes a view.
2. **High-fidelity screens**, desktop first (1440 px), each in light and dark:
   - Network overview: KPI row, OTP by mode, worst/best routes, fleet in service curve, and a delay map.
   - Route page: stringline/delay-accumulation strip, Marey diagram, headway regularity, and running time versus schedule.
   - Segment comparison with 4 slots A–D (evolve the existing screen).
   - Station page, trip page, vehicle/block page.
   - Data health page.
3. **Chart system**: one consistent grammar for distributions (ECDF, box/strip), time-of-day bands (median with a p10–p90 ribbon plus a dashed timetable line), calendar heatmaps, Marey diagrams, strip-map axes, and small multiples. Include palette rules for categorical slots A–D versus UTA line colors versus diverging delay (early ↔ on time ↔ late, colorblind-safe), and the tooltip format.
4. **States**: first-run with timetable only, sparse data ("n = 7 trips, treat with caution"), segments that start at a terminal (no realtime), a stale collector (last poll 12 min ago), and loading.
5. **Responsive behavior**: laptop (1280), tablet, and a usable read-only phone layout. Phone is for glancing at a shared link, not for building comparisons.
6. **Component inventory**: route bullet/badge, station strip, comparison card, filter bar, KPI tile with sparkline and sample size, stat table, map legend, and data-maturity badge.

Density and tone: favor information density over whitespace, but give every chart a plain-language question as its title. Use tabular numerals. Minutes:seconds for durations, signed values for delays (+2:10 late, −0:45 early). Nothing decorative that doesn't carry data.
