<script lang="ts">
  // Explanations live behind an ⓘ (hover / focus / tap), not on the page.
  import { tip } from "../tip.svelte";
  let { text }: { text: string } = $props();
</script>

<button type="button" class="i" aria-label={text} onmouseenter={(e) => tip.show(e, text)} onmouseleave={() => tip.hide()}
  onfocus={(e) => { const r = (e.currentTarget as HTMLElement).getBoundingClientRect(); tip.show({ clientX: r.left, clientY: r.bottom } as MouseEvent, text); }}
  onblur={() => tip.hide()} onclick={(e) => tip.show(e, text)}>i</button>

<style>
  .i { width: 17px; height: 17px; flex: none; border-radius: 50%; border: 1.3px solid var(--faint); background: none; color: var(--muted);
    font: italic 700 10.5px/1 Georgia, serif; padding: 0; display: inline-grid; place-items: center; vertical-align: 1px; }
  .i:hover { color: var(--ink); border-color: var(--ink-2); }
</style>
