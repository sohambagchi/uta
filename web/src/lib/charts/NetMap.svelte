<script lang="ts">
  // Delay map without a basemap: route shapes as grey casing, stations coloured by median delay.
  import type { NetworkLine } from "../api";
  import { dcol, delay } from "../format";
  import { tip } from "../tip.svelte";
  import { router } from "../router.svelte";
  type St = { id: string; name: string; lat: number; lon: number; n: number; median: number };
  let { lines, rail, stations, height = 860, minN = 15 }: { lines: NetworkLine[]; rail: Set<string>; stations: St[]; height?: number; minN?: number } = $props();
  let w = $state(420);
  const pts = $derived(stations.filter((s) => s.n >= minN));
  const proj = $derived.by(() => {
    if (!pts.length) return null;
    const lats = pts.map((s) => s.lat), lons = pts.map((s) => s.lon);
    // at least ~30 km across, so a scope with one or two stations still reads as a map
    const grow = (a: number, b: number, m: number) => (b - a >= m ? [a, b] : [(a + b) / 2 - m / 2, (a + b) / 2 + m / 2]);
    const [la0, la1] = grow(Math.min(...lats) - 0.02, Math.max(...lats) + 0.02, 0.3);
    const [lo0, lo1] = grow(Math.min(...lons) - 0.03, Math.max(...lons) + 0.03, 0.35);
    const kx = Math.cos(((la0 + la1) / 2) * Math.PI / 180);
    const k = Math.min((w - 20) / ((lo1 - lo0) * kx), (height - 20) / (la1 - la0));
    const ox = (w - (lo1 - lo0) * kx * k) / 2, oy = (height - (la1 - la0) * k) / 2;
    return { k, P: (lon: number, lat: number): [number, number] => [ox + (lon - lo0) * kx * k, oy + (la1 - lat) * k],
      inb: (lon: number, lat: number) => lat >= la0 && lat <= la1 && lon >= lo0 && lon <= lo1 };
  });
  const paths = $derived.by(() => {
    if (!proj) return [];
    return lines.map((l) => {
      const c = l.coords.filter(([lo, la]) => proj.inb(lo, la)).map(([lo, la]) => proj.P(lo, la));
      return { rail: rail.has(l.route_id), d: c.length > 1 ? "M" + c.map(([a, b]) => `${a.toFixed(1)},${b.toFixed(1)}`).join("L") : "" };
    }).sort((a, b) => Number(a.rail) - Number(b.rail));
  });
  const dots = $derived(proj ? [...pts].sort((a, b) => a.median - b.median).map((s) => {
    const [x, y] = proj.P(s.lon, s.lat);
    return { s, x, y, r: 1.6 + Math.min(3.2, Math.sqrt(s.n) / 6) };
  }) : []);
  // hubs labelled whatever the scope: [name, lat, lon, side]
  const HUBS: [string, number, number, 1 | -1][] = [
    ["Ogden Central", 41.2238, -111.9799, 1], ["Salt Lake Central", 40.7627, -111.9089, -1], ["West Valley Central", 40.6938, -111.9601, -1],
    ["Murray Central", 40.6599, -111.8955, 1], ["Daybreak Pkwy", 40.5439, -112.014, -1], ["Provo Central", 40.2252, -111.6611, -1],
  ];
  const labels = $derived(proj ? HUBS.filter(([, la, lo]) => proj.inb(lo, la)).map(([name, la, lo, side]) => {
    const [x, y] = proj.P(lo, la);
    return { name, x, y, side };
  }) : []);
</script>

<div bind:clientWidth={w}>
  <svg class="chart" width={w} {height} role="img" aria-label="Stations coloured by median delay" style="background: var(--panel-2); border-radius: 4px">
    {#each paths as p}{#if p.d}<path d={p.d} fill="none" stroke={p.rail ? "var(--axis)" : "var(--grid)"} stroke-width={p.rail ? 2.4 : 1.1} stroke-linejoin="round" />{/if}{/each}
    {#each dots as dt (dt.s.id)}
      <circle role="link" tabindex="-1" cx={dt.x} cy={dt.y} r={dt.r} fill={dcol(dt.s.median)} fill-opacity="0.92" style="cursor: pointer"
        onmouseenter={(e) => tip.show(e, dt.s.name, [{ k: "Median delay", v: delay(dt.s.median) }, { k: "Visits", v: dt.s.n.toLocaleString() }])}
        onmouseleave={() => tip.hide()} onclick={() => router.go(`stations/${dt.s.id}`)} onkeydown={() => {}} />
    {/each}
    {#each labels as l}
      <line x1={l.x + l.side * 3} x2={l.x + l.side * 12} y1={l.y} y2={l.y} stroke="var(--ink-2)" />
      <text x={l.x + l.side * 15} y={l.y + 3.5} text-anchor={l.side > 0 ? "start" : "end"}
        style="fill: var(--ink); font-size: 10.5px; font-weight: 600; paint-order: stroke; stroke: var(--panel-2); stroke-width: 3px">{l.name}</text>
    {/each}
    {#if proj}
      {@const kmv = [20, 10, 5, 2, 1].find((k) => (k / 111) * proj.k <= w / 3) ?? 1}
      {@const km = (kmv / 111) * proj.k}
      <line x1="14" x2={14 + km} y1={height - 16} y2={height - 16} stroke="var(--ink-2)" stroke-width="2" /><text x="14" y={height - 22}>{kmv} km</text>
    {/if}
  </svg>
</div>
