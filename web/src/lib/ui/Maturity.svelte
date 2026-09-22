<script lang="ts">
  // How much history backs the views: hours → 3 days (time-of-day) → 3 weeks (weekdays).
  let { days = 0, hours = 0 }: { days?: number; hours?: number } = $props();
  const steps = $derived([days >= 1 || hours > 0, days >= 3, days >= 21]);
  const label = $derived(days <= 1 ? `${Math.max(1, Math.round(hours))} h of history` : `${days} days of history`);
</script>

<span class="mt" title="Time-of-day patterns need about 3 days; weekday comparisons about 3 weeks">
  <span class="bar">{#each steps as on}<span class:on></span>{/each}</span>{label}
</span>

<style>
  .mt { display: inline-flex; align-items: center; gap: 6px; font-size: 11.5px; color: var(--muted); white-space: nowrap; }
  .bar { display: inline-flex; gap: 2px; }
  .bar span { width: 22px; height: 6px; border-radius: 1px; background: var(--sunk); border: 1px solid var(--border); }
  .bar span.on { background: var(--ink); border-color: var(--ink); }
</style>
