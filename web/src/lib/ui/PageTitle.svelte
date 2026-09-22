<script lang="ts">
  import type { Snippet } from "svelte";
  let { title, sub = "", lead, right, children }: { title: string; sub?: string; lead?: Snippet; right?: Snippet; children?: Snippet } = $props();
</script>

<div class="pt">
  {#if lead}<div class="lead">{@render lead()}</div>{/if}
  <div class="h"><h1>{title}{#if children} {@render children()}{/if}</h1>{#if sub}<div class="sub">{sub}</div>{/if}</div>
  {#if right}<div class="right">{@render right()}</div>{/if}
</div>

<style>
  .pt { display: flex; align-items: center; gap: 14px; padding: 16px 20px 12px; flex-wrap: wrap; }
  .h { flex: 1; min-width: 240px; }
  h1 { font-size: 26px; font-weight: 700; letter-spacing: -.02em; font-stretch: 90%; }
  .sub { font-size: 13px; color: var(--muted); margin-top: 2px; }
  .right { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }
  .lead { display: flex; }
</style>
