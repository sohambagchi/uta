// Helpers shared by the compare charts. Durations are seconds throughout.

import { dur } from "../format";

/** Round minute ticks (as seconds) covering [lo, hi], about `n` of them. */
export function minuteTicks(lo: number, hi: number, n = 5): number[] {
  const span = Math.max(60, hi - lo) / 60;
  const step = [0.5, 1, 2, 5, 10, 15, 30, 60].find((s) => span / s <= n) ?? 120;
  const out: number[] = [];
  for (let m = Math.ceil(lo / 60 / step) * step; m * 60 <= hi + 1e-6; m += step) out.push(Math.round(m * 60));
  return out;
}

/** Duration domain padded to whole minutes, at least `minSpan` seconds wide. */
export function durDomain(values: number[], minSpan = 240): [number, number] {
  const v = values.filter((x) => Number.isFinite(x));
  if (!v.length) return [0, 600];
  let lo = Math.min(...v), hi = Math.max(...v);
  if (hi - lo < minSpan) { const mid = (lo + hi) / 2; lo = mid - minSpan / 2; hi = mid + minSpan / 2; }
  return [Math.max(0, Math.floor(lo / 60) * 60), Math.ceil(hi / 60) * 60];
}

/** Whole service hours spanning the given minutes-after-midnight, at least two hours wide. */
export function hourDomain(minutes: number[]): [number, number] {
  if (!minutes.length) return [6, 24];
  const lo = Math.floor(Math.min(...minutes) / 60);
  const hi = Math.ceil((Math.max(...minutes) + 1) / 60);
  return [lo, Math.max(lo + 2, hi)];
}

/** Every `step` hours in [h0, h1]. */
export function hourSteps(h0: number, h1: number, width: number): number[] {
  const n = h1 - h0;
  const step = n / Math.max(1, Math.floor(width / 48)) > 1 ? Math.ceil(n / Math.max(1, Math.floor(width / 48))) : 1;
  const out: number[] = [];
  for (let h = Math.ceil(h0 / step) * step; h <= h1; h += step) out.push(h);
  return out;
}

export const hh = (h: number) => String(((h % 24) + 24) % 24).padStart(2, "0");

/** Spread labels vertically so none overlap: each wants `y`, gets the nearest free slot `gap` apart. */
export function dodge<T extends { y: number }>(items: T[], gap = 17, lo = -Infinity, hi = Infinity): (T & { ly: number })[] {
  const s = [...items].sort((a, b) => a.y - b.y).map((it) => ({ ...it, ly: it.y }));
  for (let i = 1; i < s.length; i++) if (s[i].ly - s[i - 1].ly < gap) s[i].ly = s[i - 1].ly + gap;
  // pushed past the bottom: shift the stack up
  const over = s.length ? s[s.length - 1].ly - hi : 0;
  if (over > 0) for (const it of s) it.ly -= over;
  if (s.length && s[0].ly < lo) { const d = lo - s[0].ly; for (const it of s) it.ly += d; }
  return s;
}

export function q(sorted: number[], p: number): number {
  if (!sorted.length) return NaN;
  const i = (sorted.length - 1) * p, a = Math.floor(i), b = Math.ceil(i);
  return sorted[a] + (sorted[b] - sorted[a]) * (i - a);
}

/** "8:00" style tick labels for durations; signed for differences. */
export const tickDur = (s: number) => dur(s);
export const tickSigned = (s: number) => (s > 0 ? "+" : s < 0 ? "−" : "") + dur(Math.abs(s));

/** Polyline runs through the finite points, broken at gaps. */
export function runs(pts: [number, number | null][]): [number, number][][] {
  const out: [number, number][][] = [];
  let cur: [number, number][] = [];
  for (const [x, y] of pts) {
    if (y == null || !Number.isFinite(y)) { if (cur.length) out.push(cur); cur = []; continue; }
    cur.push([x, y]);
  }
  if (cur.length) out.push(cur);
  return out;
}

export const pathOf = (pts: [number, number][]) => (pts.length ? "M" + pts.map(([a, b]) => `${a.toFixed(1)},${b.toFixed(1)}`).join("L") : "");
