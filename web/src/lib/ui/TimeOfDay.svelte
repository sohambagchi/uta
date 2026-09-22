<script lang="ts" module>
  // Service-day hours: a service day runs ~03:00 to ~03:00 the next morning, so hours 24–30
  // are after midnight (shown as 01:00 +1). The URL keeps `h=<from>-<to>` in service hours.
  export const DAY: [number, number] = [3, 27];
  export const PRESETS: { key: string; label: string; h: [number, number] }[] = [
    { key: "all", label: "All day", h: DAY },
    { key: "am", label: "AM peak", h: [6, 9] },
    { key: "mid", label: "Midday", h: [9, 15] },
    { key: "pm", label: "PM peak", h: [15, 18] },
    { key: "eve", label: "Evening", h: [18, 22] },
    { key: "night", label: "Night", h: [22, 27] },
  ];
  export function hourLabel(h: number): string {
    return `${String(h % 24).padStart(2, "0")}:00${h >= 24 ? " +1" : ""}`;
  }
  export function rangeLabel(h0: number, h1: number): string {
    const p = PRESETS.find((x) => x.h[0] === h0 && x.h[1] === h1);
    if (p?.key === "all") return "All day";
    const r = `${hourLabel(h0).replace(" +1", "")}–${hourLabel(h1)}`;
    return p ? `${p.label} · ${r}` : r;
  }
</script>

<script lang="ts">
  let { h0, h1, onchange }: { h0: number; h1: number; onchange: (h0: number, h1: number) => void } = $props();
  let open = $state(false);
  let a = $state(0), b = $state(0);
  $effect(() => { a = h0; b = h1; });
  let root: HTMLDivElement;

  function set(x: number, y: number) {
    if (y <= x) y = x + 1;
    a = x; b = y;
    onchange(x, y);
  }
  const pos = (h: number) => ((h - DAY[0]) / (DAY[1] - DAY[0])) * 100;
  const TICKS = [3, 6, 9, 12, 15, 18, 21, 24, 27];

  $effect(() => {
    if (!open) return;
    const close = (e: PointerEvent) => { if (!root.contains(e.target as Node)) open = false; };
    const key = (e: KeyboardEvent) => { if (e.key === "Escape") open = false; };
    addEventListener("pointerdown", close);
    addEventListener("keydown", key);
    return () => { removeEventListener("pointerdown", close); removeEventListener("keydown", key); };
  });
</script>

<div class="tod" bind:this={root}>
  <button class="chip trigger" aria-haspopup="dialog" aria-expanded={open} class:on={!(h0 === DAY[0] && h1 === DAY[1])}
    onclick={() => (open = !open)}>
    <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true"><circle cx="6" cy="6" r="5" fill="none" stroke="currentColor" stroke-width="1.3" /><path d="M6 3v3l2 1.5" fill="none" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" /></svg>
    {rangeLabel(h0, h1)}
  </button>
  {#if open}
    <div class="pop" role="dialog" aria-label="Time of day">
      <div class="presets">
        {#each PRESETS as p}
          <button class="chip" aria-pressed={p.h[0] === h0 && p.h[1] === h1} onclick={() => { set(p.h[0], p.h[1]); open = false; }}>
            {p.label}{#if p.key !== "all"}<span class="pr">{hourLabel(p.h[0]).replace(" +1", "")}–{hourLabel(p.h[1])}</span>{/if}
          </button>
        {/each}
      </div>
      <div class="custom">
        <div class="val"><b>{hourLabel(a)}</b><span class="muted">to</span><b>{hourLabel(b)}</b></div>
        <div class="track">
          <div class="rail"></div>
          <div class="fill" style:left="{pos(a)}%" style:width="{pos(b) - pos(a)}%"></div>
          <div class="mid" style:left="{pos(24)}%" title="Midnight"></div>
          <input type="range" min={DAY[0]} max={DAY[1] - 1} step="1" value={a} aria-label="From"
            oninput={(e) => set(Math.min(+(e.currentTarget as HTMLInputElement).value, b - 1), b)} />
          <input type="range" min={DAY[0] + 1} max={DAY[1]} step="1" value={b} aria-label="To"
            oninput={(e) => set(a, Math.max(+(e.currentTarget as HTMLInputElement).value, a + 1))} />
        </div>
        <div class="ticks">
          {#each TICKS as t}<span style:left="{pos(t)}%">{String(t % 24).padStart(2, "0")}</span>{/each}
        </div>
        <div class="foot muted">Service day · 03:00 to 03:00 next morning</div>
      </div>
    </div>
  {/if}
</div>

<style>
  .tod { position: relative; }
  .trigger { gap: 6px; }
  .trigger.on { border-color: var(--ink); color: var(--ink); font-weight: 600; }
  .pop { position: absolute; right: 0; top: calc(100% + 6px); z-index: 40; width: 340px; background: var(--panel); border: 1px solid var(--border);
    border-radius: 6px; box-shadow: var(--shadow-pop); padding: 12px; display: flex; flex-direction: column; gap: 12px; }
  .presets { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 6px; }
  .presets .chip { justify-content: space-between; width: 100%; }
  .pr { font-family: var(--mono); font-size: 10.5px; opacity: .7; }
  .custom { border-top: 1px solid var(--grid); padding-top: 10px; display: flex; flex-direction: column; gap: 6px; }
  .val { display: flex; gap: 8px; align-items: baseline; font-size: 13px; font-family: var(--mono); }
  .track { position: relative; height: 22px; }
  .rail, .fill { position: absolute; top: 9px; height: 4px; border-radius: 2px; }
  .rail { left: 0; right: 0; background: var(--sunk); }
  .fill { background: var(--ink); }
  .mid { position: absolute; top: 4px; width: 1px; height: 14px; background: var(--axis); }
  input[type="range"] { position: absolute; inset: 0; width: 100%; margin: 0; background: none; pointer-events: none;
    appearance: none; -webkit-appearance: none; height: 22px; }
  input[type="range"]::-webkit-slider-thumb { pointer-events: auto; appearance: none; -webkit-appearance: none; width: 14px; height: 14px;
    border-radius: 50%; background: var(--panel); border: 2px solid var(--ink); cursor: pointer; }
  input[type="range"]::-moz-range-thumb { pointer-events: auto; width: 12px; height: 12px; border-radius: 50%; background: var(--panel);
    border: 2px solid var(--ink); cursor: pointer; }
  input[type="range"]::-webkit-slider-runnable-track { background: none; }
  input[type="range"]::-moz-range-track { background: none; }
  .ticks { position: relative; height: 14px; font-size: 10px; color: var(--muted); font-family: var(--mono); }
  .ticks span { position: absolute; transform: translateX(-50%); }
  .foot { font-size: 11px; }
  @media (max-width: 760px) { .tod { position: static; } .pop { left: 12px; right: 12px; width: auto; top: auto; margin-top: 6px; } }
</style>
