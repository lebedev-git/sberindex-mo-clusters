/* Лендинг «Типы локальных экономик России». Чистый D3 v7, данные — site/data/*.json. */
(async function () {
  const DATA_VERSION = "20261009p"; // меняется при пересборке данных, чтобы браузер не брал старые из кэша
  const ru = d3.formatLocale({ decimal: ",", thousands: " ", grouping: [3], currency: ["", " ₽"] });
  const fInt = ru.format(",.0f"), fPct = ru.format(".1%"), f2 = ru.format(".2f"), f3 = ru.format(".3f"), fPct0 = ru.format(".0%");
  const MON = ["янв", "фев", "мар", "апр", "май", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"];
  const CAT_SHORT = ["Продукты", "Здоровье", "Общепит", "Транспорт", "Маркетплейсы"];
  const C = { nodata: "#e4e3dd", absent: "#f0efec", ink: "#0b0b0b", ink2: "#52514e", muted: "#898781", grid: "#e1e0d9", other: "#e9e8e2" };
  const BLUE = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#1c5cab", "#104281"];
  const DIV = ["#1c5cab", "#5598e7", "#b7d3f6", "#f0efec", "#f5b9b8", "#e66767", "#b8302f"];
  const RULE_RU = { attr: "Признаки (евклид)", corr: "Корреляция рядов", cosine: "Косинус корзины трат", dtw: "DTW (лаги)", road: "Дороги (км)" };
  const METHOD_RU = { kmeans: "k-means (признаки)", ward: "Ward (признаки)", spectral: "Спектральный (признаки + сеть)", leiden: "Leiden (сеть)", kefrin: "KEFRiN (признаки + сеть)" };

  d3.select("#map-sub").text("Загрузка данных (≈2 МБ)…");
  const [geo, mo, types, meta, series, macro] = await Promise.all([
    ...["mo.geojson", "mo.json", "types.json", "meta.json", "series.json", "macro.json"].map((f) => d3.json(`data/${f}?v=${DATA_VERSION}`)),
  ]);
  // субъекты, которых нет в справочнике МО (ДНР, ЛНР, Запорожская и Херсонская области): только контуры
  const extra = await d3.json(`data/new_regions.geojson?v=${DATA_VERSION}`).catch(() => null);
  // D3 рисует полигоны на сфере: кольцо с «обратным» обходом закрашивает весь глобус.
  // Части, пересекающие 180° (Чукотка), после плоского упрощения могут развернуться — чиним по площади.
  const fixRings = (features) => features.forEach((f) => {
    const g = f.geometry;
    const polys = (g.type === "Polygon" ? [g.coordinates] : g.coordinates).filter((poly) => {
      if (d3.geoArea({ type: "Polygon", coordinates: poly }) > 2 * Math.PI) poly.forEach((ring) => ring.reverse());
      return d3.geoArea({ type: "Polygon", coordinates: poly }) <= 2 * Math.PI; // вырожденные части отбрасываем
    });
    f.geometry = { type: "MultiPolygon", coordinates: polys };
  });
  fixRings(geo.features);
  if (extra) fixRings(extra.features);
  const byId = new Map(mo.map((m) => [m.id, m]));
  const ok = mo.filter((m) => m.status === "ok");
  const cur = () => (state.level === "macro" ? macro : types);
  const tColor = (t) => (cur()[t] && cur()[t].color) || "#888";
  const tName = (t) => (cur()[t] ? cur()[t].name : "—");
  const dColor = (t) => (types[t] && types[t].color) || "#888";
  const dName = (t) => (types[t] ? types[t].name : "—");
  const W = meta.windows;
  const winLabel = (end) => {
    const [y, mm] = end.split("-").map(Number);
    const s = new Date(y, mm - 12, 1);
    return mm === 12 ? `${y} год` : `${MON[s.getMonth()]} ${s.getFullYear()} – ${MON[mm - 1]} ${y}`;
  };
  const state = { level: "types", period: "main", mode: "type", region: "", kind: "", isolate: null, sel: null };
  const short = (t) => (t && (t.short || t.name)) || "—";
  const typeOf = (m) => (state.level === "macro" ? m.macro : state.period === "main" ? m.type : m.types[+state.period]);
  const tip = d3.select("#tooltip");
  const showTip = (ev, html) => { tip.attr("hidden", null).html(html).style("left", ev.clientX + 14 + "px").style("top", ev.clientY + 14 + "px"); };
  const hideTip = () => tip.attr("hidden", true);

  /* ---------- плитки ---------- */
  const moved = ok.filter((m) => m.moved).length;
  const arcticType = types.find((t) => t.official && t.official.far_north_or_equated >= 0.99);
  const tiles = [
    [`${macro.length} → ${types.length}`, `типов локальной экономики у ${fInt(meta.n_panel)} МО; уровни вложены на ${fPct0(meta.final_icvi.nestedness_detailed_in_macro)}`],
    [arcticType ? fPct0(arcticType.official.far_north_or_equated) : "—", `МО типа «${arcticType ? arcticType.name : "Арктика"}» — в официальном перечне районов Крайнего Севера и приравненных местностей, хотя модель его не видела`],
    [fPct0(meta.external["eta2:log_pop"]), "разброса логарифма численности населения (Росстат) объясняют типы — без данных о населении в модели"],
    [fInt(moved), `МО значимо сменили тип за год — из ${fInt(ok.filter((m) => m.types[0] !== m.types[W.length - 1]).length)} формальных смен`],
  ];
  d3.select("#tiles").selectAll("div").data(tiles).join("div").attr("class", "tile").html((d) => `<div class="v">${d[0]}</div><div class="l">${d[1]}</div>`);
  const gh = location.hostname.endsWith("github.io") ? `https://github.com/${location.hostname.split(".")[0]}/${location.pathname.split("/")[1]}` : null;
  d3.select("#links").html([gh ? `<a href="${gh}">Репозиторий с кодом</a>` : null, `<a href="report.pdf">Методологический отчёт (PDF)</a>`,
    `<a href="data/typology.csv" download>Типология всех МО (CSV)</a>`].filter(Boolean).join(""));

  /* ---------- фильтры ---------- */
  const per = d3.select("#f-period");
  per.append("option").attr("value", "main").text("Весь период 2023–2024");
  W.forEach((e, i) => per.append("option").attr("value", i).text("Окно: " + winLabel(e)));
  const regions = [...new Set(mo.map((m) => m.region))].sort((a, b) => a.localeCompare(b, "ru"));
  d3.select("#f-region").selectAll("option.r").data(regions).join("option").attr("class", "r").attr("value", (d) => d).text((d) => d);
  const kinds = [...new Set(mo.map((m) => m.kind))].sort();
  d3.select("#f-kind").selectAll("option.k").data(kinds).join("option").attr("class", "k").attr("value", (d) => d).text((d) => d);
  d3.select("#mo-list").selectAll("option").data(ok).join("option").attr("value", (m) => `${m.name} — ${m.region}`);

  /* ---------- карта ---------- */
  const MW = 1000, MH = 540;
  const svg = d3.select("#map-svg").attr("viewBox", `0 0 ${MW} ${MH}`);
  const proj = d3.geoConicEqualArea().parallels([52, 64]).rotate([-100, 0]).fitExtent([[6, 6], [MW - 6, MH - 6]], geo);
  const path = d3.geoPath(proj);
  const g = svg.append("g");
  const extraLayer = g.append("g").attr("class", "extra-layer");
  if (extra) extraLayer.selectAll("path").data(extra.features).join("path").attr("class", "mo extra").attr("d", path).attr("fill", C.absent)
    .on("mousemove", (ev, f) => showTip(ev, `<b>${f.properties.region}</b><br>Нет в справочнике МО и в данных организатора`))
    .on("mouseleave", hideTip)
    .on("click", (ev, f) => {
      state.sel = null; paint();
      const P = d3.select("#panel").html("");
      backBtn(P);
      P.append("h3").text(f.properties.region);
      P.append("div").attr("class", "muted").text("Субъект Российской Федерации");
      P.append("p").text("Этого субъекта нет ни в справочнике муниципальных образований СберИндекса, ни в данных о расходах, поэтому он показан контуром и в типологию не входит.");
    });
  const geoLayer = g.append("g");
  const paths = geoLayer.selectAll("path").data(geo.features).join("path").attr("class", "mo").attr("d", path);
  const featById = new Map(geo.features.map((f) => [f.id, f]));
  const centerOf = (id) => path.centroid(featById.get(id));
  const linkLayer = g.append("g").attr("class", "links-layer").style("pointer-events", "none");
  function drawLinks() {
    linkLayer.selectAll("*").remove();
    const m = state.sel && byId.get(state.sel);
    if (!m || m.status !== "ok") return;
    const c0 = centerOf(m.id);
    m.nb.map((id) => byId.get(id)).filter((x) => x && featById.get(x.id)).forEach((x) => {
      const c1 = centerOf(x.id);
      linkLayer.append("line").attr("x1", c0[0]).attr("y1", c0[1]).attr("x2", c1[0]).attr("y2", c1[1])
        .attr("stroke", C.ink).attr("stroke-width", 1.2).attr("vector-effect", "non-scaling-stroke").attr("stroke-opacity", 0.75);
      linkLayer.append("circle").attr("cx", c1[0]).attr("cy", c1[1]).attr("data-r", 3.5).attr("fill", dColor(x.type)).attr("stroke", C.ink).attr("stroke-width", 0.8).attr("vector-effect", "non-scaling-stroke");
    });
    linkLayer.append("circle").attr("cx", c0[0]).attr("cy", c0[1]).attr("data-r", 5).attr("fill", "#fff").attr("stroke", C.ink).attr("stroke-width", 1.5).attr("vector-effect", "non-scaling-stroke");
    const kz = d3.zoomTransform(svg.node()).k;
    linkLayer.selectAll("circle").attr("r", function () { return +this.dataset.r / kz; });
  }
  const zoom = d3.zoom().scaleExtent([1, 60]).on("zoom", (e) => {
    g.attr("transform", e.transform);
    g.selectAll(".links-layer circle").attr("r", function () { return +this.dataset.r / e.transform.k; });
  });
  svg.call(zoom).on("dblclick.zoom", null);
  const zoomTo = (feats, maxK = 60) => {
    if (!feats.length) return;
    const [[x0, y0], [x1, y1]] = path.bounds({ type: "FeatureCollection", features: feats });
    const k = Math.min(maxK, 0.85 / Math.max((x1 - x0) / MW, (y1 - y0) / MH));
    svg.transition().duration(650).call(zoom.transform, d3.zoomIdentity.translate(MW / 2, MH / 2).scale(k).translate(-(x0 + x1) / 2, -(y0 + y1) / 2));
  };
  d3.select("#reset-zoom").on("click", () => svg.transition().duration(500).call(zoom.transform, d3.zoomIdentity));
  const zoomRegion = (r) => zoomTo(geo.features.filter((f) => byId.get(f.id) && byId.get(f.id).region === r));
  d3.select("#zoom-msk").on("click", () => zoomRegion("Москва"));
  d3.select("#zoom-spb").on("click", () => zoomRegion("Санкт-Петербург"));

  const metricOf = {
    spend: (m) => m.spend, share2: (m) => m.shares[2], share4: (m) => m.shares[4], share3: (m) => m.shares[3], summer: (m) => m.summer, ma: (m) => m.ma,
    growth: (m) => m.growth, dmp: (m) => m.dmp, pop: (m) => m.pop,
  };
  const DIVERGING = new Set(["summer", "growth", "dmp"]);
  const sign = (v) => (v > 0 ? "+" : "");
  const metricFmt = { spend: (v) => fInt(v) + " ₽", share2: fPct, share4: fPct, share3: fPct, summer: (v) => sign(v) + fPct(Math.expm1(v)), ma: (v) => fInt(v),
    growth: (v) => sign(v) + fPct(v), dmp: (v) => sign(v) + ru.format(".1f")(v * 100) + " п.п.", pop: (v) => fInt(v) + " чел." };
  let seq = null;
  function buildScale() {
    if (!metricOf[state.mode]) { seq = null; return; }
    const vals = ok.map(metricOf[state.mode]).filter((v) => v != null && isFinite(v));
    if (DIVERGING.has(state.mode)) {
      const a = d3.quantile(vals.map(Math.abs).sort(d3.ascending), 0.95);
      seq = d3.scaleQuantize().domain([-a, a]).range(DIV);
    } else {
      seq = d3.scaleQuantile().domain(vals).range(BLUE);
    }
  }
  function fill(f) {
    const m = byId.get(f.id);
    if (!m) return C.absent;
    if (m.status !== "ok") return m.status === "incomplete" ? C.nodata : C.absent;
    if (state.mode === "type") return tColor(typeOf(m));
    if (state.mode === "moved") return m.moved ? dColor(m.types[W.length - 1]) : C.other;
    const v = metricOf[state.mode](m);
    return v == null ? C.nodata : seq(v);
  }
  function dimmed(f) {
    const m = byId.get(f.id);
    if (!m) return state.region !== "" || state.isolate != null;
    if (state.region && m.region !== state.region) return true;
    if (state.kind && m.kind !== state.kind) return true;
    if (state.isolate != null && (m.status !== "ok" || typeOf(m) !== state.isolate)) return true;
    return false;
  }
  function paint() {
    paths.attr("fill", fill).classed("dim", dimmed).classed("sel", (f) => f.id === state.sel);
    paths.filter((f) => f.id === state.sel).raise();
    extraLayer.selectAll("path").classed("dim", state.region !== "" || state.isolate != null);
    linkLayer.raise();
    drawLinks();
    renderLegend();
    const titles = { type: "Типы экономики", moved: "Значимо сменили тип 2023→2024 (цвет — тип в 2024)" };
    d3.select("#map-title").text(titles[state.mode] || d3.select(`#f-mode option[value=${state.mode}]`).text());
    d3.select("#map-sub").text((state.level === "macro" ? "4 макротипа · " : "6 типов · ") + (state.level === "macro" || state.period === "main" ? "весь период 2023–2024" : "скользящее окно: " + winLabel(W[+state.period])));
    d3.select("#f-period").property("disabled", state.level === "macro");
  }
  paths
    .on("mousemove", (ev, f) => {
      const m = byId.get(f.id);
      if (!m) return showTip(ev, "Нет в справочнике");
      let h = `<b>${m.name}</b><br>${m.region}<br>`;
      if (m.status !== "ok") h += m.status === "incomplete" ? "Неполный ряд в наборе данных" : "Регион отсутствует в наборе данных";
      else {
        h += `<span class="sw" style="background:${tColor(typeOf(m))}"></span> ${tName(typeOf(m))}<br>Траты: ${fInt(m.spend)} ₽/мес. на жителя`;
        if (metricOf[state.mode] && state.mode !== "spend") h += `<br>${d3.select(`#f-mode option[value=${state.mode}]`).text()}: ${metricFmt[state.mode](metricOf[state.mode](m))}`;
      }
      showTip(ev, h);
    })
    .on("mouseleave", hideTip)
    .on("click", (ev, f) => { const m = byId.get(f.id); if (m) select(m.id, false); });

  function renderLegend() {
    const L = d3.select("#legend").html("");
    if (state.mode === "type" || state.mode === "moved") {
      const counts = d3.rollup(ok, (v) => v.length, (m) => (state.mode === "moved" ? (m.moved ? m.types[W.length - 1] : -1) : typeOf(m)));
      (state.mode === "moved" ? types : cur()).forEach((t) => {
        const b = L.append("button").attr("type", "button").attr("class", "item")
          .classed("on", state.isolate === t.id).classed("off", state.isolate != null && state.isolate !== t.id)
          .attr("aria-pressed", state.isolate === t.id)
          .on("click", () => { state.isolate = state.isolate === t.id ? null : t.id; paint(); });
        b.append("span").attr("class", "sw").style("background", t.color);
        b.append("span").text(`${t.name} · ${fInt(counts.get(t.id) || 0)}`);
      });
      if (state.mode === "moved") L.append("span").attr("class", "item").html(`<span class="sw" style="background:${C.other}"></span>тип не менялся или колебание на границе`);
    } else if (seq) {
      const r = L.append("div").attr("class", "ramp");
      const dom = seq.domain();
      const lo = DIVERGING.has(state.mode) ? dom[0] : d3.min(dom), hi = DIVERGING.has(state.mode) ? dom[1] : d3.max(dom);
      r.append("span").text(metricFmt[state.mode](lo));
      r.append("div").attr("class", "bar").selectAll("span").data(seq.range()).join("span").style("background", (d) => d);
      r.append("span").text(metricFmt[state.mode](hi));
      r.append("span").text(DIVERGING.has(state.mode) ? "· серый — как у страны" : "· 7 групп по квантилям");
    }
    L.append("span").attr("class", "item").html(`<span class="sw" style="background:${C.nodata}"></span>неполный ряд`);
    L.append("span").attr("class", "item").html(`<span class="sw" style="background:${C.absent};border:1px solid #c3c2b7"></span>регион не вошёл в набор`);
  }

  d3.select("#f-period").on("change", (e) => { state.period = e.target.value; paint(); if (state.sel) renderPanel(byId.get(state.sel)); });
  d3.select("#f-level").on("change", (e) => { state.level = e.target.value; state.isolate = null; paint(); if (state.sel) renderPanel(byId.get(state.sel)); });
  d3.select("#f-mode").on("change", (e) => { state.mode = e.target.value; buildScale(); paint(); });
  d3.select("#f-region").on("change", (e) => {
    state.region = e.target.value; paint();
    zoomTo(state.region ? geo.features.filter((f) => byId.get(f.id) && byId.get(f.id).region === state.region) : geo.features);
  });
  d3.select("#f-kind").on("change", (e) => { state.kind = e.target.value; paint(); });
  d3.select("#f-search").on("change", (e) => {
    const v = e.target.value;
    const m = ok.find((x) => `${x.name} — ${x.region}` === v) || ok.find((x) => x.name.toLowerCase() === v.toLowerCase());
    if (m) select(m.id, true);
  });

  function select(id, zoomIn) {
    state.sel = id;
    paint();
    renderPanel(byId.get(id));
    if (zoomIn) {
      const m = byId.get(id);
      const feats = [id, ...((m && m.nb) || [])].map((x) => featById.get(x)).filter(Boolean);
      if (feats.length) zoomTo(feats, 12);
    }
  }

  /* ---------- карточка МО ---------- */
  function lineChart(el, opts) {
    const w = opts.w || 320, h = opts.h || 150, m = { t: 8, r: 10, b: 22, l: 46 };
    const s = d3.select(el).append("svg").attr("viewBox", `0 0 ${w} ${h}`).attr("width", "100%");
    const x = d3.scaleLinear().domain([0, opts.n - 1]).range([m.l, w - m.r]);
    const all = opts.series.flatMap((d) => d.values).concat(opts.band ? opts.band.lo.concat(opts.band.hi) : []);
    const y = d3.scaleLinear().domain(opts.yDomain || [d3.min(all) * 0.95, d3.max(all) * 1.05]).nice().range([h - m.b, m.t]);
    s.append("g").attr("class", "gridline").attr("transform", `translate(${m.l},0)`).call(d3.axisLeft(y).ticks(4).tickSize(-(w - m.l - m.r)).tickFormat("")).select(".domain").remove();
    s.append("g").attr("class", "axis").attr("transform", `translate(${m.l},0)`).call(d3.axisLeft(y).ticks(4).tickFormat(opts.yFmt || ((v) => fInt(v)))).select(".domain").remove();
    s.append("g").attr("class", "axis").attr("transform", `translate(0,${h - m.b})`).call(d3.axisBottom(x).tickValues(opts.ticks || []).tickFormat((d) => (opts.xFmt || ((i) => i))(d))); // без индекса деления: он не «длинная подпись»
    if (opts.band) {
      s.append("path").attr("fill", opts.band.color).attr("fill-opacity", 0.18)
        .attr("d", d3.area().x((d, i) => x(i)).y0((d, i) => y(opts.band.lo[i])).y1((d, i) => y(opts.band.hi[i]))(opts.band.lo));
    }
    opts.series.forEach((sr) => {
      s.append("path").attr("fill", "none").attr("stroke", sr.color).attr("stroke-width", sr.width || 2).attr("stroke-dasharray", sr.dash || null)
        .attr("d", d3.line().x((d, i) => x(i)).y((d) => y(d))(sr.values));
    });
    if (opts.marker != null) s.append("circle").attr("cx", x(opts.marker.i)).attr("cy", y(opts.marker.v)).attr("r", 5).attr("fill", opts.marker.color).attr("stroke", "#fcfcfb").attr("stroke-width", 2);
    // слой наведения: перекрестье и подсказка
    const hl = s.append("line").attr("stroke", C.muted).attr("y1", m.t).attr("y2", h - m.b).style("opacity", 0);
    s.append("rect").attr("x", m.l).attr("y", m.t).attr("width", w - m.l - m.r).attr("height", h - m.t - m.b).attr("fill", "transparent")
      .on("mousemove", (ev) => {
        const [px] = d3.pointer(ev);
        const i = Math.max(0, Math.min(opts.n - 1, Math.round(x.invert(px))));
        hl.attr("x1", x(i)).attr("x2", x(i)).style("opacity", 1);
        showTip(ev, `<b>${(opts.xFmt || ((i) => i))(i, true)}</b><br>` + opts.series.map((sr) => `<span class="sw" style="background:${sr.color}"></span> ${sr.name}: ${(opts.yFmt || fInt)(sr.values[i])}`).join("<br>"));
      })
      .on("mouseleave", () => { hl.style("opacity", 0); hideTip(); });
    if (opts.legend !== false && opts.series.length > 1) {
      const lg = d3.select(el).append("div").attr("class", "legend");
      opts.series.forEach((sr) => lg.append("span").attr("class", "item").html(`<span class="sw" style="background:${sr.color}"></span>${sr.name}`));
    }
    return s;
  }
  const monthFmt = (i, long) => { const [y, mm] = meta.months[i].split("-"); return long ? `${MON[+mm - 1]} ${y}` : (+mm === 1 ? y : MON[+mm - 1]); };

  // стартовая карточка: по одному типичному МО (медоиду, ближайшему к центру типа) на каждый из шести типов
  function renderHome() {
    const P0 = d3.select("#panel").html("");
    P0.append("h3").text("Карточка муниципалитета");
    P0.append("p").attr("class", "muted").style("margin", "0 0 4px").text("Щёлкните любое МО на карте или найдите его через поиск — здесь появятся его тип, траты, соседи по сети и динамика.");
    P0.append("p").attr("class", "muted").style("margin", "0").text("Для начала — самый типичный муниципалитет каждого из шести типов (ближайший к центру типа):");
    const exList = P0.append("ul").attr("class", "examples");
    types.forEach((t) => {
      const id = Number(String(t.typical_ids || "").split(" ")[0]);
      const m0 = byId.get(id) || ok.find((x) => x.type === t.id);
      if (!m0) return;
      exList.append("li").attr("tabindex", 0).html(`<span class="sw" style="background:${t.color}"></span><span><b>${m0.name}</b> <span class="t">${m0.region} · ${t.name}</span></span>`)
        .on("click", () => select(m0.id, true)).on("keydown", (ev) => { if (ev.key === "Enter") select(m0.id, true); });
    });
  }
  function goHome() {
    state.sel = null; paint(); renderHome();
    svg.transition().duration(500).call(zoom.transform, d3.zoomIdentity);
  }
  const backBtn = (P) => P.append("button").attr("type", "button").attr("class", "btn back").text("← К списку типов").on("click", goHome);

  function renderPanel(m) {
    const P = d3.select("#panel").html("");
    if (m) backBtn(P);
    if (!m) return;
    P.append("h3").text(m.name);
    P.append("div").attr("class", "muted").text(`${m.region} · ${m.kind}${m.capital ? " · столица региона" : ""}`);
    if (m.status !== "ok") { P.append("p").text(m.status === "incomplete" ? "В наборе есть данные, но ряд неполный — МО не вошло в анализ." : "Регион отсутствует в наборе данных организатора."); return; }
    const t = state.period === "main" ? m.type : m.types[+state.period];
    const lv = P.append("div").attr("class", "levels");
    lv.append("div").attr("class", "k").text("Макротип");
    lv.append("div").html(`<span class="chip"><span class="sw" style="background:${macro[m.macro].color}"></span>${macro[m.macro].name}</span>`);
    lv.append("div").attr("class", "k").text("Тип");
    lv.append("div").html(`<span class="chip"><span class="sw" style="background:${dColor(t)}"></span>${dName(t)}</span>`);
    if (types[m.type].macro !== m.macro) P.append("div").attr("class", "muted").style("font-size", "12px")
      .text(`МО на границе уровней: тип «${dName(m.type)}» в основном входит в макротип «${macro[types[m.type].macro].name}» (так у ${fPct0(ok.filter((x) => types[x.type].macro !== x.macro).length / ok.length)} МО).`);
    if (m.flags && m.flags.length) P.append("div").attr("class", "muted").style("font-size", "12px").text("Официальные категории: " + m.flags.join(", "));
    P.append("div").attr("class", "muted").style("font-size", "12px").text("Тип по скользящим годовым окнам:");
    const st = P.append("div").attr("class", "strip");
    m.types.forEach((x, i) => st.append("span").style("background", dColor(x)).attr("title", `${winLabel(W[i])}: ${dName(x)}`)
      .on("mousemove", (ev) => showTip(ev, `<b>${winLabel(W[i])}</b><br>${dName(x)}`)).on("mouseleave", hideTip));
    P.append("div").attr("class", "strip-axis").html(`<span>${winLabel(W[0])}</span><span>${winLabel(W[W.length - 1])}</span>`);
    if (m.moved) P.append("p").style("font-size", "13px").html(`<b>Значимый переход:</b> ${dName(m.types[0])} → ${dName(m.types[W.length - 1])}`);
    else if (m.types[0] !== m.types[W.length - 1]) P.append("p").style("font-size", "13px").attr("class", "muted").text(`Смена типа ${dName(m.types[0])} → ${dName(m.types[W.length - 1])} — колебание на границе (уверенность ${f2(m.conf[0])} / ${f2(m.conf[1])} ниже порога ${f2(meta.final.tau)}).`);
    const natTot = d3.median(ok, (x) => x.spend);
    const kv = P.append("div").attr("class", "kv");
    const add = (k, v) => { kv.append("div").attr("class", "k").text(k); kv.append("div").attr("class", "v").text(v); };
    add("Население, 1.01.2024", m.pop ? fInt(m.pop) : "—");
    add("Траты на жителя, ₽/мес.", fInt(m.spend));
    add("К медиане России", (m.spend >= natTot ? "+" : "") + fPct(m.spend / natTot - 1));
    add("Доступность рынков (0–1000)", m.ma == null ? "—" : fInt(m.ma));
    add("Летом траты сверх сезона страны", (m.summer > 0 ? "+" : "") + fPct(Math.expm1(m.summer)));
    add("Рост трат 2024/2023 отн. страны", metricFmt.growth(m.growth));
    add("Уверенность в типе 2023 / 2024", `${f2(m.conf[0])} / ${f2(m.conf[1])}`);
    // доли: МО vs тип vs Россия
    const natSh = d3.range(5).map((j) => d3.median(ok, (x) => x.shares[j]));
    const tb = P.append("table");
    tb.append("tr").html("<th>Доля трат</th><th>МО</th><th>Тип</th><th>Россия</th>");
    d3.range(5).forEach((j) => tb.append("tr").html(`<td>${CAT_SHORT[j]}</td><td>${fPct(m.shares[j])}</td><td>${fPct(types[t].shares[j])}</td><td>${fPct(natSh[j])}</td>`));
    const sr = series[m.id];
    if (sr) {
      P.append("h4").style("margin", "14px 0 4px").style("font-size", "14px").text("Траты на жителя по месяцам, ₽");
      const div = P.append("div").node();
      const tt = types[m.type];
      lineChart(div, {
        n: meta.months.length, ticks: [0, 6, 12, 18, 23], xFmt: monthFmt,
        series: [{ name: m.name, values: sr[0], color: C.ink }, { name: "Медиана типа", values: tt.q50, color: tt.color }],
        band: { lo: tt.q25, hi: tt.q75, color: tt.color },
      });
    }
    P.append("h4").style("margin", "12px 0 2px").style("font-size", "14px").text("Соседи в сети: синхронность трат (линии на карте)");
    const ul = P.append("ul").attr("class", "examples");
    m.nb.map((id) => byId.get(id)).filter(Boolean).forEach((x) => ul.append("li").attr("tabindex", 0).html(`<span class="sw" style="background:${dColor(x.type)}"></span><span><b>${x.name}</b><span class="t">${x.region} · ${short(types[x.type])}</span></span>`).on("click", () => select(x.id, true)).on("keydown", (ev) => { if (ev.key === "Enter") select(x.id, true); }));
  }

  /* ---------- типы ---------- */
  const natSh = d3.range(5).map((j) => d3.median(ok, (x) => x.shares[j]));
  // макротипы: полоса показывает, из каких типов состоит макротип
  const mrow = d3.select("#macro-row");
  macro.forEach((mc) => {
    const inM = ok.filter((m) => m.macro === mc.id);
    const parts = d3.rollups(inM, (v) => v.length, (m) => m.type).sort((a, b) => b[1] - a[1]);
    const el = mrow.append("div").attr("class", "macro");
    const bar = el.append("div").attr("class", "mbar");
    parts.forEach(([t, c]) => bar.append("span").style("flex", c).style("background", types[t].color)
      .on("mousemove", (ev) => showTip(ev, `<b>${types[t].name}</b><br>${fInt(c)} МО макротипа (${fPct0(c / inM.length)})`)).on("mouseleave", hideTip));
    el.append("h3").html(`<span class="sw" style="background:${mc.color}"></span>${mc.name}`);
    el.append("div").attr("class", "mnum").text(`${fInt(mc.size)} МО · ${fInt(mc.spend)} ₽ на жителя в мес.`);
    el.append("p").text(mc.description);
    el.append("div").attr("class", "mtypes").text("Состав: " + parts.filter(([, c]) => c / inM.length >= 0.05).map(([t, c]) => `${short(types[t])} ${fPct0(c / inM.length)}`).join(" · "));
  });
  const grid = d3.select("#types-grid");
  const ordered = macro.flatMap((mc) => types.filter((t) => t.macro === mc.id));
  const pr = d3.geoConicEqualArea().parallels([52, 64]).rotate([-100, 0]).fitExtent([[4, 4], [596, 296]], geo);
  ordered.forEach((t) => {
    const showType = () => {
      state.level = "types"; d3.select("#f-level").property("value", "types");
      state.isolate = t.id; state.mode = "type"; d3.select("#f-mode").property("value", "type"); buildScale(); paint();
      document.getElementById("map").scrollIntoView({ behavior: "smooth" });
    };
    const c = grid.append("div").attr("class", "tcard").attr("tabindex", 0).attr("role", "button").attr("aria-label", `Показать тип «${t.name}» на карте`)
      .on("click", showType).on("keydown", (ev) => { if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); showType(); } });
    const inT = ok.filter((m) => m.type === t.id);
    const parts = d3.rollups(inT, (v) => v.length / inT.length, (m) => m.macro).sort((a, b) => b[1] - a[1]);
    const transitional = parts.length && parts[0][1] < 0.7;
    c.append("div").attr("class", "tmacro").text(transitional ? "Переходный тип" : `Макротип «${macro[t.macro].name}»`);
    c.append("h3").html(`<span class="sw" style="background:${t.color}"></span>${t.name}`);
    const cw = 600, ch = 300, dpr = window.devicePixelRatio || 1;
    const cv = c.append("canvas").attr("width", cw * dpr).attr("height", ch * dpr).attr("role", "img").attr("aria-label", `Карта: где находится тип «${t.name}»`).node();
    const ctx = cv.getContext("2d"); ctx.scale(dpr, dpr);
    const gp = d3.geoPath(pr, ctx);
    if (extra) extra.features.forEach((f) => { ctx.beginPath(); gp(f); ctx.fillStyle = "#f4f3ef"; ctx.fill(); });
    geo.features.forEach((f) => {
      const m = byId.get(f.id);
      ctx.beginPath(); gp(f);
      ctx.fillStyle = m && m.status === "ok" && m.type === t.id ? t.color : (m && m.status === "ok" ? C.other : "#f4f3ef");
      ctx.fill();
    });
    c.append("p").text(t.description);
    if (transitional) c.append("p").attr("class", "transit").html(`<b>Переходный тип:</b> на макроуровне его МО делятся между ${parts.map(([k, s]) => `«${macro[k].name}» ${fPct0(s)}`).join(", ")}.`);
    if (t.mirkin_top) c.append("p").style("font-size", "12px").html(`<b>Отличия от среднего по МО</b> (правило Миркина): ${t.mirkin_top.replace(/-/g, "−")}`);
    c.append("div").attr("class", "nums").html(`<div><b>${fInt(t.size)}</b>МО</div><div><b>${fInt(t.spend)} ₽</b>трат на жителя в мес.</div><div><b>${fInt(t.ma)}</b>доступность рынков</div>`);
    const bars = c.append("div").attr("class", "bars");
    d3.range(5).forEach((j) => {
      const r = bars.append("div").attr("class", "row");
      r.append("span").text(CAT_SHORT[j]);
      const b = r.append("span").style("position", "relative").style("height", "8px").style("background", "#f0efec").style("border-radius", "4px");
      b.append("span").style("position", "absolute").style("left", 0).style("top", 0).style("bottom", 0).style("border-radius", "4px")
        .style("width", Math.min(100, (t.shares[j] / 0.55) * 100) + "%").style("background", t.color);
      b.append("span").style("position", "absolute").style("top", "-3px").style("bottom", "-3px").style("width", "2px").style("background", C.ink)
        .style("left", Math.min(100, (natSh[j] / 0.55) * 100) + "%").attr("title", "медиана России");
      r.append("span").text(fPct(t.shares[j]));
    });
    c.append("div").attr("class", "typ").text("Типичные: " + t.typical);
  });
  const tt = d3.select("#types-table").append("table");
  tt.append("tr").html("<th>Тип</th><th>МО</th><th>Траты, ₽</th>" + CAT_SHORT.map((c) => `<th>${c}</th>`).join("") + "<th>Летний избыток</th><th>Доступность рынков</th>");
  types.forEach((t) => tt.append("tr").html(`<td><span class="sw" style="background:${t.color}"></span> ${t.name}</td><td>${t.size}</td><td>${fInt(t.spend)}</td>` +
    t.shares.map((s) => `<td>${fPct(s)}</td>`).join("") + `<td>${fPct(Math.expm1(t.summer))}</td><td>${fInt(t.ma)}</td>`));

  /* ---------- динамика ---------- */
  const T = meta.transitions, TC = meta.transitions_confident;
  const tm = d3.select("#trans").append("table").attr("class", "tm");
  const hr = tm.append("tr"); hr.append("th").text("2023 \\ 2024");
  types.forEach((t) => hr.append("th").attr("class", "col").attr("title", t.name).html(`<span class="sw" style="background:${t.color}"></span>${short(t)}`));
  T.forEach((row, i) => {
    const tr = tm.append("tr");
    tr.append("th").style("text-align", "left").attr("title", types[i].name).html(`<span class="tname"><span class="sw" style="background:${types[i].color}"></span> ${short(types[i])}</span>`);
    const tot = d3.sum(row);
    row.forEach((v, j) => {
      const sh = tot ? v / tot : 0;
      tr.append("td").style("background", v ? d3.interpolateRgb("#fcfcfb", "#256abf")(Math.min(1, sh * 1.1)) : null)
        .style("color", sh > 0.55 ? "#fff" : null).style("font-weight", i === j ? 700 : null)
        .html(v ? `${v}${i !== j && TC[i][j] ? ` <small>(${TC[i][j]})</small>` : ""}` : "")
        .on("mousemove", (ev) => showTip(ev, `<b>${types[i].name} → ${types[j].name}</b><br>${v} МО (${fPct(sh)} строки)` + (i !== j ? `<br>значимых переходов: ${TC[i][j]}` : ""))).on("mouseleave", hideTip);
    });
  });
  // аллювиальная диаграмма: столбцы — типы 2023 и 2024, ленты — потоки МО
  (function alluvial() {
    const w = 1100, h = 440, top = 22, padY = 6, colW = 16, x0 = 375, x1 = w - 375;
    const n = d3.sum(T.flat());
    const ky = (h - top - padY * (types.length - 1)) / n;
    const svgA = d3.select("#alluvial").append("svg").attr("viewBox", `0 0 ${w} ${h}`).attr("width", "100%").attr("role", "img")
      .attr("aria-label", "Потоки МО между типами 2023 и 2024 годов");
    const outT = T.map((r) => d3.sum(r)), inT = types.map((_, j) => d3.sum(T, (r) => r[j]));
    const yL = [], yR = [];
    let acc = top; outT.forEach((v, i) => { yL.push(acc); acc += v * ky + padY; });
    acc = top; inT.forEach((v, j) => { yR.push(acc); acc += v * ky + padY; });
    const offL = yL.slice(), offR = yR.slice();
    const links = [];
    // поток делится на значимую часть и колебания на границе: ширина каждой — своё число МО
    T.forEach((row, i) => row.forEach((v, j) => {
      if (!v) return;
      if (i === j) { links.push({ i, j, v, kind: "keep", total: v, sig: 0 }); return; }
      const sg = TC[i][j];
      if (sg) links.push({ i, j, v: sg, kind: "sig", total: v, sig: sg });
      if (v - sg) links.push({ i, j, v: v - sg, kind: "edge", total: v, sig: sg });
    }));
    // порядок лент: сначала к верхним целям, чтобы ленты меньше пересекались
    const ord = { sig: 0, edge: 1, keep: 0 };
    links.sort((a, b) => a.i - b.i || a.j - b.j || ord[a.kind] - ord[b.kind]);
    const lyL = new Map(), lyR = new Map();
    links.forEach((l) => { lyL.set(l, offL[l.i]); offL[l.i] += l.v * ky; });
    [...links].sort((a, b) => a.j - b.j || a.i - b.i || ord[a.kind] - ord[b.kind]).forEach((l) => { lyR.set(l, offR[l.j]); offR[l.j] += l.v * ky; });
    const band = (l) => {
      const a0 = lyL.get(l), a1 = a0 + l.v * ky, b0 = lyR.get(l), b1 = b0 + l.v * ky, xm = (x0 + colW + x1) / 2;
      return `M${x0 + colW},${a0}C${xm},${a0} ${xm},${b0} ${x1},${b0}L${x1},${b1}C${xm},${b1} ${xm},${a1} ${x0 + colW},${a1}Z`;
    };
    svgA.append("g").selectAll("path").data(links).join("path").attr("d", band)
      .attr("fill", (l) => types[l.i].color)
      .attr("fill-opacity", (l) => (l.kind === "keep" ? 0.2 : l.kind === "sig" ? 0.9 : 0.3))
      .on("mousemove", (ev, l) => showTip(ev, `<b>${types[l.i].name} → ${types[l.j].name}</b><br>` + (l.kind === "keep" ? `${fInt(l.v)} МО сохранили тип` : `${fInt(l.total)} МО сменили тип, из них значимо — ${fInt(l.sig)}`)))
      .on("mouseleave", hideTip);
    const col = (x, ys, vals, anchor, dx) => types.forEach((t, k) => {
      svgA.append("rect").attr("x", x).attr("y", ys[k]).attr("width", colW).attr("height", Math.max(1, vals[k] * ky)).attr("fill", t.color).attr("rx", 2);
      svgA.append("text").attr("x", x + dx).attr("y", ys[k] + (vals[k] * ky) / 2).attr("dy", "0.35em").attr("text-anchor", anchor)
        .attr("font-size", 12).attr("fill", C.ink).text(`${t.name} · ${fInt(vals[k])}`);
    });
    col(x0, yL, outT, "end", -8);
    col(x1, yR, inT, "start", colW + 8);
    svgA.append("text").attr("x", x0 + colW / 2).attr("y", 12).attr("text-anchor", "middle").attr("font-size", 12).attr("fill", C.muted).text("2023");
    svgA.append("text").attr("x", x1 + colW / 2).attr("y", 12).attr("text-anchor", "middle").attr("font-size", 12).attr("fill", C.muted).text("2024");
  })();
  const flows = d3.rollups(ok.filter((m) => m.moved), (v) => v, (m) => m.types[0] + ">" + m.types[W.length - 1]).sort((a, b) => b[1].length - a[1].length).slice(0, 12);
  const fl = d3.select("#flows");
  fl.append("p").attr("class", "sub").text(`Значимые переходы: ${fInt(moved)} МО (порог уверенности τ = ${f2(meta.final.tau)}). Направления и примеры:`);
  flows.forEach(([key, arr]) => {
    const [a, b] = key.split(">").map(Number);
    const r = fl.append("div").attr("class", "flow");
    r.append("span").html(`<span class="sw" style="background:${tColor(a)}"></span> ${tName(a)}`);
    r.append("span").text("→");
    r.append("span").html(`<span class="sw" style="background:${tColor(b)}"></span> ${tName(b)}`);
    r.append("span").attr("class", "n").text(arr.length);
    fl.append("div").attr("class", "flow-ex")
      .text(arr.slice(0, 4).map((m) => `${m.name} (${m.region})`).join("; "));
  });
  const ts0 = d3.select("#tau-sens").append("details").attr("class", "table-view");
  ts0.append("summary").text("Чувствительность к порогу уверенности τ");
  const tst = ts0.append("table");
  tst.append("tr").html("<th>τ</th><th>Сменили тип формально</th><th>Значимых переходов</th>");
  meta.moves_sensitivity.forEach((r) => tst.append("tr").classed("final", Math.abs(r.tau - meta.final.tau) < 1e-9).html(`<td>${f2(r.tau)}</td><td>${fInt(r.changed_type)}</td><td>${fInt(r.confident_moves)}</td>`));
  const dyn = meta.dynamics;
  const wc = d3.select("#win-charts");
  [["SW", "Силуэт (признаки)", f3], ["MQ", "Модулярность (сеть)", f3]].forEach(([key, label, fmt]) => {
    const d = wc.append("div"); d.append("div").attr("class", "chart-label").text(label);
    lineChart(d.node(), { n: dyn.length, ticks: [0, 6, 12], xFmt: (i, long) => (long ? winLabel(W[i]) : `до ${MON[+W[i].slice(5) - 1]} ${W[i].slice(2, 4)}`), yFmt: fmt, series: [{ name: label, values: dyn.map((r) => r[key]), color: "#2a78d6" }], legend: false, w: 560, h: 150 });
  });
  const ts = d3.select("#type-series").node();
  lineChart(ts, { n: meta.months.length, ticks: [0, 6, 12, 18, 23], xFmt: monthFmt, h: 230, w: 560,
    series: types.map((t) => ({ name: t.name, values: t.q50, color: t.color })).concat([{ name: "Россия (медиана МО)", values: meta.national.total, color: C.ink, dash: "4 3", width: 1.5 }]) });

  /* ---------- метод ---------- */
  const steps = [
    ["Данные", `${fInt(meta.n_panel)} МО × 24 мес. × 6 категорий трат СберИндекса; справочник МО, доступность рынков, дороги.`],
    ["Признаки узлов", "Уровень трат, лог-профиль 5 категорий (CLR), сезонность сверх общероссийской — всё относительно медианы страны."],
    ["Рёбра: 5 правил", "Признаки, корреляция рядов, косинус корзины, DTW с лагом, дороги. Основное — синхронность трат."],
    ["5 методов + ICVI", "k-means, Ward, спектральный, Leiden, KEFRiN; SW, CH, S_Dbw, MQ, AVI, AVU, устойчивость."],
    ["Выбор", "Коупленд по 45 конфигурациям выбирает метод и макроуровень; детальный уровень — тот же метод, наименьшее k ≥ 6 с ARI ≥ 0,75; доля сети — наибольшая при потере силуэта ≤ 0,005."],
    ["Динамика", "13 скользящих годовых окон, своя сеть в каждом; KEFRiN с якорным стартом; значимый переход — уверенность ≥ τ в 2023 и в 2024."],
  ];
  d3.select("#pipeline").selectAll("li").data(steps).join("li").html((d) => `<b>${d[0]}</b>${d[1]}`);
  const gtab = d3.select("#graphs-table").append("table");
  gtab.append("tr").html("<th>Правило</th><th>Рёбер</th><th>Ср. степень</th><th>Компонент</th><th>Гомофилия</th><th>Внутри региона</th><th>Медиана длины ребра, км</th><th>ARI с итогом</th><th>NMI сообществ с регионом</th>");
  const rulesBy = new Map(meta.rules.map((r) => [r.rule, r]));
  meta.graphs.forEach((r) => {
    const rr = rulesBy.get(r.rule) || {};
    gtab.append("tr").classed("final", r.rule === "corr").html(`<td>${RULE_RU[r.rule] || r.rule}${r.rule === "corr" ? " — основное" : ""}</td><td>${fInt(r.edges)}</td><td>${f2(r.mean_degree)}</td><td>${r.components}</td><td>${f2(r.attr_homophily)}</td><td>${fPct(r.same_region_share)}</td><td>${fInt(r.median_edge_road_km)}</td><td>${rr.ARI_vs_main != null ? f2(rr.ARI_vs_main) : "—"}</td><td>${rr.leiden_NMI_with_region != null ? f2(rr.leiden_NMI_with_region) : "—"}</td>`);
  });
  const jd = d3.select("#graphs-table").append("details").attr("class", "table-view");
  jd.append("summary").text("Пересечение рёбер между правилами (индекс Жаккара)");
  const jt = jd.append("table"); const rs = Object.keys(meta.jaccard);
  jt.append("tr").html("<th></th>" + rs.map((r) => `<th>${RULE_RU[r]}</th>`).join(""));
  rs.forEach((a) => jt.append("tr").html(`<td>${RULE_RU[a]}</td>` + rs.map((b) => `<td>${f2(meta.jaccard[b][a])}</td>`).join("")));

  const sw = d3.select("#sweep");
  const chosen = meta.final.net_share;
  [["SW", "Силуэт ↑"], ["MQ", "Модулярность ↑"]].forEach(([key, label]) => {
    const d = sw.append("div"); d.append("div").attr("class", "chart-label").text(label);
    const vals = meta.sweep.map((r) => r[key]);
    const ci = meta.sweep.findIndex((r) => Math.abs(r.net_share - chosen) < 1e-9);
    lineChart(d.node(), { n: vals.length, ticks: d3.range(vals.length).filter((i) => i % 2 === 0), xFmt: (i) => f2(meta.sweep[i].net_share).replace(",00", ""), yFmt: f3, h: 150,
      series: [{ name: label, values: vals, color: "#2a78d6" }], legend: false, marker: ci >= 0 ? { i: ci, v: vals[ci], color: "#eb6834" } : null });
  });
  sw.append("p").attr("class", "note").style("grid-column", "1/-1").text(`Оранжевая точка — выбранная доля сети ${f2(chosen)}: правило берёт наибольшую долю, при которой силуэт теряет не больше 0,005 относительно k-means. До неё модулярность растёт почти без потерь по признакам, после 0,5 силуэт обрывается вдвое.`);

  const ex = meta.external;
  d3.select("#external").append("div").attr("class", "ext").selectAll("div").data([
    [fPct0(ex["eta2:log_pop"]), "η² логарифма численности населения (Росстат)"],
    [fPct0(ex.eta2_market_access), "η² индекса доступности рынков СберИндекса"],
    [f2(ex["V:arctic_any"]), "V Крамера с Арктической зоной"],
    [f2(ex["V:far_north_or_equated"]), "V Крамера с районами Крайнего Севера"],
    [f2(ex.cramers_v_mo_type), "V Крамера с видом МО (город / район / округ)"],
    [f2(ex.cramers_v_region), "V Крамера с регионом"],
  ]).join("div").attr("class", "tile").html((d) => `<div class="v">${d[0]}</div><div class="l">${d[1]}</div>`);
  d3.select("#external").append("p").attr("class", "note").text("η² — доля разброса показателя, которую объясняют 6 типов; V Крамера — сила связи с категорией от 0 до 1. Модель не видела ни одной из этих характеристик.");

  const J = meta.justification;
  if (J && J.admin) {
    const A = J.admin, rowsA = [["eta2:log_pop", "η² численности населения"], ["eta2_market_access", "η² доступности рынков"], ["V:arctic_any", "V: Арктическая зона"],
      ["V:far_north_or_equated", "V: Крайний Север"], ["V:monotown", "V: моногорода"], ["V:onp_agglomeration_core", "V: ядра агломераций"], ["V:regional_capital", "V: столицы регионов"]];
    const at = d3.select("#admin-table").append("table");
    at.append("tr").html(`<th>Внешний показатель</th><th>${A.types.groups} типов</th><th>Вид МО (${A.mo_kind.groups} категории)</th>`);
    let wins = 0;
    rowsA.forEach(([k, l]) => {
      const a = A.types[k], b = A.mo_kind[k];
      if (a > b) wins += 1;
      at.append("tr").html(`<td>${l}</td><td class="${a > b ? "best" : ""}">${f2(a)}</td><td class="${b > a ? "best" : ""}">${f2(b)}</td>`);
    });
    d3.select("#admin-table").append("p").attr("class", "note").style("margin-top", "10px").text(`Типы связаны с внешними метками сильнее, чем официальный вид МО, в ${wins} из ${rowsA.length} показателей. Вид МО выигрывает там, где метка почти совпадает с ним по определению (столица региона — всегда городской округ). Типология добавляет к административному делению то, чего в нём нет: север, удалённость и уклад потребления.`);
  }
  if (J && J.network) {
    const N = J.network;
    d3.select("#net-adds").html(`<div class="big-stat">
      <div class="tile"><div class="v">${fInt(N.reassigned)}</div><div class="l">МО сеть перевела в другой тип; остальные ${fInt(meta.n_panel - N.reassigned)} — как у k-means (ARI ${f2(N.ari_kefrin_vs_kmeans)})</div></div>
      <div class="tile"><div class="v">${fPct0(N.sync_within_reassigned_kmeans)} → ${fPct0(N.sync_within_reassigned_kefrin)}</div><div class="l">доля связей синхронности у этих МО внутри своего типа: k-means → KEFRiN</div></div></div>
      <p class="note">По всем МО доля связей синхронности внутри типов — ${fPct0(N.sync_within_kmeans)} у k-means и ${fPct0(N.sync_within_kefrin)} у KEFRiN; силуэт переназначенных МО ${f3(N.silhouette_reassigned_kmeans)} → ${f3(N.silhouette_reassigned_kefrin)}: это пограничные МО, по профилю трат они почти одинаково близки к двум типам. Сеть не создаёт типы, а решает такие пограничные случаи в пользу тех, с кем траты колеблются синхронно. Поэтому типология почти не зависит от правила рёбер (ARI 0,86–0,90).</p>`);
  }
  // устойчивость к настройкам: одна настройка меняется, остальные как в итоге
  (function robust() {
    const BLK = { level: "уровень трат", profile: "структура корзины", season: "сезонность" };
    const chip = (label, ari, fin) => `<span class="chip" style="margin:2px 4px 2px 0${fin ? ";border-color:#0b0b0b" : ""}">${label}: <b>${f2(ari)}</b></span>`;
    const rt = d3.select("#robust").append("table").attr("class", "left");
    rt.append("tr").html("<th>Настройка</th><th>Совпадение 6 типов с итогом (ARI)</th>");
    if (meta.knn_sensitivity.length) rt.append("tr").html(`<td>Число соседей в сети</td><td>${meta.knn_sensitivity.map((r) => chip(`k = ${r.k_nn}`, r.ARI_vs_main, r.k_nn === 15)).join("")}</td>`);
    rt.append("tr").html(`<td>Правило рёбер</td><td>${meta.rules.map((r) => chip(RULE_RU[r.rule].replace(/ \(.*\)/, ""), r.ARI_vs_main, r.rule === "corr")).join("")}</td>`);
    const WS = meta.weights_sensitivity;
    d3.groups(WS, (r) => r.block).forEach(([b, rs]) => rt.append("tr").html(`<td>Вес блока «${BLK[b] || b}»</td><td>${rs.map((r) => chip(`× ${ru.format(".1f")(r.weight)}`, r.ARI_vs_main)).join("")}</td>`));
    const net = [...meta.knn_sensitivity.filter((r) => r.k_nn !== 15), ...meta.rules.filter((r) => r.rule !== "corr")].map((r) => r.ARI_vs_main);
    const sh = meta.justification && meta.justification.block_variance_share;
    let txt = `Обведено — итоговое значение. К настройкам сети типология нечувствительна: ARI ${f2(d3.min(net))}–${f2(d3.max(net))}.`;
    if (WS.length && WS[0].jaccard_type0 != null) {
      const variants = WS.filter((r) => !(r.block === "season" && r.weight >= 1));
      const minJ = types.map((t) => d3.min(variants, (r) => r[`jaccard_type${t.id}`]));
      const stable = types.filter((t, i) => minJ[i] >= 0.7).map((t) => `«${short(t)}»`);
      const moving = types.filter((t, i) => minJ[i] < 0.7).map((t) => `«${short(t)}»`);
      txt += ` Веса блоков важнее: при изменении на ±30% макроуровень сохраняется (ARI ${f2(d3.min(variants, (r) => r.ARI_macro_vs_main))}–${f2(d3.max(variants, (r) => r.ARI_macro_vs_main))}), устойчивы ${stable.join(", ")}; сдвигаются границы трёх типов — ${moving.join(", ")}: они различаются в первую очередь сезонностью и структурой корзины и лежат на непрерывном спектре.`;
    }
    if (sh) txt += ` Итоговые веса выбраны так, чтобы три блока давали равные доли разброса: уровень ${fPct0(sh.level)}, корзина ${fPct0(sh.profile)}, сезонность ${fPct0(sh.season)}; при весе сезонности 1,0 её доля выросла бы до ${fPct0((WS.find((r) => r.block === "season" && r.weight >= 1) || {}).block_share || NaN)} и перестроила бы макроуровень.`;
    d3.select("#robust").append("p").attr("class", "note").style("margin-top", "10px").text(txt);
  })();
  // карта компромиссов: силуэт (признаки) против модулярности (сеть) для всех конфигураций
  (function tradeoff() {
    const rows = meta.methods.filter((r) => r.SW != null && r.MQ != null);
    const MC = { kmeans: "#6c6a65", ward: "#b9b7ae", spectral: "#2a78d6", leiden: "#1baf7a", kefrin: "#eb6834" };
    const w = 600, h = 340, m = { t: 18, r: 18, b: 44, l: 52 };
    const s = d3.select("#tradeoff").append("svg").attr("viewBox", `0 0 ${w} ${h}`).attr("width", "100%").attr("role", "img")
      .attr("aria-label", "Силуэт и модулярность всех 45 конфигураций методов");
    const x = d3.scaleLinear().domain(d3.extent(rows, (r) => r.SW)).nice().range([m.l, w - m.r]);
    const y = d3.scaleLinear().domain(d3.extent(rows, (r) => r.MQ)).nice().range([h - m.b, m.t]);
    const rr = d3.scaleSqrt().domain([0.4, 1]).range([3, 10]).clamp(true);
    s.append("g").attr("class", "gridline").attr("transform", `translate(${m.l},0)`).call(d3.axisLeft(y).ticks(5).tickSize(-(w - m.l - m.r)).tickFormat("")).select(".domain").remove();
    s.append("g").attr("class", "gridline").attr("transform", `translate(0,${h - m.b})`).call(d3.axisBottom(x).ticks(6).tickSize(-(h - m.t - m.b)).tickFormat("")).select(".domain").remove();
    s.append("g").attr("class", "axis").attr("transform", `translate(${m.l},0)`).call(d3.axisLeft(y).ticks(5).tickFormat(f2)).select(".domain").remove();
    s.append("g").attr("class", "axis").attr("transform", `translate(0,${h - m.b})`).call(d3.axisBottom(x).ticks(6).tickFormat(f2)).select(".domain").remove();
    s.append("text").attr("x", w - m.r).attr("y", h - 8).attr("text-anchor", "end").attr("font-size", 11).attr("fill", C.muted).text("силуэт по признакам →");
    s.append("text").attr("x", m.l).attr("y", 10).attr("font-size", 11).attr("fill", C.muted).text("↑ модулярность сети");
    const pts = [...rows].sort((a, b) => (a.method === "kefrin") - (b.method === "kefrin"));
    s.append("g").selectAll("circle").data(pts).join("circle").attr("cx", (r) => x(r.SW)).attr("cy", (r) => y(r.MQ)).attr("r", (r) => rr(r.stability_ARI ?? 0.6))
      .attr("fill", (r) => MC[r.method]).attr("fill-opacity", 0.8).attr("stroke", "#fcfcfb").attr("stroke-width", 1)
      .on("mousemove", (ev, r) => showTip(ev, `<b>${METHOD_RU[r.method]}, k = ${r.k}</b><br>силуэт ${f3(r.SW)} · модулярность ${f3(r.MQ)}<br>устойчивость ${r.stability_ARI == null ? "—" : f3(r.stability_ARI)} · Коупленд ${r.copeland == null ? "—" : fInt(r.copeland)}`))
      .on("mouseleave", hideTip);
    // подписи итоговых конфигураций — в свободном правом верхнем углу, с выносками к точкам
    [[meta.final.method, meta.final.macro_k, "макроуровень: KEFRiN, 4 типа"], [meta.final.method, meta.final.k, "итог: KEFRiN, 6 типов"]].forEach(([mm, kk, label], i) => {
      const r = rows.find((q) => q.method === mm && q.k === kk);
      if (!r) return;
      const px = x(r.SW), py = y(r.MQ), ly = m.t + 30 + i * 30, lx = px - 6;
      s.append("circle").attr("cx", px).attr("cy", py).attr("r", rr(r.stability_ARI ?? 0.6) + 3).attr("fill", "none").attr("stroke", C.ink).attr("stroke-width", 1.5).style("pointer-events", "none");
      s.append("path").attr("d", `M${px},${py - rr(r.stability_ARI ?? 0.6) - 3}L${px},${ly + 6}`).attr("stroke", C.ink).attr("stroke-width", 0.8).attr("fill", "none");
      s.append("text").attr("x", lx).attr("y", ly).attr("text-anchor", "end").attr("font-size", 12).attr("font-weight", 600).attr("fill", C.ink).text(label);
    });
    const lg = d3.select("#tradeoff").append("div").attr("class", "legend");
    Object.entries(MC).forEach(([k, c]) => lg.append("span").attr("class", "item").html(`<span class="sw" style="background:${c};border-radius:50%"></span>${METHOD_RU[k]}`));
    d3.select("#tradeoff").append("p").attr("class", "note").style("margin-top", "8px").text("Методы только по признакам лежат справа внизу, только по сети — слева вверху: силуэт около нуля, типы не различаются по тратам. KEFRiN держит силуэт k-means и поднимает модулярность — лучший компромисс; правило Коупленда выбирает его без ручного вмешательства.");
  })();

  const fk = meta.final.k, fm = meta.final.method;
  const cols = [["SW", 1], ["CH", 1], ["S_Dbw", -1], ["MQ", 1], ["AVI", 1], ["AVU", -1], ["ANUI", 1], ["stability_ARI", 1], ["copeland", 1]].filter(([c]) => meta.methods.some((r) => r[c] != null));
  const atK = meta.methods.filter((r) => r.k === fk);
  const best = Object.fromEntries(cols.map(([c, d]) => [c, d > 0 ? d3.max(atK, (r) => r[c]) : d3.min(atK, (r) => r[c])]));
  d3.select("#methods-sub").text(`Все методы при k = ${fk} на одних узлах, признаках и сети. ↑ — больше лучше, ↓ — меньше лучше; жирным — лучшее значение. Коупленд — победы минус поражения в попарных «выборах» метрик по всем 45 конфигурациям. Если сравнивать только методы при k = ${fk}, первым будет спектральный: он выигрывает по графовым индексам и устойчивости, но его силуэт ${f3(meta.methods.find((r) => r.method === "spectral" && r.k === fk).SW)} — типы почти не различаются по профилю трат и не интерпретируются. Поэтому метод выбирается на макроуровне, где KEFRiN — первый из всех конфигураций, а детальный уровень строится тем же методом, чтобы уровни были вложены.`);
  const mt = d3.select("#methods-table").append("table");
  const lab = { SW: "SW ↑", CH: "CH ↑", S_Dbw: "S_Dbw ↓", MQ: "MQ (Q) ↑", AVI: "AVI ↑", AVU: "AVU ↓", ANUI: "ANUI ↑", stability_ARI: "Устойчивость (ARI) ↑", copeland: "Коупленд ↑" };
  mt.append("tr").html("<th>Метод</th>" + cols.map(([c]) => `<th>${lab[c]}</th>`).join(""));
  atK.forEach((r) => mt.append("tr").classed("final", r.method === fm).html(`<td>${METHOD_RU[r.method] || r.method}${r.method === fm ? " — итог" : ""}</td>` +
    cols.map(([c]) => `<td class="${r[c] === best[c] ? "best" : ""}">${r[c] == null ? "—" : c === "CH" || c === "copeland" ? fInt(r[c]) : f3(r[c])}</td>`).join("")));
  const WHEN = [
    ["k-means", "Только признаки узлов", "Быстро, устойчиво, лучший силуэт", "Не видит сети: синхронные, но разные по профилю МО не связываются", "Когда сеть не нужна или ненадёжна"],
    ["Ward", "Только признаки", "Иерархия типов «из коробки»", "Неустойчив на подвыборках (ARI ≈ 0,4)", "Для разведки иерархии, не для итога"],
    ["Спектральный", "Смесь сходств признаков и сети", "Высокие графовые индексы, устойчив", "Силуэт около 0,06: типы не различаются по профилю трат", "Когда важнее связность, чем интерпретация"],
    ["Leiden", "Только сеть", "Максимальная модулярность", "Силуэт около 0: группирует соседей по региону, а не по экономике", "Для поиска сообществ синхронности"],
    ["KEFRiN", "Признаки и сеть в одном критерии", "Держит силуэт k-means и добавляет сетевую структуру; доля сети настраивается", "Требует выбора доли сети; при N ≫ признаков сеть без настройки доминирует", "Атрибутированные сети — наш итог"],
  ];
  const wt = d3.select("#methods-when").append("table").attr("class", "left");
  wt.append("tr").html("<th>Метод</th><th>Что использует</th><th>Сильная сторона</th><th>Ограничение на наших данных</th><th>Когда уместен</th>");
  WHEN.forEach((r) => wt.append("tr").html(r.map((c, i) => (i ? `<td>${c}</td>` : `<td><b>${c}</b></td>`)).join("")));
  const md = d3.select("#methods-table").append("details").attr("class", "table-view");
  md.append("summary").text("Все конфигурации: метод × число типов");
  const mt2 = md.append("table");
  mt2.append("tr").html("<th>Метод</th><th>k</th>" + cols.map(([c]) => `<th>${lab[c]}</th>`).join(""));
  meta.methods.forEach((r) => mt2.append("tr").classed("final", r.method === fm && r.k === fk).html(`<td>${METHOD_RU[r.method]}</td><td>${r.k}</td>` +
    cols.map(([c]) => `<td>${r[c] == null ? "—" : c === "CH" || c === "copeland" ? fInt(r[c]) : f3(r[c])}</td>`).join("")));

  const fi = meta.final_icvi;
  const fiKeys = [["SW", "SW ↑"], ["CH", "CH ↑"], ["S_Dbw", "S_Dbw ↓"], ["MQ", "MQ (Q) ↑"], ["AVI", "AVI ↑"], ["AVU", "AVU ↓"], ["ANUI", "ANUI ↑"]];
  const fit = d3.select("#final-icvi").append("div").append("table");
  fit.append("tr").html("<th>Индекс</th><th>Итог</th><th>Случайное разбиение</th><th>z</th>");
  fiKeys.forEach(([k, l]) => fit.append("tr").html(`<td>${l}</td><td>${k === "CH" ? fInt(fi[k]) : f3(fi[k])}</td><td>${k === "CH" ? fInt(fi.random_mean[k]) : f3(fi.random_mean[k])}</td><td>${fi.vs_random_z[k] == null ? "—" : ru.format(",.1f")(fi.vs_random_z[k])}</td>`));
  d3.select("#final-icvi").append("div").append("p").attr("class", "note").text(`z > 0 — итог лучше случайного с учётом направления индекса. AVU у всех методов (0,45–0,50) близок к случайному уровню и даже хуже его: на kNN-графе синхронности межтиповые связи сосредоточены между соседними по профилю типами, поэтому AVU здесь не различает разбиения — выводы опираются на AVI, MQ и ANUI. S_Dbw: Scat = ${f3(fi.Scat)}, Dens_bw = ${f3(fi.Dens_bw)}; кластеров с нулевой плотностью в центре — ${fi.S_Dbw_zero_density_clusters}, поэтому S_Dbw сравнивается только при одинаковом k. CH/N = ${f3(fi.CH_per_N)}. MQ трактуется как модулярность Ньюмана–Гирван (в Положении не расшифрован).`);

  /* ---------- калибровка ---------- */
  if (meta.calibration && window.renderCalibration) window.renderCalibration(meta.calibration, { fPct, f2, f3, fInt });
  else if (meta.calibration) d3.select("#calib").html(meta.calibration.html || "");

  /* ---------- международный опыт и официальные метки ---------- */
  d3.select("#intl").html(`
    <h3>Как типологизируют локальные экономики в мире</h3>
    <p><b>США</b> (USDA ERS, County Typology Codes 2025): округ относят к фермерскому, добывающему, обрабатывающему, государственному или рекреационному типу, если доля отрасли в заработках или занятости выше порога «среднее по неметро-округам + 1 СКО». <b>Канада</b> (StatCan, Index of Remoteness): удалённость по гравитационной формуле Σ население / издержки доступа — та же форма, что у индекса доступности рынков СберИндекса. <b>ЕС и ОЭСР</b> (DEGURBA, TL3), <b>Австралия</b> (ARIA+), <b>Бразилия</b> (REGIC) — пороги урбанизации, удалённости и иерархии центров.</p>
    <p><b>Закономерность:</b> официальные типологии строятся пороговыми правилами по структуре <i>производства</i> (занятость, заработки) и <i>удалённости</i>. Открытых местных данных о тратах вместе с типологией нет ни в одной стране — типология по потреблению даёт новый ракурс.</p>
    <h3>Проверка на США</h3>
    <p>Открытые карточные данные по округам (Opportunity Insights, Affinity) содержат только общий индекс трат к январю 2020 — без категорий и уровней. Кластеризация по их динамике официальные производственные типы ERS почти не восстанавливает (ARI ≈ 0,03, NMI ≈ 0,02 на 1 971 округе; AUC «фермерский против остальных» 0,75, рекреационный 0,66). Вывод для нашей работы: типы по тратам — самостоятельная <i>потребительская</i> оптика, а не замена производственной классификации; поэтому названия типов описывают уклад потребления и проверяются российскими официальными категориями территорий.</p>
    <h3>Российский аналог разметки</h3>
    <p>Росстат (численность и перечни на 1.01.2024): моногорода трёх категорий, районы Крайнего Севера и приравненные, Арктическая зона; перечень опорных населённых пунктов (ядра агломераций); столицы регионов. Сопоставлено по ОКТМО с 2 176 из 2 190 МО.</p>`);
  const OFF = [["arctic_any", "Арктика"], ["far_north_or_equated", "Крайний Север"], ["monotown", "Моно­города"], ["onp_agglomeration_core", "Ядра агломе­раций"], ["regional_capital", "Столицы"]];
  const ot = d3.select("#official").append("table");
  ot.append("tr").html("<th>Тип</th>" + OFF.map((o) => `<th>${o[1]}</th>`).join("") + "<th>Население, медиана</th>");
  const offRow = (t) => ot.append("tr").html(`<td title="${t.name}"><span class="tname"><span class="sw" style="background:${t.color}"></span> ${short(t)}</span></td>` + OFF.map(([k]) => {
    const v = t.official[k];
    return `<td style="background:${v > 0 ? d3.interpolateRgb("#fcfcfb", "#256abf")(Math.min(1, v * 1.2)) : "transparent"};color:${v > 0.6 ? "#fff" : "inherit"}">${fPct0(v)}</td>`;
  }).join("") + `<td>${fInt(t.official.pop_median)}</td>`);
  types.forEach(offRow);
  const ex2 = meta.external;
  d3.select("#official").append("p").attr("class", "note").html(`Связь шести типов с метками (V Крамера): Арктика ${f2(ex2["V:arctic_any"])}, Крайний Север ${f2(ex2["V:far_north_or_equated"])}, моногорода ${f2(ex2["V:monotown"])}, ядра агломераций ${f2(ex2["V:onp_agglomeration_core"])}, столицы ${f2(ex2["V:regional_capital"])}; η² логарифма населения ${f2(ex2["eta2:log_pop"])}.`);

  /* ---------- данные ---------- */
  d3.select("#data-notes").html(`
    <h3>Источник</h3>
    <p>Конкурсный набор СберИндекса: средние безналичные траты жителей МО по категориям, янв 2023 – дек 2024 (${fInt(meta.n_panel + meta.n_dropped)} МО в наборе), индекс доступности рынков 2024, матрица автодорожных и железнодорожных расстояний. Лицензия CC BY-SA 4.0.</p>
    <h3>Что не вошло</h3>
    <p>Регионы, которых нет в наборе организатора: ${meta.missing_regions.join(", ")}. Регионы, все МО которых исключены из-за неполных рядов: ${meta.incomplete_regions.join(", ")} (например, у Бурятии данные только за 2023 год). Всего исключено ${fInt(meta.n_dropped)} МО с неполными рядами.</p>
    <p>Донецкой и Луганской Народных Республик, Запорожской и Херсонской областей нет ни в справочнике муниципальных образований СберИндекса, ни в данных о расходах: на карте они показаны контурами субъектов и в расчёты не входят. Крым и Севастополь в справочнике есть (35 МО), но данных о расходах по ним в наборе нет.</p>
    <p>Структура типов умеренная (силуэт ${f3(meta.final_icvi.SW)}, CH/N ${f3(meta.final_icvi.CH_per_N)} — ниже ориентиров для хорошо разделённых кластеров): территории образуют непрерывный спектр, а типы — его устойчивое разбиение. Поэтому доверие к типам опирается на устойчивость на подвыборках, сравнение со случайным разбиением и внешние официальные метки, а не на один индекс.</p>
    <h3>Как читать</h3>
    <p>Траты номинальные и относятся к безналичным операциям; признаки центрированы медианой страны в каждом месяце, поэтому тип — это относительное положение МО, а не реальный рост доходов. Типы описывают структуру потребления, а не производства; названия типов — интерпретация профилей, подтверждённая внешними признаками (вид МО, доступность рынков). Высокая доля маркетплейсов в сельских типах — доля среди <i>безналичных</i> трат: в сёлах чаще платят наличными, поэтому это гипотеза о замещении редкой розницы, а не вывод.</p>
    <h3>Воспроизведение</h3>
    <p><code>python scripts/download_data.py</code> → <code>python run.py --config configs/default.yaml</code>. Все гиперпараметры — в YAML; результаты — в <code>results/</code>; методология — в <code>docs/report.md</code>.</p>`);

  /* ---------- разобранные примеры ---------- */
  (function cases() {
    const natSpend = d3.median(ok, (x) => x.spend);
    const pctS = (v) => (v >= 0 ? "+" : "−") + fPct0(Math.abs(v));
    const iFS = meta.categories.indexOf("Общественное питание");
    // летний избыток в году y относительно страны: (июнь–август) минус среднее года, в логарифмах — как признак модели
    const yearSummer = (sr, nat, y) => {
      const rel = d3.range(12).map((i) => Math.log(sr[y * 12 + i]) - Math.log(nat[y * 12 + i]));
      return Math.expm1(d3.mean([5, 6, 7], (i) => rel[i]) - d3.mean(rel));
    };
    const fsSummer = (m, y) => yearSummer(series[m.id][1 + iFS], meta.national.cats[iFS], y);
    const byShort = (s) => types.find((t) => short(t) === s);
    const out = [];
    // 1. сравнение внутри типа против сравнения с областью: МО у медианы своего типа, но далеко от медианы области
    const tA = byShort("Аграрная периферия");
    if (tA) {
      const regMed = d3.rollup(ok, (v) => d3.median(v, (x) => x.spend), (x) => x.region);
      const regN = d3.rollup(ok, (v) => v.length, (x) => x.region);
      const mA = ok.filter((x) => x.type === tA.id && regN.get(x.region) >= 10 && Math.abs(x.spend / tA.spend - 1) < 0.05)
        .sort((a, b) => a.spend / regMed.get(a.region) - b.spend / regMed.get(b.region))[0];
      if (mA) out.push({ m: mA, title: "Сравнивать с похожими, а не с областью", facts: [[fInt(mA.spend) + " ₽", "траты на жителя в месяц"], [pctS(mA.spend / regMed.get(mA.region) - 1), "к медиане МО своего региона"], [pctS(mA.spend / tA.spend - 1), "к медиане своего типа"]],
        text: `${mA.name} (${mA.region}) на фоне своего региона выглядит отстающим, но для типа «${tA.name}» это обычный уровень. Рейтинг внутри типа не путает сельский уклад с отставанием и показывает, кто действительно выбивается из похожих.` });
    }
    // 2. ранний сигнал: из главного потока — МО с самым сильным изменением летнего пика в общепите
    const fromT = byShort("Аграрная периферия"), toT = byShort("Глубинка");
    if (fromT && toT && iFS >= 0) {
      const flow = ok.filter((x) => x.moved && x.types[0] === fromT.id && x.types[W.length - 1] === toT.id && series[x.id]);
      const stay = ok.filter((x) => x.types[0] === fromT.id && x.types[W.length - 1] === fromT.id && series[x.id]);
      const mB = flow.filter((x) => Math.min(x.conf[0], x.conf[1]) >= 0.2).sort((a, b) => (fsSummer(b, 0) - fsSummer(b, 1)) - (fsSummer(a, 0) - fsSummer(a, 1)))[0];
      if (mB) {
        const med = (arr, y) => d3.median(arr, (x) => fsSummer(x, y));
        out.push({ m: mB, title: "Ранний сигнал: исчез летний пик", facts: [[pctS(fsSummer(mB, 0)), "летом в общепите сверх страны, 2023"], [pctS(fsSummer(mB, 1)), "то же, 2024"], [`${f2(mB.conf[0])} / ${f2(mB.conf[1])}`, "уверенность в типе 2023 / 2024"]],
          text: `${mB.name} (${mB.region}) уверенно перешёл из «${fromT.name}» в «${toT.name}»: летний подъём трат в общепите сменился провалом. У всех ${fInt(flow.length)} МО этого потока медиана ${pctS(med(flow, 0))} → ${pctS(med(flow, 1))}, у оставшихся в типе — ${pctS(med(stay, 0))} → ${pctS(med(stay, 1))}; обратный поток — ${fInt(meta.transitions_confident[toT.id][fromT.id])} МО. Это кандидаты для проверки сезонного туризма, дачников и отъезда жителей, а не готовый вывод о причине.` });
      }
    }
    // 3. север: высокие траты при низкой доле маркетплейсов
    const tC = arcticType, mC = tC && byId.get(Number(String(tC.typical_ids || "").split(" ")[0]));
    if (mC) {
      out.push({ m: mC, title: "Север: высокие траты, мало онлайн-покупок", facts: [[pctS(mC.spend / natSpend - 1), "траты на жителя к медиане России"], [fPct(mC.shares[4]), `доля маркетплейсов (Россия ${fPct(natSh[4])})`], [mC.ma == null ? "—" : fInt(mC.ma), "доступность рынков из 1000"]],
        text: `${mC.name} (${mC.region}) — типичный представитель «${tC.name}»: траты на жителя ${mC.spend > natSpend ? "выше" : "ниже"} медианы России, а доля маркетплейсов в ${ru.format(".1f")(natSh[4] / mC.shares[4])} раза ниже. Тип собирает территории с похожими условиями доставки и цен — готовый список для логистики и розницы.` });
    }
    const box = d3.select("#cases");
    out.forEach((c) => {
      const el = box.append("div").attr("class", "card case");
      el.append("h3").text(c.title);
      el.append("div").attr("class", "facts").html(c.facts.map(([v, l]) => `<div><b>${v}</b>${l}</div>`).join(""));
      el.append("p").text(c.text);
      el.append("button").attr("type", "button").attr("class", "btn").text(`Показать ${c.m.name} на карте`).on("click", () => {
        state.isolate = null; select(c.m.id, true);
        document.getElementById("map").scrollIntoView({ behavior: "smooth" });
      });
    });
  })();

  buildScale();
  paint();
  renderHome();
  // Esc — вернуться к стартовой карточке
  document.addEventListener("keydown", (ev) => { if (ev.key === "Escape" && state.sel != null) goHome(); });
})();
