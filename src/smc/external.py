"""Внешняя проверка типов официальными российскими метками (data/external/ru_official_labels.csv).

Модель эти метки не видит. Если разбиение с ними связано, типы описывают реальные различия территорий.
Для бинарной метки — V Крамера с типами; для численности населения — η² логарифма.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .metrics import cramers_v, eta_squared

BINARY = {
    "arctic_any": "Арктическая зона",
    "far_north_or_equated": "Крайний Север и приравненные",
    "monotown": "Моногород (кат. 1–3)",
    "onp_agglomeration_core": "Ядро агломерации",
    "regional_capital": "Столица региона",
}


def load_labels(path: str, ids: np.ndarray) -> pd.DataFrame:
    L = pd.read_csv(path).set_index("territory_id").reindex(ids)
    L["monotown"] = L["monotown_min_category"].notna().astype(int)
    for c in BINARY:
        L[c] = L[c].fillna(0).astype(int)
    L["log_pop"] = np.log(L["pop_2024_rosstat"])
    return L


def official_validity(lab: np.ndarray, L: pd.DataFrame) -> dict:
    out = {f"V:{c}": cramers_v(lab, L[c].to_numpy()) for c in BINARY}
    out["eta2:log_pop"] = eta_squared(L["log_pop"].to_numpy(dtype=float), lab)
    out["external_mean"] = float(np.mean(list(out.values())))
    return out


def type_label_profile(lab: np.ndarray, L: pd.DataFrame) -> pd.DataFrame:
    g = pd.DataFrame({c: L[c].to_numpy() for c in BINARY}).groupby(lab).mean()
    g["pop_median"] = pd.Series(L["pop_2024_rosstat"].to_numpy()).groupby(lab).median()
    return g
