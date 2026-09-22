<script lang="ts">
  // Filters for every chart and table on the page (kept in the #/compare?… URL by the store).
  import { store } from "../store.svelte";
  import Info from "../ui/Info.svelte";
  import NBadge from "../ui/NBadge.svelte";
  import TimeOfDay from "../ui/TimeOfDay.svelte";
  import DateRange from "../ui/DateRange.svelte";
  import { app } from "../app.svelte";

  let { trimmed = 0 }: { trimmed?: number } = $props();

  const PRESETS: [string, number[]][] = [["Weekdays", [0, 1, 2, 3, 4]], ["Weekend", [5, 6]]];
  const DAYS = ["M", "T", "W", "T", "F", "S", "S"];
  const DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
  const BINS: [number, string][] = [[15, "15 min"], [30, "30 min"], [60, "1 h"], [120, "2 h"]];
  const f = $derived(store.filters);

  function toggleDow(d: number) {
    const s = new Set(f.dows);
    s.has(d) ? s.delete(d) : s.add(d);
    store.filters.dows = [...s].sort();
  }
  function preset(days: number[]) {
    const same = f.dows.length === days.length && days.every((d) => f.dows.includes(d));
    store.filters.dows = same ? [] : [...days];
  }
  function setHours(a: number, b: number) {
    store.filters.hourFrom = a;
    store.filters.hourTo = b;
  }
</script>

<div class="bar" role="group" aria-label="Filters">
  <div class="f"><span class="lab">Dates</span>
    <DateRange from={f.from} to={f.to} days={app.days} onchange={(a, b) => { store.filters.range = ""; store.filters.from = a; store.filters.to = b; }} />
  </div>
  <div class="f"><span class="lab">Days</span>
    {#each PRESETS as [name, days]}
      <button class="chip" aria-pressed={f.dows.length === days.length && days.every((d) => f.dows.includes(d))} onclick={() => preset(days)}>{name}</button>
    {/each}
    {#each DAYS as d, i}<button class="chip day" aria-pressed={f.dows.includes(i)} aria-label={DAY_NAMES[i]} onclick={() => toggleDow(i)}>{d}</button>{/each}
  </div>
  <div class="f"><span class="lab">Departing</span><TimeOfDay h0={f.hourFrom} h1={f.hourTo} onchange={setHours} />
    <Info text="Time of day by departure from the first stop, on the service day (03:00 to 03:00 next morning)." /></div>
  <div class="f"><span class="lab">Bin</span>
    {#each BINS as [v, label]}<button class="chip" aria-pressed={f.bin === v} onclick={() => (store.filters.bin = v)}>{label}</button>{/each}
  </div>
  <label class="f chk"><input type="checkbox" bind:checked={store.filters.trim} /> Drop far outliers
    <Info text="Drops trips more than 3× the interquartile range outside the middle half: data errors, not slow trips." /></label>
  <span class="sp"></span>
  {#if store.filters.trim}<NBadge n="{trimmed} dropped" warn={false} />{/if}
  <button class="icon-btn" title="Fetch trips recorded since the page loaded" aria-label="Refresh" onclick={() => store.refreshSegments()}>
    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
      <path d="M13.5 8a5.5 5.5 0 1 1-1.6-3.9M13.5 2.5v3h-3" /></svg>
  </button>
</div>

<style>
  .bar { display: flex; flex-wrap: wrap; align-items: center; gap: 10px 18px; background: var(--panel); border: 1px solid var(--border);
    border-radius: 6px; padding: 9px 14px; }
  .f { display: flex; align-items: center; gap: 4px; flex-wrap: wrap; }
  .lab { font-size: 11px; color: var(--muted); text-transform: uppercase; letter-spacing: .06em; font-weight: 600; font-stretch: 90%;
    margin-right: 4px; white-space: nowrap; }
  .day { min-width: 26px; justify-content: center; }
  .chk { gap: 6px; font-size: 12px; color: var(--ink-2); white-space: nowrap; cursor: pointer; }
  .sp { flex: 1; }
</style>
