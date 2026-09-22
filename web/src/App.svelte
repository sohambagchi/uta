<script lang="ts">
  import { onMount } from "svelte";
  import { api, type Status } from "./lib/api";
  import { store } from "./lib/store.svelte";
  import Sidebar from "./lib/Sidebar.svelte";
  import MapView from "./lib/MapView.svelte";
  import Analysis from "./lib/Analysis.svelte";

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
    return () => clearInterval(t);
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
    if (statusError) return { cls: "bad", label: "API unreachable" };
    if (age == null) return { cls: "off", label: "Collector never ran" };
    if (age < 120) return { cls: "ok", label: "Collector live" };
    if (age < 900) return { cls: "warn", label: `Last poll ${Math.round(age / 60)} min ago` };
    return { cls: "bad", label: `Collector stopped ${Math.round(age / 3600)} h ago` };
  });

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
    <span class="logo" aria-hidden="true"></span>
    <h1>UTA Transit Explorer</h1>
  </div>
  <div class="status" title="Collector status">
    <span><span class="dot {collector.cls}"></span>{collector.label}</span>
    {#if status}
      <span>{status.active_vehicles.toLocaleString()} vehicles active</span>
      <span class="muted">{status.observed.trips.toLocaleString()} trips observed{status.observed.first ? ` since ${status.observed.first}` : ""}</span>
      <span class="muted">GTFS {status.gtfs_feed_version ?? "not imported"}</span>
    {/if}
  </div>
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
      tabindex="0" onpointerdown={startResize} onkeydown={resizeKey}></div>
    <div class="analysis">
      {#if ready}<Analysis />{/if}
    </div>
  </main>
</div>

<style>
  .top {
    height: 48px; display: flex; align-items: center; gap: 24px; padding: 0 20px;
    background: var(--surface); border-bottom: 1px solid var(--border); overflow: hidden;
  }
  .brand { display: flex; align-items: center; gap: 10px; white-space: nowrap; }
  .logo { width: 20px; height: 20px; border-radius: 6px; background: var(--accent);
    box-shadow: inset 0 -6px 0 rgba(0, 0, 0, .18); }
  .status { margin-left: auto; display: flex; gap: 16px; font-size: 12px; color: var(--ink-2);
    overflow: hidden; white-space: nowrap; }
  .dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-right: 6px; background: var(--no-data); }
  .dot.ok { background: var(--good); }
  .dot.warn { background: var(--warning); }
  .dot.bad { background: var(--critical); }

  .layout { display: grid; grid-template-columns: var(--sidebar-w) minmax(0, 1fr); height: calc(100vh - 48px); }
  .side { border-right: 1px solid var(--border); background: var(--surface); overflow: auto; }
  .pad { padding: 16px; }
  .main { display: flex; flex-direction: column; min-width: 0; min-height: 0; }
  .map-wrap { position: relative; flex: none; }
  .resizer { flex: none; height: 8px; cursor: row-resize; background: var(--surface-2);
    border-block: 1px solid var(--border); }
  .resizer:hover, .resizer:focus-visible { background: var(--grid); }
  .analysis { flex: 1; overflow: auto; min-height: 0; }

  @media (max-width: 900px) {
    .top { padding: 0 16px; }
    .status span:nth-child(n + 3) { display: none; }
    .layout { display: block; height: auto; }
    .side { border-right: 0; border-bottom: 1px solid var(--border); max-height: 60vh; }
    .analysis { overflow: visible; }
    .map-wrap { height: 60vh !important; }
    .resizer { display: none; }
  }
</style>
