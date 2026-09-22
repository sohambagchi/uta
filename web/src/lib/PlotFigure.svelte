<script lang="ts" module>
  export interface ReadoutRow { color?: string; value: string; name?: string; dashed?: boolean }
  export interface Readout { x: number | Date; title: string; rows: ReadoutRow[] }
</script>

<script lang="ts">
  // Renders an Observable Plot chart at the container's width and, for charts with
  // a continuous x scale, adds a snapping crosshair with one tooltip for every series.
  type PlotEl = (SVGSVGElement | HTMLElement) & {
    scale: (name: string) => { apply: (v: unknown) => number; invert?: (px: number) => unknown; range?: number[] } | undefined;
  };

  let {
    render,
    readout,
    height = 240,
    empty = "No data",
    isEmpty = false,
  }: {
    render: (width: number) => PlotEl;
    readout?: (x: number) => Readout | null;
    height?: number;
    empty?: string;
    isEmpty?: boolean;
  } = $props();

  let host: HTMLDivElement;
  let width = $state(0);
  let plot: PlotEl | null = null;
  let tip = $state<{ left: number; top: number; r: Readout } | null>(null);
  let cross = $state<{ x: number; y1: number; y2: number } | null>(null);

  $effect(() => {
    const ro = new ResizeObserver(([e]) => (width = Math.floor(e.contentRect.width)));
    ro.observe(host);
    return () => ro.disconnect();
  });

  $effect(() => {
    if (!width || isEmpty) { host.replaceChildren(); plot = null; return; }
    const el = render(width);
    host.replaceChildren(el);
    plot = el;
    tip = null;
    cross = null;
  });

  function svgOf(el: Element): SVGSVGElement | null {
    return el instanceof SVGSVGElement ? el : el.querySelector("svg");
  }

  function move(e: PointerEvent) {
    if (!readout || !plot) return;
    const x = plot.scale("x"), y = plot.scale("y");
    const svg = svgOf(plot);
    if (!x?.invert || !svg) return;
    const box = svg.getBoundingClientRect(), hostBox = host.getBoundingClientRect();
    const px = e.clientX - box.left;
    const r = readout(x.invert(px) as number);
    if (!r) { leave(); return; }
    const sx = x.apply(r.x);
    const [y1, y2] = y?.range ? [Math.min(...y.range), Math.max(...y.range)] : [0, box.height];
    cross = { x: sx + box.left - hostBox.left, y1: y1 + box.top - hostBox.top, y2: y2 + box.top - hostBox.top };
    const left = e.clientX - hostBox.left + 14;
    tip = { left: left + 200 > hostBox.width ? e.clientX - hostBox.left - 214 : left, top: e.clientY - hostBox.top + 12, r };
  }
  function leave() { tip = null; cross = null; }
</script>

<div class="wrap">
  <!-- svelte-ignore a11y_no_static_element_interactions -->
  <div class="plot-figure" bind:this={host} style:min-height="{isEmpty ? 0 : height}px"
    onpointermove={move} onpointerleave={leave}></div>
  {#if isEmpty}<div class="none">{empty}</div>{/if}
  {#if cross}<div class="cross" style:left="{cross.x}px" style:top="{cross.y1}px" style:height="{cross.y2 - cross.y1}px"></div>{/if}
  {#if tip}
    <div class="tip" style:left="{tip.left}px" style:top="{tip.top}px" role="tooltip">
      <div class="tt-title">{tip.r.title}</div>
      {#each tip.r.rows as row}
        <div class="tt-row">
          {#if row.color}<span class="tt-key" class:dashed={row.dashed} style:--k={row.color}></span>{/if}
          <strong>{row.value}</strong>
          {#if row.name}<span class="tt-name">{row.name}</span>{/if}
        </div>
      {/each}
    </div>
  {/if}
</div>

<style>
  .wrap { position: relative; }
  .none { color: var(--muted); font-size: 13px; padding: 36px 0; text-align: center; }
  .cross { position: absolute; width: 1px; background: var(--axis); pointer-events: none; }
  .tip { position: absolute; z-index: 5; pointer-events: none; background: var(--surface); color: var(--ink);
    border: 1px solid var(--border); border-radius: 8px; padding: 7px 10px; font-size: 12px; min-width: 150px;
    box-shadow: 0 6px 20px rgba(0,0,0,.14); }
  .tt-title { color: var(--ink-2); margin-bottom: 3px; }
  .tt-row { display: flex; align-items: center; gap: 8px; white-space: nowrap; }
  .tt-row strong { font-variant-numeric: tabular-nums; }
  .tt-key { width: 12px; height: 2px; border-radius: 1px; background: var(--k); flex: none; }
  .tt-key.dashed { background: repeating-linear-gradient(90deg, var(--k) 0 4px, transparent 4px 6px); }
  .tt-name { color: var(--ink-2); }
</style>
