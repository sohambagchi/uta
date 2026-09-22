<script lang="ts">
  let { kind = "info", children }: { kind?: "info" | "warn" | "bad" | "hatch" | "ok"; children: import("svelte").Snippet } = $props();
</script>

<span class="tag {kind}">{#if kind === "hatch"}<span class="sw"></span>{/if}{@render children()}</span>

<style>
  .tag { display: inline-flex; align-items: center; gap: 5px; height: 20px; padding: 0 7px; border-radius: 3px; font-size: 11px;
    font-weight: 600; white-space: nowrap; background: var(--sunk); color: var(--ink-2); }
  .warn { background: var(--warn-bg); color: var(--warn-ink); }
  .bad { background: var(--bad-bg); color: var(--bad-ink); }
  .ok { color: var(--ok); }
  .hatch { background: var(--panel); border: 1px solid var(--border); color: var(--muted); }
  .sw { width: 10px; height: 10px; border-radius: 2px; border: 1px solid var(--faint);
    background: repeating-linear-gradient(45deg, var(--muted) 0 1.5px, transparent 1.5px 4px); }
</style>
