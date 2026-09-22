// Tiny scale helpers for the hand-drawn SVG charts.

export function lin(d0: number, d1: number, r0: number, r1: number) {
  const k = (r1 - r0) / (d1 - d0 || 1);
  return (v: number) => r0 + (v - d0) * k;
}

/** Whole hours (service-day seconds) between t0 and t1, every `step` hours. */
export function hourTicks(t0: number, t1: number, step = 1): number[] {
  const out: number[] = [];
  for (let h = Math.ceil(t0 / 3600 / step) * step; h * 3600 <= t1; h += step) out.push(h * 3600);
  return out;
}

export function hh(t: number): string {
  return String(Math.floor(t / 3600)).padStart(2, "0") + ":00";
}

/** Split points into runs, breaking where a value is null or a gap interval is crossed. */
export function runs<T>(pts: T[], x: (p: T) => number, ok: (p: T) => boolean, gaps: [number, number][] = []): T[][] {
  const out: T[][] = [];
  let cur: T[] = [];
  let prev: T | null = null;
  for (const p of pts) {
    const crosses = prev && gaps.some(([a, b]) => x(prev!) <= b && x(p) >= a);
    if (!ok(p) || crosses) { if (cur.length) out.push(cur); cur = []; }
    if (ok(p)) cur.push(p);
    prev = p;
  }
  if (cur.length) out.push(cur);
  return out;
}

export const d = (pts: [number, number][]) => (pts.length ? "M" + pts.map(([a, b]) => `${a.toFixed(1)},${b.toFixed(1)}`).join("L") : "");

export function niceMax(v: number, steps = [1, 2, 2.5, 5, 10]): number {
  if (v <= 0) return 1;
  const p = 10 ** Math.floor(Math.log10(v));
  for (const s of steps) if (s * p >= v) return s * p;
  return 10 * p;
}

/** Whole-number ticks 0..≥max with a 1/2/5 step, about `n` intervals (counts: vehicles, arrivals). */
export function niceTicks(max: number, n = 4): number[] {
  const raw = Math.max(max, 1) / n, p = 10 ** Math.floor(Math.log10(raw));
  const st = Math.max(1, [1, 2, 5, 10].map((k) => k * p).find((s) => s >= raw)!);
  const out: number[] = [];
  for (let v = 0; out.length === 0 || out.at(-1)! < max; v += st) out.push(v);
  return out;
}
