<script lang="ts">
  import { onMount } from "svelte";
  import * as maplibregl from "maplibre-gl";
  import type { GeoJSONSource, Map as MLMap } from "maplibre-gl";
  import type { Feature, FeatureCollection } from "geojson";
  // MapLibre 6 loads its tile worker from a separate module; bundle it and point MapLibre at it.
  import workerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url";
  import { api, type NetworkLine, type Vehicle, type LngLat } from "./api";
  import { store } from "./store.svelte";
  import { fmtSignedMin } from "./format";

  maplibregl.setWorkerUrl(workerUrl);

  // Vector basemap tiles are the only third-party resource (OpenFreeMap, no key).
  const STYLES = {
    light: "https://tiles.openfreemap.org/styles/positron",
    dark: "https://tiles.openfreemap.org/styles/dark",
  };
  const LIVE_EVERY_MS = 15_000;
  const ANIMATE_MS = 1200;

  // Delay status: reserved status colors, always paired with a label in the legend/popup.
  const STATUS = [
    { key: "early", label: "Early > 1 min", color: "#fab219", test: (d: number) => d < -60 },
    { key: "ok", label: "On time", color: "#0ca30c", test: (d: number) => d <= 300 },
    { key: "late", label: "Late 5–10 min", color: "#ec835a", test: (d: number) => d <= 600 },
    { key: "vlate", label: "Late > 10 min", color: "#d03b3b", test: () => true },
  ];
  const NO_DATA = { key: "none", label: "No prediction", color: "#898781" };
  const statusOf = (d: number | null) => (d == null ? NO_DATA : STATUS.find((s) => s.test(d))!);

  let container: HTMLDivElement;
  let map: MLMap | undefined;
  let styleReady = $state(false);
  let dark = $state(matchMedia("(prefers-color-scheme: dark)").matches);
  let vehicleScope = $state<"compared" | "all">("all");
  let showNetwork = $state(true);
  let network: NetworkLine[] = [];
  let vehicles = $state<Vehicle[]>([]);
  let asOf = $state<number | null>(null);
  let liveError = $state(false);
  let selectedVehicle: string | null = null;
  let popup: maplibregl.Popup | null = null;

  // animated positions
  const pos = new Map<string, { from: LngLat; to: LngLat; cur: LngLat }>();
  let animStart = 0;
  let raf = 0;

  function css(name: string): string {
    return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  }
  const seriesColor = (slot: number) => css(`--series-${slot + 1}`);

  const comparedRoutes = $derived(new Set(store.comparisons.map((c) => c.routeId).filter(Boolean)));

  // ------------------------------------------------------------ layers

  function installLayers() {
    if (!map) return;
    const empty = { type: "FeatureCollection", features: [] } as FeatureCollection;
    for (const id of ["network", "route", "segments", "stations", "vehicles"]) {
      if (!map.getSource(id)) map.addSource(id, { type: "geojson", data: empty });
    }
    const ink2 = css("--ink-2"), surface = css("--surface");
    map.addLayer({ id: "network", type: "line", source: "network",
      layout: { "line-join": "round", "line-cap": "round" },
      paint: { "line-color": css("--muted"), "line-width": ["interpolate", ["linear"], ["zoom"], 9, 0.6, 14, 1.6], "line-opacity": 0.45 } });
    map.addLayer({ id: "route", type: "line", source: "route",
      layout: { "line-join": "round", "line-cap": "round" },
      paint: { "line-color": ink2, "line-width": ["interpolate", ["linear"], ["zoom"], 9, 1.5, 15, 4], "line-opacity": 0.55 } });
    map.addLayer({ id: "segments-casing", type: "line", source: "segments",
      layout: { "line-join": "round", "line-cap": "round" },
      paint: { "line-color": surface, "line-width": ["interpolate", ["linear"], ["zoom"], 9, 5, 15, 11] } });
    map.addLayer({ id: "segments", type: "line", source: "segments",
      layout: { "line-join": "round", "line-cap": "round" },
      paint: { "line-color": ["get", "color"], "line-width": ["interpolate", ["linear"], ["zoom"], 9, 3, 15, 7],
        "line-offset": ["get", "offset"] } });
    map.addLayer({ id: "stations", type: "circle", source: "stations",
      paint: {
        "circle-radius": ["interpolate", ["linear"], ["zoom"],
          10, ["case", ["get", "end"], 6, ["get", "hover"], 5, 2.5],
          15, ["case", ["get", "end"], 8, ["get", "hover"], 7, 4.5]],
        "circle-color": ["case", ["get", "end"], ["get", "color"], surface],
        "circle-stroke-color": ["case", ["get", "end"], surface, ["get", "between"], ["get", "color"], ink2],
        "circle-stroke-width": ["case", ["get", "end"], 2.5, 1.5],
      } });
    map.addLayer({ id: "station-labels", type: "symbol", source: "stations",
      minzoom: 13,
      filter: ["any", [">=", ["zoom"], 14.5], ["get", "end"], ["get", "hover"]],
      layout: { "text-field": ["get", "name"], "text-font": ["Noto Sans Regular"], "text-size": 11,
        "text-offset": [0.9, 0], "text-anchor": "left", "text-optional": true },
      paint: { "text-color": css("--ink"), "text-halo-color": surface, "text-halo-width": 1.5 } });
    map.addLayer({ id: "vehicles-other", type: "circle", source: "vehicles",
      filter: ["!", ["get", "compared"]],
      paint: { "circle-radius": ["interpolate", ["linear"], ["zoom"], 9, 2, 15, 4.5], "circle-color": css("--muted"),
        "circle-opacity": 0.75, "circle-stroke-color": surface, "circle-stroke-width": 1 } });
    map.addLayer({ id: "vehicles", type: "circle", source: "vehicles",
      filter: ["get", "compared"],
      paint: { "circle-radius": ["interpolate", ["linear"], ["zoom"], 9, 5, 15, 9], "circle-color": ["get", "color"],
        "circle-stroke-color": surface, "circle-stroke-width": 2 } });
    map.addLayer({ id: "vehicle-arrows", type: "symbol", source: "vehicles",
      filter: ["all", ["get", "compared"], ["has", "bearing"]],
      layout: { "icon-image": "arrow", "icon-size": ["interpolate", ["linear"], ["zoom"], 9, 0.45, 15, 0.8],
        "icon-rotate": ["get", "bearing"], "icon-rotation-alignment": "map", "icon-allow-overlap": true,
        "icon-ignore-placement": true } });
    styleReady = true;
    pushNetwork();
    pushRoute();
    pushSegments();
    pushStations();
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

  function source(id: string): GeoJSONSource | undefined {
    return styleReady ? (map?.getSource(id) as GeoJSONSource | undefined) : undefined;
  }
  const line = (coords: LngLat[], props: Record<string, unknown> = {}): Feature => (
    { type: "Feature", properties: props, geometry: { type: "LineString", coordinates: coords } });
  const fc = (features: Feature[]): FeatureCollection => ({ type: "FeatureCollection", features });

  function pushNetwork() {
    source("network")?.setData(fc(showNetwork ? network.map((n) => line(n.coords)) : []));
  }
  function pushRoute() {
    const shape = store.direction(store.active)?.shape;
    source("route")?.setData(fc(shape?.length ? [line(shape)] : []));
  }
  function pushSegments() {
    const feats: Feature[] = [];
    // comparisons sharing a road are offset side by side so each stays visible
    const shown = store.comparisons.map((c) => ({ c, s: store.segment(c) }))
      .filter((x) => x.s?.status === "ok" && x.s.data.geometry.length > 1);
    shown.forEach(({ c, s }, k) => {
      if (s?.status !== "ok") return;
      const offset = shown.length > 1 ? (k - (shown.length - 1) / 2) * 5 : 0;
      feats.push(line(s.data.geometry, { color: seriesColor(c.slot), offset }));
    });
    source("segments")?.setData(fc(feats));
  }
  function pushStations() {
    const c = store.active;
    const dir = store.direction(c);
    const st = dir?.stations ?? [];
    const fi = st.findIndex((s) => s.station_id === c?.from), ti = st.findIndex((s) => s.station_id === c?.to);
    const color = c ? seriesColor(c.slot) : "";
    source("stations")?.setData(fc(st.map((s, i) => ({
      type: "Feature",
      properties: {
        id: s.station_id, name: s.name, color,
        end: i === fi || i === ti,
        between: fi >= 0 && ti > fi && i > fi && i < ti,
        hover: store.hoverStation === s.station_id,
      },
      geometry: { type: "Point", coordinates: [s.lon, s.lat] },
    }))));
  }

  function pushVehicles(t: number) {
    const src = source("vehicles");
    if (!src) return;
    const e = t < 1 ? 1 - Math.pow(1 - t, 3) : 1;   // ease-out
    const feats: Feature[] = [];
    for (const v of vehicles) {
      const p = pos.get(v.vehicle_id);
      if (!p) continue;
      p.cur = [p.from[0] + (p.to[0] - p.from[0]) * e, p.from[1] + (p.to[1] - p.from[1]) * e];
      const compared = comparedRoutes.has(v.route_id ?? "");
      if (vehicleScope === "compared" && !compared) continue;
      const props: Record<string, unknown> = { id: v.vehicle_id, compared, color: statusOf(v.delay_s).color };
      if (v.bearing != null) props.bearing = v.bearing;
      feats.push({ type: "Feature", properties: props, geometry: { type: "Point", coordinates: p.cur } });
      if (v.vehicle_id === selectedVehicle) popup?.setLngLat(p.cur);
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

  // ------------------------------------------------------------ live data

  async function refreshLive() {
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
      if (selectedVehicle && !seen.has(selectedVehicle)) popup?.remove();
      else if (selectedVehicle) popup?.setDOMContent(vehicleCard(d.vehicles.find((v) => v.vehicle_id === selectedVehicle)!));
      animate();
    } catch {
      liveError = true;
    }
  }

  function vehicleCard(v: Vehicle): HTMLElement {
    const el = document.createElement("div");
    const s = statusOf(v.delay_s);
    const age = Math.max(0, Math.round(Date.now() / 1000 - v.ts));
    const rows: [string, string][] = [
      [`Route ${v.route_short_name ?? "?"}`, v.trip_headsign ? `→ ${v.trip_headsign}` : ""],
      [v.delay_s == null ? "No prediction" : `${fmtSignedMin(v.delay_s)} min`, v.delay_s == null ? "" : s.label.toLowerCase()],
      ["Next stop", v.next_stop_name ?? "–"],
      [`Vehicle ${v.vehicle_id}`, `${v.speed != null ? Math.round(v.speed * 2.237) + " mph · " : ""}${age}s ago`],
    ];
    for (const [a, b] of rows) {
      const r = document.createElement("div");
      const strong = document.createElement("strong");
      strong.textContent = a;
      const span = document.createElement("span");
      span.style.color = "var(--ink-2)";
      span.textContent = b ? " " + b : "";
      r.append(strong, span);
      el.append(r);
    }
    return el;
  }

  // ------------------------------------------------------------ focus

  let handledFocus = 0;
  function fit(coords: LngLat[]) {
    if (!map || coords.length < 2) return;
    const b = new maplibregl.LngLatBounds(coords[0], coords[0]);
    for (const c of coords) b.extend(c);
    map.fitBounds(b, { padding: 60, maxZoom: 15.5, duration: 700 });
  }
  /** Geometry to frame for a comparison, or null while its segment is still loading. */
  function framing(c: (typeof store.comparisons)[number]): LngLat[] | null {
    const seg = store.segment(c);
    if (c.from && c.to && seg?.status === "loading") return null;
    if (seg?.status === "ok" && seg.data.geometry.length > 1) return seg.data.geometry;
    if (c.routeId && !store.direction(c)) return c.routeId && store.details[c.routeId]?.status === "error" ? [] : null;
    return store.direction(c)?.shape ?? [];
  }
  $effect(() => {
    const req = store.focusRequest;
    if (!req || req.n === handledFocus || !styleReady) return;
    const targets = req.id === -1 ? store.comparisons.filter((c) => c.routeId) : store.comparisons.filter((c) => c.id === req.id);
    const parts = targets.map(framing);
    if (parts.some((p) => p === null)) return;   // wait for geometry
    fit(parts.flat() as LngLat[]);
    handledFocus = req.n;
  });

  // ------------------------------------------------------------ reactive pushes

  $effect(() => { store.active; store.active?.directionId; store.active?.routeId; store.details; pushRoute(); });
  $effect(() => {
    for (const c of store.comparisons) { c.routeId; c.from; c.to; c.slot; store.segment(c)?.status; }
    pushSegments();
  });
  $effect(() => {
    store.active?.from; store.active?.to; store.active?.slot; store.hoverStation; store.details; pushStations();
  });
  $effect(() => { vehicleScope; comparedRoutes; pushVehicles(1); });
  $effect(() => { showNetwork; pushNetwork(); });

  const counts = $derived.by(() => {
    const m: Record<string, number> = {};
    for (const v of vehicles) {
      if (!comparedRoutes.has(v.route_id ?? "")) continue;
      const k = statusOf(v.delay_s).key;
      m[k] = (m[k] ?? 0) + 1;
    }
    return m;
  });

  // ------------------------------------------------------------ lifecycle

  onMount(() => {
    const mq = matchMedia("(prefers-color-scheme: dark)");
    const m = new maplibregl.Map({
      container, style: dark ? STYLES.dark : STYLES.light, center: [-111.89, 40.68], zoom: 10,
      attributionControl: { compact: true },
    });
    map = m;
    m.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-left");
    // basemap styles occasionally reference sprite images they don't ship; draw nothing for those
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
      selectedVehicle = v.vehicle_id;
      popup = new maplibregl.Popup({ offset: 12, maxWidth: "280px" })
        .setLngLat(pos.get(v.vehicle_id)?.cur ?? [v.lon, v.lat]).setDOMContent(vehicleCard(v)).addTo(m);
      popup.on("close", () => { if (selectedVehicle === v.vehicle_id) selectedVehicle = null; });
    });
    m.on("click", "stations", (e) => {
      const id = e.features?.[0]?.properties?.id as string | undefined;
      if (id && store.active) store.pickStation(store.active, id);
    });
    for (const layer of ["vehicles", "stations"]) {
      m.on("mouseenter", layer, () => (m.getCanvas().style.cursor = "pointer"));
      m.on("mouseleave", layer, () => (m.getCanvas().style.cursor = ""));
    }
    m.on("mousemove", "stations", (e) => {
      store.hoverStation = (e.features?.[0]?.properties?.id as string) ?? null;
    });
    m.on("mouseleave", "stations", () => (store.hoverStation = null));

    const onScheme = (e: MediaQueryListEvent) => {
      dark = e.matches;
      styleReady = false;
      map?.setStyle(dark ? STYLES.dark : STYLES.light);
    };
    mq.addEventListener("change", onScheme);
    const ro = new ResizeObserver(() => map?.resize());
    ro.observe(container);

    api.network().then((n) => { network = n; pushNetwork(); }).catch(() => {});
    refreshLive();
    const timer = setInterval(refreshLive, LIVE_EVERY_MS);
    return () => {
      clearInterval(timer);
      cancelAnimationFrame(raf);
      mq.removeEventListener("change", onScheme);
      ro.disconnect();
      map?.remove();
    };
  });
