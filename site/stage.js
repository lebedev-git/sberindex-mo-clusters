/* Сцена истории: одни и те же 2 016 точек-МО в семи состояниях (география → равновеликая карта → сеть →
   типы в сети → острова типов → время → итоговая карта с неопределённостью). Canvas 2D; D3 — проекция,
   силы, интерполяция. Каждое МО сохраняет идентичность при переходах — глаз прослеживает его путь. */
window.SMCStage = function (D) {
  const { geo, mo, types, macro, meta } = D;
  const stage = document.getElementById("stage");
  const canvas = document.getElementById("stage-canvas");
  if (!stage || !canvas) return;
  const ctx = canvas.getContext("2d");
  const ru = d3.formatLocale({ decimal: ",", thousands: " ", grouping: [3] });
  const fInt = ru.format(",.0f"), fPct0 = ru.format(".0%"), f2 = ru.format(".2f");
  const MON = ["янв", "фев", "мар", "апр", "май", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"];
  const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const W_END = meta.windows;
  const winLabel = (end) => { const [y, m] = end.split("-").map(Number); const s = new Date(y, m - 12, 1); return `${MON[s.getMonth()]} ${s.getFullYear()} – ${MON[m - 1]} ${y}`; };

  const ok = mo.filter((m) => m.status === "ok");
  const N = ok.length;
  const featById = new Map(geo.features.map((f) => [f.id, f]));
  const rgb = (c) => { const k = d3.rgb(c); return [k.r, k.g, k.b]; };
  const typeRGB = types.map((t) => rgb(t.color));
  // на тёмном фоне тёмные цвета (Арктика) теряются — поднимаем светлоту до 0,62
  const typeNight = types.map((t) => { const h = d3.hsl(t.color); h.l = Math.max(h.l, 0.62); return rgb(h.formatHex()); });
  const conf = (m) => (m.conf ? (m.conf[0] + m.conf[1]) / 2 : 0);
  // уверенность → доля цвета типа (палитра с подавлением значения: 4 ступени)
  const certLevel = (c) => (c >= 0.25 ? 1 : c >= 0.1 ? 0.6 : 0.27); // 3 ступени: ≥ 0,25 · 0,10–0,25 · < 0,10
  const PAPER = [241, 240, 236];
  const mix = (a, b, t) => [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t];
  const INK = [17, 17, 16], NIGHT_DOT = [214, 220, 230];

  const nodes = ok.map((m, i) => ({
    i, m, id: m.id, t: m.type, conf: conf(m),
    x: 0, y: 0, r: 0, c: INK.slice(), a: 0, ring: 0,
    from: null, to: null, delay: 0,
  }));
  const nodeById = new Map(nodes.map((n) => [n.id, n]));

  /* ---------- числа для текста шагов (считаются из данных, не вписаны руками) ---------- */
  const lonOf = (f) => { let l = d3.geoCentroid(f)[0]; if (l < 0) l += 360; return l; };
  // сферические площади и центры — после первого кадра (текст шага 01 ниже первого экрана)
  setTimeout(() => {
    let nWest = 0, aWest = 0, aAll = 0, pWest = 0, pAll = 0;
    nodes.forEach((n) => {
      const f = featById.get(n.id); if (!f) return;
      const a = d3.geoArea(f), west = lonOf(f) < 60;
      aAll += a; if (west) { aWest += a; nWest++; }
      if (n.m.pop) { pAll += n.m.pop; if (west) pWest += n.m.pop; }
    });
    set("s-geo", `Западнее Урала (60° в. д.) — <b>${fPct0(nWest / N)}</b> муниципалитетов выборки и ${pAll ? fPct0(pWest / pAll) : "—"} их населения, но только <b>${fPct0(aWest / aAll)}</b> площади. Обычная карта отдаёт взгляд огромным северным районам, а большинство территорий страны — плотная мозаика на западе.`);
  }, 1500);
  const corr = (meta.graphs || []).find((g) => g.rule === "corr") || {};
  const km = corr.median_edge_road_km ? Math.round(corr.median_edge_road_km / 10) * 10 : null;
  const syncIn = meta.justification && meta.justification.network ? meta.justification.network.sync_within_kefrin : null;
  const moved = ok.filter((m) => m.moved).length;
  const formal = ok.filter((m) => m.types[0] !== m.types[W_END.length - 1]).length;
  const asym = (meta.asymmetry || [])[0];
  const byTypeN = types.map((t) => ok.filter((m) => m.type === t.id).length);
  const tBig = types[d3.maxIndex(byTypeN)], tSmall = types[d3.minIndex(byTypeN)];
  const arctic = types.find((t) => t.official && t.official.far_north_or_equated >= 0.99);
  const set = (id, html) => { const el = document.getElementById(id); if (el) el.innerHTML = html; };
  set("s-dorling", `Уравняем веса: каждое МО становится точкой одного размера и встаёт как можно ближе к своему месту. Запад «раздувается», север сжимается — так выглядит страна, если считать территории, а не квадратные километры. Дальше важна не площадь, а то, как в них тратят деньги.`);
  set("s-net", `Свяжем каждое МО с 15 муниципалитетами, чьи месячные траты колеблются синхронно с ним (корреляция рядов, очищенных от общероссийской динамики). Раскладка t-SNE ставит рядом МО, похожие по тратам и связанные в сети; оси не имеют единиц. ${km ? `Медиана длины связи по дорогам — <b>≈${fInt(km)} км</b>: экономические соседи редко соседи по карте.` : ""}`);
  set("s-netcolor", `Цвет — тип, найденный методом KEFRiN: он ищет группы, похожие одновременно по профилю трат и по связям в сети. Типы занимают свои области сети${syncIn ? `: <b>${fPct0(syncIn)}</b> веса связей ведут внутрь своего типа` : ""}, модулярность ${f2(meta.final_icvi.MQ)} против нуля у случайного разбиения.`);
  set("s-islands", `Типы вложены в 4 макротипа на ${fPct0(meta.final_icvi.nestedness_detailed_in_macro)}. В центре каждого острова — МО, уверенно принадлежащие типу, на кромке — пограничные. Самый крупный тип — «${tBig.name}» (${fInt(d3.max(byTypeN))} МО), самый редкий — «${tSmall.name}» (${fInt(d3.min(byTypeN))}).`);
  set("s-time", `13 годовых окон со сдвигом в месяц: в каждом своя сеть и своё разбиение. Точки чужого цвета на кромке острова — МО, которые в этом окне ведут себя как другой тип. Формально тип сменили ${fInt(formal)} МО, значимо — <b>${fInt(moved)}</b>.${asym ? ` Главный поток — <b>${fInt(asym.backward)}</b> МО из «${types[asym.to].name}» в «${types[asym.from].name}»: у них исчез летний подъём трат в общепите; обратно — ${fInt(asym.forward)}.` : ""}`);
  set("s-final", `Цвет — тип, насыщенность — уверенность: бледные МО лежат на границе соседних типов, и карта не выдаёт размытую границу за чёткую. Типы согласуются с данными, которых модель не видела${arctic ? `: все МО типа «${arctic.name}» — в перечне районов Крайнего Севера и приравненных местностей` : ""}, типы объясняют ${fPct0(meta.external["eta2:log_pop"])} разброса логарифма численности населения.`);

  // выводы: числа из данных
  const medSpend = d3.median(ok, (m) => m.spend), medMp = d3.median(ok, (m) => m.shares[4]), medFood = d3.median(ok, (m) => m.shares[2]);
  const capT = types.find((t) => t.short === "Столичные") || types[d3.maxIndex(types, (t) => t.spend)];
  const pctD = (x) => (x >= 0 ? "+" : "−") + fPct0(Math.abs(x));
  const F = document.getElementById("s-findings");
  if (F) F.insertAdjacentHTML("afterbegin", [
    arctic ? `<li><b>Север живёт отдельно.</b> «${arctic.name}»: траты на жителя ${pctD(arctic.spend / medSpend - 1)} к медиане МО, но доля маркетплейсов ${fPct0(arctic.shares[4])} против ${fPct0(medMp)} — дорогая жизнь при сложной доставке.</li>` : "",
    capT ? `<li><b>Столицы в отрыве.</b> «${capT.short || capT.name}»: траты ${pctD(capT.spend / medSpend - 1)} к медиане, доля общепита в ${ru.format(".1f")(capT.shares[2] / medFood)} раза выше.</li>` : "",
    asym ? `<li><b>У части сёл пропадает лето.</b> ${fInt(asym.backward)} МО типа «${types[asym.to].short || types[asym.to].name}» за год перешли в тип «${types[asym.from].short || types[asym.from].name}»: летний подъём трат в общепите исчез; обратно — ${fInt(asym.forward)}.</li>` : "",
  ].join(""));

  /* ---------- геометрия сцены ---------- */
  let W = 0, H = 0, dpr = 1, proj, path;
  const P = {};          // позиции состояний: P.geo, P.dorling, P.net, P.islands, P.time[w]
  let layerGray = null, layerType = null, islandCenters = [];
  let edges = [];        // пары индексов узлов
  let netXY = null;      // нормированные координаты сети из net.json

  function frame() {
    const top = 58, bottom = W < 700 ? 64 : 104, side = 24, right = W < 700 ? 24 : 72; // справа — навигатор шагов
    return { x0: side, y0: top, x1: W - right, y1: H - bottom };
  }

  // «нет полных данных» — штриховка, чтобы не путать с бледным цветом низкой уверенности
  const HATCH = (() => { const c = document.createElement("canvas"); c.width = c.height = 6; const x = c.getContext("2d");
    x.fillStyle = "#f6f5f2"; x.fillRect(0, 0, 6, 6); x.strokeStyle = "#cfcec7"; x.lineWidth = 0.8; x.beginPath(); x.moveTo(0, 6); x.lineTo(6, 0); x.stroke();
    return ctx.createPattern(c, "repeat"); })();
  function buildLayer(fillOf) {
    const c = document.createElement("canvas");
    c.width = Math.round(W * dpr); c.height = Math.round(H * dpr);
    const x = c.getContext("2d"); x.scale(dpr, dpr);
    const p = d3.geoPath(proj, x);
    x.lineJoin = "round";
    geo.features.forEach((f) => {
      x.beginPath(); p(f);
      x.fillStyle = fillOf(f); x.fill();
      x.strokeStyle = "rgba(255,255,255,0.9)"; x.lineWidth = 0.35; x.stroke();
    });
    return c;
  }

  function computeGeo() {
    const F = frame();
    const L = D.layouts;
    if (L && L.centroid && L.bounds) {
      // проекция и центры — из готовой раскладки: линейный перенос вместо fitExtent и path.centroid
      const [[x0, y0], [x1, y1]] = L.bounds, k = Math.min((F.x1 - F.x0) / (x1 - x0), (F.y1 - F.y0) / (y1 - y0));
      const cc = [(x0 + x1) / 2, (y0 + y1) / 2], cF = [(F.x0 + F.x1) / 2, (F.y0 + F.y1) / 2];
      proj = d3.geoConicEqualArea().parallels([52, 64]).rotate([-100, 0]).scale(L.scale * k)
        .translate([(L.translate[0] - cc[0]) * k + cF[0], (L.translate[1] - cc[1]) * k + cF[1]]);
      path = d3.geoPath(proj);
      const at = new Map(L.ids.map((id, j) => [id, L.centroid[j]]));
      P.geo = nodes.map((n) => { const p = at.get(n.id); return p ? [(p[0] - cc[0]) * k + cF[0], (p[1] - cc[1]) * k + cF[1]] : [W / 2, H / 2]; });
    } else {
    proj = d3.geoConicEqualArea().parallels([52, 64]).rotate([-100, 0]).fitExtent([[F.x0, F.y0], [F.x1, F.y1]], geo);
    path = d3.geoPath(proj);
    P.geo = nodes.map((n) => {
      const f = featById.get(n.id);
      let c = f ? path.centroid(f) : [NaN, NaN];
      if (!isFinite(c[0])) { const g = f ? proj(d3.geoCentroid(f)) : null; c = g || [W / 2, H / 2]; }
      return c;
    });
    }
    const okIds = new Set(ok.map((m) => m.id));
    layerGray = buildLayer((f) => (okIds.has(f.id) ? "#e2e1db" : HATCH));
    layerType = null;
  }
  function computeTypeLayer() {
    layerType = buildLayer((f) => {
      const n = nodeById.get(f.id);
      if (!n) return HATCH;
      const c = mix(PAPER, typeRGB[n.t], certLevel(n.conf));
      return `rgb(${c[0] | 0},${c[1] | 0},${c[2] | 0})`;
    });
  }
  // всё, что не нужно первому экрану, считается после первого кадра (или сразу, если читатель уже прокрутил)
  let restReady = false;
  function ensureRest() {
    if (restReady || !P.geo) return;
    computeTypeLayer(); computeDorling(); computeNet(); computeIslands();
    restReady = true;
  }

  function computeDorling() {
    const F = frame();
    let r, sim;
    const L = D.layouts;
    if (L && L.dorling) {
      // раскладка посчитана заранее (scripts/build_site_layouts.js) в единицах той же проекции: переносим линейно
      const k = proj.scale() / L.scale, t = proj.translate(), tc = L.translate, at = new Map(L.ids.map((id, j) => [id, L.dorling.xy[j]]));
      sim = nodes.map((n, i) => { const p = at.get(n.id); return p ? { x: (p[0] - tc[0]) * k + t[0], y: (p[1] - tc[1]) * k + t[1] } : { x: P.geo[i][0], y: P.geo[i][1] }; });
      r = L.dorling.r * k;
    } else {
      const area = (F.x1 - F.x0) * (F.y1 - F.y0);
      r = Math.max(2.2, Math.min(5.2, Math.sqrt((area * 0.16) / (N * Math.PI))));
      sim = nodes.map((n, i) => ({ x: P.geo[i][0], y: P.geo[i][1], gx: P.geo[i][0], gy: P.geo[i][1] }));
      const s = d3.forceSimulation(sim).randomSource(d3.randomLcg(7))
        .force("x", d3.forceX((d) => d.gx).strength(0.09)).force("y", d3.forceY((d) => d.gy).strength(0.09))
        .force("c", d3.forceCollide(r + 0.55).iterations(2)).stop();
      for (let k = 0; k < 240; k++) s.tick();
    }
    // вписываем результат в кадр
    const xs = d3.extent(sim, (d) => d.x), ys = d3.extent(sim, (d) => d.y);
    const sc = Math.min((F.x1 - F.x0) / (xs[1] - xs[0]), (F.y1 - F.y0) / (ys[1] - ys[0]), 1);
    const ox = (F.x0 + F.x1) / 2 - ((xs[0] + xs[1]) / 2) * sc, oy = (F.y0 + F.y1) / 2 - ((ys[0] + ys[1]) / 2) * sc;
    P.dorling = sim.map((d) => [d.x * sc + ox, d.y * sc + oy]);
    P.rDorling = r * Math.sqrt(sc);
  }

  function computeNet() {
    const F = frame();
    if (netXY) {
      const xs = d3.extent(netXY, (d) => d[0]), ys = d3.extent(netXY, (d) => d[1]);
      const sc = Math.min((F.x1 - F.x0) / (xs[1] - xs[0] || 1), (F.y1 - F.y0) / (ys[1] - ys[0] || 1)) * 0.94;
      const cx = (F.x0 + F.x1) / 2, cy = (F.y0 + F.y1) / 2, mx = (xs[0] + xs[1]) / 2, my = (ys[0] + ys[1]) / 2;
      P.net = nodes.map((n) => { const v = netXY.get(n.id); return v ? [cx + (v[0] - mx) * sc, cy + (v[1] - my) * sc] : [cx, cy]; });
      return;
    }
    // запасной вариант: силовая раскладка по 10 ближайшим соседям из mo.json
    const sim = nodes.map((n, i) => ({ i, x: P.dorling[i][0], y: P.dorling[i][1] }));
    const links = [];
    nodes.forEach((n, i) => (n.m.nb || []).forEach((id) => { const j = nodeById.get(id); if (j && j.i > i) links.push({ source: i, target: j.i }); }));
    edges = links.map((l) => [l.source, l.target]);
    const s = d3.forceSimulation(sim).randomSource(d3.randomLcg(11))
      .force("l", d3.forceLink(links).distance(12).strength(0.35))
      .force("q", d3.forceManyBody().strength(-7).theta(1.1).distanceMax(160))
      .force("x", d3.forceX((F.x0 + F.x1) / 2).strength(0.02)).force("y", d3.forceY((F.y0 + F.y1) / 2).strength(0.03)).stop();
    for (let k = 0; k < 220; k++) s.tick();
    const xs = d3.extent(sim, (d) => d.x), ys = d3.extent(sim, (d) => d.y);
    const sc = Math.min((F.x1 - F.x0) / (xs[1] - xs[0]), (F.y1 - F.y0) / (ys[1] - ys[0])) * 0.94;
    const cx = (F.x0 + F.x1) / 2, cy = (F.y0 + F.y1) / 2, mx = (xs[0] + xs[1]) / 2, my = (ys[0] + ys[1]) / 2;
    P.net = sim.map((d) => [cx + (d.x - mx) * sc, cy + (d.y - my) * sc]);
  }

  // острова типов: круги ∝ √n уложены плотно (packSiblings), внутри — филлотаксис по уверенности
  const GOLD = Math.PI * (3 - Math.sqrt(5));
  function computeIslands() {
    const F = frame();
    // две строки, внутри — группы по макротипам: [столичные] [города, удалённая Сибирь] / [Арктика] [глубинка, аграрная]
    const rows = [[[3], [0, 4]], [[2], [1, 5]]];
    const GIN = 7, GOUT = 18, LAB = 74;
    const rad = (t) => Math.sqrt(byTypeN[t]);
    const rowW = rows.map((r) => d3.sum(r, (g) => d3.sum(g, (t) => 2 * rad(t)) + GIN * (g.length - 1)) + GOUT * (r.length - 1));
    const rowH = rows.map((r) => 2 * d3.max(r.flat(), rad));
    const sc = Math.min((F.x1 - F.x0) / d3.max(rowW), (F.y1 - F.y0 - LAB * rows.length - 20) / d3.sum(rowH));
    islandCenters = []; P.groups = [];
    let y = F.y0 + 22 + (F.y1 - F.y0 - 20 - LAB * rows.length - d3.sum(rowH) * sc) / 2;
    rows.forEach((r, ri) => {
      let x = (F.x0 + F.x1) / 2 - (rowW[ri] * sc) / 2;
      const cy = y + (rowH[ri] * sc) / 2;
      r.forEach((g, gi) => {
        const gx0 = x;
        g.forEach((t, k) => { const R = rad(t) * sc; islandCenters[t] = { x: x + R, y: cy, R }; x += 2 * R + (k < g.length - 1 ? GIN * sc : 0); });
        P.groups.push({ x: (gx0 + x) / 2, y: cy - (d3.max(g, rad) * sc) - 12, name: macro[types[g[0]].macro].name });
        x += gi < r.length - 1 ? GOUT * sc : 0;
      });
      y += rowH[ri] * sc + LAB;
    });
    P.cIsl = sc * 0.93;  // шаг филлотаксиса: радиус острова ≈ sc·√n
    P.rIsl = Math.max(1.6, Math.min(5.2, sc * 0.56));
    P.islands = new Array(N);
    types.forEach((t) => {
      const mem = nodes.filter((n) => n.t === t.id).sort((a, b) => b.conf - a.conf || a.id - b.id);
      place(mem, islandCenters[t.id], P.islands);
    });
    P.timeR = [];
    P.time = W_END.map((_, w) => {
      const out = new Array(N), R = [];
      types.forEach((t) => {
        const mem = nodes.filter((n) => n.m.types[w] === t.id);
        const guest = (n) => (n.t === t.id ? 0 : 1); // свои — в центре, «гости» — на кромке
        mem.sort((a, b) => guest(a) - guest(b) || b.conf - a.conf || a.id - b.id);
        // остров может вырасти не больше чем в 1,3 раза по радиусу — дальше точки уплотняются
        const c = P.cIsl * Math.min(1, 1.3 * Math.sqrt(byTypeN[t.id] / Math.max(1, mem.length)));
        place(mem, islandCenters[t.id], out, c);
        R[t.id] = c * Math.sqrt(mem.length);
      });
      P.timeR.push(R);
      return out;
    });
  }
  function place(mem, c, out, step = P.cIsl) {
    mem.forEach((n, k) => {
      const rr = step * Math.sqrt(k + 0.5), th = k * GOLD;
      out[n.i] = [c.x + rr * Math.cos(th), c.y + rr * Math.sin(th)];
    });
  }

  /* ---------- состояния ---------- */
  const STATES = {
    hero:     { label: "00 · <b>Столичные и Арктика</b> — цветом", count: () => `${fInt(N)} МО`, night: false, layer: "gray", legend: true, only: [3, 2] },
    geo:      { label: "01 · <b>География</b> · центры МО на контурах", count: () => `${fInt(N)} МО`, night: false, layer: "gray" },
    dorling:  { label: "02 · <b>Равновеликая карта</b> · каждое МО — одна точка", count: () => `${fInt(N)} точек одного размера`, night: false, layer: null },
    net:      { label: "03 · <b>Сеть синхронности трат</b>", count: () => `${fInt(N)} узлов · ${fInt(edges.length)} рёбер`, night: false, layer: null, edges: 1 },
    netcolor: { label: "04 · <b>Сеть</b> · цвет — тип (KEFRiN), линии — связи внутри типа", count: () => `6 типов · модулярность ${f2(meta.final_icvi.MQ)}`, night: false, layer: null, edges: 0.7, legend: true },
    islands:  { label: "05 · <b>Типы</b> · центр — уверенные МО, кромка — пограничные", count: () => `6 типов · 4 макротипа`, night: false, layer: null, labels: true },
    time:     { label: "06 · <b>Время</b>", count: () => `значимо сменили тип: ${fInt(moved)}`, night: false, layer: null, labels: true, time: true },
    final:    { label: "07 · <b>Тип и уверенность</b>", count: () => `насыщенность — уверенность`, night: false, layer: "type", legend: true, vsup: true },
  };
  let cur = null, win = 0, layerA = { gray: 1, type: 0 }, layerFrom = null, layerTo = null, edgeA = 0, edgeFrom = 0, edgeTo = 0;

  function target(state, w) {
    const pos = state === "geo" || state === "final" || state === "hero" ? P.geo : state === "dorling" ? P.dorling
      : state === "net" || state === "netcolor" ? P.net : state === "islands" ? P.islands : P.time[w];
    const night = STATES[state].night;
    const small = W < 700;
    const r = state === "geo" || state === "hero" ? (small ? 1.3 : 1.7) : state === "final" ? 1.4 : state === "dorling" ? P.rDorling : state === "islands" || state === "time" ? P.rIsl : small ? 1.25 : 2.1;
    return nodes.map((n, i) => {
      let c = INK, a = 0.9, ring = 0, rr = r;
      if (state === "hero") { const hl = STATES.hero.only.includes(n.t); c = hl ? typeRGB[n.t] : [150, 149, 144]; a = hl ? 0.95 : 0.5; rr = hl ? (small ? 1.8 : 2.3) : (small ? 1.1 : 1.5); }
      else if (state === "net") { c = INK; a = 0.72; }
      else if (state === "netcolor") { c = typeRGB[n.t]; a = 0.92; }
      else if (state === "islands") { c = typeRGB[n.t]; a = 0.35 + 0.65 * certLevel(n.conf); }
      else if (state === "time") { c = typeRGB[n.t]; a = n.m.types[w] === n.t ? 0.92 : 1; ring = n.m.moved ? 1 : 0; }
      else if (state === "final") { c = typeRGB[n.t]; a = 0; }
      else if (state === "dorling") { c = INK; a = 0.82; }
      return { x: pos[i][0], y: pos[i][1], r: rr, c, a, ring };
    });
  }

  let anim = null;
  function go(state, w = 0, dur = 1500) {
    if (!P.geo) return;
    if (state !== "hero" && state !== "geo") ensureRest();
    const st = STATES[state];
    const tgt = target(state, w);
    const now = performance.now();
    // волна: задержка по положению цели слева направо (или по типу для островов)
    const key = state === "islands" || state === "time" ? (i) => tgt[i].x : (i) => tgt[i].x + tgt[i].y * 0.3;
    const ext = d3.extent(nodes, (n, i) => key(i));
    const span = state === "time" ? 220 : 520;
    nodes.forEach((n, i) => {
      n.from = { x: n.x, y: n.y, r: n.r, c: n.c.slice(), a: n.a, ring: n.ring };
      n.to = tgt[i];
      n.delay = reduce ? 0 : ((key(i) - ext[0]) / (ext[1] - ext[0] || 1)) * span;
    });
    layerFrom = { ...layerA };
    layerTo = { gray: st.layer === "gray" ? 1 : 0, type: st.layer === "type" ? 1 : 0 };
    edgeFrom = edgeA; edgeTo = st.edges || 0;
    anim = { start: now, dur: reduce ? 1 : dur, span: reduce ? 0 : span };
    stage.classList.toggle("night", !!st.night);
    document.getElementById("story").classList.toggle("night", !!st.night);
    document.body.classList.toggle("is-night", !!st.night);
    document.getElementById("stage-state").innerHTML = state === "time" ? `06 · <b>Окно</b> · ${winLabel(W_END[w])}` : st.label;
    document.getElementById("stage-count").textContent = st.count();
    legend(st);
    labels(state);
    document.getElementById("stage-time").classList.toggle("show", !!st.time);
    requestAnimationFrame(tick);
  }

  const ease = d3.easeCubicInOut;
  function tick(now) {
    if (!anim) return;
    const total = anim.dur + anim.span;
    const g = Math.min(1, (now - anim.start) / total);
    nodes.forEach((n) => {
      const k = ease(Math.max(0, Math.min(1, (now - anim.start - n.delay) / anim.dur)));
      const f = n.from, t = n.to;
      n.x = f.x + (t.x - f.x) * k; n.y = f.y + (t.y - f.y) * k; n.r = f.r + (t.r - f.r) * k;
      n.c = mix(f.c, t.c, k); n.a = f.a + (t.a - f.a) * k; n.ring = f.ring + (t.ring - f.ring) * k;
    });
    const kg = ease(g);
    layerA = { gray: layerFrom.gray + (layerTo.gray - layerFrom.gray) * kg, type: layerFrom.type + (layerTo.type - layerFrom.type) * kg };
    edgeA = edgeFrom + (edgeTo - edgeFrom) * kg;
    draw();
    if (g < 1) requestAnimationFrame(tick); else { anim = null; buildIndex(); if (cur) labels(cur); }
  }

  function draw() {
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, W, H);
    if (layerA.gray > 0.01) { ctx.globalAlpha = layerA.gray; ctx.drawImage(layerGray, 0, 0, W, H); }
    if (layerA.type > 0.01 && layerType) { ctx.globalAlpha = layerA.type; ctx.drawImage(layerType, 0, 0, W, H); }
    ctx.globalAlpha = 1;
    if (edgeA > 0.01 && edges.length) {
      ctx.beginPath();
      const same = cur === "netcolor";
      for (const [a, b] of edges) { const p = nodes[a], q = nodes[b]; if (same && p.t !== q.t) continue; ctx.moveTo(p.x, p.y); ctx.lineTo(q.x, q.y); }
      ctx.strokeStyle = `rgba(17,17,16,${0.045 * edgeA})`; ctx.lineWidth = 0.5; ctx.stroke();
    }
    for (const n of nodes) {
      if (n.a < 0.02) continue;
      ctx.globalAlpha = n.a;
      ctx.fillStyle = `rgb(${n.c[0] | 0},${n.c[1] | 0},${n.c[2] | 0})`;
      ctx.beginPath(); ctx.arc(n.x, n.y, n.r, 0, 6.2832); ctx.fill();
    }
    ctx.globalAlpha = 1;
    // кольца значимых переходов
    ctx.lineWidth = 1.1; ctx.strokeStyle = "#111110";
    ctx.beginPath();
    for (const n of nodes) if (n.ring > 0.5 && n.a > 0.2) { ctx.moveTo(n.x + n.r + 1.6, n.y); ctx.arc(n.x, n.y, n.r + 1.6, 0, 6.2832); }
    ctx.stroke();
    if (hover) {
      ctx.lineWidth = 2; ctx.strokeStyle = stage.classList.contains("night") ? "#fff" : "#111";
      ctx.beginPath(); ctx.arc(hover.x, hover.y, hover.r + 3, 0, 6.2832); ctx.stroke();
    }
  }

  function legend(st) {
    const el = document.getElementById("stage-legend");
    if (!st.legend) { el.classList.remove("show"); return; }
    let html = types.filter((t) => !st.only || st.only.includes(t.id)).map((t) => `<span><i style="background:${t.color}"></i>${st.only ? t.name : t.short || t.name}</span>`).join("") + (st.only ? `<span><i style="background:#969590"></i>остальные типы</span>` : "");
    if (st.vsup) html = types.map((t, k) => `<span>${[1, 0.6, 0.27].map((v) => { const c = mix(PAPER, typeRGB[k], v); return `<i style="border-radius:1px;width:10px;background:rgb(${c.map((x) => x | 0)})"></i>`; }).join("")}&nbsp;${t.short || t.name}</span>`).join("") + `<span>уверенность в типе: высокая · средняя · низкая</span>`;
    el.innerHTML = html; el.classList.add("show");
    // легенда — сразу под содержимым сцены, а не у нижнего края
    const yMax = st === STATES.final || st === STATES.hero ? path.bounds(geo)[1][1] : d3.max(P.net || [], (p) => p[1]) || H - 80;
    el.style.top = Math.min(H - el.offsetHeight - 12, yMax + 20) + "px"; el.style.bottom = "auto";
  }

  function labels(state) {
    const el = document.getElementById("stage-labels");
    el.classList.toggle("show", (state === "islands" || state === "time") && !anim);
    el.classList.toggle("geo", state === "geo");
    if (!islandCenters.length) return;
    const spend = (t) => t.spend ? `${fInt(t.spend)} ₽/мес · ` : "";
    el.innerHTML = types.map((t) => {
      const c = islandCenters[t.id]; if (!c) return "";
      const n = state === "time" ? ok.filter((m) => m.types[win] === t.id).length : byTypeN[t.id];
      const R = state === "time" && P.timeR ? Math.max(c.R, P.timeR[win][t.id] || 0) : c.R;
      return `<div class="il" style="left:${c.x}px;top:${c.y + R + 6}px"><b>${t.short || t.name}</b><span>${spend(t)}${fInt(n)} МО</span></div>`;
    }).join("") + (P.groups || []).map((g) => `<div class="ml" style="left:${g.x}px;top:${g.y}px">${g.name}</div>`).join("")
      + (proj && W >= 700 ? [[37.6, 55.75, "Москва"], [30.3, 59.94, "Петербург"], [82.9, 55.0, "Новосибирск"], [129.7, 62.0, "Якутск"], [131.9, 43.1, "Владивосток"], [33.1, 68.97, "Мурманск"]]
        .map(([lo, la, s]) => { const p = proj([lo, la]); return p ? `<div class="city" style="left:${p[0]}px;top:${p[1]}px">${s}</div>` : ""; }).join("") : "");
    el.classList.toggle("cities", state === "hero" || state === "final" || state === "geo");
  }

  /* ---------- наведение и выбор ---------- */
  let qt = null, hover = null;
  const tipEl = document.getElementById("stage-tip");
  function buildIndex() { qt = d3.quadtree(nodes.filter((n) => n.a > 0.05), (n) => n.x, (n) => n.y); }
  canvas.addEventListener("mousemove", (ev) => {
    if (!qt || anim) return;
    const b = canvas.getBoundingClientRect(), x = ev.clientX - b.left, y = ev.clientY - b.top;
    const n = qt.find(x, y, 14);
    if (n !== hover) { hover = n; draw(); }
    if (!n) { tipEl.hidden = true; canvas.style.cursor = ""; return; }
    canvas.style.cursor = "pointer";
    const tw = cur === "time" ? n.m.types[win] : n.t;
    const extra = cur === "time" && tw !== n.t ? `<br>в этом окне ведёт себя как «${types[tw].name}»` : "";
    tipEl.innerHTML = `<div class="m">${n.m.region}</div><b>${n.m.name}</b><br>${types[n.t].name}${extra}<br><span class="m">уверенность ${f2(n.conf)} · щелчок — карточка</span>`;
    tipEl.hidden = false;
    const tx = Math.min(x + 14, W - 290), ty = Math.min(y + 14, H - 90);
    tipEl.style.left = tx + "px"; tipEl.style.top = ty + "px";
  });
  canvas.addEventListener("mouseleave", () => { hover = null; tipEl.hidden = true; draw(); });
  window.addEventListener("scroll", () => { if (!tipEl.hidden) { tipEl.hidden = true; hover = null; draw(); } }, { passive: true });
  canvas.addEventListener("click", () => { if (hover) window.dispatchEvent(new CustomEvent("smc:select", { detail: hover.id })); });

  /* ---------- время ---------- */
  const range = document.getElementById("stage-range"), playBtn = document.getElementById("stage-play"), tLab = document.getElementById("stage-t");
  range.max = String(W_END.length - 1);
  let timer = null;
  const setWin = (w, dur) => { win = w; range.value = String(w); tLab.textContent = winLabel(W_END[w]); if (cur === "time") go("time", w, dur); };
  const stop = () => { clearInterval(timer); timer = null; playBtn.textContent = "▶"; playBtn.setAttribute("aria-label", "Проиграть окна"); };
  const play = () => {
    stop(); playBtn.textContent = "❚❚"; playBtn.setAttribute("aria-label", "Пауза");
    timer = setInterval(() => { const w = (win + 1) % W_END.length; setWin(w, 900); if (w === W_END.length - 1) stop(); }, 1300);
  };
  playBtn.addEventListener("click", () => (timer ? stop() : (win === W_END.length - 1 && setWin(0, 600), play())));
  range.addEventListener("input", () => { stop(); setWin(+range.value, 700); });
  tLab.textContent = winLabel(W_END[0]);

  /* ---------- первый экран: столичные и Арктика, затем по очереди остальные типы ---------- */
  const HERO_SEQ = [[3, 2], [3], [2], [0], [4], [1], [5]];
  let heroT = null, heroI = 0;
  function heroCycle(on) {
    clearInterval(heroT); heroT = null;
    if (!on || reduce) return;
    heroT = setInterval(() => {
      if (cur !== "hero" || anim) return;
      heroI = (heroI + 1) % HERO_SEQ.length;
      STATES.hero.only = HERO_SEQ[heroI];
      const ts = STATES.hero.only.map((t) => types[t]);
      STATES.hero.label = ts.length > 1 ? "00 · <b>Столичные и Арктика</b> — цветом" : `00 · <b>${ts[0].name}</b> · ${fInt(byTypeN[ts[0].id])} МО`;
      go("hero", 0, 900);
    }, 3200);
  }

  /* ---------- прокрутка ---------- */
  const steps = [...document.querySelectorAll("#steps .step")];
  function activate(step) {
    steps.forEach((s) => s.classList.toggle("on", s === step || s.classList.contains("hero") && step === steps[0]));
    nav.querySelectorAll("button").forEach((x, i) => x.classList.toggle("on", steps[i] === step));
    const st = step.dataset.state;
    if (st === cur) return;
    cur = st;
    heroCycle(st === "hero");
    if (st === "time") { setWin(0, 0); go("time", 0); if (!reduce) setTimeout(() => { if (cur === "time" && !timer) play(); }, 1700); }
    else { stop(); go(st); }
  }
  const nav = document.getElementById("stage-nav");
  nav.innerHTML = steps.map((st, i) => `<button type="button" data-i="${i}" aria-label="Шаг ${i}">${String(i).padStart(2, "0")}</button>`).join("");
  nav.addEventListener("click", (e) => {
    const b = e.target.closest("button"); if (!b) return;
    const el = steps[+b.dataset.i];
    window.scrollTo({ top: el.offsetTop + el.offsetHeight / 2 - innerHeight / 2, behavior: reduce ? "auto" : "smooth" });
  });
  const io = new IntersectionObserver((es) => {
    es.forEach((e) => { if (e.isIntersecting) activate(e.target); });
  }, { rootMargin: window.matchMedia("(max-width: 820px)").matches ? "-66% 0px -26% 0px" : "-48% 0px -48% 0px" });
  steps.forEach((s) => io.observe(s));

  /* ---------- размеры ---------- */
  function layout() {
    const b = stage.getBoundingClientRect();
    if (b.width < 10 || b.height < 10) return false;
    W = b.width; H = b.height; dpr = Math.min(window.devicePixelRatio || 1, 2);
    canvas.width = Math.round(W * dpr); canvas.height = Math.round(H * dpr);
    computeGeo(); restReady = false;
    if (cur && cur !== "hero" && cur !== "geo") ensureRest(); else setTimeout(ensureRest, 400);
    return true;
  }
  function snap(state) { // мгновенно поставить состояние (после изменения размеров)
    if (state !== "hero" && state !== "geo") ensureRest();
    const t = target(state, win);
    nodes.forEach((n, i) => Object.assign(n, { x: t[i].x, y: t[i].y, r: t[i].r, c: t[i].c.slice(), a: t[i].a, ring: t[i].ring }));
    const st = STATES[state];
    layerA = { gray: st.layer === "gray" ? 1 : 0, type: st.layer === "type" ? 1 : 0 }; edgeA = st.edges || 0;
    labels(state); legend(st); draw(); buildIndex();
  }
  let rT = null;
  window.addEventListener("resize", () => { clearTimeout(rT); rT = setTimeout(() => { const w0 = W; if (layout() && Math.abs(W - w0) > 2) snap(cur || "geo"); else if (W) snap(cur || "geo"); }, 180); });

  /* ---------- запуск: сеть из net.json, если она есть ---------- */
  function start() {
    if (!layout()) return;
    // заставка: точки опускаются на карту волной с запада на восток; постер первого экрана гаснет
    nodes.forEach((n, i) => { n.x = P.geo[i][0]; n.y = P.geo[i][1] - 16; n.r = 1.7; n.c = INK.slice(); n.a = 0; });
    layerA = { gray: 0.6, type: 0 };
    cur = "hero";
    go("hero", 0, reduce ? 1 : 900);
    heroCycle(true);
    const poster = document.getElementById("stage-poster");
    if (poster) { poster.classList.add("gone"); setTimeout(() => poster.remove(), 900); }
    // сеть (t-SNE) догружается в фоне: к шагу 03 она уже на месте
    d3.json(`data/net.json?v=${D.version || ""}`).then((nj) => {
      if (!nj || !nj.ids || !nj.xy) return;
      const m = new Map(nj.ids.map((id, k) => [id, nj.xy[k]]));
      netXY = Object.assign([...m.values()], { get: (id) => m.get(id) });
      const idx = new Map(nodes.map((n) => [n.id, n.i]));
      if (nj.edges) edges = nj.edges.map(([a, b]) => [idx.get(nj.ids[a]), idx.get(nj.ids[b])]).filter(([a, b]) => a != null && b != null);
      if (restReady) { computeNet(); if (cur === "net" || cur === "netcolor") snap(cur); }
    }).catch(() => {});
  }
  start();
};
