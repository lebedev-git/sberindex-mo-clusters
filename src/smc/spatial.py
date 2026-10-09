"""Пространственная автокорреляция типов (статистика совпадений по соседству, join count) против сети.

Для набора пар МО (рёбер) считается доля пар одного типа и сравнивается с перестановочным нулём:
метки типов случайно перемешиваются между МО (размеры типов сохраняются). Два набора пар:
  geo — географические соседи: полигоны МО из справочника СберИндекса соприкасаются;
  net — рёбра основной сети синхронности (corr).
Если обе доли выше нуля — типы пространственно сгруппированы; если доля по сети выше, чем по
географическому соседству, — сеть связывает МО одного типа сильнее, чем общая граница.
"""
from __future__ import annotations

import geopandas as gpd
import numpy as np
import scipy.sparse as sp


def geo_pairs(polygons_path: str, year: int, ids: np.ndarray) -> np.ndarray:
    g = gpd.read_file(polygons_path)
    g["territory_id"] = g["territory_id"].astype(int)
    g = g[(g.year_from <= year) & (g.year_to > year)].drop_duplicates("territory_id")
    pos = {int(t): i for i, t in enumerate(ids)}
    g = g[g.territory_id.isin(pos)].reset_index(drop=True)
    geom = g.geometry.buffer(0)    # исправление самопересечений перед поиском соседей
    a, b = geom.sindex.query(geom, predicate="intersects")
    keep = a < b
    tid = g.territory_id.to_numpy()
    return np.array([[pos[int(tid[x])], pos[int(tid[y])]] for x, y in zip(a[keep], b[keep])])


def join_count(pairs: np.ndarray, lab: np.ndarray, reps: int, seed: int) -> dict:
    same = float((lab[pairs[:, 0]] == lab[pairs[:, 1]]).mean())
    rng = np.random.default_rng(seed)
    null = np.array([(l[pairs[:, 0]] == l[pairs[:, 1]]).mean() for l in (rng.permutation(lab) for _ in range(reps))])
    return {"pairs": int(len(pairs)), "same": same, "null": float(null.mean()), "null_sd": float(null.std()),
            "z": float((same - null.mean()) / null.std()), "ratio": same / float(null.mean())}


def analyze(polygons_path: str, year: int, ids: np.ndarray, A: sp.csr_matrix, lab: np.ndarray, macro: np.ndarray,
            region: np.ndarray, reps: int, seed: int) -> dict:
    G = geo_pairs(polygons_path, year, ids)
    U = sp.triu(A, 1).tocoo()
    N = np.column_stack([U.row, U.col])
    covered = np.zeros(len(ids), bool)
    covered[G.ravel()] = True
    # рёбра сети между географическими соседями и между удалёнными МО
    geo_set = {(int(x), int(y)) for x, y in G}
    net_is_geo = np.array([(int(x), int(y)) in geo_set for x, y in N])
    out = {"mo_with_neighbours": int(covered.sum()), "net_edges_between_neighbours_share": float(net_is_geo.mean())}
    for name, l in (("types", lab), ("macro", macro), ("region", region)):
        out[name] = {"geo": join_count(G, l, reps, seed), "net": join_count(N, l, reps, seed),
                     "net_not_neighbours": join_count(N[~net_is_geo], l, reps, seed)}
    # доля одного типа среди соседей из того же региона и из разных регионов: тип не сводится к региону
    same_reg = region[G[:, 0]] == region[G[:, 1]]
    out["types"]["geo_same_region"] = float((lab[G[same_reg, 0]] == lab[G[same_reg, 1]]).mean())
    out["types"]["geo_cross_region"] = float((lab[G[~same_reg, 0]] == lab[G[~same_reg, 1]]).mean())
    return out
