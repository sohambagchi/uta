<script lang="ts">
  // Median by weekday per slot (dot, p25–p75 line). Until each weekday has 3 service days of
  // history it shows progress towards that instead of a chart.
  import type { Series } from "../series";
  import { dowStats } from "../chartdata";
  import { tip } from "../tip.svelte";
  import { dur } from "../format";
  import { lin } from "../charts/scale";
  import Tag from "../ui/Tag.svelte";
  import { durDomain, minuteTicks } from "./util";

  let { series }: { series: Series[] } = $props();
  const NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
  const NEED = 3;
  // service days of history per weekday, across every slot
  const days = $derived.by(() => {
    const per = NAMES.map(() => new Set<string>());
    for (const s of series) for (const t of s.trips) per[t.dow].add(t.date);
    return per.map((d) => d.size);
  });
  const ready = $derived(days.some((n) => n >= NEED));
  const stats = $derived(series.map((s) => ({ s, pts: dowStats(s) })));
  const shownDays = $derived(NAMES.filter((d, i) => days[i] >= NEED && stats.some(({ pts }) => pts.some((p) => p.dow === d))));
  let w = $state(460);
  const L = 40, R = 10, T = 6, B = 20;
  const rowH = $derived(12 * Math.max(1, series.length) + 12);
  const height = $derived(T + shownDays.length * rowH + B);
  const xdom = $derived(durDomain(stats.flatMap(({ pts }) => pts.flatMap((p) => [p.p25 * 60, p.p75 * 60]))));
  const x = $derived(lin(xdom[0], xdom[1], L, w - R));
</script>

{#if !ready}
  <div class="meter">
    <div class="days">
      {#each NAMES as d, i}
        <div class="d"><div class="dn">{d}</div>
          <div class="bars">{#each Array(NEED) as _, k}<span class:on={k < days[i]}></span>{/each}</div>
          <div class="mono small muted">{Math.min(days[i], NEED)}/{NEED}</div></div>
      {/each}
    </div>
    <Tag>unlocks at {NEED} of a weekday</Tag>
  </div>
{:else}
  <div bind:clientWidth={w}>
    <svg class="chart" width={w} {height} role="img" aria-label="Median travel time by weekday">
      {#each minuteTicks(xdom[0], xdom[1], Math.max(3, Math.floor(w / 80))) as v}
        <line class="gl" x1={x(v)} x2={x(v)} y1={T} y2={height - B} /><text x={x(v)} y={height - 4} text-anchor="middle">{dur(v)}</text>
      {/each}
      {#each shownDays as d, r}
        <text x="0" y={T + r * rowH + rowH / 2 + 4} style="fill: var(--ink); font-weight: 600; font-size: 11px">{d}</text>
        {#each stats as { s, pts }, k}
          {@const p = pts.find((q) => q.dow === d)}
          {#if p}
            {@const yy = T + r * rowH + 8 + k * 12}
            <line x1={x(p.p25 * 60)} x2={x(p.p75 * 60)} y1={yy} y2={yy} stroke={s.color} stroke-width="3" opacity="0.5" />
            <circle role="presentation" cx={x(p.median * 60)} cy={yy} r="4.5" fill={s.color} stroke="var(--panel)" stroke-width="1.5"
              onmouseenter={(e) => tip.show(e, `${d} · ${s.letter} ${s.routeShort}`, [{ k: "Median", v: dur(p.median * 60) },
                { k: "p25–p75", v: `${dur(p.p25 * 60)}–${dur(p.p75 * 60)}` }, { k: "Trips", v: String(p.n) }])}
              onmouseleave={() => tip.hide()} />
          {/if}
        {/each}
      {/each}
    </svg>
  </div>
{/if}

<style>
  .meter { display: flex; align-items: center; gap: 18px; flex-wrap: wrap; }
  .days { display: grid; grid-template-columns: repeat(7, minmax(44px, 1fr)); gap: 6px; flex: 1 1 380px; max-width: 560px; }
  .dn { font-size: 11px; font-weight: 600; color: var(--ink-2); }
  .bars { display: flex; gap: 2px; margin: 3px 0; }
  .bars span { flex: 1 1 0; height: 10px; border-radius: 1px; background: var(--sunk); }
  .bars span.on { background: var(--ink); }
</style>
