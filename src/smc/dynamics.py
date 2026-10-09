"""Динамика типов: эволюционная кластеризация последовательности сетей.

Снимок t — 12-месячное окно (шаг 1 мес.), своя сеть G_t и свои признаки X_t в общей шкале.
Разбиение снимка t получается k-means в пространстве KEFRiN [X_t, sqrt(rho) P_t], запущенным из
центров основной типологии (якорный тёплый старт; ср. эволюционную кластеризацию Chakrabarti et al., 2006).
Старт от предыдущего снимка отвергнут: ошибки накапливаются. Номер типа сохраняет смысл между снимками,
а каждый снимок оптимизируется по своим данным. Значимый переход — confident_moves, правило «трёх окон»
(persistent_moves) оставлено только для сравнения в results/moves_sensitivity.csv.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.optimize import linear_sum_assignment
from sklearn.cluster import KMeans
from sklearn.metrics import adjusted_rand_score

from .clustering import kefrin_network_block


def kefrin_space(X: np.ndarray, A, rho: float) -> np.ndarray:
    return np.hstack([X, np.sqrt(rho) * kefrin_network_block(A)])


def warm_kmeans(Z: np.ndarray, prev_lab: np.ndarray, k: int) -> tuple[np.ndarray, np.ndarray]:
    """k-means с тёплым стартом; возвращает метки и уверенность принадлежности
    margin_i = (d2 - d1) / d2, где d1, d2 — расстояния до ближайшего и второго центра (0 — на границе)."""
    init = np.vstack([Z[prev_lab == c].mean(0) for c in range(k)])
    km = KMeans(k, init=init, n_init=1).fit(Z)
    d = np.sort(km.transform(Z), axis=1)
    return km.labels_, (d[:, 1] - d[:, 0]) / np.maximum(d[:, 1], 1e-12)


def confident_moves(lab_a: np.ndarray, lab_b: np.ndarray, conf_a: np.ndarray, conf_b: np.ndarray, tau: float) -> np.ndarray:
    """Значимый переход: МО уверенно (margin >= tau) в типе A в первом окне и уверенно в типе B != A во втором.
    Окна 2023 и 2024 не пересекаются по месяцам, поэтому это два независимых наблюдения."""
    return (lab_a != lab_b) & (conf_a >= tau) & (conf_b >= tau)


def match_to_reference(ref: np.ndarray, lab: np.ndarray, k: int) -> tuple[np.ndarray, np.ndarray]:
    """Перенумерация меток по максимальному пересечению с эталоном; возвращает метки и Жаккар пар."""
    J = np.zeros((k, k))
    for a in range(k):
        A = ref == a
        for b in range(k):
            B = lab == b
            J[a, b] = (A & B).sum() / max(1, (A | B).sum())
    r, c = linear_sum_assignment(-J)
    mapping = np.empty(k, dtype=int)
    mapping[c] = r
    return mapping[lab], J[r, c]


def transitions(a: np.ndarray, b: np.ndarray, k: int) -> pd.DataFrame:
    return pd.crosstab(pd.Categorical(a, range(k)), pd.Categorical(b, range(k)), dropna=False)


def persistent_moves(labels: np.ndarray, run: int = 3) -> np.ndarray:
    """МО с устойчивым переходом: тип в первых `run` снимках один и тот же, в последних `run` —
    один и тот же, и они различаются. labels: [n, W]."""
    first = labels[:, :run]
    last = labels[:, -run:]
    stable_first = (first == first[:, :1]).all(1)
    stable_last = (last == last[:, :1]).all(1)
    return stable_first & stable_last & (first[:, 0] != last[:, 0])


def consecutive_ari(labels: np.ndarray) -> list[float]:
    return [float(adjusted_rand_score(labels[:, t - 1], labels[:, t])) for t in range(1, labels.shape[1])]
