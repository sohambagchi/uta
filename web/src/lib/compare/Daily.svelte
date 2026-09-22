<script lang="ts">
  // Median travel time per service day, one line per slot.
  import type { Series } from "../series";
  import { daily } from "../chartdata";
  import { tip } from "../tip.svelte";
  import { dur } from "../format";
  import { lin } from "../charts/scale";
  import Tag from "../ui/Tag.svelte";
  import { durDomain, minuteTicks, pathOf, dodge } from "./util";

  let { series, height = 190 }: { series: Series[]; height?: number } = $props();
  let w = $state(460);
  const L = 40, R = 30, T = 10, B = 20;
  const lines = $derived(series.map((s) => ({ s, pts: daily(s).map((p) => ({ date: p.date.toISOString().slice(0, 10), v: p.median * 60, n: p.n })) })));
  const dates = $derived([...new Set(lines.flatMap((l) => l.pts.map((p) => p.date)))].sort());
  const x = $derived(lin(0, Math.max(1, dates.length - 1), L, w - R));
  const ydom = $derived(durDomain(lines.flatMap((l) => l.pts.map((p) => p.v))));
  const y = $derived(lin(ydom[0], ydom[1], height - B, T));
  const drawn = $derived(lines.filter((l) => l.pts.length).map((l) => ({ ...l, xy: l.pts.map((p) => [x(dates.indexOf(p.date)), y(p.v)] as [number, number]) })));
  const labels = $derived(dodge(drawn.map((l) => ({ l, y: l.xy.at(-1)![1] })), 18, T + 8, height - B - 8));
  const every = $derived(Math.max(1, Math.ceil(dates.length / Math.max(1, Math.floor((w - L - R) / 70)))));
  const label = (d: string) => new Date(d + "T12:00").toLocaleDateString("en-GB", { day: "numeric", month: "short" });

  function move(e: PointerEvent) {
    const r = (e.currentTarget as SVGElement).getBoundingClientRect();
    const i = Math.round(((e.clientX - r.left - L) / (w - L - R)) * Math.max(1, dates.length - 1));
    const d = dates[Math.max(0, Math.min(dates.length - 1, i))];
    tip.show(e, label(d), lines.map(({ s, pts }) => {
      const p = pts.find((q) => q.date === d);
      return { k: `${s.letter} · ${s.routeShort}`, v: p ? `${dur(p.v)} · ${p.n}` : "—", color: s.color };
    }));
  }
</script>

{#if dates.length < 2}
  <Tag kind="hatch">needs 2+ days of history</Tag>
{:else}
  <div bind:clientWidth={w}>
    <svg class="chart" width={w} {height} role="img" aria-label="Median travel time per day" onpointermove={move} onpointerleave={() => tip.hide()}>
      {#each minuteTicks(ydom[0], ydom[1], 4) as v}<line class="gl" x1={L} x2={w - R} y1={y(v)} y2={y(v)} /><text x={L - 5} y={y(v) + 3.5} text-anchor="end">{dur(v)}</text>{/each}
      {#each dates as d, i}{#if i % every === 0}<text x={x(i)} y={height - 4} text-anchor="middle">{label(d)}</text>{/if}{/each}
      {#each drawn as { s, xy } (s.c.id)}
        <path d={pathOf(xy)} fill="none" stroke={s.color} stroke-width="2" stroke-linejoin="round" />
        {#if dates.length <= 31}{#each xy as [cx, cy]}<circle {cx} {cy} r="2.6" fill={s.color} />{/each}{/if}
      {/each}
      {#each labels as { l, y: y0, ly } (l.s.c.id)}
        <line x1={l.xy.at(-1)![0]} x2={w - R + 6} y1={y0} y2={ly} stroke={l.s.color} stroke-width="1" opacity="0.4" />
        <circle cx={w - R + 14} cy={ly} r="8" fill={l.s.color} />
        <text x={w - R + 14} y={ly + 3.8} text-anchor="middle" style="fill: #fff; font-size: 10.5px; font-weight: 750">{l.s.letter}</text>
      {/each}
    </svg>
  </div>
{/if}
