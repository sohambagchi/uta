<script lang="ts">
  // Live map: every vehicle on a trip, coloured by delay (diverging palette), pointed along its
  // bearing and animated between polls. Network lines grey, rail in UTA line colours.
  import { onMount } from "svelte";
  import * as maplibregl from "maplibre-gl";
  import type { GeoJSONSource, Map as MLMap } from "maplibre-gl";
  import type { Feature, FeatureCollection } from "geojson";
  import workerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url";
  import { api, type Vehicle, type LngLat } from "./api";
  import { app } from "./app.svelte";
  import { theme } from "./theme.svelte";
  import { delay as fmtDelay, epochClock, title } from "./format";
  import Tag from "./ui/Tag.svelte";
  import Info from "./ui/Info.svelte";

  maplibregl.setWorkerUrl(workerUrl);

  const STYLES = {
    light: "https://tiles.openfreemap.org/styles/positron",
    dark: "https://tiles.openfreemap.org/styles/dark",
  };
  const LIVE_EVERY_MS = 10_000;
  const ANIMATE_MS = 1200;
  const LINE_VARS = new Set(["701", "703", "704", "720", "750"]);

  // delay bins, same thresholds as dcol() in format.ts
  const BINS = [
    { key: "early", v: "--early", label: "< −1:00", test: (d: number) => d < -60 },
    { key: "ontime", v: "--ontime", label: "±1:00", test: (d: number) => d <= 60 },
    { key: "l1", v: "--late-1", label: "+1–3", test: (d: number) => d <= 180 },
    { key: "l2", v: "--late-2", label: "+3–5", test: (d: number) => d <= 300 },
    { key: "l3", v: "--late-3", label: "+5–10", test: (d: number) => d <= 600 },
    { key: "l4", v: "--late-4", label: "> +10", test: () => true },
  ];
  const binOf = (d: number | null) => (d == null ? null : BINS.find((b) => b.test(d))!);

  let container: HTMLDivElement;
  let map: MLMap | undefined;
  let styleReady = $state(false);
  let vehicles = $state<Vehicle[]>([]);
  let asOf = $state<number | null>(null);
  let liveError = $state(false);
  let loaded = $state(false);
  let selected: string | null = null;
  let popup: maplibregl.Popup | null = null;

  const pos = new Map<string, { from: LngLat; to: LngLat; cur: LngLat }>();
  let animStart = 0;
  let raf = 0;

  const css = (name: string) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  const colorOf = (d: number | null) => { const b = binOf(d); return b ? css(b.v) : css("--faint"); };
  const lineColorOf = (short: string | null | undefined, hex: string | null | undefined) =>
    short && LINE_VARS.has(short) ? css(`--line-${short}`) : hex ? `#${hex}` : css("--muted");

  const fc = (features: Feature[]): FeatureCollection => ({ type: "FeatureCollection", features });

  function source(id: string): GeoJSONSource | undefined {
    return styleReady ? (map?.getSource(id) as GeoJSONSource | undefined) : undefined;
  }

  function installLayers() {
    if (!map) return;
    for (const id of ["network", "vehicles"]) if (!map.getSource(id)) map.addSource(id, { type: "geojson", data: fc([]) });
    const panel = css("--panel");
    map.addLayer({ id: "network", type: "line", source: "network",
      layout: { "line-join": "round", "line-cap": "round", "line-sort-key": ["case", ["get", "rail"], 1, 0] },
      paint: {
        "line-color": ["case", ["get", "rail"], ["get", "color"], css("--muted")],
        "line-width": ["interpolate", ["linear"], ["zoom"], 9, ["case", ["get", "rail"], 2, 0.6], 14, ["case", ["get", "rail"], 4, 1.6]],
        "line-opacity": ["case", ["get", "rail"], 0.6, 0.3],
      } });
    map.addLayer({ id: "vehicles", type: "circle", source: "vehicles",
      paint: { "circle-radius": ["interpolate", ["linear"], ["zoom"], 9, 4, 15, 9], "circle-color": ["get", "color"],
        "circle-stroke-color": panel, "circle-stroke-width": 1.5 } });
    map.addLayer({ id: "vehicle-arrows", type: "symbol", source: "vehicles",
      filter: ["has", "bearing"], minzoom: 11,
      layout: { "icon-image": "arrow", "icon-size": ["interpolate", ["linear"], ["zoom"], 11, 0.45, 15, 0.8],
        "icon-rotate": ["get", "bearing"], "icon-rotation-alignment": "map", "icon-allow-overlap": true,
        "icon-ignore-placement": true } });
    styleReady = true;
    pushNetwork();
    pushVehicles(1);
  }

  function arrowImage(): ImageData {
    const s = 32, c = document.createElement("canvas");
    c.width = c.height = s;
    const g = c.getContext("2d")!;
    g.fillStyle = "#fff";
    g.beginPath();
    g.moveTo(s / 2, 6); g.lineTo(s - 9, s - 9); g.lineTo(s / 2, s - 13); g.lineTo(9, s - 9);
    g.closePath();
    g.fill();
    return g.getImageData(0, 0, s, s);
  }

  function pushNetwork() {
    const byId = new Map(app.routes.map((r) => [r.route_id, r]));
    source("network")?.setData(fc(app.lines.map((n) => {
      const r = byId.get(n.route_id);
      const rail = r != null && r.route_type !== 3;
      return { type: "Feature", properties: { rail, color: rail ? lineColorOf(r?.route_short_name, n.color) : "" },
        geometry: { type: "LineString", coordinates: n.coords } };
    })));
  }

  function pushVehicles(t: number) {
    const src = source("vehicles");
    if (!src) return;
    const e = t < 1 ? 1 - Math.pow(1 - t, 3) : 1;
    const feats: Feature[] = [];
    // on-time first so late vehicles draw on top
    const order = [...vehicles].sort((a, b) => (a.delay_s ?? 0) - (b.delay_s ?? 0));
    for (const v of order) {
      const p = pos.get(v.vehicle_id);
      if (!p) continue;
      p.cur = [p.from[0] + (p.to[0] - p.from[0]) * e, p.from[1] + (p.to[1] - p.from[1]) * e];
      const props: Record<string, unknown> = { id: v.vehicle_id, color: colorOf(v.delay_s) };
      if (v.bearing != null) props.bearing = v.bearing;
      feats.push({ type: "Feature", properties: props, geometry: { type: "Point", coordinates: p.cur } });
      if (v.vehicle_id === selected) popup?.setLngLat(p.cur);
    }
    src.setData(fc(feats));
  }

  function animate() {
    cancelAnimationFrame(raf);
    animStart = performance.now();
    const step = (now: number) => {
      const t = Math.min(1, (now - animStart) / ANIMATE_MS);
      pushVehicles(t);
      if (t < 1) raf = requestAnimationFrame(step);
    };
    raf = requestAnimationFrame(step);
  }

  async function refresh() {
    try {
      const d = await api.live();
      liveError = false;
      asOf = d.as_of;
      const seen = new Set<string>();
      for (const v of d.vehicles) {
        seen.add(v.vehicle_id);
        const to: LngLat = [v.lon, v.lat];
        const p = pos.get(v.vehicle_id);
        pos.set(v.vehicle_id, p ? { from: p.cur, to, cur: p.cur } : { from: to, to, cur: to });
      }
      for (const id of [...pos.keys()]) if (!seen.has(id)) pos.delete(id);
      vehicles = d.vehicles;
      if (selected && !seen.has(selected)) popup?.remove();
      else if (selected) popup?.setDOMContent(card(d.vehicles.find((v) => v.vehicle_id === selected)!));
      animate();
    } catch {
      liveError = true;
    }
    loaded = true;
  }

  function card(v: Vehicle): HTMLElement {
    const el = document.createElement("div");
    el.className = "lv-card";
    const add = (parent: HTMLElement, tag: string, cls: string, text = "") => {
      const e = document.createElement(tag);
      e.className = cls;
      e.textContent = text;
      parent.append(e);
      return e;
    };
    const head = add(el, "div", "lv-head");
    const rail = v.route_type != null && v.route_type !== 3;
    const b = add(head, "span", rail ? "lv-rb rail" : "lv-rb", v.route_short_name ?? "?");
    if (rail) b.style.background = lineColorOf(v.route_short_name, v.route_color);
    add(head, "strong", "", title(v.trip_headsign) || "");
    const st = add(el, "div", "lv-row");
    add(st, "span", "lv-dot").style.background = colorOf(v.delay_s);
    add(st, "b", "", v.delay_s == null ? "—" : fmtDelay(v.delay_s));
    add(st, "span", "lv-k", "at next stop");
    const ns = add(el, "div", "lv-row");
    add(ns, "span", "lv-k", "Next");
    add(ns, "span", "", v.next_stop_name ?? "—");
    const meta = add(el, "div", "lv-row lv-meta");
    add(meta, "span", "", `${v.vehicle_id}${v.speed != null ? ` · ${Math.round(v.speed * 2.237)} mph` : ""}`);
    const links = add(el, "div", "lv-links");
    const a1 = add(links, "a", "", "Vehicle →") as HTMLAnchorElement;
    a1.href = `#/vehicle/${encodeURIComponent(v.vehicle_id)}`;
    const a2 = add(links, "a", "", "Trip →") as HTMLAnchorElement;
    a2.href = `#/trip/${encodeURIComponent(v.trip_id)}`;
    return el;
  }

  const counts = $derived.by(() => {
    const m: Record<string, number> = {};
    for (const v of vehicles) { const k = binOf(v.delay_s)?.key ?? "none"; m[k] = (m[k] ?? 0) + 1; }
    return m;
  });

  $effect(() => { app.lines; app.routes; pushNetwork(); });

  let shownTheme = theme.current;
  $effect(() => {
    const t = theme.current;
    if (!map || t === shownTheme) return;
    shownTheme = t;
    styleReady = false;
    map.setStyle(STYLES[t]);
  });

  onMount(() => {
    app.loadNetwork();
    const m = new maplibregl.Map({
      container, style: STYLES[shownTheme], center: [-111.89, 40.68], zoom: 10,
      attributionControl: { compact: true },
    });
    map = m;
    m.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-left");
    m.setMissingStyleImageResolver((id) => {
      if (!m.hasImage(id)) m.addImage(id, { width: 1, height: 1, data: new Uint8Array(4) });
    });
    m.on("style.load", () => {
      if (!m.hasImage("arrow")) m.addImage("arrow", arrowImage(), { pixelRatio: 2 });
      installLayers();
    });
    m.on("click", "vehicles", (e) => {
      const id = e.features?.[0]?.properties?.id as string | undefined;
      const v = vehicles.find((x) => x.vehicle_id === id);
      if (!v) return;
      popup?.remove();
      selected = v.vehicle_id;
      popup = new maplibregl.Popup({ offset: 12, maxWidth: "280px" })
        .setLngLat(pos.get(v.vehicle_id)?.cur ?? [v.lon, v.lat]).setDOMContent(card(v)).addTo(m);
      popup.on("close", () => { if (selected === v.vehicle_id) selected = null; });
    });
    m.on("mouseenter", "vehicles", () => (m.getCanvas().style.cursor = "pointer"));
    m.on("mouseleave", "vehicles", () => (m.getCanvas().style.cursor = ""));
    const ro = new ResizeObserver(() => map?.resize());
    ro.observe(container);
    refresh();
    const timer = setInterval(refresh, LIVE_EVERY_MS);
    return () => {
      clearInterval(timer);
      cancelAnimationFrame(raf);
      ro.disconnect();
      map?.remove();
    };
  });
