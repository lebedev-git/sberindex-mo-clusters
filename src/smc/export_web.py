"""Выгрузка результатов в JSON/GeoJSON для статического лендинга (site/)."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import yaml
from shapely.geometry import MultiPolygon, Polygon, mapping
from shapely.geometry.polygon import orient

from .data import load_reference
from .interpret import MIRKIN_FEATURES


def _round(obj, nd=3):
    if isinstance(obj, float):
        return None if not np.isfinite(obj) else round(obj, nd)
    if isinstance(obj, dict):
        return {k: _round(v, nd) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_round(v, nd) for v in obj]
    if isinstance(obj, (np.floating,)):
        return _round(float(obj), nd)
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, np.bool_):
        return bool(obj)
    return obj


def _clockwise(geom):
    """D3 ожидает внешние кольца по часовой стрелке (сферические полигоны)."""
    if isinstance(geom, Polygon):
        return orient(geom, sign=-1.0)
    if isinstance(geom, MultiPolygon):
        return MultiPolygon([orient(g, sign=-1.0) for g in geom.geoms])
    return geom


def _coords_round(c, nd=3):
    if isinstance(c, (list, tuple)) and c and isinstance(c[0], (int, float)):
        return [round(c[0], nd), round(c[1], nd)]
    return [_coords_round(x, nd) for x in c]


def _ring_ok(ring) -> bool:
    """После округления мелкие острова вырождаются (менее 3 различных точек или нулевая площадь);
    D3 трактует такое кольцо как всю сферу, поэтому его отбрасываем."""
    pts = {tuple(p) for p in ring}
    if len(pts) < 3:
        return False
    xs, ys = [p[0] for p in ring], [p[1] for p in ring]
    area = 0.5 * abs(sum(xs[i] * ys[i + 1] - xs[i + 1] * ys[i] for i in range(len(ring) - 1)))
    return area > 1e-7


def _clean_geometry(gj: dict, nd: int = 3) -> dict | None:
    polys = [gj["coordinates"]] if gj["type"] == "Polygon" else gj["coordinates"]
    out = []
    for poly in polys:
        poly = _coords_round(poly, nd)
        if not _ring_ok(poly[0]):
            continue
        out.append([poly[0]] + [r for r in poly[1:] if _ring_ok(r)])
    return {"type": "MultiPolygon", "coordinates": out} if out else None


def export_geometry(cfg: dict, out: Path) -> None:
    """Полигоны всех МО справочника (версия reference_year) -> site/data/mo.geojson.

    Допуск упрощения пропорционален размеру МО: районы Москвы шириной в несколько километров
    при общем допуске ~1 км теряют форму и расходятся щелями, а большим районам Сибири он не вредит.
    """
    year = cfg["data"]["reference_year"]
    gdf = gpd.read_file(cfg["data"]["reference_polygons"])
    gdf["territory_id"] = gdf["territory_id"].astype(int)
    gdf = gdf[(gdf.year_from <= year) & (gdf.year_to > year)].drop_duplicates("territory_id")
    tol_max = cfg["output"]["simplify_tolerance_deg"]
    feats = []
    for tid, geom in zip(gdf.territory_id, gdf.geometry):
        if geom is None or geom.is_empty:
            continue
        tol = min(tol_max, 0.02 * float(np.sqrt(geom.area)))
        g = _clockwise(geom.simplify(tol, preserve_topology=True))
        if g.is_empty:
            continue
        geom_clean = _clean_geometry(mapping(g), nd=3 if geom.area > 0.05 else 4)
        if geom_clean is None:
            continue
        feats.append({"type": "Feature", "id": int(tid), "properties": {}, "geometry": geom_clean})
    json.dump({"type": "FeatureCollection", "features": feats}, open(out / "mo.geojson", "w"), separators=(",", ":"))


def type_names(prof: pd.DataFrame, lab: np.ndarray, ids: np.ndarray, path: str, level: str = "types") -> dict[int, dict]:
    """Названия типов из configs/type_names.yaml: тип получает имя по «якорному» МО внутри него."""
    out = {int(c): {"name": f"Тип {c + 1}", "description": ""} for c in prof.index}
    p = Path(path)
    if not p.exists():
        return out
    pos = {int(t): i for i, t in enumerate(ids)}
    for item in (yaml.safe_load(p.read_text(encoding="utf-8")) or {}).get(level, []):
        i = pos.get(int(item["anchor"]))
        if i is not None:
            out[int(lab[i])] = {"name": item["name"], "short": item.get("short", item["name"]), "description": item.get("description", ""), "color": item.get("color")}
    return out


def export_site(state: dict) -> None:
    cfg = state["cfg"]
    p = state["panel"]
    out = Path(cfg["output"]["site_data_dir"])
    out.mkdir(parents=True, exist_ok=True)
    res = Path(cfg["output"]["results_dir"])
    lab, WL, ends = state["main_lab"], state["WL"], state["ends"]
    prof = state["prof"]
    k = int(lab.max() + 1)
    names = type_names(prof, lab, p.ids, "configs/type_names.yaml", "types")
    macro_lab, prof_macro = state["macro_lab"], state["prof_macro"]
    macro_names = type_names(prof_macro, macro_lab, p.ids, "configs/type_names.yaml", "macro")
    Lab = state["labels_official"]

    export_geometry(cfg, out)
    extra = Path(cfg["data"].get("extra_regions", ""))
    if extra.is_file():  # субъекты без МО в справочнике: рисуются на карте как «нет данных»
        shutil.copyfile(extra, out / "new_regions.geojson")
    year = cfg["data"]["reference_year"]

    # --- карточки МО ---
    ref = load_reference(cfg["data"]["reference_table"], year)
    in_panel = {int(t): i for i, t in enumerate(p.ids)}
    raw_ids = set(pd.read_parquet(cfg["data"]["consumption"], columns=["territory_id"]).territory_id.unique())
    tot = p.total.mean(1)
    shares = p.cats.mean(1) / tot[:, None]
    A = state["graphs"][cfg["graphs"]["main_rule"]]
    feat = state["full"].raw
    conf = state["conf"]
    s23, s24 = p.total[:, :12].mean(1), p.total[:, 12:].mean(1)
    g_nat = np.median(s24 / s23)
    growth_rel = (s24 / s23) / g_nat - 1                      # рост трат относительно медианного по стране
    mp = p.categories.index("Маркетплейсы")
    d_mp = p.cats[:, 12:, mp].mean(1) / s24 - p.cats[:, :12, mp].mean(1) / s23   # сдвиг доли, доли единицы
    mo = []
    for tid, r in ref.iterrows():
        tid = int(tid)
        rec = {"id": tid, "name": r["name"], "region": r["region"], "kind": r["mo_type"],
               "capital": r["mo_status"] == "административный_центр_субъекта"}
        if tid in Lab.index:
            lr = Lab.loc[tid]
            rec["pop"] = None if pd.isna(lr["pop_2024_rosstat"]) else int(lr["pop_2024_rosstat"])
            rec["flags"] = [k for k, v in (("Арктическая зона", lr["arctic_any"]), ("Крайний Север и приравненные", lr["far_north_or_equated"]),
                                           ("Ядро агломерации", lr["onp_agglomeration_core"])) if v == 1]
            if lr["monotown"] == 1:
                rec["flags"].append(f"Моногород, кат. {int(lr['monotown_min_category'])}")
        i = in_panel.get(tid)
        if i is None:
            rec["status"] = "incomplete" if tid in raw_ids else "absent"
        else:
            row = A.getrow(i)
            nb = row.indices[np.argsort(-row.data)[:10]]
            rec |= {
                "status": "ok", "type": int(lab[i]), "macro": int(macro_lab[i]), "types": [int(x) for x in WL[i]],
                "moved": bool(state["moved"][i]),
                "spend": float(tot[i]), "shares": [float(x) for x in shares[i]],
                "level": float(feat.iloc[i]["level"]), "summer": float(feat.iloc[i]["summer_all"]),
                "summer_fs": float(feat.iloc[i]["summer_food_service"]),
                "ma": None if pd.isna(p.meta.market_access.iloc[i]) else float(p.meta.market_access.iloc[i]),
                "nb": [int(p.ids[j]) for j in nb],
                "conf": [float(conf[i, 0]), float(conf[i, -1])],
                "growth": float(growth_rel[i]), "dmp": float(d_mp[i]),
            }
        mo.append(rec)
    json.dump(_round(mo), open(out / "mo.json", "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))

    # --- ряды по МО (руб.): итого + 5 категорий ---
    series = {int(t): [p.total[i].round().astype(int).tolist()] + [p.cats[i, :, j].round().astype(int).tolist()
                                                                    for j in range(len(p.categories))]
              for i, t in enumerate(p.ids)}
    json.dump(series, open(out / "series.json", "w"), separators=(",", ":"))

    # --- типы ---
    types = []
    for c in range(k):
        idx = lab == c
        q = np.percentile(p.total[idx], [25, 50, 75], axis=0)
        types.append({
            "id": c, **names[c], "size": int(idx.sum()),
            "spend": float(np.median(tot[idx])),
            "shares": [float(x) for x in np.median(shares[idx], axis=0)],
            "summer": float(np.median(feat.summer_all.to_numpy()[idx])),
            "summer_fs": float(np.median(feat.summer_food_service.to_numpy()[idx])),
            "ma": float(np.nanmedian(p.meta.market_access.to_numpy(dtype=float)[idx])),
            "q25": q[0].tolist(), "q50": q[1].tolist(), "q75": q[2].tolist(),
            "cat_median": [np.median(p.cats[idx, :, j], axis=0).tolist() for j in range(len(p.categories))],
            "typical": prof.loc[c, "typical"], "typical_ids": prof.loc[c, "typical_ids"], "regions": prof.loc[c, "top_regions"],
            "kinds": {kk.replace("kind:", ""): float(prof.loc[c, kk]) for kk in prof.columns if kk.startswith("kind:")},
            "mirkin": {MIRKIN_FEATURES[f]: float(prof.loc[c, "mirkin:" + f]) for f in MIRKIN_FEATURES if "mirkin:" + f in prof},
            "mirkin_top": prof.loc[c, "mirkin_top"],
            "macro": int(pd.Series(macro_lab[idx]).mode()[0]),
            "official": {kk.replace("official:", ""): float(prof.loc[c, kk]) for kk in prof.columns if kk.startswith("official:")},
        })
    json.dump(_round(types), open(out / "types.json", "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    macro = []
    for c in range(int(macro_lab.max() + 1)):
        idx = macro_lab == c
        macro.append({"id": c, **macro_names[c], "size": int(idx.sum()), "spend": float(np.median(tot[idx])),
                      "shares": [float(x) for x in np.median(shares[idx], axis=0)],
                      "mirkin_top": prof_macro.loc[c, "mirkin_top"], "typical": prof_macro.loc[c, "typical"],
                      "q50": np.percentile(p.total[idx], 50, axis=0).tolist(),
                      "official": {kk.replace("official:", ""): float(prof_macro.loc[c, kk]) for kk in prof_macro.columns if kk.startswith("official:")}})
    json.dump(_round(macro), open(out / "macro.json", "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))

    # справочник «МО -> тип» для скачивания с лендинга
    tab = p.meta[["name", "region", "mo_type", "oktmo"]].copy()
    tab["macro_type"] = [macro_names[int(c)]["name"] for c in macro_lab]
    tab["type"] = [names[int(c)]["name"] for c in lab]
    tab["type_2023"] = [names[int(c)]["name"] for c in WL[:, 0]]
    tab["type_2024"] = [names[int(c)]["name"] for c in WL[:, -1]]
    tab["significant_move_2023_2024"] = state["moved"]
    tab["confidence_2023"] = np.round(conf[:, 0], 3)
    tab["confidence_2024"] = np.round(conf[:, -1], 3)
    tab.to_csv(out / "typology.csv", encoding="utf-8-sig")

    # --- сводка методов и динамики ---
    def csv(name, **kw):
        f = res / name
        return pd.read_csv(f, **kw) if f.exists() else None

    meta = {
        "months": p.months, "categories": p.categories, "windows": ends,
        "national": {"total": np.median(p.total, axis=0).tolist(),
                     "cats": [np.median(p.cats[:, :, j], axis=0).tolist() for j in range(len(p.categories))]},
        "n_panel": int(len(p.ids)), "n_dropped": int(len(p.dropped)),
        # регионы, которых нет в наборе организатора совсем, и регионы, чьи МО все исключены как неполные
        "missing_regions": sorted(set(ref.region) - set(ref.loc[ref.index.isin(list(raw_ids)), "region"])),
        "incomplete_regions": sorted(set(ref.loc[ref.index.isin(list(raw_ids)), "region"]) - set(p.meta.region)),
        "methods": csv("methods_icvi.csv").to_dict("records"),
        "sweep": csv("kefrin_share_sweep.csv").to_dict("records"),
        "graphs": csv("graphs_diagnostics.csv", index_col=0).reset_index().rename(columns={"index": "rule"}).to_dict("records"),
        "jaccard": csv("graphs_jaccard.csv", index_col=0).to_dict(),
        "rules": csv("rules_sensitivity.csv").to_dict("records"),
        "dynamics": csv("dynamics_windows.csv").to_dict("records"),
        "transitions": pd.read_csv(res / "transitions_first_last.csv", index_col=0).to_numpy().tolist(),
        "external": json.load(open(res / "external_validation.json", encoding="utf-8")),
        "final": cfg["final"] | {"net_share": cfg["clustering"]["kefrin_net_share"], "tau": cfg["windows"]["confidence_tau"]},
        "final_icvi": json.load(open(res / "final_icvi.json", encoding="utf-8")),
        "moves_sensitivity": csv("moves_sensitivity.csv").to_dict("records"),
        "transitions_confident": pd.read_csv(res / "transitions_confident.csv", index_col=0).to_numpy().tolist(),
        "growth_national": float(g_nat - 1),
        "selection": state["selection"],
        "asymmetry": json.load(open(res / "dynamics_asymmetry.json", encoding="utf-8")),
        "justification": json.load(open(res / "justification.json", encoding="utf-8")) if (res / "justification.json").exists() else None,
        "knn_sensitivity": csv("knn_sensitivity.csv").to_dict("records") if (res / "knn_sensitivity.csv").exists() else [],
        "weights_sensitivity": csv("weights_sensitivity.csv").to_dict("records") if (res / "weights_sensitivity.csv").exists() else [],
        "selection_sensitivity": csv("selection_sensitivity.csv").to_dict("records") if (res / "selection_sensitivity.csv").exists() else [],
    }
    for extra in ("us_check.json",):
        f = res / extra
        if f.exists():
            meta[extra.removesuffix(".json")] = json.load(open(f, encoding="utf-8"))
    json.dump(_round(meta, 4), open(out / "meta.json", "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
