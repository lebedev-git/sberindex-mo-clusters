"""Двумерная раскладка основной сети для лендинга: «экономическое пространство» МО.

Точки — МО, координаты — t-SNE (van der Maaten & Hinton, 2008) по тому же представлению, на котором
работает KEFRiN: [Y, sqrt(rho) P], где Y — признаки, P — строки сетевой матрицы после предобработки
модулярностью. Близкие точки — МО с похожим потреблением и синхронными колебаниями трат. Инициализация
PCA и фиксированный seed делают раскладку воспроизводимой. Рёбра — рёбра основной сети (corr).
"""
from __future__ import annotations

import numpy as np
import scipy.sparse as sp
from sklearn.decomposition import PCA
from sklearn.manifold import TSNE, trustworthiness

from .clustering import kefrin_network_block, rho_for_share


def kefrin_space(X: np.ndarray, A: sp.csr_matrix, share: float) -> np.ndarray:
    P = kefrin_network_block(A)
    return np.hstack([X, np.sqrt(rho_for_share(X, P, share)) * P])


def tsne_layout(Z: np.ndarray, seed: int, perplexity: float, pca_dims: int) -> np.ndarray:
    Zp = PCA(min(pca_dims, Z.shape[1]), random_state=seed).fit_transform(Z)
    return TSNE(2, perplexity=perplexity, init="pca", random_state=seed, n_jobs=1).fit_transform(Zp), Zp


def normalize(xy: np.ndarray) -> np.ndarray:
    """В [0, 1] с сохранением пропорций; длинная ось — x."""
    xy = xy - xy.min(0)
    if xy[:, 1].max() > xy[:, 0].max():
        xy = xy[:, ::-1]
    return xy / xy[:, 0].max()


def edges(A: sp.csr_matrix, max_edges: int) -> np.ndarray:
    U = sp.triu(A, 1).tocoo()
    order = np.argsort(-U.data, kind="stable")[:max_edges]
    return np.column_stack([U.row[order], U.col[order]])


def build(X: np.ndarray, A: sp.csr_matrix, lab: np.ndarray, ids: np.ndarray, share: float, cfg_l: dict, seed: int) -> tuple[dict, dict]:
    Z = kefrin_space(X, A, share)
    xy, Zp = tsne_layout(Z, seed, cfg_l["perplexity"], cfg_l["pca_dims"])
    xy = normalize(xy)
    E = edges(A, cfg_l["max_edges"])
    # качество: доля рёбер внутри типа, доля 10 ближайших соседей на плоскости из того же типа, trustworthiness
    from sklearn.neighbors import NearestNeighbors
    nn = NearestNeighbors(n_neighbors=11).fit(xy).kneighbors(xy, return_distance=False)[:, 1:]
    quality = {
        "method": "t-SNE по [Y, sqrt(rho) P]", "edges_total": int(sp.triu(A, 1).nnz), "edges_exported": int(len(E)),
        "edge_same_type_share": float((lab[E[:, 0]] == lab[E[:, 1]]).mean()),
        "knn10_same_type_share": float((lab[nn] == lab[:, None]).mean()),
        "trustworthiness_10": float(trustworthiness(Zp, xy, n_neighbors=10)),
        "perplexity": cfg_l["perplexity"], "pca_dims": cfg_l["pca_dims"], "seed": seed,
    }
    net = {"ids": [int(t) for t in ids], "xy": np.round(xy, 4).tolist(), "edges": E.tolist(),
           "method": "t-SNE (PCA-инициализация, seed {}) по совместному представлению KEFRiN: признаки + строки сети синхронности".format(seed),
           "note": "Близкие точки — МО с похожей структурой трат и синхронными колебаниями; оси не имеют единиц. "
                   f"Рёбра — сеть синхронности (k = {cfg_l.get('k_nn', 15)} соседей), "
                   + ("все рёбра." if len(E) == quality["edges_total"] else f"{len(E)} сильнейших из {quality['edges_total']}.")}
    return net, quality
