<script lang="ts">
  export interface LegendItem { color: string; label: string; kind?: "sw" | "line" | "dash" | "dot" | "hatch" | "ring" }
  let { items, delay = false }: { items?: LegendItem[]; delay?: boolean } = $props();
  import { DELAY_BINS } from "../format";
  const all = $derived([...(delay ? DELAY_BINS.map(([color, label]) => ({ color, label, kind: "sw" as const })) : []), ...(items ?? [])]);
</script>

<div class="lg">
  {#each all as it}
    <span class="it">
      {#if it.kind === "line"}<svg width="18" height="8"><line x1="0" y1="4" x2="18" y2="4" stroke={it.color} stroke-width="2" /></svg>
      {:else if it.kind === "dash"}<svg width="18" height="8"><line x1="0" y1="4" x2="18" y2="4" stroke={it.color} stroke-width="1.5" stroke-dasharray="4 3" /></svg>
      {:else if it.kind === "dot"}<span class="dot" style:background={it.color}></span>
      {:else if it.kind === "ring"}<span class="dot ring" style:border-color={it.color}></span>
      {:else if it.kind === "hatch"}<span class="sw hatch"></span>
      {:else}<span class="sw" style:background={it.color}></span>{/if}
      {it.label}
    </span>
  {/each}
</div>

<style>
  .lg { display: flex; gap: 6px 12px; flex-wrap: wrap; align-items: center; }
  .it { display: inline-flex; align-items: center; gap: 5px; font-size: 11.5px; color: var(--ink-2); white-space: nowrap; }
  .sw { width: 12px; height: 10px; border-radius: 2px; }
  .dot { width: 8px; height: 8px; border-radius: 50%; }
  .ring { background: none; border: 1.5px solid; }
  .hatch { border: 1px solid var(--axis); background: repeating-linear-gradient(45deg, var(--axis) 0 2px, transparent 2px 5px); }
</style>
