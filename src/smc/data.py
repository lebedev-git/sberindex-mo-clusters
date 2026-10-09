"""Загрузка данных СберИндекса и справочника МО в единую панель.

Панель — массив V[mo, month, category] средних безналичных расходов на жителя (руб.),
плюс таблица атрибутов МО (название, регион, тип, координаты центра, доступность рынков).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class Panel:
    ids: np.ndarray            # territory_id, порядок узлов везде одинаковый
    months: list[str]          # 'YYYY-MM'
    categories: list[str]      # пять категорий профиля
    total: np.ndarray          # [n, T] «Все категории»
    cats: np.ndarray           # [n, T, 5]
    meta: pd.DataFrame         # атрибуты МО, индекс = territory_id в порядке ids
    dropped: pd.DataFrame      # МО, исключённые из панели, с причиной


def load_reference(path: str, year: int) -> pd.DataFrame:
    """Одна строка на territory_id: версия, действующая в `year` (year_from <= year < year_to)."""
    ref = pd.read_excel(path)
    valid = ref[(ref.year_from <= year) & (ref.year_to > year)]
    # если версии в `year` нет (МО упразднено раньше), берём последнюю известную
    rest = ref[~ref.territory_id.isin(valid.territory_id)].sort_values("year_to").groupby("territory_id").tail(1)
    ref = pd.concat([valid, rest]).drop_duplicates("territory_id", keep="first")
    cols = {
        "municipal_district_name_short": "name",
        "municipal_district_name": "name_full",
        "municipal_district_type": "mo_type",
        "municipal_district_status": "mo_status",
        "region_name": "region",
        "region_code": "region_code",
        "oktmo": "oktmo",
        "municipal_district_center": "center",
        "municipal_district_center_lat": "lat",
        "municipal_district_center_lon": "lon",
    }
    return ref.set_index("territory_id")[list(cols)].rename(columns=cols)


def load_panel(cfg: dict) -> Panel:
    d = cfg["data"]
    raw = pd.read_parquet(d["consumption"])
    raw = raw.rename(columns={"value": "consumption"})  # в PDF поле названо consumption, в файле — value
    cats = list(d["categories"])
    total_name = d["total_category"]
    months = sorted(raw.date.unique())

    wide = raw.pivot_table(index="territory_id", columns=["category", "date"], values="consumption", aggfunc="first")
    need = [total_name] + cats
    full_cols = pd.MultiIndex.from_product([need, months])
    wide = wide.reindex(columns=full_cols)

    complete = wide.notna().all(axis=1) & (wide.fillna(1) > 0).all(axis=1)
    dropped = pd.DataFrame({"n_missing": wide.isna().sum(axis=1)})[~complete]
    dropped["reason"] = "неполный ряд (нет части месяцев или категорий)"
    if d.get("require_full_series", True):
        wide = wide[complete]

    ids = wide.index.to_numpy()
    total = wide[total_name].to_numpy(dtype=float)
    cat_arr = np.stack([wide[c].to_numpy(dtype=float) for c in cats], axis=2)

    meta = load_reference(d["reference_table"], d["reference_year"]).reindex(ids)
    ma = pd.read_parquet(d["market_access"]).set_index("territory_id")["market_access"]
    meta["market_access"] = ma.reindex(ids).to_numpy()
    meta.index.name = "territory_id"
    return Panel(ids=ids, months=months, categories=cats, total=total, cats=cat_arr, meta=meta, dropped=dropped)


def load_road_distances(cfg: dict, ids: np.ndarray) -> np.ndarray:
    """Симметричная матрица автодорожных расстояний (км) между узлами панели; inf — нет связи."""
    con = pd.read_parquet(cfg["data"]["connection"], filters=[("type", "==", cfg["graphs"]["road_type"])])
    pos = pd.Series(np.arange(len(ids)), index=ids)
    con = con[con.territory_id_x.isin(pos.index) & con.territory_id_y.isin(pos.index)]
    i = pos[con.territory_id_x].to_numpy()
    j = pos[con.territory_id_y].to_numpy()
    D = np.full((len(ids), len(ids)), np.inf)
    D[i, j] = con.distance.to_numpy()
    D[j, i] = con.distance.to_numpy()  # в файле расстояние дано в одну сторону
    np.fill_diagonal(D, 0.0)
    return D
