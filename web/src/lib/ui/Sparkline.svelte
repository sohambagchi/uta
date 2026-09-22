<script lang="ts">
  let { vals, w = 86, h = 26, lo, hi, color = "var(--ink)" }: {
    vals: (number | null)[]; w?: number; h?: number; lo?: number; hi?: number; color?: string;
  } = $props();
  const segs = $derived.by(() => {
    const vs = vals.filter((v): v is number => v != null);
    if (vs.length < 2) return { paths: [] as string[], last: null as [number, number] | null };
    const a = lo ?? Math.min(...vs), b = hi ?? (Math.max(...vs) || a + 1);
    const x = (i: number) => 2 + (i * (w - 4)) / Math.max(1, vals.length - 1);
    const y = (v: number) => h - 3 - ((v - a) / (b - a || 1)) * (h - 6);
    const paths: string[] = [];
    let cur: string[] = [];
    let last: [number, number] | null = null;
    vals.forEach((v, i) => {
      if (v == null) { if (cur.length > 1) paths.push("M" + cur.join("L")); cur = []; return; }
      cur.push(`${x(i).toFixed(1)},${y(v).toFixed(1)}`);
      last = [x(i), y(v)];
    });
    if (cur.length > 1) paths.push("M" + cur.join("L"));
    return { paths, last };
  });
</script>

<svg width={w} height={h} class="chart" aria-hidden="true">
  {#each segs.paths as d}<path {d} fill="none" stroke={color} stroke-width="1.5" stroke-linejoin="round" />{/each}
  {#if segs.last}<circle cx={segs.last[0]} cy={segs.last[1]} r="2.2" fill={color} />{/if}
</svg>
