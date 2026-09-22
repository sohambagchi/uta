# TODO

- [ ] Recheck the observed lead window against GPS after a day of 10 s polling
- [ ] Refine observed arrivals with GPS proximity to the stop; would recover the visits outside the lead window (kept since v3)
- [ ] Derive trip-origin departures from GPS (UTA's TripUpdates omit stop_sequence 1)
- [ ] Daily rollup tables if segment payloads get large
- [ ] Buses crossed between two stops, same vs. other route: order of arrival times flips between shared stations (`visits_at`); a prototype took 29 ms for 73 stations
- [ ] Static `corridor` table (shared road between route directions, from `shapes`) for crossings where routes share road but not stops
- [ ] Vehicle continuity: vehicles on several routes, mid-trip swaps (`trip_vehicle`), observed vs. planned `block_id`
- [ ] Delete the pre-v3 backup (`data/uta.db.pre-v3-*.bak.zst`) once v3 has run cleanly for a while
- [ ] Index `visits(day)` (schema migration, collector-owned) once reading a day for the dashboard gets slow; today it scans the table (~0.4 s/day)
- [ ] Explain the coverage shortfall on Data health: ~27% of scheduled stop visits outside outages are never recorded, beyond first stops
- [ ] Last stops show no realtime either (Red Line's last two stations, every bus bay at Murray Central): confirm in the feed and document next to the first-stop gap
- [ ] Calendar heatmap (day × hour) and before/after a timetable change, once there are weeks of history
