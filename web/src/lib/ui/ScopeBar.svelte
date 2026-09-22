<script lang="ts">
  // Global scope: service dates, weekdays, hours, modes and the on-time window. Pages hide controls
  // that don't apply to them (see the IA board's scope matrix). All of it lives in the URL.
  import { router } from "../router.svelte";
  import { app } from "../app.svelte";
  import { dateLabel, MINUS } from "../format";
  import type { Snippet } from "svelte";
  import TimeOfDay, { rangeLabel, DAY } from "./TimeOfDay.svelte";
  import DateRange from "./DateRange.svelte";

  let { crumbs = [], show = ["dates", "days", "hours", "modes", "otp"], single = false, extra }: {
    crumbs?: [string, string | null][]; show?: string[]; single?: boolean; extra?: Snippet;
  } = $props();

  const days = $derived(app.days);
  // no dates in the URL = the whole span of history (single-day controls default to the latest day)
  const to = $derived(router.get("to"));
  const from = $derived(router.get("from"));
  const shownTo = $derived(to ?? app.latest ?? "");
  const dows = $derived(new Set((router.get("dows") ?? "").split("").map(Number).filter((x) => x >= 0 && x < 7)));
  const hours = $derived((router.get("h") ?? "").split("-").map(Number));
  const h0 = $derived(isFinite(hours[0]) && router.get("h") ? hours[0] : DAY[0]);
  const h1 = $derived(isFinite(hours[1]) && router.get("h") ? Math.min(hours[1], DAY[1]) : DAY[1]);
  const modes = $derived(new Set((router.get("modes") ?? "bus,lrt,streetcar,rail").split(",")));
  const MODES: [string, string][] = [["bus", "Bus"], ["lrt", "Light rail"], ["streetcar", "Streetcar"], ["rail", "FrontRunner"]];

  function setDow(d: number) {
    const s = new Set(dows);
    s.has(d) ? s.delete(d) : s.add(d);
    router.set({ dows: [...s].sort().join("") });
  }
  function setMode(m: string) {
    const s = new Set(modes);
    s.has(m) ? s.delete(m) : s.add(m);
    if (!s.size) return;
    router.set({ modes: s.size === 4 ? null : [...s].join(",") });
  }
  function setHours(a: number, b: number) {
    if (b <= a) b = a + 1;
    router.set({ h: a === DAY[0] && b === DAY[1] ? null : `${a}-${b}` });
  }
  const pad = (h: number) => String(h).padStart(2, "0");
  // phones: the controls fold behind one button that shows the current scope
  let open = $state(false);
</script>

<div class="scope">
  <nav aria-label="Breadcrumb" class="crumbs">
    {#each crumbs as [label, href], i}
      {#if i}<span class="sep">/</span>{/if}
      {#if href && i < crumbs.length - 1}<a {href}>{label}</a>{:else}<span class:last={i === crumbs.length - 1}>{label}</span>{/if}
    {/each}
  </nav>
  <div class="sp"></div>
  {#if show.length || extra}
    <button class="chip toggle" aria-expanded={open} onclick={() => (open = !open)}>Scope · {from || to ? `${from ? dateLabel(from).replace(/, \d{4}$/, "") + " – " : ""}${dateLabel(shownTo).replace(/, \d{4}$/, "")}` : "all dates"}{dows.size ? ` · ${dows.size} days` : ""}{router.get("h") ? ` · ${rangeLabel(h0, h1)}` : ""}</button>
  {/if}
  <div class="ctl" class:open>
  {#if show.includes("dates")}
    <div class="f"><span class="lab">{single ? "Date" : "Dates"}</span>
      <DateRange {from} {to} {days} {single} onchange={(f, t) => router.set({ from: single ? null : f, to: t })} />
    </div>
  {/if}
  {#if show.includes("days")}
    <div class="f"><span class="lab">Days</span>
      {#each "MTWTFSS".split("") as d, i}<button class="chip" aria-pressed={!dows.size || dows.has(i)} aria-label={["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"][i]} onclick={() => setDow(i)}>{d}</button>{/each}
    </div>
  {/if}
  {#if show.includes("hours")}
    <div class="f"><span class="lab">Time of day</span><TimeOfDay {h0} {h1} onchange={setHours} /></div>
  {/if}
  {#if show.includes("modes")}
    <div class="f"><span class="lab">Mode</span>
      {#each MODES as [m, label]}<button class="chip" aria-pressed={modes.has(m)} onclick={() => setMode(m)}>{label}</button>{/each}
    </div>
  {/if}
  {#if show.includes("otp")}
    <div class="f"><span class="lab">On time</span><span class="chip mono" title="Arrival within 1 min early to 5 min late">{MINUS}1 / +5 min</span></div>
  {/if}
  {#if extra}{@render extra()}{/if}
  </div>
</div>

<style>
  .scope { position: relative; background: var(--panel); border-bottom: 1px solid var(--border); min-height: 46px; display: flex; align-items: center; gap: 8px 18px;
    padding: 8px 20px; flex-wrap: wrap; }
  .crumbs { display: flex; gap: 8px; align-items: center; font-size: 13px; white-space: nowrap; color: var(--muted); }
  .crumbs a { color: var(--muted); }
  .crumbs .last { color: var(--ink); font-weight: 600; }
  .sep { color: var(--faint); }
  .sp { flex: 1; }
  .f { display: flex; align-items: center; gap: 4px; }
  .lab { font-size: 11px; color: var(--muted); text-transform: uppercase; letter-spacing: .06em; font-weight: 600; font-stretch: 90%;
    margin-right: 3px; white-space: nowrap; }
  .chip { min-width: 26px; justify-content: center; }
  .ctl { display: contents; }
  .toggle { display: none; }
  @media (max-width: 760px) {
    .scope { padding: 8px 12px; }
    .toggle { display: inline-flex; margin-left: auto; }
    .ctl { display: none; }
    .ctl.open { display: flex; flex-wrap: wrap; gap: 8px 14px; width: 100%; }
  }
</style>
