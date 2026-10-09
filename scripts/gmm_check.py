"""Гауссова смесь (GMM) как шестой метод сравнения: меняет ли она выбор правилом Коупленда.

    python scripts/gmm_check.py      # после run.py; results/gmm_check.csv, results/gmm_check.json

GMM (sklearn GaussianMixture, полные ковариации, seed из конфигурации) — модельная кластеризация признаков
без сети, с мягкой принадлежностью. Для k = 4…12 считаются те же индексы и устойчивость на подвыборках,
что и для пяти методов конвейера; строки добавляются к results/methods_icvi.csv и голосование Коупленда
повторяется на 54 конфигурациях. Итоговая типология от этого не меняется: проверяется только, остаётся ли
победитель прежним.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import yaml
from sklearn.mixture import GaussianMixture

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import os  # noqa: E402

os.chdir(ROOT)
from smc import aggregation as AG  # noqa: E402
from smc import external as E  # noqa: E402
from smc import graphs as G  # noqa: E402
from smc import metrics as M  # noqa: E402
from smc.data import load_panel  # noqa: E402
from smc.features import fit_scaler, window_features  # noqa: E402


def gmm(X: np.ndarray, k: int, seed: int, cov: str, n_init: int) -> np.ndarray:
    return GaussianMixture(k, covariance_type=cov, n_init=n_init, random_state=seed).fit(X).predict(X)


def main() -> None:
    cfg = yaml.safe_load(open("configs/default.yaml", encoding="utf-8"))
    seed, cl, gc = cfg["seed"], cfg["clustering"], cfg["gmm"]
    p = load_panel(cfg)
    n, T = p.total.shape
    full = window_features(p, 0, T, cfg["features"]["summer_months"])
    X = fit_scaler(full, cfg["features"]["block_weights"]).transform(full.raw)
    A = G.build_graph(cfg["graphs"]["main_rule"], series=full.series, k=cfg["graphs"]["k"])
    Lab = E.load_labels(cfg["data"]["external_labels"], p.ids)
    rows = []
    for k in cl["k_range"]:
        lab = gmm(X, k, seed, gc["covariance"], gc["n_init"])
        r = {"method": "gmm", "k": k, "min_size": int(np.bincount(lab, minlength=k).min())} | M.icvi(X, A, lab)
        r["stability_ARI"] = M.bootstrap_ari(lambda idx, k=k: gmm(X[idx], k, seed, gc["covariance"], 1),
                                             n, cl["bootstrap"], cl["bootstrap_frac"], seed)
        rows.append(r | E.official_validity(lab, Lab))
        print(f"gmm k={k}: SW={r['SW']:.3f} устойчивость={r['stability_ARI']:.3f}", flush=True)
    g = pd.DataFrame(rows).set_index(["method", "k"])
    comp = pd.read_csv("results/methods_icvi.csv").set_index(["method", "k"]).drop(columns="copeland")
    allc = pd.concat([comp, g])
    dirs = {m: M.DIRECTIONS[m] for m in ("SW", "CH", "S_Dbw", "MQ", "AVI", "AVU", "stability_ARI")}
    el = allc[allc.min_size >= 0.01 * n]
    cop = AG.copeland(el, dirs)
    allc["copeland_with_gmm"] = cop.reindex(allc.index)
    allc.loc["gmm"].to_csv("results/gmm_check.csv")
    win = cop.idxmax()
    best_gmm = cop.xs("gmm", level="method")
    res = {"covariance": gc["covariance"], "candidates": int(len(el)), "gmm_eligible": int(len(best_gmm)),
           "winner_with_gmm": [str(win[0]), int(win[1])], "winner_unchanged": [str(win[0]), int(win[1])] == ["kefrin", cfg["final"]["macro_k"]],
           "best_gmm_k": int(best_gmm.idxmax()) if len(best_gmm) else None,
           "best_gmm_rank": int((cop > best_gmm.max()).sum() + 1) if len(best_gmm) else None,
           "best_gmm_copeland": float(best_gmm.max()) if len(best_gmm) else None,
           "final_copeland_with_gmm": float(cop.loc[("kefrin", cfg["final"]["macro_k"])])}
    json.dump(res, open("results/gmm_check.json", "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(json.dumps(res, ensure_ascii=False))
    from smc.export_web import export_v2
    export_v2(ROOT / "results", ROOT / "site" / "data")   # сводка для лендинга (site/data/v2.json)


if __name__ == "__main__":
    main()
