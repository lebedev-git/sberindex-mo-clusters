"""Пять методов кластеризации на одних и тех же узлах.

  kmeans   — только признаки (базовая линия без сети);
  ward     — иерархическая агломерация Уорда по признакам;
  spectral — спектральная кластеризация смешанной матрицы сходства (признаки + сеть);
  leiden   — сообщества сети (Traag et al., 2019), только структура рёбер;
  kefrin   — k-means для сетей с признаками (Shalileh & Mirkin, 2022): признаки и строки
             сетевой матрицы в одном критерии наименьших квадратов.
"""
from __future__ import annotations

import igraph as ig
import leidenalg
import numpy as np
import scipy.sparse as sp
from sklearn.cluster import AgglomerativeClustering, KMeans, SpectralClustering


def kmeans(X: np.ndarray, k: int, seed: int, n_init: int = 20) -> np.ndarray:
    return KMeans(k, n_init=n_init, random_state=seed).fit_predict(X)


def ward(X: np.ndarray, k: int) -> np.ndarray:
    return AgglomerativeClustering(k, linkage="ward").fit_predict(X)


def spectral(A_net: sp.csr_matrix, A_attr: sp.csr_matrix, k: int, alpha: float, seed: int) -> np.ndarray:
    """Смесь двух kNN-сходств; каждая матрица нормирована на свой максимум перед смешиванием."""
    W = alpha * A_net / A_net.max() + (1 - alpha) * A_attr / A_attr.max()
    W = W.maximum(W.T)
    return SpectralClustering(k, affinity="precomputed", assign_labels="cluster_qr", random_state=seed).fit_predict(W)


def to_igraph(A: sp.csr_matrix) -> ig.Graph:
    U = sp.triu(A, 1).tocoo()
    g = ig.Graph(n=A.shape[0], edges=list(zip(U.row.tolist(), U.col.tolist())), directed=False)
    g.es["weight"] = U.data.tolist()
    return g


def leiden(A: sp.csr_matrix, seed: int, resolution: float = 1.0) -> np.ndarray:
    g = to_igraph(A)
    part = leidenalg.find_partition(
        g, leidenalg.RBConfigurationVertexPartition, weights="weight",
        resolution_parameter=resolution, seed=seed, n_iterations=-1,
    )
    return np.asarray(part.membership)


def leiden_k(A: sp.csr_matrix, k: int, seed: int) -> tuple[np.ndarray, float]:
    """Подбор разрешения бисекцией так, чтобы число сообществ (размером >= 1% узлов) было k."""
    n = A.shape[0]

    def big(lab):
        return int((np.bincount(lab) >= max(2, 0.01 * n)).sum())

    lo, hi = 0.05, 5.0
    best = None
    for _ in range(30):
        mid = (lo + hi) / 2
        lab = leiden(A, seed, mid)
        c = big(lab)
        if best is None or abs(c - k) < abs(big(best[0]) - k):
            best = (lab, mid)
        if c == k:
            break
        lo, hi = (mid, hi) if c < k else (lo, mid)
    lab, res = best
    return _absorb_small(lab, A, max(2, 0.01 * n)), res


def _absorb_small(lab: np.ndarray, A: sp.csr_matrix, min_size: float) -> np.ndarray:
    """Узлы мелких сообществ присоединяются к крупному сообществу с наибольшим весом связей."""
    lab = lab.copy()
    sizes = np.bincount(lab)
    big = np.where(sizes >= min_size)[0]
    for i in np.where(~np.isin(lab, big))[0]:
        row = A.getrow(i)
        w = np.zeros(lab.max() + 1)
        np.add.at(w, lab[row.indices], row.data)
        w[~np.isin(np.arange(len(w)), big)] = -1
        lab[i] = int(np.argmax(w)) if w.max() > 0 else big[np.argmax(sizes[big])]
    _, lab = np.unique(lab, return_inverse=True)
    return lab


def kefrin_network_block(A: sp.csr_matrix) -> np.ndarray:
    """Предобработка сетевой матрицы «модулярностью»: p_ij - p_i+ p_+j / p_++ (Shalileh & Mirkin)."""
    P = A.toarray()
    r = P.sum(1)
    return P - np.outer(r, r) / r.sum()


def rho_for_share(X: np.ndarray, P: np.ndarray, share: float) -> float:
    """rho, при котором сеть даёт долю `share` полного разброса в пространстве [Y, sqrt(rho) P]."""
    vx = ((X - X.mean(0)) ** 2).sum()
    vp = ((P - P.mean(0)) ** 2).sum()
    return float(share / (1 - share) * vx / vp)


def kefrin(X: np.ndarray, A: sp.csr_matrix, k: int, seed: int, net_share: float = 0.5, n_init: int = 20) -> np.ndarray:
    """KEFRiN (евклидова версия) как k-means на конкатенации [Y, sqrt(rho) * P].

    Критерий: sum_k sum_{i in S_k} ||y_i - c_k||^2 + rho * ||p_i - lambda_k||^2, где p_i — строка
    предобработанной сетевой матрицы. rho задаётся через долю сети в общем разбросе (net_share):
    0 — обычный k-means по признакам, близко к 1 — только сеть.
    """
    if net_share <= 0:
        return kmeans(X, k, seed, n_init)
    P = kefrin_network_block(A)
    Z = np.hstack([X, np.sqrt(rho_for_share(X, P, net_share)) * P])
    return KMeans(k, n_init=n_init, random_state=seed).fit_predict(Z)


def run_method(name: str, k: int, *, X, A_net, A_attr, cfg_cl: dict, seed: int) -> np.ndarray:
    if name == "kmeans":
        return kmeans(X, k, seed, cfg_cl["n_init"])
    if name == "ward":
        return ward(X, k)
    if name == "spectral":
        return spectral(A_net, A_attr, k, cfg_cl["spectral_alpha"], seed)
    if name == "leiden":
        return leiden_k(A_net, k, seed)[0]
    if name == "kefrin":
        return kefrin(X, A_net, k, seed, cfg_cl["kefrin_net_share"], cfg_cl["n_init"])
    raise ValueError(name)
