<script lang="ts">
  // One slot's travel time by departure time: every trip as a dot, median line and p10–p90 band for bins
  // with enough trips, dashed timetable. Axes are shared across slots (passed in).
  import type { Series } from "../series";
  import { timeBins, schedBins } from "../chartdata";
  import { tip } from "../tip.svelte";
  import { dur, fmtClock } from "../format";
  import { lin } from "../charts/scale";
  import Slot from "../ui/Slot.svelte";
  import NBadge from "../ui/NBadge.svelte";
  import Tag from "../ui/Tag.svelte";
  import { minuteTicks, hourSteps, hh, runs, pathOf } from "./util";

  let { s, bin, xdom, ydom, height = 190 }: { s: Series; bin: number; xdom: [number, number]; ydom: [number, number]; height?: number } = $props();
  let w = $state(320);
  const L = 40, R = 8, T = 8, B = 20;
  const x = $derived(lin(xdom[0] * 60, xdom[1] * 60, L, w - R));   // minutes after midnight
  const y = $derived(lin(ydom[0], ydom[1], height - B, T));
  const bins = $derived(timeBins(s, bin).map((p) => ({ ...p, m: p.x * 60 })));
  // timetable only over the plotted hours
  const sched = $derived(schedBins(s, bin).filter((p) => p.x >= xdom[0] && p.x <= xdom[1]).map((p) => ({ m: p.x * 60, v: p.median * 60 })));
  const medRuns = $derived(runs(bins.map((p) => [x(p.m), Number.isFinite(p.median) ? y(p.median * 60) : null])));
  const band = $derived.by(() => {
    // one closed shape per run of finite bins
    const out: string[] = [];
    let cur: typeof bins = [];
    const flush = () => {
      if (cur.length > 1) out.push(pathOf(cur.map((p) => [x(p.m), y(p.p90 * 60)] as [number, number]))
        + "L" + [...cur].reverse().map((p) => `${x(p.m).toFixed(1)},${y(p.p10 * 60).toFixed(1)}`).join("L") + "Z");
      cur = [];
    };
    for (const p of bins) { if (Number.isFinite(p.median)) cur.push(p); else flush(); }
    flush();
    return out;
  });
  const schedPath = $derived(runs(sched.map((p) => [x(p.m), Number.isFinite(p.v) ? y(p.v) : null])).map(pathOf));
  const yt = $derived(minuteTicks(ydom[0], ydom[1], 4));
  const full = $derived(bins.some((p) => Number.isFinite(p.median)));

  function move(e: PointerEvent) {
    const r = (e.currentTarget as SVGElement).getBoundingClientRect();
    const m = xdom[0] * 60 + ((e.clientX - r.left - L) / (w - L - R)) * (xdom[1] - xdom[0]) * 60;
    const k = Math.floor(m / bin);
    const p = bins.find((b) => Math.floor(b.m / bin) === k);
    const sp = sched.find((b) => Math.floor(b.m / bin) === k);
    const trips = s.trips.filter((t) => Math.floor(t.minute / bin) === k);
    if (!p && !sp && !trips.length) { tip.hide(); return; }
    tip.show(e, `${s.letter} · ${fmtClock(k * bin)}–${fmtClock(k * bin + bin)}`, [
      { k: "Median", v: p && Number.isFinite(p.median) ? dur(p.median * 60) : "—", color: `var(--slot-${s.c.slot + 1})` },
      { k: "p10–p90", v: p && Number.isFinite(p.p10) ? `${dur(p.p10 * 60)}–${dur(p.p90 * 60)}` : "—" },
      { k: "Timetable", v: sp && Number.isFinite(sp.v) ? dur(sp.v) : "—", color: "var(--sched)" },
      { k: "Trips", v: String(trips.length) },
    ]);
  }
</script>

<div class="cell" bind:clientWidth={w}>
  <div class="h"><Slot i={s.c.slot} size={18} /><span class="nm">{s.routeShort}</span><span class="sp"></span>
    <NBadge n={s.trips.length} warn={s.trips.length < 20} /></div>
  <svg class="chart" width={w} {height} role="img" aria-label="Slot {s.letter} travel time by departure time"
    onpointermove={move} onpointerleave={() => tip.hide()}>
    {#each yt as v}<line class="gl" x1={L} x2={w - R} y1={y(v)} y2={y(v)} /><text x={L - 5} y={y(v) + 3.5} text-anchor="end">{dur(v)}</text>{/each}
    {#each hourSteps(xdom[0], xdom[1], w - L) as h}<text x={x(h * 60)} y={height - 4} text-anchor="middle">{hh(h)}</text>{/each}
    {#each band as d}<path {d} fill="var(--slot-{s.c.slot + 1})" fill-opacity="0.14" />{/each}
    {#each schedPath as d}<path {d} fill="none" stroke="var(--sched)" stroke-width="1.4" stroke-dasharray="5 4" />{/each}
    {#each s.trips as t}<circle cx={x(t.minute)} cy={y(t.dur)} r="2.6" fill="var(--slot-{s.c.slot + 1})" fill-opacity="0.45" />{/each}
    {#each medRuns as r}
      <path d={pathOf(r)} fill="none" stroke="var(--slot-{s.c.slot + 1})" stroke-width="2.2" stroke-linejoin="round" />
      {#each r as [cx, cy]}<circle {cx} {cy} r="2.6" fill="var(--slot-{s.c.slot + 1})" />{/each}
    {/each}
  </svg>
  {#if !full && s.trips.length}<div class="nb"><Tag kind="hatch">median: 3+ trips per bin</Tag></div>{/if}
</div>

<style>
  .cell { min-width: 0; }
  .h { display: flex; align-items: center; gap: 6px; font-size: 12px; margin-bottom: 2px; }
  .nm { font-weight: 650; }
  .sp { flex: 1; }
  .nb { margin-top: 4px; }
</style>
