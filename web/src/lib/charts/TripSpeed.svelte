<script lang="ts">
  import type { TripStop } from "../api";
  import { clock } from "../format";
  import { tip } from "../tip.svelte";
  import { lin, d } from "./scale";
  let { gps, stops, color = "var(--ink)", height = 150 }: { gps: [number, number, number, number | null][]; stops: TripStop[]; color?: string; height?: number } = $props();
  let w = $state(800);
  const L = 40, R = 12, T = 10, B = 20;
  const t0 = $derived(gps[0]?.[0] ?? 0), t1 = $derived(gps.at(-1)?.[0] ?? 1);
  const vmax = $derived(Math.max(20, ...gps.map((p) => p[3] ?? 0)));
  const x = $derived(lin(t0, t1, L, w - R));
  const y = $derived(lin(0, vmax, height - B, T));
  const ticks = $derived.by(() => { const o: number[] = []; for (let t = Math.ceil(t0 / 900) * 900; t <= t1; t += 900) o.push(t); return o; });
  const line = $derived(d(gps.map((p) => [x(p[0]), y(p[3] ?? 0)])));
  function move(e: PointerEvent) {
    const r = (e.currentTarget as SVGElement).getBoundingClientRect();
    const t = t0 + ((e.clientX - r.left - L) / (w - L - R)) * (t1 - t0);
    const p = gps.reduce((a, b) => (Math.abs(b[0] - t) < Math.abs(a[0] - t) ? b : a), gps[0]);
    if (p) tip.show(e, clock(p[0], true), [{ k: "Speed", v: p[3] == null ? "—" : `${p[3].toFixed(1)} m/s` }]);
  }
</script>

<div bind:clientWidth={w}>
  <svg class="chart" width={w} {height} role="img" aria-label="Speed over time" onpointermove={move} onpointerleave={() => tip.hide()}>
    {#each [0, 10, 20] as v}<line class="gl" x1={L} x2={w - R} y1={y(v)} y2={y(v)} /><text x={L - 6} y={y(v) + 3.5} text-anchor="end">{v}</text>{/each}
    <text x="2" y="9">m/s</text>
    {#each stops as s}{#if s.obs != null && s.obs >= t0 && s.obs <= t1}<line x1={x(s.obs)} x2={x(s.obs)} y1={T} y2={height - B} stroke="var(--axis)" stroke-dasharray="2 2" />{/if}{/each}
    {#each ticks as t}<text x={x(t)} y={height - 4} text-anchor="middle">{clock(t)}</text>{/each}
    {#if gps.length > 1}
      <path d={line + `L${x(t1).toFixed(1)},${y(0).toFixed(1)}L${x(t0).toFixed(1)},${y(0).toFixed(1)}Z`} fill={color} fill-opacity="0.15" />
      <path d={line} fill="none" stroke={color} stroke-width="1.6" stroke-linejoin="round" />
    {/if}
  </svg>
</div>
