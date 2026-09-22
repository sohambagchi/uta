<script lang="ts">
  import { store } from "./store.svelte";
  import { DOW, fmtHour } from "./format";

  const RANGES = [["1", "Today"], ["7", "7 days"], ["30", "30 days"], ["90", "90 days"], ["", "All"]];
  const PRESETS: [string, number[]][] = [["Weekdays", [0, 1, 2, 3, 4]], ["Weekend", [5, 6]]];

  function toggleDow(d: number) {
    const s = new Set(store.filters.dows);
    s.has(d) ? s.delete(d) : s.add(d);
    store.filters.dows = [...s].sort();
  }
  function preset(days: number[]) {
    const cur = store.filters.dows;
    const same = cur.length === days.length && days.every((d) => cur.includes(d));
    store.filters.dows = same ? [] : [...days];
  }
  function setHours(which: "from" | "to", v: number) {
    if (which === "from") store.filters.hourFrom = Math.min(v, store.filters.hourTo - 1);
    else store.filters.hourTo = Math.max(v, store.filters.hourFrom + 1);
  }
  const hourLabel = $derived(store.filters.hourFrom === 0 && store.filters.hourTo === 24
    ? "All day" : `${fmtHour(store.filters.hourFrom)}–${fmtHour(store.filters.hourTo)}`);
</script>

<div class="filters" role="group" aria-label="Filters for every chart and table below">
  <div class="field">
    <span class="lbl">History</span>
    <div class="seg">
      {#each RANGES as [v, label]}
        <button aria-pressed={store.filters.range === v} onclick={() => (store.filters.range = v)}>{label}</button>
      {/each}
    </div>
  </div>

  <div class="field">
    <span class="lbl">Days</span>
    <div class="chips">
      {#each PRESETS as [name, days]}
        <button class="chip preset" aria-pressed={days.length === store.filters.dows.length && days.every((d) => store.filters.dows.includes(d))}
          onclick={() => preset(days)}>{name}</button>
      {/each}
      {#each DOW as d, i}
        <button class="chip" aria-pressed={store.filters.dows.includes(i)} onclick={() => toggleDow(i)}>{d}</button>
      {/each}
    </div>
  </div>

  <div class="field hours">
    <span class="lbl">Departing <strong>{hourLabel}</strong></span>
    <div class="dual">
      <input type="range" min="0" max="23" step="1" value={store.filters.hourFrom} aria-label="Earliest departure hour"
        oninput={(e) => setHours("from", +(e.currentTarget as HTMLInputElement).value)} />
      <input type="range" min="1" max="24" step="1" value={store.filters.hourTo} aria-label="Latest departure hour"
        oninput={(e) => setHours("to", +(e.currentTarget as HTMLInputElement).value)} />
    </div>
  </div>

  <div class="field">
    <span class="lbl">Time bins</span>
    <select bind:value={store.filters.bin} aria-label="Time-of-day bin size">
      <option value={15}>15 min</option>
      <option value={30}>30 min</option>
      <option value={60}>1 hour</option>
      <option value={120}>2 hours</option>
    </select>
  </div>

  <label class="field toggle" title="Drop trips more than 3 IQR outside the middle half (data errors, not slow trips)">
    <input type="checkbox" bind:checked={store.filters.trim} />
    <span>Exclude far outliers</span>
  </label>

  <button class="refresh" onclick={() => store.refreshSegments()} title="Refetch trips recorded since the page loaded">↻ Refresh</button>
</div>

<style>
  .filters { display: flex; flex-wrap: wrap; gap: 14px 20px; align-items: flex-end; }
  .field { display: flex; flex-direction: column; gap: 4px; }
  .lbl { font-size: 12px; color: var(--ink-2); }
  .lbl strong { color: var(--ink); font-weight: 600; }
  .chips { display: flex; gap: 4px; flex-wrap: wrap; }
  .hours { min-width: 200px; }
  .dual { position: relative; height: 26px; }
  .dual input { position: absolute; inset: 0; width: 100%; margin: 0; pointer-events: none; background: none;
    appearance: none; -webkit-appearance: none; height: 26px; }
  .dual input::-webkit-slider-runnable-track { height: 4px; background: var(--grid); border-radius: 2px; }
  .dual input:first-child::-webkit-slider-runnable-track { background: var(--grid); }
  .dual input + input::-webkit-slider-runnable-track { background: transparent; }
  .dual input::-webkit-slider-thumb { pointer-events: auto; -webkit-appearance: none; appearance: none; width: 16px; height: 16px;
    border-radius: 50%; background: var(--ink); border: 2px solid var(--surface); margin-top: -6px; cursor: pointer; }
  .dual input::-moz-range-track { height: 4px; background: var(--grid); border-radius: 2px; }
  .dual input + input::-moz-range-track { background: transparent; }
  .dual input::-moz-range-thumb { pointer-events: auto; width: 14px; height: 14px; border-radius: 50%; background: var(--ink);
    border: 2px solid var(--surface); cursor: pointer; }
  .toggle { flex-direction: row; align-items: center; gap: 6px; font-size: 13px; color: var(--ink-2); padding-bottom: 4px; }
  .refresh { border: 1px solid var(--border); background: var(--surface); border-radius: 8px; padding: 4px 10px;
    font-size: 12px; color: var(--ink-2); margin-left: auto; }
  .refresh:hover { background: var(--surface-2); color: var(--ink); }
</style>
