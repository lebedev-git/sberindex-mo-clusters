"""Почему окна динамики стартуют от основной типологии («якорь»), а не от предыдущего окна.

    python scripts/anchor_check.py     # после run.py, ≈1 мин

Для каждого из 13 окон строится своя сеть и разбиение KEFRiN с тёплым стартом: (а) от центров основной
типологии, как в run.py; (б) от разбиения предыдущего окна (цепочка). Печатается сходство типов окна с основными
(средний Жаккар после сопоставления номеров): при цепочке ошибки окон накапливаются, при якоре — нет.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from smc import clustering as C  # noqa: E402
from smc import dynamics as D  # noqa: E402
from smc import graphs as G  # noqa: E402
from smc.data import load_panel  # noqa: E402
from smc.features import fit_scaler, window_features, window_starts  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
cfg = yaml.safe_load(open(ROOT / "configs" / "default.yaml", encoding="utf-8"))
p = load_panel(cfg)
sm, k_nn, rule = cfg["features"]["summer_months"], cfg["graphs"]["k"], cfg["graphs"]["main_rule"]
full = window_features(p, 0, p.total.shape[1], sm)
scaler = fit_scaler(full, cfg["features"]["block_weights"])
X = scaler.transform(full.raw)
main = pd.read_csv(ROOT / "results" / "assignments.csv", index_col="territory_id").reindex(p.ids).type_main.to_numpy()
k = cfg["final"]["k"]
rho = C.rho_for_share(X, C.kefrin_network_block(G.build_graph(rule, series=full.series, k=k_nn)), cfg["clustering"]["kefrin_net_share"])
L = cfg["windows"]["length"]
spaces = []
for s in window_starts(p.total.shape[1], L, cfg["windows"]["step"]):
    wf = window_features(p, s, L, sm)
    spaces.append((wf.months[-1], D.kefrin_space(scaler.transform(wf.raw), G.build_graph(rule, series=wf.series, k=k_nn), rho)))

res = {}
for mode in ("якорь", "цепочка"):
    prev, out = main, []
    for end, Z in spaces:
        start = main if mode == "якорь" else prev
        if np.bincount(start, minlength=k).min() == 0:  # пустой тип в цепочке — дальше не продолжить
            out.append(np.nan)
            continue
        lab, _ = D.warm_kmeans(Z, start, k)
        lab, jac = D.match_to_reference(main, lab, k)
        out.append(float(jac.mean()))
        prev = lab
    res[mode] = out
df = pd.DataFrame(res, index=[e for e, _ in spaces]).round(3)
print(df.to_string())
print(f"\nпоследнее окно: якорь {df['якорь'].iloc[-1]:.2f}, цепочка {df['цепочка'].iloc[-1]:.2f}; "
      f"минимум: якорь {df['якорь'].min():.2f}, цепочка {df['цепочка'].min():.2f}")
