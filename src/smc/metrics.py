"""Внутренние индексы качества кластеризации (ICVI), устойчивость и внешняя проверка.

Определения графовых индексов — по статье Shalileh, Antonov, Tsyplakova,
Doklady Mathematics 112(3):553–564 (2025), формулы (18)–(22), https://doi.org/10.1134/S1064562425700589
(AVI/AVU восходят к Biswas & Biswas, ESWA 2017).

Направление: SW, CH, AVI, ANUI, MQ — больше лучше; S_Dbw, AVU — меньше лучше.
MQ в Положении не расшифрован; используем модулярность Ньюмана–Гирван Q (обоснование в docs/report.md).
"""
from __future__ import annotations

import numpy as np
import scipy.sparse as sp
from sklearn.metrics import adjusted_rand_score, calinski_harabasz_score, silhouette_score

DIRECTIONS = {"SW": 1, "CH": 1, "S_Dbw": -1, "MQ": 1, "AVI": 1, "AVU": -1, "ANUI": 1, "stability_ARI": 1}


def s_dbw(X: np.ndarray, lab: np.ndarray) -> dict:
    """S_Dbw (Halkidi & Vazirgiannis, 2001) = Scat + Dens_bw.

    Scat = mean_k ||var(C_k)|| / ||var(X)||; stdev = sqrt(sum_k ||var(C_k)||) / K.
    Плотность в центре кластера k — число его точек в радиусе stdev от центра;
    для пары (k, l) — число точек C_k ∪ C_l в радиусе stdev от середины центров.
    Dens_bw = 1/(K(K-1)) sum_{k!=l} den(k,l) / max(den(k), den(l)).
    Возвращает также число кластеров с нулевой плотностью в центре: при них индекс вырождается.
    """
    ks = np.unique(lab)
    K = len(ks)
    members = [X[lab == k] for k in ks]
    cent = np.array([m.mean(0) for m in members])
    var_norm = np.array([np.linalg.norm(m.var(0)) for m in members])
    scat = float(var_norm.mean() / np.linalg.norm(X.var(0)))
    stdev = np.sqrt(var_norm.sum()) / K
    dens_c = np.array([(np.linalg.norm(m - c, axis=1) <= stdev).sum() for m, c in zip(members, cent)])
    total, skipped = 0.0, 0
    for a in range(K):
        for b in range(K):
            if a == b:
                continue
            pts = np.vstack([members[a], members[b]])
            u = (cent[a] + cent[b]) / 2
            den_ab = (np.linalg.norm(pts - u, axis=1) <= stdev).sum()
            denom = max(dens_c[a], dens_c[b])
            if denom == 0:
                skipped += 1
                continue
            total += den_ab / denom
    dens_bw = total / (K * (K - 1))
    return {"S_Dbw": scat + dens_bw, "Scat": scat, "Dens_bw": float(dens_bw),
            "S_Dbw_zero_density_clusters": int((dens_c == 0).sum()), "S_Dbw_skipped_pairs": skipped}


def graph_indices(A: sp.spmatrix, lab: np.ndarray) -> dict:
    """AVI, AVU, ANUI и модулярность Q на сети A (симметричная, неотрицательная, без петель).

    S_kl = sum_{i in k, j in l} a_ij; O_k = sum_{l!=k} S_kl; In_l = sum_{k!=l} S_kl.
    AVI = mean_k S_kk / (S_kk + O_k)                       — изолированность сообществ, больше лучше;
    AVU = (1/K) sum_k sum_{l!=k} S_kl / (O_k + In_l - S_kl) — «склеенность» сообществ, меньше лучше;
    ANUI = AVI / (1 + AVI * AVU);  Q = sum_k [S_kk/2m - (d_k/2m)^2].
    """
    _, lab = np.unique(lab, return_inverse=True)
    K = lab.max() + 1
    M = sp.csr_matrix((np.ones(len(lab)), (np.arange(len(lab)), lab)), shape=(len(lab), K))
    S = (M.T @ A @ M).toarray()
    d = np.diag(S)
    out = S.sum(1) - d
    inn = S.sum(0) - d
    iso = np.divide(d, d + out, out=np.zeros(K), where=(d + out) > 0)
    avi = float(iso.mean())
    den = out[:, None] + inn[None, :] - S
    U = np.divide(S, den, out=np.zeros_like(S), where=den > 0)
    np.fill_diagonal(U, 0)
    avu = float(U.sum() / K)
    m2 = S.sum()
    dk = S.sum(1)
    q = float((d / m2 - (dk / m2) ** 2).sum())
    return {"AVI": avi, "AVU": avu, "ANUI": avi / (1 + avi * avu), "MQ": q}


