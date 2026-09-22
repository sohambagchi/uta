<script lang="ts">
  import { onMount } from "svelte";
  import { router } from "./lib/router.svelte";
  import { app } from "./lib/app.svelte";
  import { theme } from "./lib/theme.svelte";
  import Tooltip from "./lib/ui/Tooltip.svelte";
  import Network from "./pages/Network.svelte";
  import Routes from "./pages/Routes.svelte";
  import Route from "./pages/Route.svelte";
  import Compare from "./pages/Compare.svelte";
  import Stations from "./pages/Stations.svelte";
  import Station from "./pages/Station.svelte";
  import Trips from "./pages/Trips.svelte";
  import Trip from "./pages/Trip.svelte";
  import Vehicle from "./pages/Vehicle.svelte";
  import Health from "./pages/Health.svelte";
  import Live from "./pages/Live.svelte";

  const NAV: [string, string, string[]][] = [
    ["Network", "network", ["network"]], ["Routes", "routes", ["routes"]], ["Compare", "compare", ["compare"]],
    ["Stations", "stations", ["stations"]], ["Trips & vehicles", "trips", ["trips", "trip", "vehicle"]],
    ["Data health", "health", ["health"]], ["Live", "live", ["live"]],
  ];

  onMount(() => {
    // old bookmarks (#c=...) were comparison views
    if (location.hash && !location.hash.startsWith("#/")) location.hash = "#/compare?" + location.hash.slice(1);
    app.refresh();
    const t = setInterval(() => app.refresh(), 15_000);
    return () => clearInterval(t);
  });

  const page = $derived(router.route.page);
  const parts = $derived(router.route.parts);
  const c = $derived(app.collector);
  // phones: the nav folds into a menu; any navigation closes it
  let menu = $state(false);
  $effect(() => { router.route; menu = false; });
  const current = $derived(NAV.find(([, , pages]) => pages.includes(page))?.[0] ?? "Network");
</script>

<header class="top">
  <a class="brand" href="#/network">
    <span class="ring"><span></span></span><span class="name">UTA TRANSIT EXPLORER</span>
  </a>
  <button class="menu-btn" aria-expanded={menu} aria-controls="primary-nav" onclick={() => (menu = !menu)}>
    <svg width="16" height="12" aria-hidden="true"><path d="M0 1H16M0 6H16M0 11H16" stroke="currentColor" stroke-width="2" /></svg>{current}
  </button>
  <nav aria-label="Primary" id="primary-nav" class:open={menu}>
    {#each NAV as [label, path, pages]}
      <a href={router.href(path)} class:on={pages.includes(page)} aria-current={pages.includes(page) ? "page" : undefined}>{label}</a>
    {/each}
  </nav>
  <div class="status" title={app.status?.gtfs_feed_version ? `Timetable ${app.status.gtfs_feed_version}` : ""}>
    <span class="dot {c.cls}"></span>{c.label}
  </div>
  <button class="theme" onclick={() => theme.toggle()}>{theme.current === "dark" ? "Light" : "Dark"}</button>
</header>
{#if c.stale && app.status}
  <div class="banner"><b>Stale</b><span>{c.label.replace("Stale · ", "")}</span><span>Live hidden</span><span class="sp"></span><a href={router.href("health")}>Data health</a></div>
{/if}

<main>
  {#if page === "network"}<Network />
  {:else if page === "routes" && parts.length >= 1}{#key parts.join("/")}<Route routeId={parts[0]} dir={Number(parts[1] ?? 0)} />{/key}
  {:else if page === "routes"}<Routes />
  {:else if page === "compare"}<Compare />
  {:else if page === "stations" && parts.length}{#key parts[0]}<Station stationId={parts[0]} />{/key}
  {:else if page === "stations"}<Stations />
  {:else if page === "trip" && parts.length}{#key parts[0]}<Trip tripId={parts[0]} />{/key}
  {:else if page === "vehicle" && parts.length}{#key parts[0]}<Vehicle vehicleId={parts[0]} />{/key}
  {:else if page === "trips"}<Trips />
  {:else if page === "health"}<Health />
  {:else if page === "live"}<Live />
  {:else}<Network />{/if}
</main>
<Tooltip />

<style>
  .top { height: var(--header-h); background: var(--sign); color: var(--sign-ink); display: flex; align-items: stretch; gap: 20px; padding: 0 20px;
    box-shadow: inset 0 -1px 0 #ffffff26; position: sticky; top: 0; z-index: 20; }
  .brand { display: flex; align-items: center; gap: 10px; color: #fff; text-decoration: none; white-space: nowrap; }
  .ring { width: 22px; height: 22px; border-radius: 50%; border: 2px solid #fff; display: grid; place-items: center; }
  .ring span { width: 8px; height: 8px; border-radius: 50%; background: #fff; }
  .name { font-weight: 750; font-size: 14px; letter-spacing: .01em; font-stretch: 88%; }
  nav { display: flex; align-items: stretch; flex: 1; overflow-x: auto; scrollbar-width: none; }
  nav a { color: var(--sign-ink-2); font-size: 13px; padding: 0 12px; display: flex; align-items: center; text-decoration: none; white-space: nowrap; }
  nav a:hover { color: #fff; }
  nav a.on { color: #fff; font-weight: 600; box-shadow: inset 0 -3px 0 #fff; }
  .status { display: flex; align-items: center; gap: 6px; font-size: 12px; color: var(--sign-ink-2); white-space: nowrap; }
  .dot { width: 7px; height: 7px; border-radius: 50%; background: #888; }
  .dot.ok { background: #35c46a; }
  .dot.warn { background: #e0a030; }
  .dot.bad { background: #e0533f; }
  .menu-btn { display: none; align-self: center; align-items: center; gap: 8px; height: 30px; padding: 0 10px; border-radius: 4px;
    border: 1px solid #ffffff40; background: none; color: #fff; font-size: 13px; font-weight: 600; }
  .theme { align-self: center; background: none; border: 1px solid #ffffff40; color: #fff; border-radius: 4px; height: 26px; padding: 0 8px; font-size: 12px; }
  .banner { background: var(--bad-bg); color: var(--bad-ink); padding: 7px 20px; font-size: 12.5px; display: flex; gap: 12px; align-items: center; }
  .banner a { color: var(--bad-ink); text-decoration: underline; }
  .sp { flex: 1; }
  main { min-height: calc(100vh - var(--header-h)); }
  @media (max-width: 900px) { .name { display: none; } .status { display: none; } .top { gap: 10px; padding: 0 12px; } }
  @media (max-width: 760px) {
    .menu-btn { display: inline-flex; margin-right: auto; }
    nav { display: none; }
    nav.open { display: flex; flex-direction: column; position: absolute; top: var(--header-h); left: 0; right: 0; background: var(--sign);
      padding: 4px 0 8px; box-shadow: 0 8px 20px #0006; z-index: 30; }
    nav.open a { height: 44px; padding: 0 16px; box-shadow: none; }
    nav.open a.on { box-shadow: inset 3px 0 0 #fff; }
  }
</style>
