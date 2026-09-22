<script lang="ts">
  import { tip } from "../tip.svelte";
  let w = $state(0), h = $state(0);
  const clamp = (v: number, lo: number, hi: number) => Math.max(lo, Math.min(hi, v));
  const left = $derived(tip.cur ? clamp(tip.cur.x + 16 + w > innerWidth ? tip.cur.x - w - 12 : tip.cur.x + 14, 8, innerWidth - w - 8) : 0);
  const top = $derived(tip.cur ? (tip.cur.y + 14 + h > innerHeight - 8 ? Math.max(8, tip.cur.y - h - 10) : tip.cur.y + 14) : 0);
</script>

{#if tip.cur}
  <div class="tip" role="tooltip" bind:clientWidth={w} bind:clientHeight={h} style:left="{left}px" style:top="{top}px">
    <div class="t">{tip.cur.title}</div>
    {#each tip.cur.rows as r}
      <div class="r">{#if r.color}<span class="k" style:background={r.color}></span>{/if}<span class="kk">{r.k}</span><b>{r.v}</b></div>
    {/each}
  </div>
{/if}

<style>
  .tip { position: fixed; z-index: 50; pointer-events: none; background: var(--ink); color: var(--panel); border-radius: 5px;
    padding: 8px 10px; font-size: 12px; box-shadow: var(--shadow-pop); display: grid; gap: 2px; min-width: 170px; max-width: 320px; }
  .t { font-weight: 650; margin-bottom: 2px; }
  .r { display: flex; gap: 10px; align-items: center; }
  .kk { color: var(--faint); flex: 1; }
  :global(:root[data-theme="dark"]) .kk { color: var(--muted); }
  .k { width: 8px; height: 8px; border-radius: 2px; flex: none; }
  b { font-weight: 600; font-variant-numeric: tabular-nums; }
</style>
