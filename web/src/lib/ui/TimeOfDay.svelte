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
  // track position in CSS: thumbs travel inside the track, a half-thumb in from each end
  const at = (h: number) => `calc(var(--th) / 2 + (100% - var(--th)) * ${pos(h) / 100})`;

  // One track, two thumbs: a press grabs the nearer thumb; when the thumbs touch, the first drag's
  // direction picks (left moves From, right moves To). Drags move locally; the scope changes on release.
  let track = $state<HTMLDivElement>()!;
  let drag: "a" | "b" | "?" | null = null, start = 0;
  function hourAt(e: PointerEvent) {
    const r = track.getBoundingClientRect(), th = 22;
    const f = Math.min(1, Math.max(0, (e.clientX - r.left - th / 2) / (r.width - th)));
    return DAY[0] + f * (DAY[1] - DAY[0]);
  }
  function move(which: "a" | "b", h: number) {
    h = Math.round(h);
    if (which === "a") a = Math.max(DAY[0], Math.min(h, b - 1));
    else b = Math.min(DAY[1], Math.max(h, a + 1));
  }
  function down(e: PointerEvent) {
    const h = hourAt(e);
    track.setPointerCapture(e.pointerId);
    if (b - a <= 2 && h > a - 1 && h < b + 1) { drag = "?"; start = h; return; }
    drag = h <= a ? "a" : h >= b ? "b" : h - a <= b - h ? "a" : "b";
    move(drag, h);
  }
  function pmove(e: PointerEvent) {
    if (!drag) return;
    const h = hourAt(e);
    if (drag === "?") { if (Math.abs(h - start) < 0.4) return; drag = h < start ? "a" : "b"; }
    move(drag, h);
  }
  function up() {
    if (!drag) return;
    drag = null;
    if (a !== h0 || b !== h1) set(a, b);
  }
  function key(e: KeyboardEvent, which: "a" | "b") {
    const d = e.key === "ArrowLeft" || e.key === "ArrowDown" ? -1 : e.key === "ArrowRight" || e.key === "ArrowUp" ? 1 : 0;
    if (!d) return;
    e.preventDefault();
    move(which, (which === "a" ? a : b) + d);
    set(a, b);
  }
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
        <div class="track" bind:this={track} onpointerdown={down} onpointermove={pmove}
          onpointerup={up} onpointercancel={up} role="presentation">
          <div class="rail"></div>
          <div class="fill" style:left={at(a)} style:right="calc(100% - {at(b)})"></div>
          <div class="mid" style:left={at(24)} title="Midnight"></div>
          {#each [["a", a, "From"], ["b", b, "To"]] as [k, v, label] (k)}
            <div class="thumb" style:left={at(v as number)} role="slider" tabindex="0" aria-label={label as string}
              aria-valuemin={DAY[0]} aria-valuemax={DAY[1]} aria-valuenow={v as number} aria-valuetext={hourLabel(v as number)}
              onkeydown={(e) => key(e, k as "a" | "b")}></div>
          {/each}
        </div>
        <div class="ticks">
          {#each TICKS as t}<span style:left={at(t)}>{String(t % 24).padStart(2, "0")}</span>{/each}
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
  .custom { --th: 22px; }
  .track { position: relative; height: 32px; touch-action: none; cursor: pointer; }
  .rail, .fill { position: absolute; top: 14px; height: 4px; border-radius: 2px; }
  .rail { left: calc(var(--th) / 2); right: calc(var(--th) / 2); background: var(--sunk); }
  .fill { background: var(--ink); }
  .mid { position: absolute; top: 9px; width: 1px; height: 14px; background: var(--axis); }
  .thumb { position: absolute; top: 5px; width: var(--th); height: var(--th); margin-left: calc(var(--th) / -2); border-radius: 50%;
    background: var(--panel); border: 2px solid var(--ink); box-sizing: border-box; }
  .thumb:focus-visible { outline: 2px solid var(--ink); outline-offset: 2px; }
  .ticks { position: relative; height: 14px; font-size: 10px; color: var(--muted); font-family: var(--mono); }
  .ticks span { position: absolute; transform: translateX(-50%); }
  .foot { font-size: 11px; }
  @media (max-width: 760px) { .tod { position: static; } .pop { left: 12px; right: 12px; width: auto; top: auto; margin-top: 6px; } }
</style>
