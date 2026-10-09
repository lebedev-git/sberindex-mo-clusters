"""Опережение и запаздывание по рёбрам сети синхронности.

Для каждого ребра (i, j) основной сети считается корреляция тех же идиосинкратических рядов, что и в
правиле corr (шесть каналов: пять категорий и итог, отклонения от медианы страны и от своего среднего),
со сдвигом s = −L…+L мес.: corr(z_i(t), z_j(t + s)); s > 0 — i опережает j. Лаг ребра — сдвиг максимума.

Нулевая модель — циклический сдвиг ряда j на случайное число месяцев (≥ L + 1): сохраняет форму и
автокорреляцию ряда, но разрушает выравнивание во времени. Если доля рёбер с ненулевым лагом в данных
заметно ниже нулевой, связь в сети синхронна, а не «с запаздыванием».
Направление: среди рёбер с ненулевым лагом между двумя группами МО — доля тех, где ведёт первая группа;
при отсутствии опережения она равна 0,5 (биномиальный критерий).
"""
from __future__ import annotations

import numpy as np
import scipy.sparse as sp
from scipy.stats import binomtest


def _z(series: np.ndarray) -> np.ndarray:
    s = series - series.mean(1, keepdims=True)
    sd = s.std(1, keepdims=True)
    return s / np.where(sd > 1e-12, sd, 1.0)


def lag_corr(series: np.ndarray, i: np.ndarray, j: np.ndarray, max_lag: int) -> np.ndarray:
    """[рёбра, 2L+1]: корреляция по всем каналам на перекрывающихся месяцах при сдвиге s."""
    T = series.shape[1]
    out = np.empty((len(i), 2 * max_lag + 1))
    for c, s in enumerate(range(-max_lag, max_lag + 1)):
        a = series[i, max(0, -s):T - max(0, s)]
        b = series[j, max(0, s):T - max(0, -s)]
        a = _z(a).reshape(len(i), -1)
        b = _z(b).reshape(len(i), -1)
        out[:, c] = (a * b).mean(1)
    return out


def analyze(series: np.ndarray, A: sp.csr_matrix, groups: dict[str, np.ndarray], pairs: list[tuple[str, str]],
            max_lag: int, reps: int, seed: int) -> dict:
    U = sp.triu(A, 1).tocoo()
    i, j = U.row, U.col
    C = lag_corr(series, i, j, max_lag)
    lag = C.argmax(1) - max_lag
    share = float((lag != 0).mean())
    rng = np.random.default_rng(seed)
    T = series.shape[1]
    null = []
    for _ in range(reps):
        sh = rng.integers(max_lag + 1, T - max_lag, len(j))
        idx = (np.arange(T)[None, :] + sh[:, None]) % T            # циклический сдвиг ряда j
        sj = np.take_along_axis(series[j], idx[:, :, None], axis=1)
        tmp = np.concatenate([series[i], sj])
        n = len(i)
        Cn = lag_corr(tmp, np.arange(n), np.arange(n, 2 * n), max_lag)
        null.append(float((Cn.argmax(1) - max_lag != 0).mean()))
    null = np.array(null)
    res = {"edges": int(len(i)), "max_lag": max_lag, "share_lagged": share,
           "lag_hist": {int(s): int((lag == s).sum()) for s in range(-max_lag, max_lag + 1)},
           "null_share": float(null.mean()) if reps else None, "null_sd": float(null.std()) if reps else None,
           "p": float((1 + (null <= share).sum()) / (1 + reps)) if reps else None, "reps": reps,
           "corr_at_lag0_median": float(np.median(C[:, max_lag])),
           "gain_best_vs_lag0_median": float(np.median(C.max(1) - C[:, max_lag]))}
    leaders = []
    for ga, gb in pairs:
        a, b = groups[ga], groups[gb]
        ab = a[i] & b[j]     # i в группе A, j в B: A ведёт при lag > 0
        ba = b[i] & a[j]     # i в B, j в A: A ведёт при lag < 0
        lead_a = int(((lag > 0) & ab).sum() + ((lag < 0) & ba).sum())
        lead_b = int(((lag < 0) & ab).sum() + ((lag > 0) & ba).sum())
        tot = lead_a + lead_b
        leaders.append({"from": ga, "to": gb, "edges": int((ab | ba).sum()), "lagged": tot,
                        "share": lead_a / tot if tot else None,
                        "p_binomial": float(binomtest(lead_a, tot, 0.5).pvalue) if tot else None})
    res["leaders"] = leaders
    return res