</script>

<div class="map" bind:this={container}></div>

<div class="legend">
  <div class="top">
    <span class="dot" class:off={liveError || !vehicles.length}></span>
    <b>{vehicles.length.toLocaleString("en-US")}</b><span class="k">vehicles</span>
    <span class="t mono">{asOf ? epochClock(asOf) : "—"}</span>
    <Info text="Vehicles on a trip in the collector's latest poll, coloured by predicted delay at their next stop. Updates every 10 s." />
  </div>
  {#if loaded && liveError}<Tag kind="bad">feed unavailable</Tag>
  {:else if loaded && !vehicles.length}<Tag kind="warn">collector not running</Tag>{/if}
  {#each BINS as b}
    <div class="r"><span class="sw" style:background="var({b.v})"></span><span class="lb">{b.label}</span><span class="n">{counts[b.key] ?? 0}</span></div>
  {/each}
  <div class="r"><span class="sw" style:background="var(--faint)"></span><span class="lb">no estimate</span><span class="n">{counts.none ?? 0}</span></div>
</div>

<style>
  .map { position: absolute; inset: 0; }
  .legend { position: absolute; left: 12px; bottom: 28px; background: var(--panel); border: 1px solid var(--border); border-radius: 6px;
    padding: 10px 12px; display: grid; gap: 4px; min-width: 190px; font-size: 12px; color: var(--ink-2); }
  .top { display: flex; align-items: center; gap: 6px; margin-bottom: 4px; }
  .top b { font-size: 18px; color: var(--ink); font-weight: 650; }
  .k { color: var(--muted); }
  .t { margin-left: auto; color: var(--muted); font-size: 11px; }
  .dot { width: 8px; height: 8px; border-radius: 50%; background: #35c46a; }
  .dot.off { background: var(--faint); }
  .r { display: flex; align-items: center; gap: 8px; }
  .sw { width: 10px; height: 10px; border-radius: 50%; flex: none; }
  .lb { flex: 1; }
  .n { font-variant-numeric: tabular-nums; color: var(--muted); }
  :global(.lv-card) { display: grid; gap: 5px; min-width: 200px; padding-right: 14px; }
  :global(.lv-head) { display: flex; align-items: center; gap: 8px; }
  :global(.lv-rb) { display: inline-flex; align-items: center; justify-content: center; min-width: 28px; height: 22px; padding: 0 4px;
    border-radius: 3px; border: 1.5px solid var(--ink); font-weight: 700; font-size: 11px; font-stretch: 85%; }
  :global(.lv-rb.rail) { border: 0; color: #fff; border-radius: 5px; }
  :global(.lv-row) { display: flex; align-items: center; gap: 7px; }
  :global(.lv-dot) { width: 10px; height: 10px; border-radius: 50%; flex: none; }
  :global(.lv-k) { color: var(--muted); }
  :global(.lv-meta) { color: var(--muted); font-family: var(--mono); font-size: 11px; }
  :global(.lv-links) { display: flex; gap: 14px; margin-top: 2px; font-weight: 600; }
  @media (max-width: 600px) { .legend { display: none; } }
</style>
