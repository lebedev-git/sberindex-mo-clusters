/* Новые проверки (site/data/v2.json): правила голосования, правила типов (IMM), синтетика, опережение,
   события кластеров, пространственная автокорреляция, Росстат, мобильность. Рисуется только то, что есть. */
(async function () {
  const v = await d3.json("data/v2.json?v=20261009y").catch(() => null);
  if (!v) return;
  const types = await d3.json("data/types.json?v=20261009y").catch(() => []);
  const ru = d3.formatLocale({ decimal: ",", thousands: " ", grouping: [3] });
  const fInt = ru.format(",.0f"), f2 = ru.format(".2f"), fPct0 = ru.format(".0%"), fPct = ru.format(".1%");
  const tById = new Map(types.map((t) => [t.id, t]));
  const sw = (id) => { const t = tById.get(id); return t ? `<span class="sw" style="background:${t.color}"></span>` : ""; };
  const tn = (id) => { const t = tById.get(id); return t ? t.short || t.name : "—"; };
  const card = (host, title, sub) => {
    const c = d3.select(host).append("div").attr("class", "card");
    c.append("h3").text(title);
    if (sub) c.append("p").attr("class", "sub").html(sub);
    return c;
  };

  /* ---------- правила типов (IMM) — в карточки типов ---------- */
  if (v.imm && v.imm.types) {
    const byT = new Map(v.imm.types.map((r) => [r.type, r]));
    const put = () => d3.selectAll("#types-grid .tcard").each(function (_, i) {
      const el = d3.select(this);
      const id = +(el.attr("data-type") ?? i);
      const r = byT.get(id);
      if (!r || el.select(".rule").size()) return;
      el.insert("div", "p").attr("class", "rule")
        .html(`<em>правило типа · совпадение ${fPct0(r.fidelity)}</em>${r.rules.map((x) => "• " + x).join("<br>")}`);
    });
    put(); setTimeout(put, 1500); // карточки рисует app.js — подстраховка на порядок загрузки
  }

  // вывод о зарплатах — в итог истории
  if (v.rosstat && v.rosstat.eta2 && v.rosstat.eta2.log_wage != null) {
    const F = document.getElementById("s-findings");
    if (F) F.insertAdjacentHTML("beforeend", `<li><b>Траты следуют за доходами.</b> Типы объясняют ${fPct0(v.rosstat.eta2.log_wage)} разброса логарифма зарплаты по Росстату (${v.rosstat.year}), хотя зарплат в модели нет; связь идёт в основном через уровень трат.</li>`);
  }

  /* ---------- метод ---------- */
  const M = "#v2-method";
  if (v.aggregation && v.aggregation.length) {
    const A = v.aggregation, name = (a) => a.rule + (a.variant ? ` (${a.variant})` : "");
    const fin = A.find((a) => a.unique && a.same_as_final) || A[0];
    const detAll = A.every((a) => a.detailed.includes(fin.detailed));
    const uniq = A.filter((a) => a.unique && a.same_as_final).map(name), tie = A.filter((a) => !a.unique && a.same_as_final).map(name), other = A.filter((a) => !a.same_as_final).map(name);
    const c = card("#v2-method-main", "Устойчивость выбора к правилу голосования", "Те же 45 конфигураций и те же 7 «голосующих» (6 индексов качества и устойчивость), разные правила агрегирования.");
    c.append("p").attr("class", "verdict").text([
      detAll ? `Детальный уровень (${fin.detailed}) входит в ответ всех ${A.length} вариантов.` : "",
      uniq.length ? `Макроуровень (${fin.macro}) однозначно выбирают: ${uniq.join(", ")}.` : "",
      tie.length ? `Ничья с другой конфигурацией: ${tie.join(", ")}.` : "",
      other.length ? `Выбирают иначе: ${other.join(", ")} — макроуровень держится на компенсаторных правилах.` : "",
    ].filter(Boolean).join(" "));
    c.append("div").attr("id", "agg-table").html(`<table class="left"><thead><tr><th>Правило</th><th>Макроуровень</th><th>Детальный уровень</th><th>Место итога</th></tr></thead><tbody>${
      A.map((a) => `<tr${a.unique && a.same_as_final ? ' class="final"' : ""}><td>${name(a)}</td><td>${a.macro}</td><td>${a.detailed}</td><td>${a.final_rank != null ? a.final_rank : "—"}</td></tr>`).join("")}</tbody></table>`);
  }
  if (v.synthetic && v.synthetic.rows && v.synthetic.rows.length) {
    const c = card(M, "Проверка на синтетике с известными группами", "Атрибутированная стохастическая блочная модель: сила сигнала в признаках и в сети задаётся; ARI — совпадение найденных групп с истинными.");
    if (v.synthetic.summary) c.append("p").attr("class", "verdict").text(v.synthetic.summary);
    const rows = v.synthetic.rows, methods = [...new Set(rows.map((r) => r.method))];
    const cells = [...new Set(rows.map((r) => `${r.attr}|${r.net}`))];
    const col = d3.scaleSequential([0, 1], d3.interpolateGreys);
    c.append("div").attr("id", "synth").html(`<table><thead><tr><th>Признаки / сеть</th>${methods.map((m) => `<th>${m}</th>`).join("")}</tr></thead><tbody>${
      cells.map((k) => { const [a, n] = k.split("|"); return `<tr><td>${a} / ${n}</td>${methods.map((m) => { const r = rows.find((x) => x.method === m && `${x.attr}|${x.net}` === k); if (!r) return "<td>—</td>"; const best = d3.max(rows.filter((x) => `${x.attr}|${x.net}` === k), (x) => x.ari) - r.ari < 1e-9; return `<td style="background:${d3.color(col(r.ari * 0.55)).formatHex()};${r.ari > 0.82 ? "color:#fff;" : ""}${best ? "font-weight:700" : ""}">${f2(r.ari)}</td>`; }).join("")}</tr>`; }).join("")}</tbody></table>`);
  }
  if (v.gmm && v.gmm.summary) card(M, "Смесь гауссиан (GMM) как дополнительный метод", v.gmm.summary);

  /* ---------- динамика ---------- */
  const Dn = "#v2-dyn";
  if (v.events && v.events.counts) {
    const c = card(Dn, "События типов между соседними окнами", "Классификация эволюции кластеров MONIC: тип сохраняется, раскалывается, поглощается другим, исчезает или возникает.");
    const ru_ = { survive: "сохранился", split: "раскололся", absorb: "поглощён", disappear: "исчез", emerge: "возник" };
    c.append("div").attr("class", "ext").html(Object.entries(v.events.counts).map(([k, n]) => `<div class="tile"><div class="v">${fInt(n)}</div><div class="l">${ru_[k] || k}</div></div>`).join(""));
    if (v.events.summary) c.append("p").attr("class", "sub").text(v.events.summary);
  }
  if (v.leadlag) {
    const L = v.leadlag;
    const c = card(Dn, "Кто опережает: лаговые связи", "Для каждого ребра сети — сдвиг от −3 до +3 месяцев, при котором корреляция рядов максимальна; сравнение с перестановочным нулём.");
    if (L.summary) c.append("p").attr("class", "verdict").text(L.summary);
    const tiles = [];
    if (L.share_lagged != null) tiles.push([fPct0(L.share_lagged), "рёбер с максимумом корреляции не в нулевом лаге"]);
    if (L.null_share != null) tiles.push([fPct0(L.null_share), "то же при перемешанных месяцах"]);
    if (tiles.length) c.append("div").attr("class", "ext").html(tiles.map((t) => `<div class="tile"><div class="v">${t[0]}</div><div class="l">${t[1]}</div></div>`).join(""));
  }

  /* ---------- проверка ---------- */
  const Cl = "#v2-cal";
  if (v.rosstat) {
    const R = v.rosstat;
    const c = card("#v2-cal-main", `Росстат: зарплата и занятость${R.year ? ", " + R.year : ""}`, `Муниципальная статистика (БД ПМО, обработка «Если быть точным», CC BY 4.0) в модель не входила${R.coverage ? `; сопоставлено ${fInt(R.coverage)} МО` : ""}.`);
    if (R.summary) c.append("p").attr("class", "verdict").text(R.summary);
    const E = R.eta2 || {};
    const lab = { log_wage: "зарплата (лог)", ind: "занятость в промышленности", agr: "в сельском хозяйстве", min: "в добыче", pub: "в бюджетной сфере", trade: "в торговле" };
    c.append("div").attr("class", "ext").html(Object.entries(E).filter(([, x]) => x != null).slice(0, 6).map(([k, x]) => `<div class="tile"><div class="v">${fPct0(x)}</div><div class="l">η² — ${lab[k] || k}</div></div>`).join(""));
    if (R.types && R.types.length) {
      const emp = ["ind", "agr", "min", "pub", "trade"], empRu = ["пром.", "с/х", "добыча", "бюджет", "торговля"];
      c.append("div").attr("id", "ross-table").html(`<table><thead><tr><th>Тип</th><th>Зарплата, ₽</th>${empRu.map((e) => `<th>${e}</th>`).join("")}</tr></thead><tbody>${
        R.types.map((r) => `<tr><td class="tname">${sw(r.type)}${tn(r.type)}</td><td>${r.wage ? fInt(r.wage) : "—"}</td>${emp.map((e) => `<td>${r.emp && r.emp[e] != null ? fPct0(r.emp[e]) : "—"}</td>`).join("")}</tr>`).join("")}</tbody></table>`);
    }
    if (R.lens) c.append("p").attr("class", "sub").style("margin-top", "10px").html(`Вторая линза — типология только по рынку труда: совпадение с нашей ARI ${f2(R.lens.ari)}, NMI ${f2(R.lens.nmi)}. Траты и занятость описывают разные стороны локальной экономики.`);
  }
  if (v.spatial) {
    const S = v.spatial;
    const c = card(Cl, "Типы не сводятся к географии", "Доля пар соседей одного типа против случайной перестановки меток.");
    if (S.summary) c.append("p").attr("class", "verdict").text(S.summary);
    c.append("div").attr("class", "ext").html([[S.geo_same, S.geo_null, "соседи по границе"], [S.net_same, S.net_null, "соседи по сети синхронности"]]
      .filter((r) => r[0] != null).map((r) => `<div class="tile"><div class="v">${fPct0(r[0])}</div><div class="l">${r[2]}: одного типа (случайно — ${fPct0(r[1])})</div></div>`).join(""));
  }
  if (v.mobility && v.mobility.summary) {
    const c = card(Cl, "Покупательская мобильность (СЗФО)", `Индекс мобильности СберИндекса доступен только для Северо-Западного округа; сопоставлено ${fInt(v.mobility.n || 0)} МО.`);
    c.append("p").attr("class", "verdict").text(v.mobility.summary);
  }
})();
