<script lang="ts">
  // Calendar range picker over service dates. Days with history are marked by how much was observed;
  // the first click sets the start, the second the end. `null` for both means "all data".
  import { untrack } from "svelte";
  import type { DayInfo } from "../api";

  let { from, to, days, single = false, onchange }: {
    from: string | null; to: string | null; days: DayInfo[]; single?: boolean;
    onchange: (from: string | null, to: string | null) => void;
  } = $props();

  const iso = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
  const parse = (s: string) => { const [y, m, d] = s.split("-").map(Number); return new Date(y, m - 1, d); };
  const addDays = (s: string, n: number) => { const d = parse(s); d.setDate(d.getDate() + n); return iso(d); };
  const fmt = (s: string, withYear = false) =>
    parse(s).toLocaleDateString("en-GB", { day: "numeric", month: "short", ...(withYear ? { year: "numeric" } : {}) });

  const first = $derived(days[0]?.date ?? null);
  const last = $derived(days.at(-1)?.date ?? null);
  const byDate = $derived(new Map(days.map((d) => [d.date, d.n])));
  const maxN = $derived(Math.max(1, ...days.map((d) => d.n)));
  // effective range (null = the whole span)
  const a = $derived(single ? (to ?? last) : (from ?? first));
  const b = $derived(to ?? last);
  const isAll = $derived(!single && !from && !to);
  const nDays = $derived(a && b ? Math.round((parse(b).getTime() - parse(a).getTime()) / 86400000) + 1 : 0);
  const label = $derived.by(() => {
    if (!a || !b) return "No data yet";
    if (a === b) return fmt(a, true);
    const sameYear = a.slice(0, 4) === b.slice(0, 4);
    return `${fmt(a, !sameYear)} – ${fmt(b, true)}`;
  });

  let open = $state(false);
  let pick = $state<string | null>(null);      // first click of a range
  let hover = $state<string | null>(null);
  let month = $state<Date>(new Date());
  let root: HTMLDivElement;
  // on open: reset the half-made range and show the month of the range's end
  $effect(() => {
    if (!open) return;
    const m = parse(untrack(() => b) ?? iso(new Date()));
    m.setDate(1);
    untrack(() => { pick = null; month = m; });
  });

  $effect(() => {
    if (!open) return;
    const close = (e: PointerEvent) => { if (!root.contains(e.target as Node)) open = false; };
    const key = (e: KeyboardEvent) => { if (e.key === "Escape") open = false; };
    addEventListener("pointerdown", close);
    addEventListener("keydown", key);
    return () => { removeEventListener("pointerdown", close); removeEventListener("keydown", key); };
  });

  function click(d: string) {
    if (single) { onchange(null, d === last ? null : d); open = false; return; }
    if (!pick) { pick = d; return; }
    const [x, y] = pick <= d ? [pick, d] : [d, pick];
    pick = null;
    onchange(x === first && y === last ? null : x, x === first && y === last ? null : y);
    open = false;
  }
  function preset(n: number | null) {
    if (!last) return;
    if (n === null) onchange(null, null);
    else { const x = addDays(last, -(n - 1)); onchange(first && x < first ? first : x, last); }
    open = false;
  }

  // two months side by side: the one before `month` and `month`
  const months = $derived.by(() => {
    const out: { title: string; cells: (string | null)[] }[] = [];
    for (const off of single ? [0] : [-1, 0]) {
      const m = new Date(month.getFullYear(), month.getMonth() + off, 1);
      const lead = (m.getDay() + 6) % 7;            // Monday first
      const n = new Date(m.getFullYear(), m.getMonth() + 1, 0).getDate();
      const cells: (string | null)[] = Array(lead).fill(null);
      for (let d = 1; d <= n; d++) cells.push(iso(new Date(m.getFullYear(), m.getMonth(), d)));
      out.push({ title: m.toLocaleDateString("en-GB", { month: "long", year: "numeric" }), cells });
    }
    return out;
  });
  const shift = (k: number) => { month = new Date(month.getFullYear(), month.getMonth() + k, 1); };
  // live preview while choosing the end of a range
  const lo = $derived(pick ? (hover && hover < pick ? hover : pick) : a);
  const hi = $derived(pick ? (hover && hover > pick ? hover : pick) : b);
  const PRESETS: [string, number | null][] = [["All data", null], ["Latest day", 1], ["Last 7 days", 7], ["Last 30 days", 30]];
</script>

