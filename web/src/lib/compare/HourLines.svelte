<script lang="ts">
  // A per-bin statistic over the day, one line per slot, slot bullets dodged in the right margin.
  import type { Series } from "../series";
  import { timeBins, type BinPoint } from "../chartdata";
  import { tip } from "../tip.svelte";
  import { fmtClock } from "../format";
  import { lin } from "../charts/scale";
  import { hourSteps, hh, runs, pathOf, dodge, minuteTicks } from "./util";

  let { series, bin, field, xdom, fmt, height = 200 }: {
    series: Series[]; bin: number; field: "spread" | "vsSched"; xdom: [number, number];
    fmt: (s: number) => string; height?: number;
  } = $props();
  let w = $state(460);
  const L = 44, R = 30, T = 10, B = 20;
  // chartdata gives minutes; charts work in seconds
  const lines = $derived(series.map((s) => ({ s, pts: timeBins(s, bin).map((p: BinPoint) => ({ m: p.x * 60, v: Number.isFinite(p[field]) ? p[field] * 60 : NaN, n: p.n })) })));
  const vals = $derived(lines.flatMap((l) => l.pts.map((p) => p.v)).filter(Number.isFinite));
  // always includes zero: spread starts at 0, and "vs timetable" is read against 0
  const ydom = $derived.by((): [number, number] => {
    if (!vals.length) return [0, 60];
    const lo = Math.min(0, ...vals), hi = Math.max(0, ...vals, lo + 60);
    return [Math.floor(lo / 30) * 30, Math.ceil(hi / 30) * 30];
  });
  const x = $derived(lin(xdom[0] * 60, xdom[1] * 60, L, w - R));
  const y = $derived(lin(ydom[0], ydom[1], height - B, T));
  const drawn = $derived(lines.map((l) => ({ ...l, runs: runs(l.pts.map((p) => [x(p.m), Number.isFinite(p.v) ? y(p.v) : null])) })));
  const labels = $derived(dodge(drawn.filter((l) => l.runs.length).map((l) => ({ l, y: l.runs.at(-1)!.at(-1)![1] })), 18, T + 8, height - B - 8));
  const has = $derived(vals.length > 0);

  function move(e: PointerEvent) {
    const r = (e.currentTarget as SVGElement).getBoundingClientRect();
    const m = xdom[0] * 60 + ((e.clientX - r.left - L) / (w - L - R)) * (xdom[1] - xdom[0]) * 60;
    const k = Math.floor(m / bin);
    tip.show(e, `${fmtClock(k * bin)}–${fmtClock(k * bin + bin)}`, lines.map(({ s, pts }) => {
      const p = pts.find((q) => Math.floor(q.m / bin) === k);
      return { k: `${s.letter} · ${s.routeShort}`, v: p && Number.isFinite(p.v) ? `${fmt(p.v)} · ${p.n}` : "—", color: s.color };
    }));
  }
</script>

<div bind:clientWidth={w}>
  {#if has}
    <svg class="chart" width={w} {height} role="img" aria-label="Statistic by time of day" onpointermove={move} onpointerleave={() => tip.hide()}>
      {#each minuteTicks(ydom[0], ydom[1], 4) as v}<line class={v === 0 ? "ax" : "gl"} x1={L} x2={w - R} y1={y(v)} y2={y(v)} /><text x={L - 5} y={y(v) + 3.5} text-anchor="end">{fmt(v)}</text>{/each}
      {#each hourSteps(xdom[0], xdom[1], w - L - R) as h}<text x={x(h * 60)} y={height - 4} text-anchor="middle">{hh(h)}</text>{/each}
      {#each drawn as { s, runs: rs } (s.c.id)}
        {#each rs as r}
          <path d={pathOf(r)} fill="none" stroke={s.color} stroke-width="2" stroke-linejoin="round" />
          {#each r as [cx, cy]}<circle {cx} {cy} r="2.6" fill={s.color} />{/each}
        {/each}
      {/each}
      {#each labels as { l, y: y0, ly } (l.s.c.id)}
        {@const lx = l.runs.at(-1)!.at(-1)![0]}
        <line x1={lx} x2={w - R + 6} y1={y0} y2={ly} stroke={l.s.color} stroke-width="1" opacity="0.4" />
        <circle cx={w - R + 14} cy={ly} r="8" fill={l.s.color} />
        <text x={w - R + 14} y={ly + 3.8} text-anchor="middle" style="fill: #fff; font-size: 10.5px; font-weight: 750">{l.s.letter}</text>
      {/each}
    </svg>
  {/if}
</div>
