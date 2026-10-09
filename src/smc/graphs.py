"""Пять правил построения рёбер экономической сети МО и их диагностика.

Каждое правило даёт симметричный взвешенный kNN-граф: ребро (i, j) есть, если j среди k
ближайших к i или i среди k ближайших к j; вес — сходство в (0, 1].

  attr   — евклидово расстояние в пространстве признаков (атрибутивное сходство);
  corr   — корреляция Пирсона идиосинкратических рядов (синхронность колебаний трат);
  cosine — косинусное сходство векторов средних расходов по категориям (структура корзины);
  dtw    — динамическое выравнивание рядов с окном Сакое–Тибы (опережение/запаздывание);
  road   — автодорожное расстояние между центрами МО (физическая близость).
"""
from __future__ import annotations

import numba
import numpy as np
import scipy.sparse as sp


def _knn_from_similarity(S: np.ndarray, k: int) -> sp.csr_matrix:
    S = S.copy()
    np.fill_diagonal(S, -np.inf)
    idx = np.argpartition(-S, k, axis=1)[:, :k]
    rows = np.repeat(np.arange(S.shape[0]), k)
    vals = S[rows, idx.ravel()]
    ok = np.isfinite(vals) & (vals > 0)
    A = sp.csr_matrix((vals[ok], (rows[ok], idx.ravel()[ok])), shape=S.shape)
    return A.maximum(A.T).tocsr()


def _knn_from_distance(D: np.ndarray, k: int) -> sp.csr_matrix:
    """kNN по расстоянию; вес exp(-d^2 / (s_i s_j)), s_i — расстояние до k-го соседа (локальный масштаб)."""
    D = D.copy()
    np.fill_diagonal(D, np.inf)
    idx = np.argpartition(D, k, axis=1)[:, :k]
    kth = np.take_along_axis(D, idx, axis=1).max(axis=1)
    sigma = np.where(np.isfinite(kth) & (kth > 0), kth, np.nan)
    sigma = np.where(np.isnan(sigma), np.nanmedian(sigma), sigma)
    rows = np.repeat(np.arange(D.shape[0]), k)
    cols = idx.ravel()
    d = D[rows, cols]
    ok = np.isfinite(d)
    w = np.exp(-(d[ok] ** 2) / (sigma[rows[ok]] * sigma[cols[ok]]))
    w = np.maximum(w, 1e-6)
    A = sp.csr_matrix((w, (rows[ok], cols[ok])), shape=D.shape)
    return A.maximum(A.T).tocsr()


def _zchannels(series: np.ndarray) -> np.ndarray:
    """Нормировка каждого канала ряда МО: среднее 0, ст. отклонение 1 по времени."""
    s = series - series.mean(axis=1, keepdims=True)
    sd = s.std(axis=1, keepdims=True)
    return s / np.where(sd > 1e-12, sd, 1.0)


def corr_similarity(series: np.ndarray) -> np.ndarray:
    z = _zchannels(series).reshape(series.shape[0], -1)
    z = z / np.linalg.norm(z, axis=1, keepdims=True)
    return z @ z.T


def cosine_similarity(mean_spend: np.ndarray) -> np.ndarray:
    v = mean_spend / np.linalg.norm(mean_spend, axis=1, keepdims=True)
    return v @ v.T


@numba.njit(parallel=True, cache=True)
def _dtw_matrix(z: np.ndarray, band: int) -> np.ndarray:
    n, T, C = z.shape
    out = np.zeros((n, n))
    for i in numba.prange(n):
        cost = np.empty((T + 1, T + 1))
        for j in range(i + 1, n):
            cost[:, :] = np.inf
            cost[0, 0] = 0.0
            for a in range(1, T + 1):
                lo = max(1, a - band)
                hi = min(T, a + band)
                for b in range(lo, hi + 1):
                    d = 0.0
                    for c in range(C):
                        diff = z[i, a - 1, c] - z[j, b - 1, c]
                        d += diff * diff
                    m = cost[a - 1, b - 1]
                    if cost[a - 1, b] < m:
                        m = cost[a - 1, b]
                    if cost[a, b - 1] < m:
                        m = cost[a, b - 1]
                    cost[a, b] = d + m
            out[i, j] = np.sqrt(cost[T, T])
            out[j, i] = out[i, j]
    return out


def dtw_distance(series: np.ndarray, band: int) -> np.ndarray:
    return _dtw_matrix(np.ascontiguousarray(_zchannels(series)), band)


def build_graph(rule: str, *, X=None, series=None, mean_spend=None, road=None, k: int, dtw_band: int = 2) -> sp.csr_matrix:
    if rule == "attr":
        sq = (X ** 2).sum(1)
        D = np.sqrt(np.maximum(sq[:, None] + sq[None, :] - 2 * X @ X.T, 0))
        return _knn_from_distance(D, k)
    if rule == "corr":
        return _knn_from_similarity(corr_similarity(series), k)
    if rule == "cosine":
        return _knn_from_similarity(cosine_similarity(mean_spend), k)
    if rule == "dtw":
        return _knn_from_distance(dtw_distance(series, dtw_band), k)
    if rule == "road":
        return _knn_from_distance(road, k)
    raise ValueError(rule)


def diagnostics(A: sp.csr_matrix, X: np.ndarray, region: np.ndarray, road: np.ndarray) -> dict:
    """Описательные свойства графа: связность, гомофилия по признакам, география рёбер."""
    from scipy.sparse.csgraph import connected_components

    n = A.shape[0]
    ncomp, lab = connected_components(A, directed=False)
    U = sp.triu(A, 1).tocoo()
    i, j = U.row, U.col
    deg = np.diff(A.indptr)
    # гомофилия: средняя по признакам корреляция значений на концах рёбер
    homo = np.nanmean([np.corrcoef(X[i, f], X[j, f])[0, 1] for f in range(X.shape[1])])
    rd = road[i, j]
    rd = rd[np.isfinite(rd)]
    return {
        "edges": int(len(i)),
        "mean_degree": float(deg.mean()),
        "components": int(ncomp),
        "largest_component_share": float(np.bincount(lab).max() / n),
        "attr_homophily": float(homo),
        "same_region_share": float((region[i] == region[j]).mean()),
        "median_edge_road_km": float(np.median(rd)) if len(rd) else float("nan"),
    }


def jaccard_edges(A: sp.csr_matrix, B: sp.csr_matrix) -> float:
    a = set(zip(*sp.triu(A, 1).nonzero()))
    b = set(zip(*sp.triu(B, 1).nonzero()))
    return len(a & b) / max(1, len(a | b))
