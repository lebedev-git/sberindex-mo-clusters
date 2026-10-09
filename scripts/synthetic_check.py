"""Синтетическая проверка методов на сетях с признаками с известным разбиением.

    python scripts/synthetic_check.py      # ≈ 1–3 мин; results/synthetic.csv, results/synthetic_summary.json

Атрибутированная стохастическая блочная модель: N узлов, K равных групп. Признаки — гауссова смесь в
d измерениях, центры групп на расстоянии, задающем силу сигнала в признаках. Сеть — блочная модель
со средней степенью как у основной сети и отношением p_in / p_out, задающим силу сигнала в сети.
Сетка «сигнал в признаках × сигнал в сети» 3 × 3, методы — те же реализации, что в конвейере:
k-means (только признаки), Leiden (только сеть), спектральный (смесь kNN-сходства признаков и сети),
KEFRiN с долей сети из конфигурации. В средней ячейке — развёртка доли сети KEFRiN 0…0,8.
Качество — ARI с истинным разбиением, среднее по повторам.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import scipy.sparse as sp
import yaml
from sklearn.metrics import adjusted_rand_score

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from smc import clustering as C  # noqa: E402
from smc import graphs as G  # noqa: E402

LEVELS = ["слабый", "средний", "сильный"]


def sbm(y: np.ndarray, deg: float, ratio: float, rng) -> sp.csr_matrix:
    """Неориентированная блочная модель: p_in / p_out = ratio, средняя степень deg."""
    n, K = len(y), y.max() + 1
    p_out = deg / (n / K * ratio + n * (K - 1) / K)
    p_in = ratio * p_out
    P = np.where(y[:, None] == y[None, :], p_in, p_out)
    U = np.triu(rng.random((n, n)) < P, 1)
    A = sp.csr_matrix(U.astype(float))
    return (A + A.T).tocsr()


def features(y: np.ndarray, d: int, sep: float, rng) -> np.ndarray:
    K = y.max() + 1
    M = rng.normal(size=(K, d))
    M = M / np.linalg.norm(M, axis=1, keepdims=True) * sep    # центры на сфере радиуса sep
    return M[y] + rng.normal(size=(len(y), d))


def methods(X, A, K, share, seed, cl):
    A_attr = G.build_graph("attr", X=X, k=15)
    return {"k-means": C.kmeans(X, K, seed, 10),
            "Leiden": C.leiden_k(A, K, seed)[0],
            "Спектральный": C.spectral(A, A_attr, K, cl["spectral_alpha"], seed),
            "KEFRiN": C.kefrin(X, A, K, seed, share, 10)}


def main() -> None:
    cfg = yaml.safe_load(open(ROOT / "configs" / "default.yaml", encoding="utf-8"))
    sc, cl = cfg["synthetic"], cfg["clustering"]
    share = cl["kefrin_net_share"]
    t0 = time.time()
    rows, sweep = [], []
    for rep in range(sc["reps"]):
        rng = np.random.default_rng(cfg["seed"] + rep)
        y = np.repeat(np.arange(sc["K"]), sc["N"] // sc["K"])
        for ai, sep in enumerate(sc["attr_sep"]):
            X = features(y, sc["d"], sep, rng)
            for ni, ratio in enumerate(sc["net_ratio"]):
                A = sbm(y, sc["degree"], ratio, rng)
                for m, lab in methods(X, A, sc["K"], share, cfg["seed"], cl).items():
                    rows.append({"rep": rep, "attr": LEVELS[ai], "net": LEVELS[ni], "attr_sep": sep, "net_ratio": ratio,
                                 "method": m, "ari": adjusted_rand_score(y, lab)})
                if ai == 1 and ni == 1:
                    for s in sc["share_grid"]:
                        sweep.append({"rep": rep, "share": s, "ari": adjusted_rand_score(y, C.kefrin(X, A, sc["K"], cfg["seed"], s, 10))})
        print(f"повтор {rep + 1}: {time.time() - t0:.0f} с", flush=True)
    R = pd.DataFrame(rows)
    R.to_csv(ROOT / "results" / "synthetic.csv", index=False)
    cell = R.groupby(["attr", "net", "method"], sort=False).ari.mean().reset_index()
    best = cell.loc[cell.groupby(["attr", "net"], sort=False).ari.idxmax()]
    kef = cell[cell.method == "KEFRiN"].set_index(["attr", "net"]).ari
    others = cell[cell.method != "KEFRiN"].groupby(["attr", "net"], sort=False).ari.max()
    sw = pd.DataFrame(sweep).groupby("share").ari.mean()
    summary = {
        "N": sc["N"], "K": sc["K"], "reps": sc["reps"], "kefrin_share": share, "tie_tol": sc["tie_tol"],
        "cells": len(kef), "kefrin_best_or_tied": int((kef >= others - sc["tie_tol"]).sum()),
        "kefrin_beats_kmeans": int((kef > cell[cell.method == "k-means"].set_index(["attr", "net"]).ari + sc["tie_tol"]).sum()),
        "kefrin_beats_leiden": int((kef > cell[cell.method == "Leiden"].set_index(["attr", "net"]).ari + sc["tie_tol"]).sum()),
        "mean_ari": cell.groupby("method", sort=False).ari.mean().to_dict(),
        "best_by_cell": [{"attr": r.attr, "net": r.net, "method": r.method, "ari": r.ari} for r in best.itertuples()],
        "rows": [{"attr": r.attr, "net": r.net, "method": r.method, "ari": r.ari} for r in cell.itertuples()],
        "share_sweep": [{"share": float(s), "ari": float(a)} for s, a in sw.items()],
        "share_best": float(sw.idxmax()), "share_config_ari": float(sw.get(share, np.nan)),
        "share_config_gap_to_best": float(sw.max() - sw.get(share, np.nan)),
        "seconds": round(time.time() - t0, 1),
    }
    json.dump(summary, open(ROOT / "results" / "synthetic_summary.json", "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(json.dumps({k: v for k, v in summary.items() if k not in ("rows", "best_by_cell")}, ensure_ascii=False, indent=1))
    from smc.export_web import export_v2
    export_v2(ROOT / "results", ROOT / "site" / "data")   # сводка для лендинга (site/data/v2.json)


if __name__ == "__main__":
    main()