def icvi(X: np.ndarray, A: sp.spmatrix, lab: np.ndarray) -> dict:
    return {
        "SW": float(silhouette_score(X, lab)),
        "CH": float(calinski_harabasz_score(X, lab)),
        **s_dbw(X, lab),
        **graph_indices(A, lab),
    }


def modularity(A: sp.spmatrix, lab: np.ndarray) -> float:
    return graph_indices(A, lab)["MQ"]


def permutation_baseline(X: np.ndarray, A: sp.spmatrix, lab: np.ndarray, reps: int, seed: int) -> dict:
    """Индексы для случайных перестановок меток с теми же размерами кластеров: базовая линия
    «никакой структуры». Возвращает среднее и ст. отклонение по каждому индексу."""
    rng = np.random.default_rng(seed)
    rows = [icvi(X, A, rng.permutation(lab)) for _ in range(reps)]
    keys = ["SW", "CH", "S_Dbw", "AVI", "AVU", "ANUI", "MQ"]
    return {k: (float(np.mean([r[k] for r in rows])), float(np.std([r[k] for r in rows]))) for k in keys}


def bootstrap_ari(fn, n: int, reps: int, frac: float, seed: int) -> float:
    """Средний ARI между кластеризацией на 80% подвыборке и полной (на общих объектах)."""
    rng = np.random.default_rng(seed)
    full = fn(np.arange(n))
    scores = []
    for _ in range(reps):
        idx = np.sort(rng.choice(n, int(frac * n), replace=False))
        scores.append(adjusted_rand_score(full[idx], fn(idx)))
    return float(np.mean(scores))


def cramers_v(a: np.ndarray, b: np.ndarray) -> float:
    """Связь кластеров с категориальной внешней разметкой (тип МО, регион)."""
    import pandas as pd
    from scipy.stats import chi2_contingency

    t = pd.crosstab(a, b).to_numpy()
    chi2 = chi2_contingency(t, correction=False)[0]
    r, k = t.shape
    return float(np.sqrt(chi2 / (t.sum() * (min(r, k) - 1))))


def eta_squared(values: np.ndarray, lab: np.ndarray) -> float:
    """Доля дисперсии внешнего числового признака, объяснённая кластерами."""
    ok = np.isfinite(values)
    v, l = values[ok], lab[ok]
    grand = v.mean()
    between = sum(((v[l == k].mean() - grand) ** 2) * (l == k).sum() for k in np.unique(l))
    return float(between / ((v - grand) ** 2).sum())


def _selftest() -> None:
    """Аналитический случай из статьи Shalileh и др. (2025): две несвязные клики -> AVI = 1, AVU = 0, Q = 0.5."""
    B = np.ones((4, 4)) - np.eye(4)
    A = sp.csr_matrix(np.block([[B, np.zeros((4, 4))], [np.zeros((4, 4)), B]]))
    r = graph_indices(A, np.array([0] * 4 + [1] * 4))
    assert abs(r["AVI"] - 1) < 1e-12 and abs(r["AVU"]) < 1e-12 and abs(r["MQ"] - 0.5) < 1e-12, r
    # перенумерация меток не меняет индексы
    r2 = graph_indices(A, np.array([1] * 4 + [0] * 4))
    assert all(abs(r[k] - r2[k]) < 1e-12 for k in r)


if __name__ == "__main__":
    _selftest()
    print("metrics selftest ok")
