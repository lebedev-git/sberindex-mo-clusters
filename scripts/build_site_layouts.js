// Раскладки точек для лендинга считаются заранее, чтобы браузер не тратил на них секунды:
// равновеликая карта (сцена истории и карта «Равные точки») и карта «По населению».
// Те же функции D3, что на странице (site/vendor/d3.min.js), та же проекция и тот же seed.
//   node scripts/build_site_layouts.js        ->  site/data/layouts.json
const fs = require("fs");
const path = require("path");
const d3 = require(path.join(__dirname, "..", "site", "vendor", "d3.min.js"));

const DATA = path.join(__dirname, "..", "site", "data");
const geo = JSON.parse(fs.readFileSync(path.join(DATA, "mo.geojson"), "utf8"));
const mo = JSON.parse(fs.readFileSync(path.join(DATA, "mo.json"), "utf8"));

// как в app.js: кольца с обратным обходом и вырожденные части у 180°
geo.features.forEach((f) => {
  const g = f.geometry;
  const polys = (g.type === "Polygon" ? [g.coordinates] : g.coordinates).filter((poly) => {
    if (d3.geoArea({ type: "Polygon", coordinates: poly }) > 2 * Math.PI) poly.forEach((ring) => ring.reverse());
    return d3.geoArea({ type: "Polygon", coordinates: poly }) <= 2 * Math.PI;
  });
  f.geometry = { type: "MultiPolygon", coordinates: polys };
});

// каноническая проекция = проекция карты-исследователя (viewBox 1000 × 540)
const MW = 1000, MH = 540;
const proj = d3.geoConicEqualArea().parallels([52, 64]).rotate([-100, 0]).fitExtent([[6, 6], [MW - 6, MH - 6]], geo);
const gpath = d3.geoPath(proj);
const featById = new Map(geo.features.map((f) => [f.id, f]));
const ok = mo.filter((m) => m.status === "ok" && featById.get(m.id));
const base = ok.map((m) => { const c = gpath.centroid(featById.get(m.id)); return { m, x: c[0], y: c[1], gx: c[0], gy: c[1] }; }).filter((d) => isFinite(d.x));

function settle(nodes, rOf, ticks) {
  const sim = d3.forceSimulation(nodes).randomSource(d3.randomLcg(7))
    .force("x", d3.forceX((d) => d.gx).strength(0.09)).force("y", d3.forceY((d) => d.gy).strength(0.09))
    .force("c", d3.forceCollide(rOf).iterations(2)).stop();
  for (let k = 0; k < ticks; k++) sim.tick();
  return nodes;
}
const r2 = (x) => Math.round(x * 100) / 100;
const copy = () => base.map((d) => ({ ...d }));

// 1) равные точки для карты (r = 3,1 в единицах viewBox)
const dots = settle(copy(), () => 3.1 + 0.45, 220);
// 2) по населению: площадь круга ∝ численности, все круги ≈ 13% карты
const popNodes = copy();
const popSum = d3.sum(popNodes, (d) => d.m.pop || 0), s = Math.sqrt((0.13 * MW * MH) / (Math.PI * popSum));
popNodes.forEach((d) => { d.r = Math.max(0.8, s * Math.sqrt(d.m.pop || 0)); });
popNodes.sort((a, b) => b.r - a.r);
settle(popNodes, (d) => d.r + 0.45, 240);
// 3) равновеликая карта для сцены истории: радиус под долю 16% площади кадра
const rStage = Math.sqrt(((MW - 12) * (MH - 12) * 0.16) / (base.length * Math.PI));
const dor = settle(copy(), () => rStage + 0.55, 240);

const out = {
  note: "Предрассчитанные раскладки точек (scripts/build_site_layouts.js); координаты — в единицах карты 1000 × 540 той же проекции, что на странице.",
  frame: [MW, MH], scale: proj.scale(), translate: proj.translate(), bounds: gpath.bounds(geo).map((p) => p.map(r2)),
  ids: base.map((d) => d.m.id),
  centroid: base.map((d) => [r2(d.gx), r2(d.gy)]),
  dots: { r: 3.1, xy: base.map((d, i) => [r2(dots[i].x), r2(dots[i].y)]) },
  pop: { id: popNodes.map((d) => d.m.id), r: popNodes.map((d) => r2(d.r)), xy: popNodes.map((d) => [r2(d.x), r2(d.y)]) },
  dorling: { r: r2(rStage), xy: base.map((d, i) => [r2(dor[i].x), r2(dor[i].y)]) },
};
fs.writeFileSync(path.join(DATA, "layouts.json"), JSON.stringify(out));
console.log("layouts.json:", base.length, "МО");