</script>

<div class="map" bind:this={container}></div>

<div class="controls">
  <div class="seg" role="group" aria-label="Vehicles shown">
    <button aria-pressed={vehicleScope === "all"} onclick={() => (vehicleScope = "all")}>All vehicles</button>
    <button aria-pressed={vehicleScope === "compared"} onclick={() => (vehicleScope = "compared")}>Compared routes</button>
  </div>
  <label class="small"><input type="checkbox" bind:checked={showNetwork} /> All route lines</label>
</div>

<div class="legend small" aria-label="Vehicle delay legend">
  <div class="title">Vehicles on compared routes</div>
  {#each [...STATUS, NO_DATA] as s}
    <div><span class="dotk" style:background={s.color}></span>{s.label} <span class="muted">{counts[s.key] ?? 0}</span></div>
  {/each}
  <div><span class="dotk other"></span>Other routes</div>
  <div class="muted asof">
    {#if liveError}Live feed unavailable
    {:else if asOf}{vehicles.length} active · as of {new Date(asOf * 1000).toLocaleTimeString()}
    {:else}No active vehicles. Is the collector running?{/if}
  </div>
</div>

<style>
  .map { position: absolute; inset: 0; }
  .controls { position: absolute; top: 10px; right: 10px; display: flex; gap: 10px; align-items: center;
    background: var(--surface); border: 1px solid var(--border); border-radius: 10px; padding: 6px 8px;
    box-shadow: 0 2px 10px rgba(0,0,0,.08); flex-wrap: wrap; justify-content: flex-end; max-width: calc(100% - 80px); }
  .controls label { display: flex; gap: 4px; align-items: center; color: var(--ink-2); white-space: nowrap; }
  .legend { position: absolute; left: 10px; bottom: 26px; background: var(--surface); border: 1px solid var(--border);
    border-radius: 10px; padding: 8px 10px; display: grid; gap: 2px; color: var(--ink-2);
    box-shadow: 0 2px 10px rgba(0,0,0,.08); }
  .legend .title { font-weight: 600; color: var(--ink); margin-bottom: 2px; }
  .dotk { display: inline-block; width: 10px; height: 10px; border-radius: 50%; margin-right: 6px; vertical-align: -1px;
    box-shadow: 0 0 0 2px var(--surface); }
  .dotk.other { width: 7px; height: 7px; margin: 0 7.5px 0 1.5px; background: var(--muted); opacity: .75; }
  .asof { margin-top: 4px; font-size: 11px; }
  @media (max-width: 600px) { .legend { display: none; } }
</style>
