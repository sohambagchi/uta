<script lang="ts">
  import type { TripStop } from "../api";
  import { dcol, delay, clock, lineColor } from "../format";
  import { tip } from "../tip.svelte";
  import { lin, d } from "./scale";
  let { stops, color = "var(--ink)", height = 250 }: { stops: TripStop[]; color?: string; height?: number } = $props();
  let w = $state(800);
  const L = 72, R = 24, T = 14, B = 64;
  const vals = $derived(stops.map((s) => s.delay).filter((v): v is number => v != null));
  const lo = $derived(Math.min(-60, ...vals.map((v) => Math.floor(v / 60) * 60)));
  const hi = $derived(Math.max(120, ...vals.map((v) => Math.ceil(v / 60) * 60)));
  const x = $derived(lin(0, Math.max(1, stops.length - 1), L, w - R));
  const y = $derived(lin(lo, hi, height - B, T));
  const pts = $derived(stops.map((s, i) => ({ s, i })).filter((p) => p.s.delay != null));
  const line = $derived(d(pts.map((p) => [x(p.i), y(p.s.delay!)])));
  const areaD = $derived(pts.length > 1 ? line + `L${x(pts.at(-1)!.i).toFixed(1)},${y(0).toFixed(1)}L${x(pts[0].i).toFixed(1)},${y(0).toFixed(1)}Z` : "");
  const ticks = $derived.by(() => { const step = hi - lo > 600 ? 120 : 60; const o: number[] = []; for (let v = lo; v <= hi; v += step) o.push(v); return o; });
  const ext = $derived.by(() => {
    if (!pts.length) return new Set<number>();
    const mx = pts.reduce((a, b) => (b.s.delay! > a.s.delay! ? b : a));
    const mn = pts.reduce((a, b) => (b.s.delay! < a.s.delay! ? b : a));
    return new Set([mx.i, mn.i, pts.at(-1)!.i]);
  });
  const short = (n: string | null) => (n ?? "").replace(/ Station$/, "").slice(0, 16);
  // rotated labels need ~14 px each; thin them on narrow screens (every stop is still in the tooltips)
  const every = $derived(Math.max(1, Math.ceil((stops.length * 14) / Math.max(1, w - 60))));
</script>

<div bind:clientWidth={w}>
  <svg class="chart" width={w} {height} role="img" aria-label="Delay by stop">
    {#each ticks as v}<line class={v === 0 ? "ax" : "gl"} x1={L} x2={w - R} y1={y(v)} y2={y(v)} /><text x={L - 6} y={y(v) + 3.5} text-anchor="end">{delay(v, "0")}</text>{/each}
    {#each stops as s, i}
      {#if i % every === 0 || i === stops.length - 1}
      <text x={x(i)} y={height - B + 12} text-anchor="end" transform="rotate(-40 {x(i)} {height - B + 12})" style={s.delay == null ? "fill: var(--faint)" : ""}>{short(s.name)}</text>
      {/if}
    {/each}
    {#if areaD}<path d={areaD} fill={color} fill-opacity="0.12" />{/if}
    <path d={line} fill="none" stroke={color} stroke-width="2" stroke-linejoin="round" />
    {#each pts as p}
      <circle role="presentation" cx={x(p.i)} cy={y(p.s.delay!)} r="3.4" fill={dcol(p.s.delay)} stroke="var(--panel)" stroke-width="1"
        onmouseenter={(e) => tip.show(e, p.s.name ?? "", [{ k: "Scheduled", v: clock(p.s.sched) }, { k: "Arrived", v: clock(p.s.obs, true) }, { k: "Delay", v: delay(p.s.delay) }])}
        onmouseleave={() => tip.hide()} />
      {#if ext.has(p.i)}<text x={x(p.i)} y={y(p.s.delay!) - 8} text-anchor="middle" style="fill: var(--ink); font-weight: 600; font-size: 10.5px; paint-order: stroke; stroke: var(--panel); stroke-width: 3px">{delay(p.s.delay)}</text>{/if}
    {/each}
  </svg>
</div>
