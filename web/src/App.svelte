<script lang="ts">
  import { onMount } from "svelte";
  import { api, type Status } from "./lib/api";
  import { store } from "./lib/store.svelte";
  import Sidebar from "./lib/Sidebar.svelte";
  import MapView from "./lib/MapView.svelte";
  import Analysis from "./lib/Analysis.svelte";
  import { theme } from "./lib/theme.svelte";

  let status = $state<Status | null>(null);
  let statusError = $state(false);
  let ready = $state(false);
  let mapHeight = $state(Math.round(window.innerHeight * 0.46));

  async function refreshStatus() {
    try {
      status = await api.status();
      statusError = false;
    } catch {
      statusError = true;
    }
  }

  onMount(() => {
    store.fromHash(location.hash);
    store.loadRoutes().then(() => (ready = true));
    refreshStatus();
    const t = setInterval(refreshStatus, 30_000);
    // edited URL / back-forward: our own replaceState calls don't fire this
    const onHash = () => { if (location.hash.replace(/^#/, "") !== store.toHash()) store.fromHash(location.hash); };
    addEventListener("hashchange", onHash);
    return () => { clearInterval(t); removeEventListener("hashchange", onHash); };
  });

  // fetch segments for complete comparisons
  $effect(() => {
    for (const c of store.comparisons) {
      if (store.segmentKey(c)) store.loadSegment(c);
    }
  });

  // keep the URL in sync
  $effect(() => {
    const h = store.toHash();
    if (ready || h) history.replaceState(null, "", h ? "#" + h : location.pathname);
  });

  const collector = $derived.by(() => {
    const age = status?.last_ok_poll_age_s;
    if (statusError) return { cls: "bad", label: "Can't reach the server" };
    if (age == null) return { cls: "off", label: "Collector hasn't run yet" };
    if (age < 120) return { cls: "ok", label: "Live" };
    if (age < 900) return { cls: "warn", label: `Updated ${Math.round(age / 60)} min ago` };
    return { cls: "bad", label: `Collector stopped ${Math.round(age / 3600)} h ago` };
  });
  const since = $derived(status?.observed.first
    ? new Date(status.observed.first + "T12:00").toLocaleDateString(undefined, { month: "short", day: "numeric" }) : null);

  function startResize(e: PointerEvent) {
    const startY = e.clientY, startH = mapHeight;
    const el = e.currentTarget as HTMLElement;
    el.setPointerCapture(e.pointerId);
    const move = (ev: PointerEvent) => {
      mapHeight = Math.max(200, Math.min(window.innerHeight - 160, startH + ev.clientY - startY));
    };
    const up = () => { el.removeEventListener("pointermove", move); el.removeEventListener("pointerup", up); };
    el.addEventListener("pointermove", move);
    el.addEventListener("pointerup", up);
  }
  function resizeKey(e: KeyboardEvent) {
    if (e.key === "ArrowUp") mapHeight = Math.max(200, mapHeight - 40);
    else if (e.key === "ArrowDown") mapHeight = Math.min(window.innerHeight - 160, mapHeight + 40);
    else return;
    e.preventDefault();
  }
</script>

<header class="top">
  <div class="brand">
    <span class="logo" aria-hidden="true">
      <span class="bullet sm" style:--c="var(--series-1)">U</span><span class="bullet sm" style:--c="var(--series-2)">T</span><span class="bullet sm" style:--c="var(--series-3)">A</span>
    </span>
    <div>
      <h1>Transit Explorer</h1>
      <p class="tagline">How long does the ride really take?</p>
    </div>
  </div>
  <div class="status" title={status ? `Timetable: GTFS ${status.gtfs_feed_version ?? "not imported"}` : "Collector status"}>
    <span class="pill {collector.cls}"><span class="dot"></span>{collector.label}</span>
    {#if status}
      <span class="pill"><strong>{status.active_vehicles.toLocaleString()}</strong>&nbsp;vehicles out now</span>
      <span class="pill quiet"><strong>{status.observed.trips.toLocaleString()}</strong>&nbsp;trips logged{since ? ` since ${since}` : ""}</span>
    {/if}
  </div>
  <button class="theme" onclick={() => theme.toggle()} aria-label="Switch to {theme.current === 'dark' ? 'light' : 'dark'} mode"
    title="Switch to {theme.current === 'dark' ? 'light' : 'dark'} mode">
    {#if theme.current === "dark"}
      <svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="4.5" /><path d="M12 2v2.5M12 19.5V22M2 12h2.5M19.5 12H22M4.9 4.9l1.8 1.8M17.3 17.3l1.8 1.8M4.9 19.1l1.8-1.8M17.3 6.7l1.8-1.8" /></svg>
    {:else}
      <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5Z" /></svg>
    {/if}
  </button>
</header>

<div class="layout">
  <aside class="side">
    {#if ready}<Sidebar />{:else}<p class="muted pad">Loading routes…</p>{/if}
  </aside>
  <main class="main">
    <div class="map-wrap" style:height="{mapHeight}px">
      <MapView />
    </div>
    <!-- svelte-ignore a11y_no_noninteractive_tabindex, a11y_no_noninteractive_element_interactions -->
    <div class="resizer" role="separator" aria-orientation="horizontal" aria-label="Resize map (arrow keys)"
      tabindex="0" onpointerdown={startResize} onkeydown={resizeKey}><span class="grip"></span></div>
    <div class="analysis">
      {#if ready}<Analysis />{/if}
    </div>
  </main>
</div>

<style>
  .top {
    height: var(--header-h); display: flex; align-items: center; gap: 24px; padding: 0 20px;
    background: var(--sign); color: var(--sign-ink); overflow: hidden; position: relative;
  }
  /* the thin white pinstripe along the top of subway station signs */
  .top::before { content: ""; position: absolute; left: 0; right: 0; top: 5px; height: 1.5px; background: rgba(255, 255, 255, .55); }
  .brand { display: flex; align-items: center; gap: 12px; white-space: nowrap; }
  .logo { display: flex; gap: 3px; }
  .brand h1 { font-size: 18px; line-height: 1.15; }
  .tagline { font-size: 12px; color: var(--sign-ink-2); }
  .status { margin-left: auto; display: flex; gap: 8px; font-size: 12.5px; overflow: hidden; white-space: nowrap; }
  .pill { display: inline-flex; align-items: center; gap: 7px; padding: 5px 12px; border-radius: 999px;
    background: rgba(255, 255, 255, .1); color: var(--sign-ink); }
  .pill.quiet { background: none; color: var(--sign-ink-2); }
  .pill strong { font-weight: 700; color: var(--sign-ink); }
  .dot { width: 8px; height: 8px; border-radius: 50%; background: var(--no-data); flex: none; }
  .ok .dot { background: var(--good); box-shadow: 0 0 0 0 var(--good); animation: pulse 2.4s infinite; }
  .warn .dot { background: var(--warning); }
  .bad .dot { background: var(--critical); }
  @keyframes pulse {
    0% { box-shadow: 0 0 0 0 color-mix(in srgb, var(--good) 70%, transparent); }
    70%, 100% { box-shadow: 0 0 0 7px transparent; }
  }
  @media (prefers-reduced-motion: reduce) { .ok .dot { animation: none; } }
  .theme { flex: none; display: grid; place-items: center; width: 36px; height: 36px; border-radius: 50%; border: 0;
    background: rgba(255, 255, 255, .1); color: var(--sign-ink); transition: background .15s; }
  .theme:hover { background: rgba(255, 255, 255, .2); }
  .theme svg { width: 18px; height: 18px; fill: none; stroke: currentColor; stroke-width: 1.8; stroke-linecap: round; stroke-linejoin: round; }

  .layout { display: grid; grid-template-columns: var(--sidebar-w) minmax(0, 1fr); height: calc(100vh - var(--header-h)); }
  .side { border-right: 1px solid var(--border); background: var(--surface); overflow: auto; }
  .pad { padding: 20px; }
  .main { display: flex; flex-direction: column; min-width: 0; min-height: 0; }
  .map-wrap { position: relative; flex: none; }
  .resizer { flex: none; height: 12px; cursor: row-resize; background: var(--page); display: grid; place-items: center;
    border-top: 1px solid var(--border); }
  .grip { width: 44px; height: 4px; border-radius: 2px; background: var(--axis); transition: background .15s, width .15s; }
  .resizer:hover .grip, .resizer:focus-visible .grip { background: var(--muted); width: 60px; }
  .analysis { flex: 1; overflow: auto; min-height: 0; }

  @media (max-width: 1100px) { .pill.quiet { display: none; } }
  @media (max-width: 900px) {
    .top { padding: 0 16px; gap: 12px; }
    .tagline { display: none; }
    .status .pill:nth-child(n + 2) { display: none; }
    .layout { display: block; height: auto; }
    .side { border-right: 0; border-bottom: 1px solid var(--border); max-height: 60vh; }
    .analysis { overflow: visible; }
    .map-wrap { height: 60vh !important; }
    .resizer { display: none; }
  }
  @media (max-width: 480px) { .logo { display: none; } }
</style>
