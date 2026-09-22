// One tooltip for the whole app: charts call tip.show(event, title, rows) on hover.

export interface TipRow { k: string; v: string; color?: string }
class Tip {
  cur = $state<{ x: number; y: number; title: string; rows: TipRow[] } | null>(null);
  show(e: MouseEvent | PointerEvent, title: string, rows: TipRow[] = []) {
    this.cur = { x: e.clientX, y: e.clientY, title, rows };
  }
  hide() { this.cur = null; }
}
export const tip = new Tip();
