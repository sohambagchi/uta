<script lang="ts">
  // One shared strip-map station axis: station labels | Marey (time-space) | delay accumulation | dwell.
  import type { RouteDay } from "../api";
  import { tip } from "../tip.svelte";
  import { router } from "../router.svelte";
  import { clock, delay, dur } from "../format";
  import { lin, hourTicks, hh } from "./scale";
  import Hatch from "../ui/Hatch.svelte";

  let { r, color }: { r: RouteDay; color: string } = $props();
  const id = $props.id();
  let w = $state(1200);

  const RH = 22, TOP = 30, BOT = 24, GAP = 18;
  // phones: the station axis keeps only the delay column (the Marey needs width)
  const compact = $derived(w < 700);
  const LW = $derived(compact ? Math.min(170, Math.floor(w * 0.46)) : 190);
  const AW = $derived(compact ? Math.max(140, w - LW - 4) : 240);
  const DW = 140;
  const ns = $derived(r.stations.length);
  const H = $derived(TOP + ns * RH + BOT);
  const ys = (i: number) => TOP + i * RH + RH / 2;
  const mw = $derived(Math.max(300, w - LW - AW - DW - 2 * GAP));
  const noRt = $derived(new Set(r.marey.no_rt ?? []));

  // time domain: every timetable and observed point on the Marey day
  // time domain: the observed part of the day (whole timetable when nothing was observed)
  const tdom = $derived.by(() => {
    let a = Infinity, b = -Infinity;
    for (const t of r.marey.trips) for (const o of t.obs) { a = Math.min(a, o[1]); b = Math.max(b, o[1]); }
    if (!isFinite(a)) {
      for (const t of [...r.marey.trips, ...r.marey.sched_only]) for (const [, v] of t.sched) { a = Math.min(a, v); b = Math.max(b, v); }
    }
    if (!isFinite(a)) return [5 * 3600, 24 * 3600];
    // the scope's hours narrow the window
    const [h0, h1] = r.scope.h;
    a = Math.max(a, h0 * 3600); b = Math.min(b, h1 * 3600);
    if (b <= a) b = a + 3600;
    return [Math.floor(a / 1800) * 1800 - 900, Math.ceil(b / 1800) * 1800 + 900];
  });
  const x = $derived(lin(tdom[0], tdom[1], 6, mw - 6));
  const step = $derived((tdom[1] - tdom[0]) / 3600 > 14 ? 2 : 1);
  const line = (pts: [number, number][]) => (pts.length > 1 ? "M" + pts.map(([a, b]) => `${a.toFixed(1)},${b.toFixed(1)}`).join("L") : "");
  const schedPaths = $derived([
    ...r.marey.sched_only.map((t) => line(t.sched.map(([i, s]) => [x(s), ys(i)]))),
    ...r.marey.trips.map((t) => line(t.sched.map(([i, s]) => [x(s), ys(i)]))),
  ]);
  const obsTrips = $derived(r.marey.trips.filter((t) => t.obs.length > 1).map((t) => ({ t, d: line(t.obs.map(([i, a]) => [x(a), ys(i)])) })));
  let hot = $state<string | null>(null);

  function hover(e: MouseEvent, t: RouteDay["marey"]["trips"][number]) {
    hot = t.trip_id;
    const ds = t.obs.map((o) => o[2]);
    const last = t.obs.at(-1);
    tip.show(e, `Trip ${t.trip_id}${t.vehicle ? " · " + t.vehicle : ""}`, [
      { k: "First observed", v: clock(t.obs[0][1]) },
      { k: "Last observed", v: last ? `${clock(last[1])} · ${r.stations[last[0]]?.name.replace(/ Station$/, "") ?? ""}` : "—" },
      { k: "Delay at end", v: delay(last?.[2]) },
      { k: "Worst delay", v: delay(Math.max(...ds)) },
      { k: "Stops observed", v: String(t.obs.length) },
    ]);
  }

  // delay accumulation
  const ok = $derived(r.acc.filter((a) => a.n > 0 && a.median != null));
  // axis from the bulk of the band; a lone extreme station is clipped and labelled instead
  const q9 = (xs: number[]) => { const t = [...xs].sort((p, q) => p - q); return t[Math.floor((t.length - 1) * 0.9)] ?? 0; };
  const dmin = $derived(Math.max(-600, Math.min(-120, ...ok.map((a) => a.p10 ?? 0))));
  const dmax = $derived(Math.min(1200, Math.max(300, q9(ok.map((a) => a.p90 ?? 0)))));
  const dx = $derived(lin(dmin, dmax, 10, AW - 10));
  const cdx = (v: number) => dx(Math.max(dmin, Math.min(dmax, v)));
  const dticks = $derived.by(() => {
    const out: number[] = [];
    for (const v of [-300, -120, -60, 0, 60, 180, 300, 600, 900, 1200]) {
      if (v < dmin || v > dmax) continue;
      if (out.length && dx(v) - dx(out.at(-1)!) < 34) continue;
      out.push(v);
    }
    return out;
  });
  const band = $derived(ok.length > 1 ? "M" + ok.map((a) => `${cdx(a.p90!).toFixed(1)},${ys(a.i).toFixed(1)}`).join("L")
    + "L" + [...ok].reverse().map((a) => `${cdx(a.p10!).toFixed(1)},${ys(a.i).toFixed(1)}`).join("L") + "Z" : "");
  const medPath = $derived(line(ok.map((a) => [cdx(a.median!), ys(a.i)])));
  const worst = $derived(ok.length ? ok.reduce((m, a) => (a.median! > m.median! ? a : m), ok[0]) : null);
  const clamped = $derived(ok.filter((a) => a.median! > dmax || a.median! < dmin));

  // dwell
  const wmax = $derived(Math.max(60, ...r.acc.map((a) => Math.max(a.dwell ?? 0, a.sdwell ?? 0))));
  const wx = $derived(lin(0, Math.ceil(wmax / 60) * 60, 8, DW - 18));
  const wticks = $derived(Array.from({ length: Math.ceil(wmax / 60) + 1 }, (_, k) => k * 60));

  const short = (s: string) => s.replace(/ Station$/, "");
  /** Truncate a label to fit `px` at 11.5 px Archivo (capitals are wider). */
  function fit(s: string, px: number): string {
    const wid = (t: string) => [...t].reduce((a, c) => a + (c >= "A" && c <= "Z" ? 7.6 : c === " " ? 3 : 6), 0);
    if (wid(s) <= px) return s;
    let t = s;
    while (t.length > 3 && wid(t + "…") > px) t = t.slice(0, -1);
    return t.trimEnd() + "…";
  }
