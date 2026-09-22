<script lang="ts">
  // Rail: filled rounded square in the line colour. Bus and flex: outlined numeral box in ink.
  import { lineColor } from "../format";
  let { short, color = null, mode = "bus", size = 22 }: { short: string | null; color?: string | null; mode?: string | null; size?: number } = $props();
  const rail = $derived(mode !== "bus");
  const fs = $derived((short ?? "").length <= 3 ? size * 0.5 : size * 0.43);
</script>

<span class="rb" class:rail style:--s="{size}px" style:--fs="{fs}px" style:--lc={rail ? lineColor(short, color) : undefined} style:--li={rail ? `var(--line-ink-${short}, #fff)` : undefined}>{short ?? "?"}</span>

<style>
  .rb { display: inline-flex; align-items: center; justify-content: center; min-width: calc(var(--s) + 6px); height: var(--s); padding: 0 4px;
    border-radius: 3px; border: 1.5px solid var(--ink); color: var(--ink); font-size: var(--fs); font-weight: 700; font-stretch: 85%;
    flex: none; line-height: 1; }
  .rail { min-width: var(--s); padding: 0 3px; border-radius: calc(var(--s) * .23); border: 0; background: var(--lc); color: var(--li, #fff); }
</style>
