<script lang="ts">
  import * as Plot from "@observablehq/plot";
  import PlotFigure, { type Readout, type ReadoutRow } from "./PlotFigure.svelte";
  import type { Series } from "./series";
  import { cdf, cdfAt, daily, dowStats, lastPoints, nearest, padDomain, schedBins, timeBins, MIN_PER_BIN,
    type BinPoint } from "./chartdata";
  import { fmtHour, fmtClock } from "./format";

  let { series, active, bin }: { series: Series[]; active: Series | undefined; bin: number } = $props();

    const SURFACE = "var(--surface)";
  const fmt1 = (m: number) => (Math.abs(m) < 10 ? m.toFixed(1) : Math.round(m).toString());
  // axis ticks keep a decimal when the step is fractional (fmt1 would print 57.5 as "58" twice)
  const tick = (v: number) => (Number.isInteger(v) ? String(v) : v.toFixed(1));
  const signed = (m: number) => (m > 0 ? "+" : m < 0 ? "−" : "") + fmt1(Math.abs(m));
  const name = (s: { letter: string }) => {
    const x = series.find((q) => q.letter === s.letter);
    return x ? `${x.letter} · ${x.routeShort}` : s.letter;
  };

  function base(width: number, height: number, extra: Record<string, unknown> = {}): Plot.PlotOptions {
    return {
      width, height, marginLeft: 44, marginRight: 40, marginTop: 14, marginBottom: 30,
      style: { background: "transparent", fontSize: "11px", overflow: "visible" },
      color: { type: "identity" },
      ...extra,
    } as Plot.PlotOptions;
  }
  const hourAxis = (domain: [number, number]) => ({
    domain, label: null, tickFormat: (h: number) => fmtHour(h),
    ticks: Math.max(2, Math.min(12, Math.round(domain[1] - domain[0]))),
  });

  /** Small dot at every non-gap bin, so a bin isolated between gaps (no line segment) still shows. */
  function binDots(y: keyof BinPoint & string) {
    return Plot.dot(binPts.filter((p) => isFinite(p[y] as number)), { x: "x", y, r: 2.5, fill: "color" });
  }

  /** Subway bullet just past the last point of each line: selective direct labels. */
  function endLabels<T extends { letter: string; color: string }>(pts: T[], x: keyof T & string, y: keyof T & string) {
    const last = lastPoints(pts, y);
    return [
      Plot.dot(last, { x, y, r: 4, fill: "color", stroke: SURFACE, strokeWidth: 2 }),
      Plot.dot(last, { x, y, dx: 17, r: 9, fill: "color", stroke: SURFACE, strokeWidth: 1.5 }),
      Plot.text(last, { x, y, dx: 17, dy: 0.5, text: "letter", fontWeight: 700, fontSize: 11, ariaLabel: "bullet" }),
    ];
  }

  // ------------------------------------------------------------ data

  const withTrips = $derived(series.filter((s) => s.trips.length >= 2));
  const cdfData = $derived(withTrips.map((s) => ({ s, pts: cdf(s), sorted: s.trips.map((t) => t.dur / 60).sort((a, b) => a - b) })));
  const bins = $derived(series.map((s) => ({ s, pts: timeBins(s, bin) })));
  const binPts = $derived(bins.flatMap((b) => b.pts));
  const activeSched = $derived(active ? schedBins(active, bin) : []);
  const activeBins = $derived(bins.find((b) => b.s === active)?.pts ?? []);
  const scatter = $derived(series.flatMap((s) => s.trips.map((t) => ({
    letter: s.letter, color: s.color, x: t.minute / 60, y: t.dur / 60, date: t.date, minute: t.minute,
  }))));
  /** Whole hours spanning xs, at least two hours wide. */
  function hoursSpan(xs: number[]): [number, number] {
    if (!xs.length) return [0, 24];
    const lo = Math.max(0, Math.floor(Math.min(...xs)));
    return [lo, Math.min(24, Math.max(lo + 2, Math.ceil(Math.max(...xs))))];
  }
  // time-of-day chart also shows the active timetable; the observed-only charts span observed trips
  const hourDomain = $derived(hoursSpan([...scatter.map((d) => d.x), ...activeSched.filter((p) => isFinite(p.median)).map((p) => p.x)]));
  const obsDomain = $derived(hoursSpan(scatter.map((d) => d.x)));
  const binCenters = $derived([...new Set([...binPts.map((p) => p.x), ...activeSched.map((p) => p.x)])].sort((a, b) => a - b));
  const dowData = $derived(series.flatMap(dowStats));
  const dailyData = $derived(series.flatMap(daily));
  const dates = $derived([...new Set(dailyData.map((d) => +d.date))].sort((a, b) => a - b));

  function binReadout(field: keyof BinPoint, label: (v: number, p: BinPoint) => string, withSched = false) {
    return (x: number): Readout | null => {
      const c = nearest(binCenters, (v) => v, x);
      if (c == null) return null;
      const rows: ReadoutRow[] = [];
      for (const { s, pts } of bins) {
        const p = pts.find((q) => q.x === c);
        if (p && isFinite(p[field] as number)) rows.push({ color: s.color, letter: s.letter, value: label(p[field] as number, p), name: s.routeShort });
        else rows.push({ color: s.color, letter: s.letter, value: "–", name: `${s.routeShort} · ${p?.n ?? 0} trips` });
        if (withSched && s === active) {
          const sp = activeSched.find((q) => q.x === c);
          if (sp && isFinite(sp.median)) rows.push({ color: s.color, dashed: true, value: `${fmt1(sp.median)} min`, name: `${s.letter} timetable` });
        }
      }
      const start = (c * 60 - bin / 2);
      return { x: c, title: `Leaving ${fmtClock(start)}–${fmtClock(start + bin)}`, rows };
    };
  }

  // ------------------------------------------------------------ charts

  const cdfPlot = (width: number) => Plot.plot(base(width, 250, {
    x: { label: "Minutes", labelAnchor: "right", labelArrow: "none" },
    y: { domain: [0, 1], tickFormat: "%", grid: true, label: null, ticks: 5 },
    marks: [
      Plot.ruleY([0], { stroke: "var(--axis)" }),
      Plot.ruleY([0.5], { stroke: "var(--axis)", strokeOpacity: 0.8 }),
      ...cdfData.map(({ pts }) => Plot.lineY(pts, { x: "x", y: "y", stroke: "color", strokeWidth: 2.5, curve: "step-after" })),
      ...endLabels(cdfData.map(({ pts }) => pts[pts.length - 1]), "x", "y"),
    ],
  })) as never;
  const cdfReadout = (x: number): Readout | null => {
    if (!isFinite(x)) return null;
    return {
      x, title: `Rides of ${fmt1(x)} min or less`,
      rows: cdfData.map(({ s, sorted }) => ({ color: s.color, letter: s.letter, value: `${Math.round(cdfAt(sorted, x) * 100)}%`, name: s.routeShort })),
    };
  };

  const hourY = $derived(padDomain([
    ...scatter.map((d) => d.y), ...binPts.flatMap((p) => [p.median, p.p10, p.p90]), ...activeSched.map((p) => p.median)]));
  const hourPlot = (width: number) => Plot.plot(base(width, 250, {
    x: hourAxis(hourDomain),
    y: { grid: true, label: null, tickFormat: tick, domain: hourY, nice: true },
    marks: [
      // individual trips as faint context, so hours with too few trips for a median still show data
      Plot.dot(scatter, { x: "x", y: "y", r: 2.5, fill: "color", fillOpacity: 0.4 }),
      Plot.areaY(activeBins, { x: "x", y1: "p10", y2: "p90", fill: active?.color, fillOpacity: 0.1, curve: "monotone-x" }),
      Plot.lineY(activeSched, { x: "x", y: "median", stroke: active?.color, strokeWidth: 1.5, strokeDasharray: "4 3", curve: "monotone-x" }),
      ...bins.map(({ pts }) => Plot.lineY(pts, { x: "x", y: "median", stroke: "color", strokeWidth: 2.5, curve: "monotone-x" })),
      binDots("median"),
      ...endLabels(binPts, "x", "median"),
    ],
  })) as never;

  const spreadPlot = (width: number) => Plot.plot(base(width, 220, {
    x: hourAxis(obsDomain),
    y: { grid: true, label: null, tickFormat: tick, domain: [0, Math.max(2, ...binPts.map((p) => p.spread).filter(isFinite))], nice: true },
    marks: [
      Plot.ruleY([0], { stroke: "var(--axis)" }),
      ...bins.map(({ pts }) => Plot.lineY(pts, { x: "x", y: "spread", stroke: "color", strokeWidth: 2.5, curve: "monotone-x" })),
      binDots("spread"),
      ...endLabels(binPts, "x", "spread"),
    ],
  })) as never;

  const vsPlot = (width: number) => Plot.plot(base(width, 220, {
    x: hourAxis(obsDomain),
    y: { grid: true, label: null, tickFormat: (v: number) => (v > 0 ? "+" : v < 0 ? "−" : "") + tick(Math.abs(v)) },
    marks: [
      Plot.ruleY([0], { stroke: "var(--axis)" }),
      ...bins.map(({ pts }) => Plot.lineY(pts, { x: "x", y: "vsSched", stroke: "color", strokeWidth: 2.5, curve: "monotone-x" })),
      binDots("vsSched"),
      ...endLabels(binPts, "x", "vsSched"),
    ],
  })) as never;

  const letters = $derived(series.map((s) => s.letter));
  const dowsShown = $derived(["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"].filter((d) => dowData.some((p) => p.dow === d)));
  const dowLetters = $derived([...new Set(dowData.map((d) => d.letter))]);
  const dowPlot = (width: number) => Plot.plot(base(width, 40 + dowsShown.length * (dowLetters.length * 14 + 14), {
    marginLeft: 44,
    x: { grid: true, label: "Minutes", labelAnchor: "right", labelArrow: "none", tickFormat: tick },
    y: { domain: dowLetters, axis: null, inset: 4 },
    fy: { domain: dowsShown, label: null, padding: 0.1 },
    marks: [
      Plot.ruleY(dowData, { fy: "dow", y: "letter", x1: "p25", x2: "p75", stroke: "color", strokeWidth: 3, strokeOpacity: 0.5, strokeLinecap: "round" }),
      Plot.dot(dowData, { fy: "dow", y: "letter", x: "median", r: 5, fill: "color", stroke: SURFACE, strokeWidth: 2 }),
      Plot.tip(dowData, Plot.pointer({
        fy: "dow", y: "letter", x: "median", fill: SURFACE, stroke: "var(--border)",
        title: (d) => `${d.dow} · ${name(d)}\nmedian ${fmt1(d.median)} min\nmiddle half ${fmt1(d.p25)}–${fmt1(d.p75)} min\n${d.n} trips`,
      })),
    ],
  })) as never;

  const dailyPlot = (width: number) => Plot.plot(base(width, 220, {
    x: { type: "utc", label: null, ticks: Math.min(dates.length, Math.floor(width / 80)) },
    y: { grid: true, label: null, tickFormat: tick, domain: padDomain(dailyData.map((d) => d.median)), nice: true },
    marks: [
      ...series.map((s) => Plot.lineY(dailyData.filter((d) => d.letter === s.letter),
        { x: "date", y: "median", stroke: "color", strokeWidth: 2.5, marker: dates.length <= 31 ? "circle-stroke" : null })),
      ...endLabels(dailyData, "date", "median"),
    ],
  })) as never;
  const dailyReadout = (x: number): Readout | null => {
    const d = nearest(dates, (v) => v, +x);
    if (d == null) return null;
    const date = new Date(d);
    return {
      x: date,
      title: date.toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric", timeZone: "UTC" }),
      rows: series.map((s) => {
        const p = dailyData.find((q) => q.letter === s.letter && +q.date === d);
        return { color: s.color, letter: s.letter, value: p ? `${fmt1(p.median)} min` : "–", name: p ? `${s.routeShort} · ${p.n} trips` : s.routeShort };
      }),
    };
  };

  const scatterLetters = $derived(letters.filter((l) => scatter.some((d) => d.letter === l)));
  const scatterPlot = (width: number) => Plot.plot(base(width, 40 + scatterLetters.length * 130, {
    marginRight: 40,
    x: hourAxis(obsDomain),
    y: { grid: true, label: null, tickFormat: tick, ticks: 4, domain: padDomain(scatter.map((d) => d.y)), nice: true },
    fy: { domain: scatterLetters, label: null, tickFormat: (l: string) => l, padding: 0.15 },
    marks: [
      Plot.dot(scatter, { fy: "letter", x: "x", y: "y", r: 2.5, fill: "color", fillOpacity: 0.7 }),
      Plot.tip(scatter, Plot.pointer({
        fy: "letter", x: "x", y: "y", fill: SURFACE, stroke: "var(--border)",
        title: (d) => `${name(d)} · ${d.date} ${fmtClock(d.minute)}\n${fmt1(d.y)} min`,
      })),
    ],
  })) as never;
