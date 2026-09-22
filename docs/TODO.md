# TODO

- [ ] Refine observed arrivals with GPS proximity to the stop; would recover visits discarded by the lead window
- [ ] Derive trip-origin departures from GPS (UTA's TripUpdates omit stop_sequence 1)
- [ ] Route pages: per-stop delay accumulation, headway regularity, bunching
- [ ] Daily rollup tables if segment payloads get large
- [ ] Retention policy for `vehicle_positions` (~800k rows/day)
