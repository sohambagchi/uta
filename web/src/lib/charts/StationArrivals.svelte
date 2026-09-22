<script lang="ts">
  // Observed arrivals per service-day hour, stacked by mode; collector gaps hatched.
  import type { Gap, Mode } from "../api";
  import { MODE_LABEL } from "../format";
  import { tip } from "../tip.svelte";
  import { lin, niceMax, niceTicks } from "./scale";
  import Hatch from "../ui/Hatch.svelte";

  let { hours, gaps, colors, height = 170 }: {
    hours: ({ h: number } & Partial<Record<Mode, number>>)[]; gaps: Gap[]; colors: Record<Mode, string>; height?: number;
  } = $props();
  const ORDER: Mode[] = ["lrt", "streetcar", "rail", "bus"];
  let w = $state(520);
  const id = $props.id();
  const L = 30, R = 6, T = 10, B = 18;
  const h0 = $derived(Math.min(...hours.map((x) => x.h), ...gaps.map(([a]) => Math.floor(a / 3600))));
  const h1 = $derived(Math.max(...hours.map((x) => x.h + 1), ...gaps.map(([, b]) => Math.ceil(b / 3600))));
  const total = (x: Partial<Record<Mode, number>>) => ORDER.reduce((a, m) => a + (x[m] ?? 0), 0);
  const yt = $derived(niceTicks(Math.max(4, ...hours.map(total))));
  const ymax = $derived(yt.at(-1)!);
  const x = $derived(lin(h0, h1, L, w - R));
  const y = $derived(lin(0, ymax, height - B, T));
  const bw = $derived(Math.max(2, x(h0 + 1) - x(h0) - 6));
</script>

<div bind:clientWidth={w}>
  {#if hours.length}
    <svg class="chart" width={w} {height} role="img" aria-label="Arrivals by hour">
      <Hatch {id} />
      {#each yt as v}<line class="gl" x1={L} x2={w - R} y1={y(v)} y2={y(v)} /><text x={L - 6} y={y(v) + 3.5} text-anchor="end">{v}</text>{/each}
      {#each gaps as [a, b]}
        {@const xa = Math.max(L, x(a / 3600))}{@const xb = Math.min(w - R, x(b / 3600))}
        {#if xb > xa}<rect x={xa} y={T} width={xb - xa} height={height - B - T} fill="url(#{id})" />{/if}
      {/each}
      {#each hours as hr}
        {@const stack = ORDER.filter((m) => hr[m])}
        {#each stack as m, k}
          {@const below = stack.slice(0, k).reduce((a, mm) => a + (hr[mm] ?? 0), 0)}
          <rect role="presentation" x={x(hr.h) + 3} width={bw} y={y(below + (hr[m] ?? 0))} height={y(below) - y(below + (hr[m] ?? 0))} fill={colors[m]}
            onmouseenter={(e) => tip.show(e, `${String(hr.h % 24).padStart(2, "0")}:00`, ORDER.filter((mm) => hr[mm]).map((mm) => ({ k: MODE_LABEL[mm], v: String(hr[mm]), color: colors[mm] })))}
            onmouseleave={() => tip.hide()} />
        {/each}
      {/each}
      {#each Array.from({ length: h1 - h0 }, (_, k) => h0 + k) as h}
        <text x={x(h + 0.5)} y={height - 4} text-anchor="middle">{String(h % 24).padStart(2, "0")}</text>
      {/each}
    </svg>
  {:else}
    <div class="none">—</div>
  {/if}
</div>

<style>
  .none { color: var(--faint); padding: 30px 0; text-align: center; }
</style>