</script>

<div bind:clientWidth={w} class="wrap">
  {#if compact}
    <div class="heads" style:grid-template-columns="{LW}px {AW}px"><span></span><span>DELAY AT STOP</span></div>
  {:else}
    <div class="heads" style:grid-template-columns="{LW}px {mw}px {GAP}px {AW}px {GAP}px {DW}px">
      <span></span><span>TIME-SPACE · {r.marey.date}</span><span></span><span>DELAY AT STOP · MEDIAN, P10–P90</span><span></span><span>DWELL · VS TIMETABLE</span>
    </div>
  {/if}
  <div class="cols">
    <!-- strip map -->
    <svg class="chart" width={LW} height={H} role="img" aria-label="Stations">
      <line x1={LW - 14} x2={LW - 14} y1={ys(0)} y2={ys(ns - 1)} stroke={color} stroke-width="5" />
      {#each r.stations as s, i}
        <circle cx={LW - 14} cy={ys(i)} r={i === 0 || i === ns - 1 ? 4.2 : 3.2} fill="var(--panel)" stroke={color} stroke-width="2"
          stroke-dasharray={noRt.has(i) ? "2 2" : undefined} />
        <a href={router.href(`stations/${s.station_id}`)}>
          <text x={LW - 26} y={ys(i) + 4} text-anchor="end" style="font-size: 11.5px; fill: {noRt.has(i) ? 'var(--faint)' : 'var(--ink)'}; font-weight: {i === 0 || i === ns - 1 ? 600 : 450}">{fit(short(s.name), LW - 30)}</text>
        </a>
      {/each}
    </svg>

    {#if !compact}
    <!-- Marey -->
    <svg class="chart" width={mw} height={H} role="img" aria-label="Time-space diagram of every trip">
      <Hatch {id} />
      <defs><clipPath id="{id}c"><rect x="0" y="0" width={mw} height={H} /></clipPath></defs>
      {#each r.stations as _, i}
        {#if noRt.has(i)}<rect x="0" y={ys(i) - RH / 2} width={mw} height={RH} fill="url(#{id})" opacity="0.55" />{/if}
        <line class="gl" x1="0" x2={mw} y1={ys(i)} y2={ys(i)} />
      {/each}
      {#each hourTicks(tdom[0], tdom[1], step) as t}
        <line class="gl" x1={x(t)} x2={x(t)} y1={TOP - 4} y2={H - BOT} />
        <text x={x(t)} y={TOP - 10} text-anchor="middle">{hh(t)}</text>
        <text x={x(t)} y={H - 8} text-anchor="middle">{hh(t)}</text>
      {/each}
      {#each r.marey.gaps as [a, b]}
        {@const xa = Math.max(0, x(a))}{@const xb = Math.min(mw, x(b))}
        {#if xb > xa}<rect x={xa} y={TOP} width={xb - xa} height={ns * RH} fill="url(#{id})" />
          {#if xb - xa > 70}<text x={(xa + xb) / 2} y={TOP + 12} text-anchor="middle" style="font-weight: 500">collector offline</text>
            <text x={(xa + xb) / 2} y={TOP + 24} text-anchor="middle">{clock(a)}–{clock(b)}</text>{/if}{/if}
      {/each}
      <g clip-path="url(#{id}c)">
      {#each schedPaths as p}{#if p}<path d={p} fill="none" stroke="var(--sched)" stroke-width="1" stroke-dasharray="3 3" opacity="0.8" />{/if}{/each}
      {#each obsTrips as { t, d } (t.trip_id)}
        <path {d} fill="none" stroke={color} stroke-width={hot === t.trip_id ? 3 : 1.7} stroke-linejoin="round" />
        <!-- wide invisible hit area -->
        <path {d} fill="none" stroke="transparent" stroke-width="9" style="cursor: pointer" role="link" tabindex="-1"
          onmouseenter={(e) => hover(e, t)} onmousemove={(e) => hover(e, t)} onmouseleave={() => { hot = null; tip.hide(); }}
          onclick={() => router.go(`trip/${t.trip_id}`, { date: r.marey.date }, false)} onkeydown={() => {}} />
      {/each}
      </g>
    </svg>
    <div style:width="{GAP}px"></div>
    {/if}

    <!-- delay accumulation -->
    <svg class="chart" width={AW} height={H} role="img" aria-label="Delay by station">
      <Hatch id="{id}a" />
      {#each dticks as v}
        <line class={v === 0 ? "ax" : "gl"} x1={dx(v)} x2={dx(v)} y1={TOP} y2={H - BOT} />
        <text x={dx(v)} y={TOP - 10} text-anchor="middle">{delay(v, "0")}</text>
      {/each}
      {#each r.acc as a}
        {#if noRt.has(a.i)}
          <rect x="0" y={ys(a.i) - RH / 2} width={AW} height={RH} fill="url(#{id}a)" opacity="0.55" />
          <text x={AW / 2} y={ys(a.i) + 4} text-anchor="middle">no realtime</text>
        {/if}
      {/each}
      {#if band}<path d={band} fill={color} fill-opacity="0.14" />{/if}
      <path d={medPath} fill="none" stroke={color} stroke-width="2" stroke-linejoin="round" />
      {#each ok as a}
        <circle role="presentation" cx={cdx(a.median!)} cy={ys(a.i)} r="3" fill={color}
          onmouseenter={(e) => tip.show(e, short(r.stations[a.i].name), [
            { k: "Median delay", v: delay(a.median) }, { k: "p10 – p90", v: `${delay(a.p10)} – ${delay(a.p90)}` }, { k: "Visits", v: String(a.n) }])}
          onmouseleave={() => tip.hide()} />
      {/each}
      {#each clamped as a}
        {@const hi = a.median! > dmax}
        {@const ex = hi ? AW - 10 : 10}
        <path d={hi ? `M${ex - 1},${ys(a.i) - 5}L${ex + 6},${ys(a.i)}L${ex - 1},${ys(a.i) + 5}Z` : `M${ex + 1},${ys(a.i) - 5}L${ex - 6},${ys(a.i)}L${ex + 1},${ys(a.i) + 5}Z`} fill={color} />
      {/each}
      {#if worst && worst.median! > 60}
        <text x={worst.median! > dmax ? AW - 14 : Math.min(cdx(worst.median!) + 6, AW - 40)} y={ys(worst.i) + (worst.median! > dmax ? -7 : 4)}
          text-anchor={worst.median! > dmax ? "end" : "start"}
          style="fill: var(--ink-2); font-size: 10.5px; font-weight: 600; paint-order: stroke; stroke: var(--panel); stroke-width: 4px">{delay(worst.median)}</text>
      {/if}
    </svg>
    {#if !compact}
    <div style:width="{GAP}px"></div>

    <!-- dwell -->
    <svg class="chart" width={DW} height={H} role="img" aria-label="Dwell by station">
      {#each wticks as v}
        <line class="gl" x1={wx(v)} x2={wx(v)} y1={TOP} y2={H - BOT} />
        <text x={wx(v)} y={TOP - 10} text-anchor="middle">{dur(v)}</text>
      {/each}
      {#each r.acc as a}
        {#if a.dwell != null && a.n > 0}
          <line x1={wx(0)} x2={wx(a.dwell)} y1={ys(a.i)} y2={ys(a.i)} stroke="var(--ink-2)" stroke-width="5" opacity="0.3" />
          <circle role="presentation" cx={wx(a.dwell)} cy={ys(a.i)} r="2.6" fill="var(--ink)"
            onmouseenter={(e) => tip.show(e, short(r.stations[a.i].name), [{ k: "Median dwell", v: dur(a.dwell) }, { k: "Timetable", v: dur(a.sdwell) }])}
            onmouseleave={() => tip.hide()} />
        {/if}
        {#if a.sdwell != null}<line x1={wx(a.sdwell)} x2={wx(a.sdwell)} y1={ys(a.i) - 6} y2={ys(a.i) + 6} stroke="var(--sched)" stroke-width="1.5" />{/if}
      {/each}
    </svg>
    {/if}
  </div>
</div>

<style>
  .wrap { overflow-x: auto; }
  .heads { display: grid; font-size: 11px; font-weight: 650; color: var(--muted); letter-spacing: .05em; font-stretch: 90%; }
  .cols { display: flex; }
  .cols > :global(*) { flex-shrink: 0; }
  a text:hover { text-decoration: underline; }
</style>
