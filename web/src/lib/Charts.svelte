<script lang="ts">
  import * as Plot from "@observablehq/plot";
  import PlotFigure, { type Readout, type ReadoutRow } from "./PlotFigure.svelte";
  import type { Series } from "./series";
  import { cdf, cdfAt, daily, dowStats, lastPoints, nearest, padDomain, schedBins, timeBins, MIN_PER_BIN,
    type BinPoint } from "./chartdata";
  import { fmtHour, fmtClock } from "./format";

  let { series, active, bin }: { series: Series[]; active: Series | undefined; bin: number } = $props();

  const INK2 = "var(--ink-2)";
  const SURFACE = "var(--surface)";
  const fmt1 = (m: number) => (Math.abs(m) < 10 ? m.toFixed(1) : Math.round(m).toString());
  const signed = (m: number) => (m > 0 ? "+" : m < 0 ? "−" : "") + fmt1(Math.abs(m));
  const name = (s: { letter: string }) => {
    const x = series.find((q) => q.letter === s.letter);
    return x ? `${x.letter} · ${x.routeShort}` : s.letter;
  };

  function base(width: number, height: number, extra: Record<string, unknown> = {}): Plot.PlotOptions {
    return {
      width, height, marginLeft: 44, marginRight: 34, marginTop: 14, marginBottom: 30,
      style: { background: "transparent", fontSize: "11px", overflow: "visible" },
      color: { type: "identity" },
      ...extra,
    } as Plot.PlotOptions;
  }
  const hourAxis = (domain: [number, number]) => ({
    domain, label: null, tickFormat: (h: number) => fmtHour(h),
    ticks: Math.max(2, Math.min(12, Math.round(domain[1] - domain[0]))),
  });

  /** Dot + letter at the last point of each line: selective direct labels. */
  function endLabels<T extends { letter: string; color: string }>(pts: T[], x: keyof T & string, y: keyof T & string) {
    const last = lastPoints(pts, y);
    return [
      Plot.dot(last, { x, y, r: 4, fill: "color", stroke: SURFACE, strokeWidth: 2 }),
      Plot.text(last, { x, y, text: "letter", dx: 9, textAnchor: "start", fill: INK2, fontWeight: 600 }),
    ];
  }

  // ------------------------------------------------------------ data

  const withTrips = $derived(series.filter((s) => s.trips.length >= 2));
  const cdfData = $derived(withTrips.map((s) => ({ s, pts: cdf(s), sorted: s.trips.map((t) => t.dur / 60).sort((a, b) => a - b) })));
  const bins = $derived(series.map((s) => ({ s, pts: timeBins(s, bin) })));
  const binPts = $derived(bins.flatMap((b) => b.pts));
  const activeSched = $derived(active ? schedBins(active, bin) : []);
  const activeBins = $derived(bins.find((b) => b.s === active)?.pts ?? []);
  const hourDomain = $derived.by((): [number, number] => {
    const xs = [...binPts.filter((p) => isFinite(p.median)).map((p) => p.x), ...activeSched.filter((p) => isFinite(p.median)).map((p) => p.x)];
    if (!xs.length) return [0, 24];
    const pad = bin / 120;
    return [Math.max(0, Math.min(...xs) - pad), Math.min(24, Math.max(...xs) + pad)];
  });
  const binCenters = $derived([...new Set([...binPts.map((p) => p.x), ...activeSched.map((p) => p.x)])].sort((a, b) => a - b));
  const dowData = $derived(series.flatMap(dowStats));
  const dailyData = $derived(series.flatMap(daily));
  const dates = $derived([...new Set(dailyData.map((d) => +d.date))].sort((a, b) => a - b));
  const scatter = $derived(series.flatMap((s) => s.trips.map((t) => ({
    letter: s.letter, color: s.color, x: t.minute / 60, y: t.dur / 60, date: t.date, minute: t.minute,
  }))));

  function binReadout(field: keyof BinPoint, label: (v: number, p: BinPoint) => string, withSched = false) {
    return (x: number): Readout | null => {
      const c = nearest(binCenters, (v) => v, x);
      if (c == null) return null;
      const rows: ReadoutRow[] = [];
      for (const { s, pts } of bins) {
        const p = pts.find((q) => q.x === c);
        if (p && isFinite(p[field] as number)) rows.push({ color: s.color, value: label(p[field] as number, p), name: name(s) });
        else rows.push({ color: s.color, value: "–", name: `${name(s)} · ${p?.n ?? 0} trips` });
        if (withSched && s === active) {
          const sp = activeSched.find((q) => q.x === c);
          if (sp && isFinite(sp.median)) rows.push({ color: s.color, dashed: true, value: `${fmt1(sp.median)} min`, name: `${s.letter} scheduled` });
        }
      }
      const start = (c * 60 - bin / 2);
      return { x: c, title: `Departing ${fmtClock(start)}–${fmtClock(start + bin)}`, rows };
    };
  }

  // ------------------------------------------------------------ charts

  const cdfPlot = (width: number) => Plot.plot(base(width, 250, {
    x: { label: "Minutes", labelAnchor: "right", labelArrow: "none" },
    y: { domain: [0, 1], tickFormat: "%", grid: true, label: null, ticks: 5 },
    marks: [
      Plot.ruleY([0], { stroke: "var(--axis)" }),
      Plot.ruleY([0.5], { stroke: "var(--axis)", strokeOpacity: 0.8 }),
      ...cdfData.map(({ pts }) => Plot.lineY(pts, { x: "x", y: "y", stroke: "color", strokeWidth: 2, curve: "step-after" })),
      ...endLabels(cdfData.map(({ pts }) => pts[pts.length - 1]), "x", "y"),
    ],
  })) as never;
  const cdfReadout = (x: number): Readout | null => {
    if (!isFinite(x)) return null;
    return {
      x, title: `Trips taking ${fmt1(x)} min or less`,
      rows: cdfData.map(({ s, sorted }) => ({ color: s.color, value: `${Math.round(cdfAt(sorted, x) * 100)}%`, name: name(s) })),
    };
  };

  const hourY = $derived(padDomain([
    ...binPts.flatMap((p) => [p.median, p.p10, p.p90]), ...activeSched.map((p) => p.median)]));
  const hourPlot = (width: number) => Plot.plot(base(width, 250, {
    x: hourAxis(hourDomain),
    y: { grid: true, label: null, tickFormat: (v: number) => fmt1(v), domain: hourY, nice: true },
    marks: [
      Plot.areaY(activeBins, { x: "x", y1: "p10", y2: "p90", fill: active?.color, fillOpacity: 0.1, curve: "monotone-x" }),
      Plot.lineY(activeSched, { x: "x", y: "median", stroke: active?.color, strokeWidth: 1.5, strokeDasharray: "4 3", curve: "monotone-x" }),
      ...bins.map(({ pts }) => Plot.lineY(pts, { x: "x", y: "median", stroke: "color", strokeWidth: 2, curve: "monotone-x" })),
      ...endLabels(binPts, "x", "median"),
    ],
  })) as never;

  const spreadPlot = (width: number) => Plot.plot(base(width, 220, {
    x: hourAxis(hourDomain),
    y: { grid: true, label: null, tickFormat: (v: number) => fmt1(v), domain: [0, Math.max(2, ...binPts.map((p) => p.spread).filter(isFinite))], nice: true },
    marks: [
      Plot.ruleY([0], { stroke: "var(--axis)" }),
      ...bins.map(({ pts }) => Plot.lineY(pts, { x: "x", y: "spread", stroke: "color", strokeWidth: 2, curve: "monotone-x" })),
      ...endLabels(binPts, "x", "spread"),
    ],
  })) as never;

  const vsPlot = (width: number) => Plot.plot(base(width, 220, {
    x: hourAxis(hourDomain),
    y: { grid: true, label: null, tickFormat: (v: number) => signed(v) },
    marks: [
      Plot.ruleY([0], { stroke: "var(--axis)" }),
      ...bins.map(({ pts }) => Plot.lineY(pts, { x: "x", y: "vsSched", stroke: "color", strokeWidth: 2, curve: "monotone-x" })),
      ...endLabels(binPts, "x", "vsSched"),
    ],
  })) as never;

  const letters = $derived(series.map((s) => s.letter));
  const dowsShown = $derived(["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"].filter((d) => dowData.some((p) => p.dow === d)));
  const dowPlot = (width: number) => Plot.plot(base(width, 30 + dowsShown.length * Math.max(24, letters.length * 11 + 8), {
    marginLeft: 44,
    x: { grid: true, label: "Minutes", labelAnchor: "right", labelArrow: "none", tickFormat: (v: number) => fmt1(v) },
    y: { domain: letters, axis: null },
    fy: { domain: dowsShown, label: null, padding: 0.15 },
    marks: [
      Plot.ruleY(dowData, { fy: "dow", y: "letter", x1: "p25", x2: "p75", stroke: "color", strokeWidth: 2, strokeOpacity: 0.6 }),
      Plot.dot(dowData, { fy: "dow", y: "letter", x: "median", r: 4, fill: "color", stroke: SURFACE, strokeWidth: 2 }),
      Plot.tip(dowData, Plot.pointer({
        fy: "dow", y: "letter", x: "median", fill: SURFACE, stroke: "var(--border)",
        title: (d) => `${d.dow} · ${name(d)}\nmedian ${fmt1(d.median)} min\nmiddle half ${fmt1(d.p25)}–${fmt1(d.p75)} min\n${d.n} trips`,
      })),
    ],
  })) as never;

  const dailyPlot = (width: number) => Plot.plot(base(width, 220, {
    x: { type: "utc", label: null, ticks: Math.min(dates.length, Math.floor(width / 80)) },
    y: { grid: true, label: null, tickFormat: (v: number) => fmt1(v), domain: padDomain(dailyData.map((d) => d.median)), nice: true },
    marks: [
      ...series.map((s) => Plot.lineY(dailyData.filter((d) => d.letter === s.letter),
        { x: "date", y: "median", stroke: "color", strokeWidth: 2, marker: dates.length <= 31 ? "circle-stroke" : null })),
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
        return { color: s.color, value: p ? `${fmt1(p.median)} min` : "–", name: p ? `${name(s)} · ${p.n} trips` : name(s) };
      }),
    };
  };

  const scatterPlot = (width: number) => Plot.plot(base(width, 20 + letters.length * 130, {
    marginRight: 40,
    x: { ...hourAxis([Math.floor(Math.min(...scatter.map((d) => d.x))), Math.ceil(Math.max(...scatter.map((d) => d.x)))]) },
    y: { grid: true, label: null, tickFormat: (v: number) => fmt1(v), ticks: 4 },
    fy: { domain: letters, label: null, tickFormat: (l: string) => l },
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
      <h2>How long trips take</h2>
      <p>Share of trips that finish within a given number of minutes. A steeper curve means more predictable
        trips; a curve further left means faster ones.</p>
    </figcaption>
    <PlotFigure render={cdfPlot} readout={cdfReadout} height={250} isEmpty={!cdfData.length}
      empty="Needs at least two observed trips" />
  </figure>

  <figure class="card">
    <figcaption>
      <h2>By time of day</h2>
      <p>Median minutes by departure time. The shaded band is {active?.letter ?? ""}'s p10–p90 range and the dashed line is
        {active?.letter ?? ""}'s timetable. Bins with fewer than {MIN_PER_BIN} trips are gaps.</p>
    </figcaption>
    <PlotFigure render={hourPlot} readout={binReadout("median", (v, p) => `${fmt1(v)} min · ${p.n} trips`, true)} height={250}
      isEmpty={!binPts.some((p) => isFinite(p.median)) && !activeSched.length} empty="No trips in the selected hours" />
  </figure>

  <figure class="card">
    <figcaption>
      <h2>Variability by time of day</h2>
      <p>Spread between the fastest and slowest tenth of trips (p90 − p10), in minutes. Higher means less predictable.</p>
    </figcaption>
    <PlotFigure render={spreadPlot} readout={binReadout("spread", (v, p) => `${fmt1(v)} min · ${p.n} trips`)} height={220}
      isEmpty={!binPts.some((p) => isFinite(p.spread))} empty="Not enough observed trips yet" />
  </figure>

  <figure class="card">
    <figcaption>
      <h2>Versus the timetable</h2>
      <p>Median of each trip's observed minus scheduled minutes, by departure time. Above zero is slower than scheduled.</p>
    </figcaption>
    <PlotFigure render={vsPlot} readout={binReadout("vsSched", (v, p) => `${signed(v)} min · ${p.n} trips`)} height={220}
      isEmpty={!binPts.some((p) => isFinite(p.vsSched))} empty="Not enough observed trips yet" />
  </figure>

  <figure class="card">
    <figcaption>
      <h2>By day of week</h2>
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
      <h2>Every trip</h2>
      <p>Each dot is one observed trip: departure time against minutes taken, one row per comparison.</p>
    </figcaption>
    <PlotFigure render={scatterPlot} height={150} isEmpty={!scatter.length} empty="No observed trips yet" />
  </figure>
</div>

<style>
  .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 460px), 1fr)); gap: 14px; margin: 16px 0; }
  .card { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); padding: 14px 16px;
    margin: 0; min-width: 0; }
  .card.wide { grid-column: 1 / -1; }
  figcaption { margin-bottom: 8px; }
  figcaption p { color: var(--muted); font-size: 12px; margin-top: 2px; }
</style>
