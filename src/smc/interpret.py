"""Профили типов в исходных единицах: рубли на жителя, доли категорий, сезонность, география."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .data import Panel


def unit_table(p: Panel, months: slice = slice(None)) -> pd.DataFrame:
    """Показатели МО в понятных единицах за период: средние траты и доли категорий в «Все категории»."""
    tot = p.total[:, months].mean(1)
    cats = p.cats[:, months, :].mean(1)
    t = pd.DataFrame({"spend_total": tot}, index=pd.Index(p.ids, name="territory_id"))
    for j, c in enumerate(p.categories):
        t[f"share:{c}"] = cats[:, j] / tot
    t["share:Прочее"] = 1 - cats.sum(1) / tot
    return t


MIRKIN_FEATURES = {
    "spend_total": "Траты на жителя",
    "share:Продовольствие": "Продукты", "share:Здоровье": "Здоровье", "share:Общественное питание": "Общепит",
    "share:Транспорт": "Транспорт", "share:Маркетплейсы": "Маркетплейсы", "share:Прочее": "Прочее",
    "season_amp": "Сезонность", "market_access": "Доступность рынков",
}


def mirkin_deviations(u: pd.DataFrame, lab: np.ndarray) -> pd.DataFrame:
    """Правило интерпретации Миркина: d_kv = (c_kv - g_v) / g_v — относительное отклонение среднего
    типа от среднего по всем МО в исходных (нестандартизованных) единицах. Характерные признаки
    типа — с наибольшим |d_kv|. Применяем только к положительным признакам, где деление осмысленно."""
    cols = [c for c in MIRKIN_FEATURES if c in u]
    g = u[cols].mean()
    c = u[cols].groupby(lab).mean()
    return (c - g) / g


def cluster_profiles(p: Panel, raw: pd.DataFrame, X: np.ndarray, lab: np.ndarray, months: slice = slice(None)) -> pd.DataFrame:
    u = unit_table(p, months).join(raw[["summer_all", "summer_food_service", "season_amp"]])
    u["market_access"] = p.meta.market_access.to_numpy()
    mk = mirkin_deviations(u, lab)
    u["cluster"] = lab
    prof = u.groupby("cluster").median()
    prof.insert(0, "size", u.groupby("cluster").size())
    kinds = pd.crosstab(lab, p.meta.mo_type.to_numpy(), normalize="index")
    prof = prof.join(kinds.add_prefix("kind:"))
    # медоиды: МО, ближайшие к центру типа в пространстве признаков
    names = (p.meta.name + " (" + p.meta.region + ")").to_numpy()
    med, med_ids = {}, {}
    for c in np.unique(lab):
        idx = np.where(lab == c)[0]
        d = np.linalg.norm(X[idx] - X[idx].mean(0), axis=1)
        top = idx[np.argsort(d)[:5]]
        med[c] = "; ".join(names[top])
        med_ids[c] = " ".join(str(int(t)) for t in p.ids[top])
    prof["typical"] = pd.Series(med)
    prof["typical_ids"] = pd.Series(med_ids)
    reg = p.meta.region.to_numpy()
    top_regions = {c: ", ".join(pd.Series(reg[lab == c]).value_counts().head(4).index) for c in np.unique(lab)}
    prof["top_regions"] = pd.Series(top_regions)
    prof = prof.join(mk.add_prefix("mirkin:"))
    prof["mirkin_top"] = pd.Series({
        c: "; ".join(f"{MIRKIN_FEATURES[f]} {v:+.0%}" for f, v in mk.loc[c].reindex(mk.loc[c].abs().sort_values(ascending=False).index).head(3).items())
        for c in mk.index})
    return prof
