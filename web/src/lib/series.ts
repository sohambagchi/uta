// A comparison's data after filters: what every chart and table consumes.

import type { Segment } from "./api";
import type { Comparison } from "./store.svelte";
import { slotColor } from "./store.svelte";
import { LETTERS } from "./format";
import { filterScheduled, filterTrips, summarize, wquantile, type Filters, type SchedRow, type Summary, type Trip } from "./stats";

export interface Series {
  c: Comparison;
  letter: string;
  color: string;
  routeShort: string;
  label: string;
  seg: Segment;
  trips: Trip[];
  trimmed: number;
  sched: SchedRow[];
  obs: Summary | null;
  schedMedian: number | null;
  schedP10: number | null;
  schedP90: number | null;
  schedTrips: number;      // timetabled trips in a typical week matching the filters
}

export function buildSeries(c: Comparison, seg: Segment, routeShort: string, f: Filters): Series {
  const { trips, trimmed } = filterTrips(seg.observed, f);
  const sched = filterScheduled(seg.scheduled, f);
  const pairs = sched.map((r) => [r.dur, r.weight] as [number, number]);
  const q = (p: number) => (pairs.length ? wquantile(pairs, p) : null);
  const schedTrips = sched.length;   // one row per (trip, weekday it runs)
  return {
    c, letter: LETTERS[c.slot], color: slotColor(c.slot), routeShort,
    label: `${routeShort}: ${seg.from.name} → ${seg.to.name}`,
    seg, trips, trimmed, sched,
    obs: summarize(trips.map((t) => t.dur)),
    schedMedian: q(0.5), schedP10: q(0.1), schedP90: q(0.9), schedTrips,
  };
}
