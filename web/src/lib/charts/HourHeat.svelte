<script lang="ts">
  import { dcol, dink, delay, pct, MINUS, MODE_LABEL } from "../format";
  import { tip } from "../tip.svelte";
  import Hatch from "../ui/Hatch.svelte";
  type Cell = { mode: string; h: number; n: number; median: number | null; otp: number | null };
  let { cells, hours, modes }: { cells: Cell[]; hours: number[]; modes: string[] } = $props();
  const id = $props.id();
  const rows = $derived(["all", ...modes]);
  const byKey = $derived(new Map(cells.map((c) => [`${c.mode}|${c.h}`, c])));
  const LX = 92, CH = 30;
  let w = $state(440);
  const cw = $derived(Math.max(16, Math.min(40, (w - LX) / Math.max(1, hours.length))));
  const fmt = (v: number) => { const m = v / 60; return (m > 0.05 ? "+" : m < -0.05 ? MINUS : "") + Math.abs(m).toFixed(1); };
</script>

<div bind:clientWidth={w}>
  <svg class="chart" width={LX + cw * hours.length} height={18 + CH * rows.length} role="img" aria-label="Median delay by mode and hour">
    <Hatch {id} />
    {#each hours as h, j}<text x={LX + j * cw + cw / 2} y="10" text-anchor="middle">{String(h % 24).padStart(2, "0")}</text>{/each}
    {#each rows as m, i}
      <text x="0" y={18 + i * CH + CH / 2 + 4} style="fill: var(--ink); font-size: 11.5px; font-weight: {m === 'all' ? 600 : 450}">{m === "all" ? "All" : MODE_LABEL[m]}</text>
      {#each hours as h, j}
        {@const c = byKey.get(`${m}|${h}`)}
        {#if !c || c.n < 15 || c.median == null}
          <rect x={LX + j * cw + 1} y={18 + i * CH + 1} width={cw - 2} height={CH - 2} fill="url(#{id})" />
        {:else}
          <rect role="presentation" x={LX + j * cw + 1} y={18 + i * CH + 1} width={cw - 2} height={CH - 2} rx="2" fill={dcol(c.median)}
            onmouseenter={(e) => tip.show(e, `${m === "all" ? "All modes" : MODE_LABEL[m]} · ${String(h % 24).padStart(2, "0")}:00`, [
              { k: "Median delay", v: delay(c.median) }, { k: "On time", v: pct(c.otp) }, { k: "Visits", v: c.n.toLocaleString() }])}
            onmouseleave={() => tip.hide()} />
          {#if cw >= 30}<text x={LX + j * cw + cw / 2} y={18 + i * CH + CH / 2 + 4} text-anchor="middle" pointer-events="none"
            style="fill: {dink(c.median)}; font-size: 10.5px; font-weight: 600">{fmt(c.median)}</text>{/if}
        {/if}
      {/each}
    {/each}
  </svg>
</div>
