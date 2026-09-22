// Aggregations behind the charts. All durations in seconds in, minutes out.

import type { Series } from "./series";
import { groupBy, quantile, wquantile } from "./stats";
import { DOW } from "./format";

/** Bins with fewer observed trips than this are left as gaps. */
export const MIN_PER_BIN = 3;

export interface BinPoint {
  letter: string;
  color: string;
  x: number;              // bin centre, hours after midnight
  median: number;         // minutes; NaN where the bin is too thin (gap)
  p10: number;
  p90: number;
  spread: number;         // p90 - p10
  vsSched: number;        // median(observed - scheduled)
  n: number;
}

const min = (s: number) => s / 60;

/** Observed time-of-day bins for one series, with NaN gaps between first and last bin. */
export function timeBins(s: Series, bin: number): BinPoint[] {
  const groups = groupBy(s.trips, (t) => Math.floor(t.minute / bin));
  const keys = [...groups.keys()];
  if (!keys.length) return [];
  const out: BinPoint[] = [];
  for (let k = Math.min(...keys); k <= Math.max(...keys); k++) {
    const g = groups.get(k) ?? [];
    const d = g.map((t) => t.dur).sort((a, b) => a - b);
    const diff = g.filter((t) => t.sched != null).map((t) => t.dur - t.sched!).sort((a, b) => a - b);
    const ok = d.length >= MIN_PER_BIN;
    out.push({
      letter: s.letter, color: s.color, x: (k * bin + bin / 2) / 60, n: d.length,
      median: ok ? min(quantile(d, 0.5)) : NaN,
      p10: ok ? min(quantile(d, 0.1)) : NaN,
      p90: ok ? min(quantile(d, 0.9)) : NaN,
      spread: ok ? min(quantile(d, 0.9) - quantile(d, 0.1)) : NaN,
      vsSched: diff.length >= MIN_PER_BIN ? min(quantile(diff, 0.5)) : NaN,
    });
  }
  return out;
}

export interface SchedPoint { letter: string; color: string; x: number; median: number }

/** Timetable median per time-of-day bin (weighted by days run). */
export function schedBins(s: Series, bin: number): SchedPoint[] {
  const groups = groupBy(s.sched, (r) => Math.floor(r.minute / bin));
  const keys = [...groups.keys()];
  if (!keys.length) return [];
  const out: SchedPoint[] = [];
  for (let k = Math.min(...keys); k <= Math.max(...keys); k++) {
    const g = groups.get(k);
    out.push({
      letter: s.letter, color: s.color, x: (k * bin + bin / 2) / 60,
      median: g ? min(wquantile(g.map((r) => [r.dur, r.weight]), 0.5)) : NaN,
    });
  }
  return out;
}

export interface CdfPoint { letter: string; color: string; x: number; y: number }

/** Empirical CDF: share of trips taking at most x minutes. */
export function cdf(s: Series): CdfPoint[] {
  const d = s.trips.map((t) => min(t.dur)).sort((a, b) => a - b);
  if (!d.length) return [];
  const start = { letter: s.letter, color: s.color, x: d[0], y: 0 };
  return [start, ...d.map((x, i) => ({ letter: s.letter, color: s.color, x, y: (i + 1) / d.length }))];
}

export function cdfAt(sortedMinutes: number[], x: number): number {
  let lo = 0, hi = sortedMinutes.length;
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    if (sortedMinutes[mid] <= x) lo = mid + 1; else hi = mid;
  }
  return sortedMinutes.length ? lo / sortedMinutes.length : NaN;
}

export interface DowPoint { letter: string; color: string; dow: string; median: number; p25: number; p75: number; n: number }

export function dowStats(s: Series): DowPoint[] {
  const groups = groupBy(s.trips, (t) => t.dow);
  const out: DowPoint[] = [];
  for (const [dow, g] of [...groups.entries()].sort((a, b) => a[0] - b[0])) {
    if (g.length < MIN_PER_BIN) continue;
    const d = g.map((t) => t.dur).sort((a, b) => a - b);
    out.push({ letter: s.letter, color: s.color, dow: DOW[dow], n: d.length,
      median: min(quantile(d, 0.5)), p25: min(quantile(d, 0.25)), p75: min(quantile(d, 0.75)) });
  }
  return out;
}

export interface DayPoint { letter: string; color: string; date: Date; median: number; n: number }

export function daily(s: Series): DayPoint[] {
  const groups = groupBy(s.trips, (t) => t.date);
  return [...groups.entries()].sort((a, b) => a[0].localeCompare(b[0]))
    .filter(([, g]) => g.length >= MIN_PER_BIN)
    .map(([date, g]) => ({
      letter: s.letter, color: s.color, date: new Date(date + "T00:00:00Z"), n: g.length,
      median: min(quantile(g.map((t) => t.dur).sort((a, b) => a - b), 0.5)),
    }));
}

/** Last non-gap point of each series, for direct end labels. */
export function lastPoints<T extends { letter: string }>(points: T[], y: keyof T): T[] {
  const last = new Map<string, T>();
  for (const p of points) if (isFinite(p[y] as number)) last.set(p.letter, p);
  return [...last.values()];
}

export function nearest<T>(items: T[], key: (t: T) => number, x: number): T | undefined {
  let best: T | undefined, bd = Infinity;
  for (const it of items) {
    const d = Math.abs(key(it) - x);
    if (d < bd) { bd = d; best = it; }
  }
  return best;
}

/** y domain with at least `minSpan` minutes of range, so flat series still get an axis. */
export function padDomain(values: number[], minSpan = 4): [number, number] | undefined {
  const v = values.filter(isFinite);
  if (!v.length) return undefined;
  let lo = Math.min(...v), hi = Math.max(...v);
  if (hi - lo < minSpan) { const mid = (lo + hi) / 2; lo = mid - minSpan / 2; hi = mid + minSpan / 2; }
  return [Math.max(0, lo), hi];
}
