<script lang="ts">
  // Sample size beside every statistic: plain from 200, amber below (caution, not error).
  let { n, label = "", warn }: { n: number | string; label?: string; warn?: boolean } = $props();
  const w = $derived(warn ?? (typeof n === "number" && n < 200));
  const txt = $derived(typeof n === "number" ? `n=${n.toLocaleString("en-US")}${label ? " " + label : ""}` : n);
</script>

<span class="nb" class:w>{txt}</span>

<style>
  .nb { font-family: var(--mono); font-size: 11px; color: var(--muted); background: var(--sunk); padding: 1px 6px; border-radius: 3px;
    white-space: nowrap; }
  .w { background: var(--warn-bg); color: var(--warn-ink); }
</style>