<div class="dr" bind:this={root}>
  <button class="chip trigger" aria-haspopup="dialog" aria-expanded={open} class:on={!isAll && !single} onclick={() => (open = !open)}>
    <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true"><rect x="1" y="2" width="10" height="9" rx="1.5" fill="none" stroke="currentColor" stroke-width="1.2" /><path d="M1 5h10M4 1v2M8 1v2" stroke="currentColor" stroke-width="1.2" /></svg>
    {label}{#if !single && nDays > 1}<span class="nd">{isAll ? "all · " : ""}{nDays} days</span>{:else if isAll}<span class="nd">all data</span>{/if}
  </button>
  {#if open}
    <div class="pop" role="dialog" aria-label="Choose dates">
      {#if !single}
        <div class="presets">
          {#each PRESETS as [lab, n]}
            <button class="chip" aria-pressed={n === null ? isAll : !isAll && b === last && nDays === n} onclick={() => preset(n)}>{lab}</button>
          {/each}
        </div>
      {/if}
      <div class="nav">
        <button class="icon-btn" aria-label="Earlier month" onclick={() => shift(-1)}>‹</button>
        <span class="hint muted">{single ? "Pick a day" : pick ? "Now pick the end" : "Pick the start"}</span>
        <button class="icon-btn" aria-label="Later month" onclick={() => shift(1)}>›</button>
      </div>
      <div class="months">
        {#each months as m}
          <div class="month">
            <div class="mt">{m.title}</div>
            <div class="grid">
              {#each ["M", "T", "W", "T", "F", "S", "S"] as d}<span class="dow">{d}</span>{/each}
              {#each m.cells as d}
                {#if d}
                  {@const n = byDate.get(d) ?? 0}
                  {@const inR = lo && hi && d >= lo && d <= hi}
                  <button class="day" class:has={n > 0} class:in={inR} class:end={d === lo || d === hi} class:today={d === iso(new Date())}
                    onmouseenter={() => (hover = d)} onclick={() => click(d)}
                    aria-label="{fmt(d, true)}{n ? `, ${n.toLocaleString()} observed visits` : ', no data'}" title={n ? `${n.toLocaleString()} visits` : "no data"}>
                    {parse(d).getDate()}
                    {#if n > 0}<span class="dot" style:opacity={0.35 + 0.65 * Math.sqrt(n / maxN)}></span>{/if}
                  </button>
                {:else}<span></span>{/if}
              {/each}
            </div>
          </div>
        {/each}
      </div>
      <div class="foot muted">
        {#if first && last}History {fmt(first)} – {fmt(last, true)} · <span class="dot inline"></span> days with data{/if}
      </div>
    </div>
  {/if}
</div>

<style>
  .dr { position: relative; }
  .trigger { gap: 6px; }
  .trigger.on { border-color: var(--ink); color: var(--ink); font-weight: 600; }
  .nd { font-family: var(--mono); font-size: 10.5px; color: var(--muted); margin-left: 2px; }
  .pop { position: absolute; left: 0; top: calc(100% + 6px); z-index: 40; background: var(--panel); border: 1px solid var(--border);
    border-radius: 6px; box-shadow: var(--shadow-pop); padding: 12px; display: flex; flex-direction: column; gap: 10px; }
  .presets { display: flex; gap: 6px; flex-wrap: wrap; }
  .nav { display: flex; align-items: center; gap: 8px; }
  .hint { flex: 1; text-align: center; font-size: 11.5px; }
  .months { display: flex; gap: 18px; }
  .month { width: 224px; }
  .mt { font-weight: 650; font-size: 12.5px; margin-bottom: 6px; }
  .grid { display: grid; grid-template-columns: repeat(7, 32px); gap: 0; }
  .dow { font-size: 10px; color: var(--muted); text-align: center; height: 18px; font-weight: 600; }
  .day { position: relative; height: 30px; border: 0; background: none; color: var(--faint); font-size: 12px; font-variant-numeric: tabular-nums;
    padding: 0; border-radius: 0; }
  .day.has { color: var(--ink); font-weight: 550; }
  .day:hover { background: var(--sunk); }
  .day.in { background: var(--sunk); }
  .day.end { background: var(--ink); color: var(--panel); border-radius: 3px; }
  .day.today::after { content: ""; position: absolute; left: 9px; right: 9px; bottom: 3px; height: 1.5px; background: var(--focus); }
  .dot { position: absolute; top: 3px; right: 5px; width: 5px; height: 5px; border-radius: 50%; background: var(--ok); }
  .day.end .dot { background: var(--panel); }
  .dot.inline { position: static; display: inline-block; vertical-align: 1px; opacity: 1; }
  .foot { font-size: 11px; }
  @media (max-width: 760px) {
    .dr { position: static; }
    .pop { left: 12px; right: 12px; margin-top: 6px; top: auto; }
    .months { justify-content: center; flex-wrap: wrap; }
    .grid { grid-template-columns: repeat(7, minmax(0, 1fr)); }
    .month { width: 100%; }
  }
</style>
