<script lang="ts">
  import type { Snippet } from "svelte";
  import NBadge from "./NBadge.svelte";
  let { label, value, sub = "", n, warn, spark }: {
    label: string; value: string; sub?: string; n?: number | string; warn?: boolean; spark?: Snippet;
  } = $props();
</script>

<div class="kpi">
  <div class="l">{label}</div>
  <div class="v"><span>{value}</span>{#if spark}<span class="sp">{@render spark()}</span>{/if}</div>
  <div class="s"><span>{sub}</span>{#if n !== undefined}<NBadge {n} {warn} />{/if}</div>
</div>

<style>
  .kpi { background: var(--panel); border: 1px solid var(--border); border-radius: 6px; padding: 11px 14px; display: flex; flex-direction: column;
    gap: 3px; min-width: 0; }
  .l { font-size: 12px; color: var(--muted); font-weight: 500; }
  .v { display: flex; align-items: flex-end; gap: 10px; font-size: 27px; font-weight: 650; letter-spacing: -.02em; line-height: 1.05;
    font-stretch: 92%; }
  .v > span:first-child { flex: 1; white-space: nowrap; }
  .sp { display: flex; }
  .s { display: flex; align-items: center; gap: 6px; font-size: 12px; color: var(--ink-2); min-height: 18px; }
  .s > span:first-child { flex: 1; }
</style>
