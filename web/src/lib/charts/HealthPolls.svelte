<script lang="ts">
  // Poll timeline: one tick per poll (errors red), then vehicles in feed, stop predictions per poll
  // and feed lag sharing the x axis. Gaps (no polls) hatched. x = epoch seconds, labels in local time.
  import type { Health } from "../api";
  import { epochClock, MINUS } from "../format";
  import { tip } from "../tip.svelte";
  import { lin, niceMax } from "./scale";
  import Hatch from "../ui/Hatch.svelte";

  let { series, gaps }: { series: Health["series"]; gaps: [number, number][] } = $props();
  let w = $state(900);
  const id = $props.id();
  const L = 50, R = 10;
  const TICK_H = 44, STRIP_H = 58, LAB = 36, AX = 14;
  const ts = $derived(series.ts);
  const t0 = $derived(Math.min(ts[0] ?? 0, ...gaps.map((g) => g[0])));
  const t1 = $derived(Math.max(ts.at(-1) ?? 1, ...gaps.map((g) => g[1])));
  const x = $derived(lin(t0, t1, L, w - R));
  const span = $derived(t1 - t0);
  const step = $derived(span > 3 * 86400 ? 86400 / 2 : span > 86400 ? 6 * 3600 : span > 12 * 3600 ? 2 * 3600 : 3600);
  const ticks = $derived.by(() => {
    const out: number[] = [];
    for (let t = Math.ceil(t0 / step) * step; t <= t1; t += step) out.push(t);
    return out;
  });

  type S = { key: "veh" | "su" | "lag"; label: string; fmt: (v: number) => string };
  const STRIPS: S[] = [
    { key: "veh", label: "VEHICLES IN FEED", fmt: (v) => String(Math.round(v)) },
    { key: "su", label: "STOP PREDICTIONS PER POLL", fmt: (v) => (v >= 1000 ? `${Math.round(v / 1000)}k` : String(Math.round(v))) },
    { key: "lag", label: "FEED LAG (S)", fmt: (v) => (v < 0 ? MINUS : "") + Math.abs(Math.round(v)) },
  ];
  const top = (k: number) => TICK_H + AX + k * (STRIP_H + LAB) + LAB;
  const height = $derived(top(STRIPS.length) - LAB + 4);

  function path(key: S["key"], y: (v: number) => number): string {
    let d = "", prev: number | null = null;
    const vals = series[key];
    for (let i = 0; i < ts.length; i++) {
      const v = vals[i];
      const broken = prev != null && (ts[i] - prev > 120 || gaps.some(([a, b]) => prev! <= b && ts[i] >= a));
      if (v == null) { prev = null; continue; }
      d += (d === "" || prev == null || broken ? "M" : "L") + x(ts[i]).toFixed(1) + "," + y(v).toFixed(1);
      prev = ts[i];
    }
    return d;
  }
  const strips = $derived(STRIPS.map((s, k) => {
    const vals = series[s.key].filter((v): v is number => v != null);
    const max = niceMax(Math.max(1, ...vals));
    // negative values (feed clock ahead of ours) get their own round tick below zero
    const min = Math.min(0, ...vals);
    const lo = min < 0 ? -niceMax(-min) : 0;
    const y = lin(lo, max, top(k) + STRIP_H, top(k));
    const yt = lo < 0 ? [lo, 0, max] : [0, max / 2, max];
    return { ...s, k, max, lo, y, yt, d: path(s.key, y) };
  }));
  const errIdx = $derived(series.err.map((e, i) => (e ? i : -1)).filter((i) => i >= 0));

  function move(e: PointerEvent) {
    if (!ts.length) return;
    const r = (e.currentTarget as SVGElement).getBoundingClientRect();
    const t = t0 + ((e.clientX - r.left - L) / (w - L - R)) * (t1 - t0);
    const g = gaps.find(([a, b]) => t >= a && t <= b);
    if (g) { tip.show(e, "No polls", [{ k: "From", v: epochClock(g[0], false) }, { k: "To", v: epochClock(g[1], false) },
      { k: "Length", v: `${Math.round((g[1] - g[0]) / 60)} min` }]); return; }
    let i = 0, best = Infinity;
    for (let j = 0; j < ts.length; j++) { const dd = Math.abs(ts[j] - t); if (dd < best) { best = dd; i = j; } }
    tip.show(e, epochClock(ts[i]), [
      { k: "Vehicles", v: series.veh[i] != null ? String(series.veh[i]) : "—" },
      { k: "Stop predictions", v: series.su[i] != null ? String(series.su[i]) : "—" },
      { k: "Feed lag", v: series.lag[i] != null ? `${series.lag[i]} s` : "—" },
      ...(series.err[i] ? [{ k: "Errors", v: String(series.err[i]), color: "var(--late-3)" }] : []),
    ]);
  }
</script>

<div bind:clientWidth={w}>
  <svg class="chart" width={w} {height} role="img" aria-label="Poll timeline" onpointermove={move} onpointerleave={() => tip.hide()}>
    <Hatch {id} />
    <!-- poll ticks -->
    <text x={L - 6} y={34} text-anchor="end">polls</text>
    {#each ts as t, i}
      {#if !series.err[i]}<line x1={x(t)} x2={x(t)} y1={18} y2={40} stroke="var(--axis)" stroke-width="0.6" />{/if}
    {/each}
    {#each errIdx as i}
      <line x1={x(ts[i])} x2={x(ts[i])} y1={18} y2={40} stroke="var(--late-3)" stroke-width="2" />
      <circle cx={x(ts[i])} cy={11} r="3" fill="var(--late-3)" />
    {/each}
    {#each gaps as [a, b]}
      {@const xa = Math.max(L, x(a))}{@const xb = Math.min(w - R, x(b))}
      {#if xb > xa}
        <rect x={xa} y={0} width={xb - xa} height={height - 4} fill="url(#{id})" />
        <text x={(xa + xb) / 2} y={12} text-anchor="middle" style="font-weight: 500">{epochClock(a, false)}–{epochClock(b, false)}</text>
      {/if}
    {/each}
    {#each ticks as t}<text x={x(t)} y={TICK_H + 12} text-anchor="middle">{epochClock(t, false)}</text>{/each}

    {#each strips as s}
      <text x={0} y={top(s.k) - 9} style="font-size: 10.5px; font-weight: 650; letter-spacing: .05em">{s.label}</text>
      {#each s.yt as v}
        <line class={v === 0 && s.lo < 0 ? "ax" : "gl"} x1={L} x2={w - R} y1={s.y(v)} y2={s.y(v)} />
        <text x={L - 6} y={s.y(v) + 3.5} text-anchor="end">{s.fmt(v)}</text>
      {/each}
      <path d={s.d} fill="none" stroke="var(--ink)" stroke-width={s.key === "lag" ? 0.8 : 1.2} stroke-linejoin="round" />
    {/each}
  </svg>
</div>
