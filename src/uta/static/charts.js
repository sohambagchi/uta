// Minimal SVG charts: line (with crosshair + band), grouped horizontal bars, heatmap.
// Marks follow fixed specs: 2px lines, <=24px bars with 4px rounded data-ends,
// 2px surface gaps, hairline grid, text in ink tokens (never series colors).
(function () {
  "use strict";
  const NS = "http://www.w3.org/2000/svg";
  const SEQ = ["#cde2fb", "#b7d3f6", "#9ec5f4", "#86b6ef", "#6da7ec", "#5598e7", "#3987e5",
               "#2a78d6", "#256abf", "#1c5cab", "#184f95", "#104281", "#0d366b"];

  function svgEl(tag, attrs, parent) {
    const e = document.createElementNS(NS, tag);
    for (const k in attrs) if (attrs[k] != null) e.setAttribute(k, attrs[k]);
    if (parent) parent.appendChild(e);
    return e;
  }
  function text(parent, x, y, str, attrs) {
    const t = svgEl("text", Object.assign({ x, y }, attrs), parent);
    t.textContent = str;
    return t;
  }
  function niceStep(span, count) {
    const raw = span / Math.max(1, count);
    const mag = Math.pow(10, Math.floor(Math.log10(raw)));
    const n = raw / mag;
    return (n <= 1 ? 1 : n <= 2 ? 2 : n <= 2.5 ? 2.5 : n <= 5 ? 5 : 10) * mag;
  }
  function niceDomain(lo, hi, count, zero) {
    if (zero) lo = Math.min(0, lo);
    if (hi === lo) hi = lo + 1;
    const step = niceStep(hi - lo, count);
    lo = Math.floor(lo / step) * step;
    hi = Math.ceil(hi / step) * step;
    const ticks = [];
    for (let v = lo; v <= hi + step / 2; v += step) ticks.push(+v.toFixed(6));
    return { lo, hi, ticks };
  }
  function css(name) {
    return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  }

  // ---------------------------------------------------------------- tooltip
  const tip = {
    el: null,
    show(evt, title, rows) {
      this.el = this.el || document.getElementById("tooltip");
      const el = this.el;
      el.replaceChildren();
      const h = document.createElement("div");
      h.className = "tt-title";
      h.textContent = title;
      el.appendChild(h);
      for (const r of rows) {
        const row = document.createElement("div");
        row.className = "tt-row";
        if (r.color) {
          const k = document.createElement("span");
          k.className = "tt-key";
          k.style.background = r.color;
          row.appendChild(k);
        }
        const v = document.createElement("strong");
        v.textContent = r.value;
        row.appendChild(v);
        if (r.name) {
          const n = document.createElement("span");
          n.className = "tt-name";
          n.textContent = r.name;
          row.appendChild(n);
        }
        el.appendChild(row);
      }
      el.hidden = false;
      const pad = 14, w = el.offsetWidth, hgt = el.offsetHeight;
      let x = evt.clientX + pad, y = evt.clientY + pad;
      if (x + w > window.innerWidth - 8) x = evt.clientX - w - pad;
      if (y + hgt > window.innerHeight - 8) y = evt.clientY - hgt - pad;
      el.style.left = x + "px";
      el.style.top = y + "px";
    },
    hide() { if (this.el) this.el.hidden = true; },
  };

  function legend(container, series, kind) {
    if (series.length < 2) return;
    const lg = document.createElement("div");
    lg.className = "legend";
    for (const s of series) {
      const item = document.createElement("span");
      const k = document.createElement("span");
      k.className = "k" + (kind === "rect" ? " rect" : "");
      k.style.background = s.color;
      item.appendChild(k);
      item.appendChild(document.createTextNode(s.name));
      lg.appendChild(item);
    }
    container.appendChild(lg);
  }

  function frame(el, spec, render) {
    el._spec = spec;
    el._render = render;
    if (!el._ro) {
      el._ro = new ResizeObserver(() => {
        if (el._w !== el.clientWidth) el._render(el, el._spec);
      });
      el._ro.observe(el);
    }
    render(el, spec);
  }

  function none(el, msg) {
    el.replaceChildren();
    const d = document.createElement("div");
    d.className = "none";
    d.textContent = msg || "No data";
    el.appendChild(d);
  }

  // ---------------------------------------------------------------- line
  // spec: {xs, xFmt, yFmt, series:[{name,color,values,band:{lo,hi}}], height}
  function line(el, spec) { frame(el, spec, renderLine); }
  function renderLine(el, spec) {
    el._w = el.clientWidth;
    const has = spec.series.some((s) => s.values.some((v) => v != null));
    if (!has) return none(el, spec.empty);
    el.replaceChildren();
    legend(el, spec.series, "line");
    const W = el.clientWidth, H = spec.height || 240;
    const m = { l: 40, r: 44, t: 10, b: 26 };
    const iw = W - m.l - m.r, ih = H - m.t - m.b;
    const xs = spec.xs;
    let lo = Infinity, hi = -Infinity;
    for (const s of spec.series) {
      for (const arr of [s.values, s.band && s.band.lo, s.band && s.band.hi]) {
        if (!arr) continue;
        for (const v of arr) if (v != null) { lo = Math.min(lo, v); hi = Math.max(hi, v); }
      }
    }
    const pad = (hi - lo) * 0.1 || 1;
    const dom = spec.yDomain
      ? niceDomain(spec.yDomain[0], spec.yDomain[1], 4, false)
      : niceDomain(Math.max(0, lo - pad), hi + pad, 4, false);
    const X = (i) => m.l + (xs.length === 1 ? iw / 2 : (i / (xs.length - 1)) * iw);
    const Y = (v) => m.t + ih - ((v - dom.lo) / (dom.hi - dom.lo)) * ih;
    const svg = svgEl("svg", { viewBox: `0 0 ${W} ${H}`, height: H, role: "img",
      "aria-label": spec.label || "line chart" }, el);

    for (const t of dom.ticks) {
      svgEl("line", { class: t === dom.lo ? "baseline" : "gridline", x1: m.l, x2: W - m.r, y1: Y(t), y2: Y(t) }, svg);
      text(svg, m.l - 6, Y(t) + 4, spec.yFmt(t), { class: "tick", "text-anchor": "end" });
    }
    const every = Math.ceil(xs.length / Math.max(2, Math.floor(iw / 44)));
    xs.forEach((x, i) => {
      if (i % every === 0) text(svg, X(i), H - 8, spec.xFmt(x), { class: "tick", "text-anchor": "middle" });
    });

    const segs = (vals) => {
      const out = []; let cur = [];
      vals.forEach((v, i) => { if (v == null) { if (cur.length) out.push(cur); cur = []; } else cur.push(i); });
      if (cur.length) out.push(cur);
      return out;
    };
    for (const s of spec.series) {
      if (!s.band) continue;
      for (const seg of segs(s.band.lo)) {
        const up = seg.map((i) => `${X(i)},${Y(s.band.hi[i])}`);
        const dn = seg.slice().reverse().map((i) => `${X(i)},${Y(s.band.lo[i])}`);
        svgEl("polygon", { points: up.concat(dn).join(" "), fill: s.bandColor || "var(--band)" }, svg);
      }
    }
    for (const s of spec.series) {
      for (const seg of segs(s.values)) {
        if (seg.length === 1) {
          svgEl("circle", { cx: X(seg[0]), cy: Y(s.values[seg[0]]), r: 4, fill: s.color,
            stroke: "var(--surface)", "stroke-width": 2 }, svg);
          continue;
        }
        svgEl("path", { d: "M" + seg.map((i) => `${X(i)},${Y(s.values[i])}`).join("L"), fill: "none",
          stroke: s.color, "stroke-width": 2, "stroke-linejoin": "round", "stroke-linecap": "round",
          "stroke-dasharray": s.dashed ? "5 4" : null }, svg);
      }
    }
    // end labels: last point of each series, skipped when they collide
    const ends = spec.series.map((s) => {
      let i = s.values.length - 1;
      while (i >= 0 && s.values[i] == null) i--;
      return i >= 0 ? { s, i, y: Y(s.values[i]) } : null;
    }).filter(Boolean);
    const collide = ends.some((a, j) => ends.some((b, k) => k > j && Math.abs(a.y - b.y) < 13));
    if (!collide) {
      for (const e of ends) {
        svgEl("circle", { cx: X(e.i), cy: e.y, r: 4, fill: e.s.color, stroke: "var(--surface)", "stroke-width": 2 }, svg);
        text(svg, X(e.i) + 8, e.y + 4, spec.yFmt(e.s.values[e.i]), { class: "dlabel" });
      }
    }

    const cross = svgEl("line", { class: "crosshair", y1: m.t, y2: m.t + ih, visibility: "hidden" }, svg);
    const dots = spec.series.map((s) => svgEl("circle", { r: 4, fill: s.color, stroke: "var(--surface)",
      "stroke-width": 2, visibility: "hidden" }, svg));
    const hit = svgEl("rect", { class: "hit", x: m.l - 10, y: m.t, width: iw + 20, height: ih, tabindex: 0 }, svg);
    const at = (i, evt) => {
      cross.setAttribute("x1", X(i)); cross.setAttribute("x2", X(i));
      cross.setAttribute("visibility", "visible");
      const rows = [];
      spec.series.forEach((s, k) => {
        const v = s.values[i];
        if (v == null) { dots[k].setAttribute("visibility", "hidden"); return; }
        dots[k].setAttribute("cx", X(i)); dots[k].setAttribute("cy", Y(v));
        dots[k].setAttribute("visibility", "visible");
        let val = spec.yFmt(v);
        if (s.band && s.band.lo[i] != null) val += `  (${spec.yFmt(s.band.lo[i])}–${spec.yFmt(s.band.hi[i])})`;
        rows.push({ color: s.color, name: s.name, value: val });
        if (s.extra) rows.push(...s.extra(i));
      });
      tip.show(evt, spec.xTitle ? spec.xTitle(xs[i]) : spec.xFmt(xs[i]), rows);
    };
    hit.addEventListener("pointermove", (evt) => {
      const r = svg.getBoundingClientRect();
      const px = ((evt.clientX - r.left) / r.width) * W;
      const i = Math.max(0, Math.min(xs.length - 1, Math.round(((px - m.l) / iw) * (xs.length - 1))));
      at(i, evt);
    });
    hit.addEventListener("pointerleave", () => {
      tip.hide(); cross.setAttribute("visibility", "hidden");
      dots.forEach((d) => d.setAttribute("visibility", "hidden"));
    });
  }

  // ---------------------------------------------------------------- horizontal bars
  // spec: {cats, catFmt?, series:[{name,color,values}], fmt, tipExtra?(catIndex)}
  function barsH(el, spec) { frame(el, spec, renderBars); }
  function renderBars(el, spec) {
    el._w = el.clientWidth;
    if (!spec.cats.length) return none(el, spec.empty);
    el.replaceChildren();
    legend(el, spec.series, "rect");
    const W = el.clientWidth;
    const ns = spec.series.length;
    const bar = ns > 1 ? 10 : 16, gap = 2, rowPad = 10;
    const rowH = ns * bar + (ns - 1) * gap + rowPad;
    const m = { l: spec.labelWidth || 120, r: 48, t: 4, b: 22 };
    const H = m.t + m.b + rowH * spec.cats.length;
    const iw = W - m.l - m.r;
    let hi = 0, lo = 0;
    for (const s of spec.series) for (const v of s.values) if (v != null) { hi = Math.max(hi, v); lo = Math.min(lo, v); }
    const dom = niceDomain(lo, hi, 4, true);
    const X = (v) => m.l + ((v - dom.lo) / (dom.hi - dom.lo)) * iw;
    const svg = svgEl("svg", { viewBox: `0 0 ${W} ${H}`, height: H, role: "img", "aria-label": spec.label || "bar chart" }, el);
    for (const t of dom.ticks) {
      svgEl("line", { class: t === 0 ? "baseline" : "gridline", x1: X(t), x2: X(t), y1: m.t, y2: H - m.b }, svg);
      text(svg, X(t), H - 6, spec.fmt(t), { class: "tick", "text-anchor": "middle" });
    }
    const maxChars = Math.floor((m.l - 10) / 6.5);
    spec.cats.forEach((cat, ci) => {
      const y0 = m.t + ci * rowH + rowPad / 2;
      let label = spec.catFmt ? spec.catFmt(cat) : String(cat);
      if (label.length > maxChars) label = label.slice(0, maxChars - 1) + "…";
      text(svg, m.l - 8, y0 + (rowH - rowPad) / 2 + 4, label, { class: "tick", "text-anchor": "end", fill: "var(--ink-2)" });
      spec.series.forEach((s, si) => {
        const v = s.values[ci];
        if (v == null) return;
        const y = y0 + si * (bar + gap);
        const x0 = X(0), x1 = X(v);
        const w = Math.abs(x1 - x0), r = Math.min(4, w, bar / 2);
        const d = v >= 0
          ? `M${x0},${y}H${x1 - r}Q${x1},${y} ${x1},${y + r}V${y + bar - r}Q${x1},${y + bar} ${x1 - r},${y + bar}H${x0}Z`
          : `M${x0},${y}H${x1 + r}Q${x1},${y} ${x1},${y + r}V${y + bar - r}Q${x1},${y + bar} ${x1 + r},${y + bar}H${x0}Z`;
        svgEl("path", { d, fill: s.color, class: "bar" }, svg);
        if (spec.labels !== false)
          text(svg, v >= 0 ? x1 + 5 : x1 - 5, y + bar / 2 + 4, spec.fmt(v),
            { class: "dlabel", "text-anchor": v >= 0 ? "start" : "end" });
      });
      const hit = svgEl("rect", { class: "hit", x: 0, y: y0 - rowPad / 2, width: W, height: rowH }, svg);
      hit.addEventListener("pointermove", (evt) => {
        const rows = spec.series.filter((s) => s.values[ci] != null)
          .map((s) => ({ color: s.color, name: s.name, value: spec.fmt(s.values[ci]) }));
        if (spec.tipExtra) rows.push(...spec.tipExtra(ci));
        tip.show(evt, spec.catFmt ? spec.catFmt(cat) : String(cat), rows);
      });
      hit.addEventListener("pointerleave", () => tip.hide());
    });
  }

  // ---------------------------------------------------------------- heatmap
  // spec: {rows, cols, rowFmt, colFmt, get(r,c) -> {v, n}|null, fmt}
  function heatmap(el, spec) { frame(el, spec, renderHeat); }
  function renderHeat(el, spec) {
    el._w = el.clientWidth;
    const vals = [];
    spec.rows.forEach((r) => spec.cols.forEach((c) => { const d = spec.get(r, c); if (d) vals.push(d.v); }));
    if (!vals.length) return none(el, spec.empty);
    el.replaceChildren();
    const lo = Math.min(...vals), hi = Math.max(...vals);
    const color = (v) => SEQ[hi === lo ? 6 : Math.round(((v - lo) / (hi - lo)) * (SEQ.length - 1))];

    const lg = document.createElement("div");
    lg.className = "legend";
    const scale = document.createElement("span");
    scale.style.cssText = `display:inline-block;width:120px;height:10px;border-radius:2px;vertical-align:middle;margin:0 6px;background:linear-gradient(90deg,${SEQ.join(",")})`;
    lg.append(spec.fmt(lo), scale, spec.fmt(hi));
    el.appendChild(lg);

    const W = el.clientWidth;
    const m = { l: 40, r: 4, t: 4, b: 22 };
    const cw = (W - m.l - m.r) / spec.cols.length;
    const ch = Math.max(18, Math.min(30, cw));
    const H = m.t + m.b + ch * spec.rows.length;
    const svg = svgEl("svg", { viewBox: `0 0 ${W} ${H}`, height: H, role: "img", "aria-label": spec.label || "heatmap" }, el);
    const every = Math.ceil(spec.cols.length / Math.max(2, Math.floor((W - m.l) / 36)));
    spec.cols.forEach((c, ci) => {
      if (ci % every === 0) text(svg, m.l + ci * cw + cw / 2, H - 6, spec.colFmt(c), { class: "tick", "text-anchor": "middle" });
    });
    spec.rows.forEach((r, ri) => {
      text(svg, m.l - 8, m.t + ri * ch + ch / 2 + 4, spec.rowFmt(r), { class: "tick", "text-anchor": "end" });
      spec.cols.forEach((c, ci) => {
        const d = spec.get(r, c);
        const x = m.l + ci * cw, y = m.t + ri * ch;
        const cell = svgEl("rect", { x: x + 1, y: y + 1, width: Math.max(0, cw - 2), height: ch - 2, rx: 2,
          fill: d ? color(d.v) : "var(--div-mid)", class: "cell", opacity: d ? 1 : 0.5 }, svg);
        cell.addEventListener("pointermove", (evt) => {
          tip.show(evt, `${spec.rowFmt(r)} ${spec.colFmt(c)}`, d
            ? [{ value: spec.fmt(d.v), name: d.n != null ? `median · ${d.n} trips` : "median" }]
            : [{ value: "no trips" }]);
        });
        cell.addEventListener("pointerleave", () => tip.hide());
      });
    });
  }

  window.Charts = { line, barsH, heatmap, tip, css, SEQ };
})();
