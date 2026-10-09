"""Проверка на США: восстанавливает ли кластеризация карточных трат официальные типы экономик?

    python scripts/us_check.py        # данные -> data/raw/us/, итог -> results/us_check.json

Метки: USDA ERS County Typology Codes 2025, `Industry_Dependence_2025` (фермерские, добывающие,
обрабатывающие, государственные, рекреационные, неспециализированные — пороговые правила по доле
отрасли в заработках и занятости). Траты: Opportunity Insights EconomicTracker, `Affinity - County - Monthly`
(только общий индекс трат к январю 2020, без категорий и уровней; Chetty et al., QJE 2024).
"""
from __future__ import annotations

import json
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import adjusted_rand_score, balanced_accuracy_score, normalized_mutual_info_score, roc_auc_score
from sklearn.model_selection import StratifiedKFold, cross_val_predict
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "us"
OI = "https://raw.githubusercontent.com/OpportunityInsights/EconomicTracker/main/data/Affinity%20-%20County%20-%20Monthly.csv"
ERS = "https://www.ers.usda.gov/media/6174/ers-county-typology-codes-2025-edition.csv"
CLASSES = {0: "неспециализированные", 1: "фермерские", 2: "добывающие", 3: "обрабатывающие", 4: "государственные", 5: "рекреационные"}


def get(url: str, name: str) -> Path:
    RAW.mkdir(parents=True, exist_ok=True)
    f = RAW / name
    if not f.exists():
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        f.write_bytes(urllib.request.urlopen(req, timeout=300).read())
    return f


def features(oi: pd.DataFrame) -> pd.DataFrame:
    oi["t"] = pd.to_datetime(dict(year=oi.year, month=oi.month, day=1))
    sa = oi.pivot(index="fips", columns="t", values="spend_all")
    ns = oi.pivot(index="fips", columns="t", values="spend_s_all")

    def win(df, a, b):
        return df.loc[:, (df.columns >= a) & (df.columns <= b)]

    F = pd.DataFrame(index=sa.index)
    F["trough_2020"] = win(sa, "2020-03-01", "2020-06-01").min(axis=1)
    F["rebound_H2_2020"] = win(sa, "2020-07-01", "2020-12-01").mean(axis=1)
    F["peak_2021"] = win(sa, "2021-01-01", "2021-12-01").max(axis=1)
    F["level_2023_24"] = win(sa, "2023-01-01", "2024-12-01").mean(axis=1)
    F["growth_2023_25"] = win(sa, "2025-01-01", "2025-12-01").mean(axis=1) - win(sa, "2023-01-01", "2023-12-01").mean(axis=1)
    F["volatility"] = win(sa.diff(axis=1), "2022-01-01", "2026-06-01").std(axis=1)
    ratio = (1 + ns) / (1 + sa)  # сезонный фактор округа
    prof = pd.DataFrame({m: ratio[[c for c in sa.columns if c.month == m and 2021 <= c.year <= 2025]].mean(axis=1) for m in range(1, 13)})
    F["seas_amp"] = prof.max(axis=1) - prof.min(axis=1)
    F["seas_summer_minus_winter"] = prof[[6, 7, 8]].mean(axis=1) - prof[[12, 1, 2]].mean(axis=1)
    F["seas_dec_peak"] = prof[12] - prof[[9, 10, 11]].mean(axis=1)
    return F


def main() -> None:
    oi = pd.read_csv(get(OI, "affinity_county_monthly.csv"))
    oi["fips"] = oi.countyfips.astype(int).astype(str).str.zfill(5)
    ers = pd.read_csv(get(ERS, "ers_county_typology_2025.csv"), dtype={"FIPStxt": str}, encoding="utf-8-sig")
    w = ers.pivot_table(index="FIPStxt", columns="Attribute", values="Value", aggfunc="first")
    D = features(oi).join(w["Industry_Dependence_2025"].astype(float).rename("cls"), how="inner").dropna()
    D = D[D.cls.isin(CLASSES)]
    y = D.cls.astype(int).to_numpy()
    X = StandardScaler().fit_transform(D.drop(columns="cls"))
    km = KMeans(6, n_init=20, random_state=0).fit_predict(X)
    cv = StratifiedKFold(5, shuffle=True, random_state=0)
    rf = RandomForestClassifier(n_estimators=300, class_weight="balanced", random_state=0, min_samples_leaf=3)
    pred = cross_val_predict(rf, X, y, cv=cv)
    auc = {}
    for c, name in CLASSES.items():
        if c == 0:
            continue
        yy = (y == c).astype(int)
        pr = cross_val_predict(rf, X, yy, cv=cv, method="predict_proba")[:, 1]
        auc[name] = float(roc_auc_score(yy, pr))
    res = {"counties": int(len(D)), "class_counts": {CLASSES[k]: int(v) for k, v in pd.Series(y).value_counts().sort_index().items()},
           "kmeans6_ARI": float(adjusted_rand_score(y, km)), "kmeans6_NMI": float(normalized_mutual_info_score(y, km)),
           "rf_balanced_accuracy": float(balanced_accuracy_score(y, pred)), "chance": 1 / 6, "auc_one_vs_rest": auc}
    out = ROOT / "results" / "us_check.json"
    out.write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(res, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
