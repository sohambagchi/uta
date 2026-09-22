// Client-side filtering and summary statistics over segment samples.
// The server sends every trip in the date range; everything else is here so
// sliders and toggles respond without a round trip.

import type { Observed, Scheduled } from "./api";

export interface Filters {
  range: string;          // legacy "days back" from old links ("" = all); from/to win
  from: string | null;    // first service date (YYYY-MM-DD), null = start of history
  to: string | null;      // last service date, null = latest
  dows: number[];         // empty = every day
  hourFrom: number;       // service-day hour (3..26), departure hour >= hourFrom
  hourTo: number;         // service-day hour (4..27; 24+ is after midnight), departure hour < hourTo
  trim: boolean;          // drop far outliers (Tukey 3×IQR)
  bin: number;            // minutes per time-of-day bin
}

/** One observed trip after filtering. Times in seconds. */
export interface Trip {
  depart: number;
  date: string;
  dow: number;
  minute: number;
  dur: number;
  sched: number | null;
  depDelay: number | null;
  tripId: string;
  vehicleId: string | null;
}

export interface Summary {
  n: number;
  mean: number;
  std: number;
  cv: number;            // std / mean
  min: number;
  p10: number;
  p25: number;
  median: number;
  p75: number;
  p90: number;
  p95: number;
  max: number;
  buffer: number;        // (p95 - median) / median: extra time to arrive on time 95% of the time
}

function inTime(dow: number, minute: number, f: Filters): boolean {
  if (f.dows.length && !f.dows.includes(dow)) return false;
  const h = minute / 60;
  // minute is the local clock; hours before 03:00 belong to the previous service day (24–27)
  const sh = h < 3 ? h + 24 : h;
  return sh >= f.hourFrom && sh < f.hourTo;
}

export function filterTrips(o: Observed, f: Filters): { trips: Trip[]; trimmed: number } {
  let trips: Trip[] = [];
  for (let i = 0; i < o.dur.length; i++) {
    if (!inTime(o.dow[i], o.minute[i], f)) continue;
    trips.push({
      depart: o.depart[i], date: o.date[i], dow: o.dow[i], minute: o.minute[i], dur: o.dur[i],
      sched: o.sched_dur[i], depDelay: o.dep_delay[i], tripId: o.trip_id[i], vehicleId: o.vehicle_id[i],
    });
  }
  let trimmed = 0;
  if (f.trim && trips.length >= 8) {
    const sorted = trips.map((t) => t.dur).sort((a, b) => a - b);
    const q1 = quantile(sorted, 0.25), q3 = quantile(sorted, 0.75), k = 3 * (q3 - q1);
    const before = trips.length;
    trips = trips.filter((t) => t.dur >= q1 - k && t.dur <= q3 + k);
    trimmed = before - trips.length;
  }
  return { trips, trimmed };
}

export interface SchedRow { minute: number; dow: number; dur: number; weight: number }

export function filterScheduled(s: Scheduled, f: Filters): SchedRow[] {
  const out: SchedRow[] = [];
  for (let i = 0; i < s.dur.length; i++) {
    if (inTime(s.dow[i], s.minute[i], f)) out.push({ minute: s.minute[i], dow: s.dow[i], dur: s.dur[i], weight: s.weight[i] });
  }
  return out;
}

/** Linear-interpolated quantile of an ascending array. */
export function quantile(sorted: number[], p: number): number {
  if (!sorted.length) return NaN;
  const i = (sorted.length - 1) * p, lo = Math.floor(i), hi = Math.ceil(i);
  return sorted[lo] + (sorted[hi] - sorted[lo]) * (i - lo);
}

/** Weighted quantile (step function) for timetable rows. */
export function wquantile(pairs: [number, number][], p: number): number {
  if (!pairs.length) return NaN;
  const sorted = [...pairs].sort((a, b) => a[0] - b[0]);
  const total = sorted.reduce((a, [, w]) => a + w, 0);
  let acc = 0;
  for (const [v, w] of sorted) {
    acc += w;
    if (acc >= p * total) return v;
  }
  return sorted[sorted.length - 1][0];
}

export function summarize(values: number[]): Summary | null {
  if (!values.length) return null;
  const s = [...values].sort((a, b) => a - b);
  const n = s.length;
  const mean = s.reduce((a, b) => a + b, 0) / n;
  const std = n > 1 ? Math.sqrt(s.reduce((a, v) => a + (v - mean) ** 2, 0) / (n - 1)) : 0;
  const median = quantile(s, 0.5), p95 = quantile(s, 0.95);
  return {
    n, mean, std, cv: mean ? std / mean : NaN, min: s[0], max: s[n - 1],
    p10: quantile(s, 0.1), p25: quantile(s, 0.25), median, p75: quantile(s, 0.75),
    p90: quantile(s, 0.9), p95, buffer: median ? (p95 - median) / median : NaN,
  };
}

export function groupBy<T, K>(items: T[], key: (t: T) => K): Map<K, T[]> {
  const m = new Map<K, T[]>();
  for (const it of items) {
    const k = key(it);
    const arr = m.get(k);
    if (arr) arr.push(it); else m.set(k, [it]);
  }
  return m;
}

/** Median of observed-minus-scheduled travel time per trip. */
export function vsSchedule(trips: Trip[]): number | null {
  const d = trips.filter((t) => t.sched != null).map((t) => t.dur - t.sched!).sort((a, b) => a - b);
  return d.length ? quantile(d, 0.5) : null;
}