</script>

<div class="grid">
  <figure class="card">
    <figcaption>
      <h2>How long is the ride?</h2>
      <p>Share of rides that arrive within a given number of minutes. Steeper means more predictable;
        further left means faster.</p>
    </figcaption>
    <PlotFigure render={cdfPlot} readout={cdfReadout} height={250} isEmpty={!cdfData.length}
      empty="Needs at least two observed trips" />
  </figure>

  <figure class="card">
    <figcaption>
      <h2>Does the time of day matter?</h2>
      <p>Faint dots are individual trips; lines are the median per time bin (bins with {MIN_PER_BIN}+ trips). The band is
        {active?.letter ?? ""}'s p10–p90 range and the dashed line is {active?.letter ?? ""}'s timetable.</p>
    </figcaption>
    <PlotFigure render={hourPlot} readout={binReadout("median", (v, p) => `${fmt1(v)} min · ${p.n} trips`, true)} height={250}
      isEmpty={!binPts.some((p) => isFinite(p.median)) && !activeSched.length} empty="No trips in the selected hours" />
  </figure>

  <figure class="card">
    <figcaption>
      <h2>How predictable is it?</h2>
      <p>Spread between the fastest and slowest tenth of trips (p90 − p10), in minutes, per time bin with {MIN_PER_BIN}+ trips.
        Higher means less predictable. Grouping by longer periods fills gaps.</p>
    </figcaption>
    <PlotFigure render={spreadPlot} readout={binReadout("spread", (v, p) => `${fmt1(v)} min · ${p.n} trips`)} height={220}
      isEmpty={!binPts.some((p) => isFinite(p.spread))} empty="Not enough observed trips yet" />
  </figure>

  <figure class="card">
    <figcaption>
      <h2>Is it keeping to the timetable?</h2>
      <p>Median of each trip's observed minus scheduled minutes, by departure time. Above zero is slower than scheduled.</p>
    </figcaption>
    <PlotFigure render={vsPlot} readout={binReadout("vsSched", (v, p) => `${signed(v)} min · ${p.n} trips`)} height={220}
      isEmpty={!binPts.some((p) => isFinite(p.vsSched))} empty="Not enough observed trips yet" />
  </figure>

  <figure class="card">
    <figcaption>
      <h2>Which days are slower?</h2>
      <p>Dot is the median; the line spans the middle half of trips (p25–p75).</p>
    </figcaption>
    <PlotFigure render={dowPlot} height={120} isEmpty={!dowData.length} empty="Not enough observed trips yet" />
  </figure>

  <figure class="card">
    <figcaption>
      <h2>Day by day</h2>
      <p>Median minutes per service day.</p>
    </figcaption>
    <PlotFigure render={dailyPlot} readout={dailyReadout} height={220} isEmpty={dates.length < 2}
      empty="Needs at least two days of history" />
  </figure>

  <figure class="card wide">
    <figcaption>
      <h2>Every ride we've seen</h2>
      <p>Each dot is one observed trip: departure time against minutes taken, one row per comparison.</p>
    </figcaption>
    <PlotFigure render={scatterPlot} height={150} isEmpty={!scatter.length} empty="No observed trips yet" />
  </figure>
</div>

<style>
  .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 460px), 1fr)); gap: 16px; }
  .card.wide { grid-column: 1 / -1; }
</style>
