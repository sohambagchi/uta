<script lang="ts">
  // Share of trips taking at most x, one step line per slot; slot bullets in the right margin, dodged.
  import type { Series } from "../series";
  import { tip } from "../tip.svelte";
  import { dur, pct } from "../format";
  import { lin } from "../charts/scale";
  import { durDomain, minuteTicks, dodge, pathOf } from "./util";

  let { series, height = 230 }: { series: Series[]; height?: number } = $props();
  let w = $state(460);
  const L = 38, R = 30, T = 10, B = 20;
  const shown = $derived(series.filter((s) => s.trips.length >= 2).map((s) => ({ s, d: s.trips.map((t) => t.dur).sort((a, b) => a - b) })));
  const xdom = $derived(durDomain(shown.flatMap(({ d }) => [d[0], d[d.length - 1]])));
  const x = $derived(lin(xdom[0], xdom[1], L, w - R));
  const y = $derived(lin(0, 1, height - B, T));
  const paths = $derived(shown.map(({ s, d }) => {
    const pts: [number, number][] = [[x(d[0]), y(0)]];
    d.forEach((v, i) => { pts.push([x(v), y(i / d.length)], [x(v), y((i + 1) / d.length)]); });
    pts.push([w - R, y(1)]);
    return { s, d, path: pathOf(pts) };
  }));
  const scheds = $derived([...new Set(series.map((s) => s.schedMedian).filter((v): v is number => v != null))]);
  // bullets where each curve crosses 50%, dodged vertically in the right margin
  const labels = $derived(dodge(paths.map(({ s }) => ({ s, y: y(0.5) })), 18, T + 8, height - B - 8));
  const labelY = $derived(new Map(labels.map((l) => [l.s.c.id, l.ly])));
  const med = (d: number[]) => d[Math.floor((d.length - 1) / 2)];

  function share(d: number[], v: number) { let k = 0; while (k < d.length && d[k] <= v) k++; return k / d.length; }
  function move(e: PointerEvent) {
    const r = (e.currentTarget as SVGElement).getBoundingClientRect();
    const v = xdom[0] + ((e.clientX - r.left - L) / (w - L - R)) * (xdom[1] - xdom[0]);
    if (v < xdom[0] || v > xdom[1]) { tip.hide(); return; }
    tip.show(e, `≤ ${dur(v)}`, shown.map(({ s, d }) => ({ k: `${s.letter} · ${s.routeShort}`, v: pct(share(d, v), 0), color: s.color })));
  }
</script>

<div bind:clientWidth={w}>
  <svg class="chart" width={w} {height} role="img" aria-label="Cumulative share of trips by travel time" onpointermove={move} onpointerleave={() => tip.hide()}>
    {#each [0, 0.25, 0.5, 0.75, 1] as v}<line class={v === 0.5 ? "ax" : "gl"} x1={L} x2={w - R} y1={y(v)} y2={y(v)} /><text x={L - 5} y={y(v) + 3.5} text-anchor="end">{v * 100}%</text>{/each}
    {#each minuteTicks(xdom[0], xdom[1], Math.max(3, Math.floor(w / 80))) as v}<text x={x(v)} y={height - 4} text-anchor="middle">{dur(v)}</text>{/each}
    {#each scheds as v}<line x1={x(v)} x2={x(v)} y1={T} y2={height - B} stroke="var(--sched)" stroke-width="1.4" stroke-dasharray="5 4" />{/each}
    {#each paths as { s, d, path } (s.c.id)}
      <path d={path} fill="none" stroke={s.color} stroke-width="2" />
      <line x1={x(med(d))} x2={w - R + 6} y1={y(0.5)} y2={labelY.get(s.c.id)} stroke={s.color} stroke-width="1" opacity="0.5" />
      <circle cx={w - R + 14} cy={labelY.get(s.c.id)} r="8" fill={s.color} />
      <text x={w - R + 14} y={(labelY.get(s.c.id) ?? 0) + 3.8} text-anchor="middle" style="fill: #fff; font-size: 10.5px; font-weight: 750">{s.letter}</text>
    {/each}
  </svg>
</div>
