(function () {
  "use strict";
  const $ = (s, r = document) => r.querySelector(s);
  const MIN_OBS_FOR_HERO = 10;
  const DOW = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
  const C = { obs: () => Charts.css("--s1"), sch: () => Charts.css("--s2") };

  const api = async (path, opts) => {
    const r = await fetch(path, opts);
    if (!r.ok) {
      let msg = r.statusText;
      try { msg = (await r.json()).detail || msg; } catch (_) {}
      throw new Error(msg);
    }
    return r.json();
  };
  const el = (tag, props = {}, ...kids) => {
    const e = document.createElement(tag);
    for (const k in props) {
      if (k === "class") e.className = props[k];
      else if (k === "style") e.style.cssText = props[k];
      else if (k.startsWith("on")) e.addEventListener(k.slice(2), props[k]);
      else if (props[k] != null) e.setAttribute(k, props[k]);
    }
    for (const kid of kids.flat()) if (kid != null) e.append(kid instanceof Node ? kid : String(kid));
    return e;
  };
  const mins = (s) => (s == null ? null : s / 60);
  const fmtMin = (m) => (m == null ? "–" : Math.abs(m) < 10 ? m.toFixed(1) : Math.round(m).toString());
  const fmtSecAsMin = (s) => fmtMin(mins(s));
  const hourFmt = (h) => (h === 0 ? "12a" : h < 12 ? `${h}a` : h === 12 ? "12p" : `${h - 12}p`);
  const hourTitle = (h) => { const e = (h + 1) % 24; return `${hourFmt(h)}–${hourFmt(e)} departures`; };
  const isoDaysAgo = (n) => { const d = new Date(); d.setDate(d.getDate() - n + 1); return d.toLocaleDateString("en-CA"); };

  let ROUTES = {};   // short_name -> route row
  let ROUTES_BY_ID = {};

  // ================================================================ tabs
  const tabs = document.querySelectorAll(".tabs button");
  function showTab(name) {
    tabs.forEach((b) => b.setAttribute("aria-selected", b.dataset.tab === name));
    document.querySelectorAll(".tab").forEach((s) => (s.hidden = s.id !== "tab-" + name));
    if (name === "live") Live.show();
    if (name === "perf") Perf.load();
    if (name === "sql") Sql.init();
    history.replaceState(null, "", "#" + (name === "travel" ? Travel.hash() : "tab=" + name));
  }
  tabs.forEach((b) => b.addEventListener("click", () => showTab(b.dataset.tab)));

  // ================================================================ status
  async function refreshStatus() {
    try {
      const s = await api("/api/status");
      const age = s.last_ok_poll_age_s;
      const color = age == null ? "var(--muted)" : age < 120 ? "var(--good)" : age < 900 ? "var(--warn)" : "var(--critical)";
      const label = age == null ? "Collector never ran" : age < 120 ? "Collector live" :
        `Collector last polled ${Math.round(age / 60)} min ago`;
      const o = s.observed || {};
      $("#status").replaceChildren(
        el("span", {}, el("span", { class: "dot", style: `background:${color}` }), label),
        el("span", {}, `${(o.trips || 0).toLocaleString()} trips observed` + (o.first ? ` since ${o.first}` : "")),
        el("span", { class: "muted" }, `GTFS ${s.gtfs_feed_version || "not imported"}`),
      );
    } catch (e) {
      $("#status").textContent = "API unreachable";
    }
  }

  // ================================================================ stop picker
  function Picker(root, { downstreamOf, onChange }) {
    let stops = [];
    let seq = 0, active = -1, results = [];
    const input = el("input", { type: "text", placeholder: "Search stop name, street, or stop code…", "aria-label": "Stop search" });
    const list = el("div", { class: "suggest", hidden: "" });
    root.append(input, list);

    function render() {
      root.querySelectorAll(".stop-tag").forEach((t) => t.remove());
      for (const s of stops) {
        root.insertBefore(el("span", { class: "stop-tag" },
          s.stop_name, el("span", { class: "code" }, s.stop_code || s.stop_id),
          el("button", { "aria-label": "Remove " + s.stop_name, onclick: () => remove(s.stop_id) }, "×")), input);
      }
      input.placeholder = stops.length ? "Add another stop…" : "Search stop name, street, or stop code…";
    }
    function remove(id) { stops = stops.filter((s) => s.stop_id !== id); render(); onChange(); }
    function add(s) {
      if (!stops.some((x) => x.stop_id === s.stop_id)) stops.push(s);
      input.value = ""; list.hidden = true; render(); onChange();
    }
    function highlight() {
      [...list.children].forEach((b, i) => b.classList.toggle("active", i === active));
    }
    let timer;
    input.addEventListener("input", () => {
      clearTimeout(timer);
      timer = setTimeout(search, 180);
    });
    input.addEventListener("focus", () => { if (input.value || downstreamOf().length) search(); });
    input.addEventListener("keydown", (e) => {
      if (e.key === "ArrowDown") { active = Math.min(results.length - 1, active + 1); highlight(); e.preventDefault(); }
      else if (e.key === "ArrowUp") { active = Math.max(0, active - 1); highlight(); e.preventDefault(); }
      else if (e.key === "Enter" && results[active]) { add(results[active]); e.preventDefault(); }
      else if (e.key === "Escape") list.hidden = true;
      else if (e.key === "Backspace" && !input.value && stops.length) remove(stops[stops.length - 1].stop_id);
    });
    document.addEventListener("click", (e) => { if (!root.contains(e.target)) list.hidden = true; });

    async function search() {
      const q = input.value.trim();
      const ds = downstreamOf();
      if (!q && !ds.length) { list.hidden = true; return; }
      const my = ++seq;
      const params = new URLSearchParams({ q, limit: 40 });
      if (ds.length) params.set("downstream_of", ds.join(","));
      results = await api("/api/stops?" + params);
      if (my !== seq) return;
      active = results.length ? 0 : -1;
      list.replaceChildren(...(results.length ? results.map((s, i) =>
        el("button", { type: "button", class: i === 0 ? "active" : "", onclick: () => add(s) },
          el("div", {}, s.stop_name),
          el("div", { class: "meta" }, `#${s.stop_code || s.stop_id} · ${s.stop_desc || ""} · routes ${s.routes || "–"}`)))
        : [el("div", { class: "muted small", style: "padding:10px" },
            ds.length ? "No stops matching that are reachable directly from the From stop" : "No matching stops")]));
      list.hidden = false;
    }
    return {
      get: () => stops,
      set: (s) => { stops = s; render(); },
    };
  }

  // ================================================================ travel time
  const Travel = (() => {
    const st = { dows: new Set(), hourFrom: null, hourTo: null, routes: null, heatSrc: "observed", data: null, allRoutes: [] };
    let from, to;

    function init() {
      from = Picker($("#pick-from"), { downstreamOf: () => [], onChange: () => { st.routes = null; st.allRoutes = []; run(); } });
      to = Picker($("#pick-to"), { downstreamOf: () => from.get().map((s) => s.stop_id), onChange: () => { st.routes = null; st.allRoutes = []; run(); } });
      $("#swap").addEventListener("click", () => { const a = from.get(); from.set(to.get()); to.set(a); st.routes = null; st.allRoutes = []; run(); });

      const dows = $("#dows");
      const presets = [["Weekdays", [0, 1, 2, 3, 4]], ["Weekend", [5, 6]]];
      for (const [name, set] of presets) {
        dows.append(el("button", { class: "chip preset", type: "button", onclick: () => {
          const same = set.length === st.dows.size && set.every((d) => st.dows.has(d));
          st.dows = new Set(same ? [] : set); syncDows(); run();
        } }, name));
      }
      DOW.forEach((d, i) => dows.append(el("button", { class: "chip", type: "button", "data-dow": i, "aria-pressed": "false",
        onclick: () => { st.dows.has(i) ? st.dows.delete(i) : st.dows.add(i); syncDows(); run(); } }, d)));

      const hf = $("#hour-from"), ht = $("#hour-to");
      hf.append(el("option", { value: "" }, "Any"));
      ht.append(el("option", { value: "" }, "Any"));
      for (let h = 0; h < 24; h++) {
        hf.append(el("option", { value: h }, hourFmt(h)));
        ht.append(el("option", { value: h }, hourFmt(h) + " hour"));
      }
      hf.addEventListener("change", run);
      ht.addEventListener("change", run);
      $("#radius").addEventListener("change", () => { st.routes = null; st.allRoutes = []; run(); });
      $("#range").addEventListener("change", run);
      $("#heat-src").addEventListener("click", (e) => {
        const b = e.target.closest("button"); if (!b) return;
        st.heatSrc = b.dataset.src;
        $("#heat-src").querySelectorAll("button").forEach((x) => x.setAttribute("aria-pressed", x === b));
        renderHeat();
      });
    }
    function syncDows() {
      document.querySelectorAll("#dows [data-dow]").forEach((b) => b.setAttribute("aria-pressed", st.dows.has(+b.dataset.dow)));
    }

    function hash() {
      const p = new URLSearchParams();
      if (from && from.get().length) p.set("from", from.get().map((s) => s.stop_id).join(","));
      if (to && to.get().length) p.set("to", to.get().map((s) => s.stop_id).join(","));
      if (+$("#radius").value) p.set("r", $("#radius").value);
      if (st.dows.size) p.set("d", [...st.dows].join(","));
      if ($("#hour-from").value) p.set("hf", $("#hour-from").value);
      if ($("#hour-to").value) p.set("ht", $("#hour-to").value);
      if ($("#range").value) p.set("range", $("#range").value);
      if (st.routes) p.set("routes", [...st.routes].join(","));
      return p.toString();
    }
    async function restore(p) {
      const load = async (ids) => {
        if (!ids) return [];
        const out = [];
        for (const id of ids.split(",")) {
          const r = await api("/api/stops?" + new URLSearchParams({ q: id, limit: 5 }));
          const s = r.find((x) => x.stop_id === id) || r[0];
          if (s) out.push(s);
        }
        return out;
      };
      from.set(await load(p.get("from")));
      to.set(await load(p.get("to")));
      if (p.get("r")) $("#radius").value = p.get("r");
      if (p.get("d")) st.dows = new Set(p.get("d").split(",").map(Number));
      if (p.get("hf")) $("#hour-from").value = p.get("hf");
      if (p.get("ht")) $("#hour-to").value = p.get("ht");
      if (p.get("range")) $("#range").value = p.get("range");
      if (p.get("routes")) st.routes = new Set(p.get("routes").split(","));
      syncDows();
      run();
    }

    let runSeq = 0;
    async function run() {
      history.replaceState(null, "", "#" + hash());
      const f = from.get(), t = to.get();
      if (!f.length || !t.length) {
        $("#travel-empty").hidden = false; $("#travel-out").hidden = true; return;
      }
      const p = new URLSearchParams({
        from: f.map((s) => s.stop_id).join(","), to: t.map((s) => s.stop_id).join(","),
        radius_m: $("#radius").value,
      });
      if (st.dows.size) p.set("dows", [...st.dows].join(","));
      if ($("#hour-from").value) p.set("hour_from", $("#hour-from").value);
      if ($("#hour-to").value) p.set("hour_to", $("#hour-to").value);
      if ($("#range").value) p.set("date_from", isoDaysAgo(+$("#range").value));
      if (st.routes) p.set("routes", [...st.routes].join(","));
      const my = ++runSeq;
      $("#travel-out").style.opacity = 0.5;
      try {
        const d = await api("/api/travel-time?" + p);
        if (my !== runSeq) return;
        st.data = d;
        if (!st.allRoutes.length) {
          const names = new Set([...d.scheduled.by_route, ...d.observed.by_route].map((r) => r.route));
          st.allRoutes = [...names].sort((a, b) => a.localeCompare(b, undefined, { numeric: true }));
        }
        render();
      } catch (e) {
        $("#tiles").replaceChildren(el("div", { class: "tile" }, "Error: " + e.message));
      } finally {
        if (my === runSeq) $("#travel-out").style.opacity = 1;
      }
    }

    function tile(label, value, unit, sub, cls, key) {
      return el("div", { class: "tile " + (cls || "") },
        el("div", { class: "label" }, key ? el("span", { class: "key", style: `background:${key}` }) : null, label),
        el("div", { class: "value" }, value, unit ? el("span", { class: "unit" }, unit) : null),
        sub ? el("div", { class: "sub" }, sub) : null);
    }

    function render() {
      const d = st.data;
      $("#travel-empty").hidden = true;
      $("#travel-out").hidden = false;
      const obs = d.observed, sch = d.scheduled;
      const O = obs.overall, S = sch.overall, D = d.observed_minus_scheduled;

      // route chips
      const chips = $("#route-chips");
      chips.replaceChildren(...(st.allRoutes.length ? st.allRoutes.map((r) =>
        el("button", { class: "chip", type: "button", "aria-pressed": st.routes ? st.routes.has(r) : "true",
          onclick: () => {
            if (!st.routes) st.routes = new Set(st.allRoutes);
            st.routes.has(r) ? st.routes.delete(r) : st.routes.add(r);
            if (st.routes.size === st.allRoutes.length || st.routes.size === 0) st.routes = null;
            run();
          } }, routeLabel(r))) : [el("span", { class: "muted small" }, "no direct route")]));

      // tiles
      // Lead with observed data only once there's enough of it to be representative.
      const useObs = O && (O.n >= MIN_OBS_FOR_HERO || !S);
      const hero = useObs ? O : S;
      const tiles = [
        tile("Typical trip", fmtSecAsMin(hero && hero.median), hero ? "min" : "",
          useObs ? `median of ${O.n.toLocaleString()} observed trips`
            : S ? `timetable median${O ? ` (only ${O.n} observed so far)` : " (nothing observed yet)"}`
            : "no direct trips between these stops",
          "hero"),
        tile("Scheduled", fmtSecAsMin(S && S.median), S ? "min" : "",
          S ? `timetable median · ${fmtSecAsMin(S.p10)}–${fmtSecAsMin(S.p90)} min p10–p90` : "not in timetable", "", C.sch()),
        tile("Observed", fmtSecAsMin(O && O.median), O ? "min" : "",
          O ? `${fmtSecAsMin(O.p10)}–${fmtSecAsMin(O.p90)} min p10–p90 · mean ${fmtSecAsMin(O.mean)}` : "collector hasn't seen a trip yet", "", C.obs()),
      ];
      if (D) {
        const m = D.median / 60;
        tiles.push(el("div", { class: "tile" },
          el("div", { class: "label" }, "Observed vs schedule"),
          el("div", { class: "value " + (m > 0.5 ? "delta-up" : m < -0.5 ? "delta-down" : "") },
            (m > 0 ? "+" : m < 0 ? "−" : "") + fmtMin(Math.abs(m)), el("span", { class: "unit" }, "min")),
          el("div", { class: "sub" }, m > 0.5 ? "slower than timetable (median)" : m < -0.5 ? "faster than timetable (median)" : "on timetable (median)")));
      }
      $("#tiles").replaceChildren(...tiles);

      // by hour
      const hours = new Set([...obs.by_hour, ...sch.by_hour].map((r) => r.hour));
      const hs = [...hours].sort((a, b) => a - b);
      const xs = hs.length ? range(hs[0], hs[hs.length - 1]) : [];
      const pick = (rows, key, f) => { const m = new Map(rows.map((r) => [r[key], r])); return (x) => { const r = m.get(x); return r ? f(r) : null; }; };
      const oh = pick(obs.by_hour, "hour", (r) => r), sh = pick(sch.by_hour, "hour", (r) => r);
      const series = [];
      if (obs.by_hour.length) series.push({
        name: "Observed", color: C.obs(), values: xs.map((x) => mins(oh(x) && oh(x).median)),
        band: { lo: xs.map((x) => mins(oh(x) && oh(x).p10)), hi: xs.map((x) => mins(oh(x) && oh(x).p90)) },
        extra: (i) => oh(xs[i]) ? [{ value: `${oh(xs[i]).n} trips observed` }] : [],
      });
      if (sch.by_hour.length) series.push({ name: "Scheduled", color: C.sch(), values: xs.map((x) => mins(sh(x) && sh(x).median)) });
      Charts.line($("#c-hour"), { xs, xFmt: hourFmt, xTitle: hourTitle, yFmt: fmtMin, series,
        label: "Travel time by hour of day", empty: "No trips in the selected hours" });

      // by route
      const routeNames = [...new Set([...sch.by_route, ...obs.by_route].map((r) => r.route))];
      const ro = pick(obs.by_route, "route", (r) => r), rs = pick(sch.by_route, "route", (r) => r);
      routeNames.sort((a, b) => ((ro(a) || rs(a)).median - (ro(b) || rs(b)).median));
      const rseries = [];
      if (obs.by_route.length) rseries.push({ name: "Observed", color: C.obs(), values: routeNames.map((r) => mins(ro(r) && ro(r).median)) });
      if (sch.by_route.length) rseries.push({ name: "Scheduled", color: C.sch(), values: routeNames.map((r) => mins(rs(r) && rs(r).median)) });
      Charts.barsH($("#c-route"), { cats: routeNames, catFmt: routeLabel, series: rseries, fmt: fmtMin, labelWidth: 150,
        tipExtra: (i) => ro(routeNames[i]) ? [{ value: `${ro(routeNames[i]).n} trips observed` }] : [],
        empty: "No direct route" });

      // by dow
      const dows = [...new Set([...obs.by_dow, ...sch.by_dow].map((r) => r.dow))].sort();
      const dob = pick(obs.by_dow, "dow", (r) => r), dsc = pick(sch.by_dow, "dow", (r) => r);
      const dseries = [];
      if (obs.by_dow.length) dseries.push({ name: "Observed", color: C.obs(), values: dows.map((x) => mins(dob(x) && dob(x).median)) });
      if (sch.by_dow.length) dseries.push({ name: "Scheduled", color: C.sch(), values: dows.map((x) => mins(dsc(x) && dsc(x).median)) });
      Charts.barsH($("#c-dow"), { cats: dows, catFmt: (i) => DOW[i], series: dseries, fmt: fmtMin, labelWidth: 50,
        tipExtra: (i) => dob(dows[i]) ? [{ value: `${dob(dows[i]).n} trips observed` }] : [] });

      renderHeat();
      renderRouteTable(routeNames, ro, rs);
      renderRecent();
      $("#stops-used").textContent = `Stops used — from: ${d.from.map((s) => `${s.stop_name} (${s.stop_id})`).join(", ")}; ` +
        `to: ${d.to.map((s) => `${s.stop_name} (${s.stop_id})`).join(", ")}`;
    }

    function renderHeat() {
      const src = st.data[st.heatSrc];
      const m = new Map(src.by_dow_hour.map((r) => [r.dow + ":" + r.hour, r]));
      const hs = src.by_dow_hour.map((r) => r.hour);
      const cols = hs.length ? range(Math.min(...hs), Math.max(...hs)) : [];
      Charts.heatmap($("#c-heat"), {
        rows: [0, 1, 2, 3, 4, 5, 6], cols, rowFmt: (r) => DOW[r], colFmt: hourFmt, fmt: (v) => fmtMin(v) + " min",
        get: (r, c) => { const x = m.get(r + ":" + c); return x ? { v: x.median / 60, n: st.heatSrc === "observed" ? x.n : null } : null; },
        empty: st.heatSrc === "observed" ? "No observed trips yet. Switch to scheduled, or let the collector run." : "No scheduled trips",
      });
    }

    function renderRouteTable(routeNames, ro, rs) {
      const head = el("tr", {}, ...["Route", "Observed median", "p10", "p90", "Trips seen", "Scheduled median", "p10", "p90", "Obs − sched"]
        .map((h, i) => el("th", { class: i ? "num" : "" }, h)));
      const rows = routeNames.map((r) => {
        const o = ro(r), s = rs(r);
        const diff = o && s ? (o.median - s.median) / 60 : null;
        return el("tr", {},
          el("td", {}, badge(r), " ", el("span", { class: "muted" }, (ROUTES[r] || {}).route_long_name || "")),
          ...[o && o.median, o && o.p10, o && o.p90].map((v) => el("td", { class: "num" }, fmtSecAsMin(v))),
          el("td", { class: "num" }, o ? o.n : "–"),
          ...[s && s.median, s && s.p10, s && s.p90].map((v) => el("td", { class: "num" }, fmtSecAsMin(v))),
          el("td", { class: "num " + (diff > 0.5 ? "delta-up" : diff < -0.5 ? "delta-down" : "") },
            diff == null ? "–" : (diff > 0 ? "+" : "") + fmtMin(diff)));
      });
      $("#t-routes").replaceChildren(el("thead", {}, head), el("tbody", {}, ...rows));
    }

    function renderRecent() {
      const rows = st.data.recent_trips;
      const head = el("tr", {}, ...["Departed", "Route", "Headsign", "Travel", "Scheduled", "Δ"].map((h, i) => el("th", { class: i > 2 ? "num" : "" }, h)));
      const body = rows.length ? rows.map((r) => {
        const diff = r.sched_travel_s != null ? (r.travel_s - r.sched_travel_s) / 60 : null;
        return el("tr", {}, el("td", {}, r.depart), el("td", {}, badge(r.route)), el("td", {}, r.headsign),
          el("td", { class: "num" }, fmtSecAsMin(r.travel_s) + " min"),
          el("td", { class: "num" }, r.sched_travel_s != null ? fmtSecAsMin(r.sched_travel_s) + " min" : "–"),
          el("td", { class: "num " + (diff > 0.5 ? "delta-up" : diff < -0.5 ? "delta-down" : "") },
            diff == null ? "–" : (diff > 0 ? "+" : "") + fmtMin(diff)));
      }) : [el("tr", {}, el("td", { colspan: 6, class: "muted" }, "No observed trips yet. Keep the collector running and history will build up here."))];
      $("#t-recent").replaceChildren(el("thead", {}, head), el("tbody", {}, ...body));
    }

    return { init, run, hash, restore };
  })();

  function range(a, b) { const out = []; for (let i = a; i <= b; i++) out.push(i); return out; }
  function routeLabel(short) {
    const r = ROUTES[short];
    return r && r.route_long_name ? `${short} · ${r.route_long_name}` : String(short);
  }
  function badge(short) {
    const r = ROUTES[short] || {};
    return el("span", { class: "route-badge", style: `background:#${r.route_color || "888"};color:#${r.route_text_color || "fff"}` }, short);
  }

  // ================================================================ route performance
  const Perf = (() => {
    let bound = false;
    async function load() {
      if (!bound) {
        bound = true;
        $("#perf-range").addEventListener("change", load);
        $("#perf-mode").addEventListener("change", load);
      }
      const p = new URLSearchParams();
      const rng = $("#perf-range").value;
      if (rng) p.set("date_from", isoDaysAgo(+rng));
      if ($("#perf-mode").value) p.set("route_type", $("#perf-mode").value);
      $("#tab-perf").style.opacity = 0.5;
      const d = await api("/api/route-performance?" + p);
      $("#tab-perf").style.opacity = 1;

      const n = d.by_route.reduce((a, r) => a + r.n, 0);
      const trips = d.by_route.reduce((a, r) => a + r.trips, 0);
      const wavg = (k) => n ? d.by_route.reduce((a, r) => a + r[k] * r.n, 0) / n : null;
      const onTime = wavg("pct_on_time"), delay = wavg("mean_delay_s");
      $("#perf-tiles").replaceChildren(
        el("div", { class: "tile hero" }, el("div", { class: "label" }, "On-time arrivals"),
          el("div", { class: "value" }, onTime == null ? "–" : onTime.toFixed(1), el("span", { class: "unit" }, "%")),
          el("div", { class: "sub" }, "from 1 min early to 5 min late")),
        el("div", { class: "tile" }, el("div", { class: "label" }, "Average delay"),
          el("div", { class: "value" }, delay == null ? "–" : fmtSecAsMin(delay), el("span", { class: "unit" }, "min")),
          el("div", { class: "sub" }, "observed minus scheduled arrival")),
        el("div", { class: "tile" }, el("div", { class: "label" }, "Trips observed"),
          el("div", { class: "value" }, trips.toLocaleString()),
          el("div", { class: "sub" }, `${n.toLocaleString()} stop arrivals`)),
      );

      const xs = d.by_hour.length ? range(d.by_hour[0].hour, d.by_hour[d.by_hour.length - 1].hour) : [];
      const hm = new Map(d.by_hour.map((r) => [r.hour, r]));
      Charts.line($("#c-perf-hour"), {
        xs, xFmt: hourFmt, xTitle: (h) => hourFmt(h) + " arrivals", yFmt: (v) => Math.round(v) + "%", yDomain: [0, 100],
        series: [{ name: "On time", color: C.obs(), values: xs.map((h) => hm.get(h) ? hm.get(h).pct_on_time : null),
          extra: (i) => hm.get(xs[i]) ? [{ value: `${hm.get(xs[i]).n.toLocaleString()} arrivals` },
            { value: `${fmtSecAsMin(hm.get(xs[i]).mean_delay_s)} min`, name: "avg delay" }] : [] }],
        empty: "No observed arrivals in this period",
      });

      const worst = d.by_route.slice(0, 25);
      Charts.barsH($("#c-perf-route"), {
        cats: worst.map((r) => r.route), catFmt: routeLabel, labelWidth: 150, fmt: fmtMin,
        series: [{ name: "Average delay", color: C.obs(), values: worst.map((r) => r.mean_delay_s / 60) }],
        tipExtra: (i) => [{ value: `${worst[i].pct_on_time}%`, name: "on time" }, { value: worst[i].trips, name: "trips" }],
        empty: "No observed arrivals in this period",
      });

      const head = el("tr", {}, ...["Route", "Trips", "Arrivals", "Avg delay", "On time", "Late >5m", "Early >1m"]
        .map((h, i) => el("th", { class: i ? "num" : "" }, h)));
      const maxDelay = Math.max(1, ...d.by_route.map((r) => r.mean_delay_s));
      const body = d.by_route.map((r) => el("tr", {},
        el("td", {}, badge(r.route), " ", el("span", { class: "muted" }, (ROUTES[r.route] || {}).route_long_name || "")),
        el("td", { class: "num" }, r.trips), el("td", { class: "num" }, r.n.toLocaleString()),
        el("td", { class: "num" }, fmtSecAsMin(r.mean_delay_s) + " min ",
          el("span", { class: "inline-bar", style: `width:${Math.max(0, (r.mean_delay_s / maxDelay) * 60)}px` })),
        el("td", { class: "num" }, r.pct_on_time + "%"), el("td", { class: "num" }, r.pct_late + "%"),
        el("td", { class: "num" }, r.pct_early + "%")));
      $("#t-perf").replaceChildren(el("thead", {}, head), el("tbody", {}, ...body));
    }
    return { load };
  })();

  // ================================================================ live map
  const Live = (() => {
    let map, layer, shapeLayer, timer;
    const STATUS = [
      { key: "early", label: "Early >1 min", color: "#fab219", test: (d) => d < -60 },
      { key: "ok", label: "On time", color: "#0ca30c", test: (d) => d <= 300 },
      { key: "late", label: "Late 5–10 min", color: "#ec835a", test: (d) => d <= 600 },
      { key: "vlate", label: "Late >10 min", color: "#d03b3b", test: () => true },
    ];
    const statusOf = (d) => (d == null ? null : STATUS.find((s) => s.test(d)));

    function show() {
      if (!map) {
        map = L.map("map", { preferCanvas: true }).setView([40.70, -111.90], 11);
        L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
          maxZoom: 19, attribution: "© OpenStreetMap contributors",
        }).addTo(map);
        shapeLayer = L.layerGroup().addTo(map);
        layer = L.layerGroup().addTo(map);
        const sel = $("#live-route");
        Object.values(ROUTES_BY_ID).forEach((r) => sel.append(el("option", { value: r.route_id }, routeLabel(r.route_short_name))));
        sel.addEventListener("change", () => { drawShape(); refresh(); });
        $("#live-color").addEventListener("change", refresh);
      }
      setTimeout(() => map.invalidateSize(), 50);
      refresh();
      clearInterval(timer);
      timer = setInterval(() => { if (!$("#tab-live").hidden) refresh(); }, 30000);
    }
    async function drawShape() {
      shapeLayer.clearLayers();
      const id = $("#live-route").value;
      if (!id) return;
      const shapes = await api(`/api/routes/${encodeURIComponent(id)}/shapes`);
      const r = ROUTES_BY_ID[id];
      const lines = Object.values(shapes).map((pts) => L.polyline(pts, { color: "#" + (r.route_color || "2a78d6"), weight: 3, opacity: 0.6 }));
      lines.forEach((l) => l.addTo(shapeLayer));
      if (lines.length) map.fitBounds(L.featureGroup(lines).getBounds(), { padding: [20, 20] });
    }
    async function refresh() {
      const d = await api("/api/vehicles/live");
      const route = $("#live-route").value;
      const byDelay = $("#live-color").value === "delay";
      layer.clearLayers();
      const vs = d.vehicles.filter((v) => !route || v.route_id === route);
      for (const v of vs) {
        const s = statusOf(v.delay_s);
        const color = byDelay ? (s ? s.color : "#898781") : "#" + (v.route_color || "898781");
        const m = L.circleMarker([v.lat, v.lon], { radius: 6, color: "#fff", weight: 2, fillColor: color, fillOpacity: 1 });
        const age = Math.round(Date.now() / 1000 - v.ts);
        const pop = el("div", {},
          el("div", {}, el("strong", {}, `Route ${v.route_short_name || "?"}`), " ", v.trip_headsign ? "→ " + v.trip_headsign : ""),
          el("div", { class: "muted" }, v.route_long_name || ""),
          el("div", {}, v.delay_s == null ? "Delay unknown" : `${s.label}: ${v.delay_s >= 0 ? "+" : "−"}${fmtSecAsMin(Math.abs(v.delay_s))} min`),
          el("div", { class: "muted" }, `Vehicle ${v.vehicle_id} · ${v.speed != null ? Math.round(v.speed * 2.237) + " mph · " : ""}${age}s ago`));
        m.bindPopup(pop);
        m.addTo(layer);
      }
      const counts = {};
      vs.forEach((v) => { const s = statusOf(v.delay_s); counts[s ? s.key : "na"] = (counts[s ? s.key : "na"] || 0) + 1; });
      $("#live-legend").replaceChildren(...(byDelay
        ? [...STATUS.map((s) => el("span", {}, el("span", { class: "k dot", style: `background:${s.color}` }), `${s.label} (${counts[s.key] || 0})`)),
           el("span", {}, el("span", { class: "k dot", style: "background:#898781" }), `No prediction (${counts.na || 0})`)]
        : [el("span", {}, "Marker color = UTA route color. Click a vehicle for details.")]));
      $("#live-asof").textContent = d.as_of ? `${vs.length} vehicles · positions as of ${new Date(d.as_of * 1000).toLocaleTimeString()} · refreshes every 30 s`
        : "No vehicle positions yet. Is the collector running?";
    }
    return { show };
  })();

  // ================================================================ SQL
  const Sql = (() => {
    let ready = false;
    const EXAMPLES = [
      ["Observed travel time between two stops, by hour", `-- Replace the stop ids (see the stops table or the Travel time tab)
SELECT a.route_short_name AS route,
       CAST(strftime('%H', a.obs_departure, 'unixepoch', 'localtime') AS INT) AS hour,
       COUNT(*) AS trips,
       ROUND(AVG(b.obs_arrival - a.obs_departure) / 60.0, 1) AS avg_min,
       ROUND(AVG(b.sched_arrival - a.sched_departure) / 60.0, 1) AS sched_min
FROM observed_stop_events a
JOIN observed_stop_events b
  ON b.service_date = a.service_date AND b.trip_id = a.trip_id AND b.stop_sequence > a.stop_sequence
WHERE a.stop_id = '{FROM}' AND b.stop_id = '{TO}'
GROUP BY route, hour
ORDER BY route, hour;`],
      ["Schedule adherence by route, today", `SELECT route_short_name AS route,
       COUNT(*) AS arrivals,
       ROUND(AVG(delay_s) / 60.0, 1) AS avg_delay_min,
       ROUND(100.0 * SUM(delay_s BETWEEN -60 AND 300) / COUNT(*), 1) AS pct_on_time
FROM observed_stop_events
WHERE service_date = date('now', 'localtime')
GROUP BY route
ORDER BY avg_delay_min DESC;`],
      ["Actual headways at a stop (gaps between buses)", `-- Minutes between consecutive observed arrivals at one stop, per route
SELECT route_short_name AS route, obs_arrival_local,
       ROUND((obs_arrival - LAG(obs_arrival) OVER (PARTITION BY route_id ORDER BY obs_arrival)) / 60.0, 1) AS headway_min
FROM observed_stop_events
WHERE stop_id = '{FROM}'
ORDER BY obs_arrival DESC
LIMIT 200;`],
      ["Slowest segments today (stop to next stop)", `SELECT a.route_short_name AS route, sa.stop_name AS from_stop, sb.stop_name AS to_stop,
       COUNT(*) AS trips,
       ROUND(AVG((b.obs_arrival - a.obs_departure) - (b.sched_arrival - a.sched_departure)) / 60.0, 2) AS avg_extra_min
FROM observed_stop_events a
JOIN observed_stop_events b
  ON b.service_date = a.service_date AND b.trip_id = a.trip_id AND b.stop_sequence = a.stop_sequence + 1
JOIN stops sa ON sa.stop_id = a.stop_id
JOIN stops sb ON sb.stop_id = b.stop_id
WHERE a.service_date = date('now', 'localtime')
GROUP BY a.route_short_name, a.stop_id, b.stop_id
HAVING trips >= 3
ORDER BY avg_extra_min DESC
LIMIT 50;`],
      ["Scheduled trips per day of week, by route", `SELECT r.route_short_name AS route, sd.dow, COUNT(*) / COUNT(DISTINCT sd.date) AS trips_per_day
FROM trips t JOIN routes r USING (route_id) JOIN service_dates sd USING (service_id)
GROUP BY route, sd.dow
ORDER BY CAST(route AS INT), sd.dow;`],
      ["Busiest stops by scheduled departures", `SELECT s.stop_id, s.stop_name, SUM(sr.n_trips) AS trips, group_concat(DISTINCT sr.route_short_name) AS routes
FROM stop_routes sr JOIN stops s USING (stop_id)
GROUP BY s.stop_id
ORDER BY trips DESC
LIMIT 50;`],
      ["Average bus speed by hour (from GPS)", `SELECT CAST(strftime('%H', ts, 'unixepoch', 'localtime') AS INT) AS hour,
       COUNT(*) AS pings, ROUND(AVG(speed) * 2.237, 1) AS avg_mph
FROM vehicle_positions
WHERE speed > 0.5
GROUP BY hour ORDER BY hour;`],
      ["Collector health", `SELECT datetime(ts, 'unixepoch', 'localtime') AS polled_at, n_vehicles, n_trip_updates, n_stop_updates, error
FROM polls ORDER BY ts DESC LIMIT 50;`],
    ];

    async function init() {
      if (ready) return;
      ready = true;
      const sel = $("#sql-examples");
      EXAMPLES.forEach(([name], i) => sel.append(el("option", { value: i }, name)));
      const fill = () => {
        const cur = new URLSearchParams(Travel.hash());
        const f = (cur.get("from") || "FROM_STOP_ID").split(",")[0];
        const t = (cur.get("to") || "TO_STOP_ID").split(",")[0];
        $("#sql").value = EXAMPLES[+sel.value][1].replaceAll("{FROM}", f).replaceAll("{TO}", t);
      };
      sel.addEventListener("change", () => { fill(); run(); });
      fill();
      $("#sql-run").addEventListener("click", run);
      $("#sql").addEventListener("keydown", (e) => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) { e.preventDefault(); run(); } });
      const schema = await api("/api/schema");
      $("#schema").replaceChildren(...schema.map((t) => el("details", {},
        el("summary", {}, t.name, el("span", { class: "t" }, t.type)), el("pre", {}, t.sql))));
    }
    async function run() {
      const t0 = performance.now();
      $("#sql-meta").textContent = "running…";
      try {
        const d = await api("/api/sql", { method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ sql: $("#sql").value }) });
        const head = el("tr", {}, ...d.columns.map((c) => el("th", {}, c)));
        const body = d.rows.map((r) => el("tr", {}, ...r.map((v) =>
          el("td", { class: typeof v === "number" ? "num" : "" }, v == null ? "NULL" : v))));
        $("#sql-table").replaceChildren(el("thead", {}, head), el("tbody", {}, ...body));
        $("#sql-meta").textContent = `${d.rows.length.toLocaleString()} rows${d.truncated ? " (truncated)" : ""} · ${Math.round(performance.now() - t0)} ms`;
      } catch (e) {
        $("#sql-table").replaceChildren();
        $("#sql-meta").textContent = "Error: " + e.message;
      }
    }
    return { init };
  })();

  // ================================================================ boot
  (async function boot() {
    const routes = await api("/api/routes");
    for (const r of routes) { ROUTES[r.route_short_name] = r; ROUTES_BY_ID[r.route_id] = r; }
    Travel.init();
    refreshStatus();
    setInterval(refreshStatus, 30000);
    const p = new URLSearchParams(location.hash.slice(1));
    if (p.get("tab")) showTab(p.get("tab"));
    else await Travel.restore(p);
  })();
})();
