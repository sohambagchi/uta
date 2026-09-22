<script lang="ts">
  import type { Snippet } from "svelte";
  import Info from "./Info.svelte";
  import NBadge from "./NBadge.svelte";
  let { q, info, cap, n, nLabel, warn, right, children, w, grow = false, loading = false }: {
    q: string; info?: string; cap?: string; n?: number | string; nLabel?: string; warn?: boolean; right?: Snippet;
    children: Snippet; w?: number; grow?: boolean; loading?: boolean;
  } = $props();
</script>

<section class="panel" class:grow class:loading style:width={w ? `${w}px` : undefined} style:flex-shrink={w ? 0 : undefined}>
  <header>
    <div class="h">
      <h2>{q}{#if info}<Info text={info} />{/if}</h2>
      {#if cap}<div class="cap">{cap}</div>{/if}
    </div>
    {#if right}<div class="right">{@render right()}</div>{/if}
    {#if n !== undefined}<NBadge {n} label={nLabel} {warn} />{/if}
  </header>
  <div class="body">{@render children()}</div>
</section>

<style>
  .panel { background: var(--panel); border: 1px solid var(--border); border-radius: 6px; padding: 14px 16px; display: flex;
    flex-direction: column; gap: 10px; min-width: 0; }
  .grow { flex: 1 1 0; }
  .loading { opacity: .55; transition: opacity .15s; }
  header { display: flex; align-items: flex-start; gap: 6px 10px; flex-wrap: wrap; }
  .body { display: flex; flex-direction: column; gap: 10px; min-width: 0; overflow-x: auto; }
  .h { flex: 1 1 220px; min-width: 0; }
  h2 { font-size: 14.5px; font-weight: 650; letter-spacing: -.005em; }
  h2 :global(.i) { margin-left: 6px; }
  .cap { font-size: 12px; color: var(--muted); margin-top: 2px; }
  .right { display: flex; gap: 6px; align-items: center; }
</style>
