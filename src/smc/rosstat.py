"""Внешняя проверка типов данными Росстата о рынке труда (БД ПМО в обработке «Если быть точным», CC BY 4.0).

Годовые зарплата и численность работников организаций (без субъектов малого предпринимательства) по
разделам ОКВЭД2 публикуются с лагом и не помесячно, поэтому в признаки модели не входят: только проверка
и интерпретация. Извлечение — scripts/download_data.py --only rosstat -> data/external/rosstat_bdpmo_2023_2024.csv.

Сопоставление по ОКТМО (8 знаков): сначала по коду записи, затем по «устойчивому» коду каталога (oktmo_stable),
который сводит прежние районы к нынешним округам. Если на один код МО приходится несколько записей,
численность суммируется, зарплата усредняется с весами численности.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.metrics import adjusted_rand_score, normalized_mutual_info_score
from sklearn.preprocessing import StandardScaler

from .metrics import eta_squared

GROUPS = {"ind": ["B", "C", "D", "E"], "agr": ["A"], "min": ["B"], "pub": ["O", "P", "Q"], "trade": ["G"]}
GROUP_NAMES = {"ind": "промышленность (B–E)", "agr": "сельское хозяйство (A)", "min": "добыча (B)",
               "pub": "бюджетная сфера (O+P+Q)", "trade": "торговля (G)"}


def _agg(g: pd.DataFrame) -> pd.Series:
    emp = g.filter(like="emp_").sum(min_count=1)
    w = g.emp_total.fillna(0).to_numpy()
    wage = np.average(g.wage_total, weights=w) if g.wage_total.notna().all() and w.sum() > 0 else g.wage_total.mean()
    return pd.concat([pd.Series({"wage_total": wage}), emp])


def match(path: str, oktmo: pd.Series, year: int) -> pd.DataFrame:
    """Строки = МО в порядке oktmo (формат «79-701-000-000» или 8/11 цифр); столбцы — wage, emp_*, доли групп."""
    d = pd.read_csv(path, dtype={"oktmo": str, "oktmo_stable": str})
    d = d[d.year == year]
    ok8 = oktmo.astype(str).str.replace(r"\D", "", regex=True).str[:8]
    by_code = d.groupby("oktmo").apply(_agg, include_groups=False)
    by_stable = d.groupby("oktmo_stable").apply(_agg, include_groups=False)
    out = by_code.reindex(ok8.to_numpy())
    miss = out.wage_total.isna() & out.emp_total.isna()
    out.loc[miss.to_numpy()] = by_stable.reindex(ok8[miss.to_numpy()].to_numpy()).to_numpy()
    out.index = oktmo.index
    tot = out.emp_total
    for g, secs in GROUPS.items():
        # раздел без значения — нет крупных и средних организаций или данные скрыты: считаем 0
        out[g] = out[[f"emp_{s}" for s in secs]].fillna(0).sum(1) / tot.where(tot > 0)
    out["matched"] = out.wage_total.notna()
    return out


def validate(lab: np.ndarray, macro: np.ndarray, R: pd.DataFrame, seed: int, k_lens: int) -> tuple[dict, pd.DataFrame]:
    ok = R.matched.to_numpy() & R[list(GROUPS)].notna().all(1).to_numpy()
    lw = np.log(R.wage_total.to_numpy(dtype=float))
    res = {"coverage": int(R.matched.sum()), "coverage_full": int(ok.sum()),
           "eta2": {"log_wage": eta_squared(lw[R.matched.to_numpy()], lab[R.matched.to_numpy()])}
           | {g: eta_squared(R[g].to_numpy(dtype=float)[ok], lab[ok]) for g in GROUPS},
           "eta2_macro": {"log_wage": eta_squared(lw[R.matched.to_numpy()], macro[R.matched.to_numpy()])}
           | {g: eta_squared(R[g].to_numpy(dtype=float)[ok], macro[ok]) for g in GROUPS}}
    # «вторая линза»: типология только по рынку труда (k-means на долях занятости и лог-зарплате)
    F = StandardScaler().fit_transform(np.column_stack([R.loc[ok, list(GROUPS)].to_numpy(dtype=float), lw[ok]]))
    lens = KMeans(k_lens, n_init=20, random_state=seed).fit_predict(F)
    res["lens"] = {"k": k_lens, "n": int(ok.sum()), "ari": float(adjusted_rand_score(lab[ok], lens)),
                   "nmi": float(normalized_mutual_info_score(lab[ok], lens)),
                   "ari_macro": float(adjusted_rand_score(macro[ok], lens)),
                   "nmi_macro": float(normalized_mutual_info_score(macro[ok], lens))}
    tab = pd.DataFrame({"type": lab, "wage": R.wage_total.to_numpy(dtype=float), **{g: R[g].to_numpy(dtype=float) for g in GROUPS}})
    types = tab.groupby("type").median().join(tab.groupby("type").wage.count().rename("n_matched"))
    return res, types
