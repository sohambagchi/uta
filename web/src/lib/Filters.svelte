<script lang="ts">
  import { store } from "./store.svelte";
  import { DOW, fmtHour } from "./format";

  const RANGES = [["1", "Today"], ["7", "Week"], ["30", "Month"], ["90", "3 months"], ["", "All time"]];
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
    ? "any time" : `${fmtHour(store.filters.hourFrom)}–${fmtHour(store.filters.hourTo)}`);
</script>

<div class="filters card" role="group" aria-label="Filters for every chart and table below">
  <div class="field">
    <span class="lbl">How far back</span>
    <div class="seg">
      {#each RANGES as [v, label]}
        <button aria-pressed={store.filters.range === v} onclick={() => (store.filters.range = v)}>{label}</button>
      {/each}
    </div>
  </div>

  <div class="field">
    <span class="lbl">Which days</span>
    <div class="chips">
      {#each PRESETS as [name, days]}
        <button class="chip preset" aria-pressed={days.length === store.filters.dows.length && days.every((d) => store.filters.dows.includes(d))}
          onclick={() => preset(days)}>{name}</button>
      {/each}
      <span class="sep" aria-hidden="true"></span>
      {#each DOW as d, i}
        <button class="chip day" aria-pressed={store.filters.dows.includes(i)} onclick={() => toggleDow(i)}>{d}</button>
      {/each}
    </div>
  </div>

  <div class="field hours">
    <span class="lbl">Leaving <strong>{hourLabel}</strong></span>
    <div class="dual" style:--lo="{store.filters.hourFrom / 23 * 100}%" style:--hi="{(store.filters.hourTo - 1) / 23 * 100}%">
      <input type="range" min="0" max="23" step="1" value={store.filters.hourFrom} aria-label="Earliest departure hour"
        oninput={(e) => setHours("from", +(e.currentTarget as HTMLInputElement).value)} />
      <input type="range" min="1" max="24" step="1" value={store.filters.hourTo} aria-label="Latest departure hour"
        oninput={(e) => setHours("to", +(e.currentTarget as HTMLInputElement).value)} />
    </div>
  </div>

  <div class="field">
    <span class="lbl">Group times by</span>
    <select bind:value={store.filters.bin} aria-label="Time-of-day bin size">
      <option value={15}>15 minutes</option>
      <option value={30}>30 minutes</option>
      <option value={60}>1 hour</option>
      <option value={120}>2 hours</option>
    </select>
  </div>

  <label class="field toggle" title="Drop trips more than 3 IQR outside the middle half (data errors, not slow trips)">
    <input type="checkbox" bind:checked={store.filters.trim} />
    <span>Hide glitchy outliers</span>
  </label>

  <button class="btn ghost refresh" onclick={() => store.refreshSegments()} title="Fetch trips recorded since the page loaded">
    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
      <path d="M13.5 8a5.5 5.5 0 1 1-1.6-3.9M13.5 2.5v3h-3" />
    </svg>
    Refresh
  </button>
</div>

<style>
  .filters { display: flex; flex-wrap: wrap; gap: 16px 26px; align-items: flex-end; padding: 16px 20px; }
  .field { display: flex; flex-direction: column; gap: 7px; }
  .lbl { font-size: 12px; font-weight: 600; color: var(--muted); text-transform: uppercase; letter-spacing: .04em; }
  .lbl strong { color: var(--ink); text-transform: none; letter-spacing: 0; font-size: 13px; }
  .chips { display: flex; gap: 5px; flex-wrap: wrap; align-items: center; }
  .chip.day { min-width: 44px; }
  .sep { width: 1px; height: 18px; background: var(--border-strong); margin: 0 3px; }
  .hours { min-width: 220px; }
  .dual { position: relative; height: 30px; }
  /* shared track, filled between the two thumbs */
  .dual::before { content: ""; position: absolute; left: 10px; right: 10px; top: 12.5px; height: 5px; border-radius: 3px;
    background: linear-gradient(90deg, var(--surface-3) var(--lo), var(--ink) var(--lo) var(--hi), var(--surface-3) var(--hi)); }
  .dual input { position: absolute; inset: 0; width: 100%; margin: 0; pointer-events: none; background: none;
    appearance: none; -webkit-appearance: none; height: 30px; }
  .dual input::-webkit-slider-runnable-track { height: 5px; background: transparent; }
  .dual input::-webkit-slider-thumb { pointer-events: auto; -webkit-appearance: none; appearance: none; width: 20px; height: 20px;
    border-radius: 50%; background: var(--surface); border: 4px solid var(--ink); margin-top: -7.5px; cursor: grab;
    box-shadow: 0 1px 4px rgba(0,0,0,.2); }
  .dual input::-moz-range-track { height: 5px; background: transparent; }
  .dual input::-moz-range-thumb { pointer-events: auto; width: 14px; height: 14px; border-radius: 50%; background: var(--surface);
    border: 4px solid var(--ink); cursor: grab; box-shadow: 0 1px 4px rgba(0,0,0,.2); }
  .toggle { flex-direction: row; align-items: center; gap: 8px; font-size: 13.5px; color: var(--ink-2); padding-bottom: 7px;
    cursor: pointer; }
  .refresh { margin-left: auto; }
  .refresh svg { width: 14px; height: 14px; }
</style>
