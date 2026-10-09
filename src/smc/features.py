"""Признаки МО (атрибуты узлов) и идиосинкратические ряды для правил рёбер.

Все величины считаются в логарифмах и центрируются медианой по стране в том же месяце,
поэтому признаки описывают относительное положение МО, а не общероссийский рост цен.

Блоки признаков за окно из L месяцев:
  level   — средний лог «Все категории» относительно медианы страны (1 признак);
  profile — средний центрированный лог-профиль пяти категорий (CLR) относительно страны (5);
  season  — сезонность сверх общероссийской: амплитуда, летний избыток всех трат
            и летний избыток общепита (3).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .data import Panel

FOOD_SERVICE = "Общественное питание"


@dataclass
class WindowFeatures:
    raw: pd.DataFrame          # признаки до масштабирования, индекс = territory_id
    blocks: dict[str, list[str]]
    series: np.ndarray         # [n, L, 6] идиосинкратические отклонения (5 категорий + итого)
    months: list[str]


def window_features(p: Panel, start: int, length: int, summer_months: list[int]) -> WindowFeatures:
    sl = slice(start, start + length)
    months = p.months[sl]
    logT = np.log(p.total[:, sl])                    # [n, L]
    logC = np.log(p.cats[:, sl, :])                  # [n, L, 5]

    relT = logT - np.median(logT, axis=0)            # минус медиана страны в каждом месяце
    clr = logC - logC.mean(axis=2, keepdims=True)    # центрированный лог-профиль
    relCLR = clr - np.median(clr, axis=0)

    level = relT.mean(axis=1)
    profile = relCLR.mean(axis=1)                    # [n, 5]

    # сезонность сверх общероссийской: отклонение от собственного среднего минус то же у страны
    e = relT - relT.mean(axis=1, keepdims=True)
    fs = p.categories.index(FOOD_SERVICE)
    relFS = logC[:, :, fs] - np.median(logC[:, :, fs], axis=0)
    e_fs = relFS - relFS.mean(axis=1, keepdims=True)
    summer = np.array([int(m[5:7]) in summer_months for m in months])
    season_amp = e.std(axis=1)
    summer_all = e[:, summer].mean(axis=1)
    summer_fs = e_fs[:, summer].mean(axis=1)

    cols_profile = [f"profile:{c}" for c in p.categories]
    raw = pd.DataFrame(
        np.column_stack([level, profile, season_amp, summer_all, summer_fs]),
        index=pd.Index(p.ids, name="territory_id"),
        columns=["level"] + cols_profile + ["season_amp", "summer_all", "summer_food_service"],
    )
    blocks = {"level": ["level"], "profile": cols_profile, "season": ["season_amp", "summer_all", "summer_food_service"]}

    # ряды для корреляций и DTW: отклонение от страны и от собственного среднего, по каналам
    relC = logC - np.median(logC, axis=0)
    chans = np.concatenate([relC, relT[:, :, None]], axis=2)
    chans = chans - chans.mean(axis=1, keepdims=True)
    return WindowFeatures(raw=raw, blocks=blocks, series=chans, months=months)


@dataclass
class Scaler:
    center: pd.Series
    scale: pd.Series
    weights: pd.Series         # итоговый множитель признака: вес блока / sqrt(размер блока)

    def transform(self, raw: pd.DataFrame) -> np.ndarray:
        z = (raw - self.center) / self.scale
        return (z * self.weights).to_numpy()


def fit_scaler(base: WindowFeatures, block_weights: dict[str, float]) -> Scaler:
    """Робастное масштабирование (медиана/IQR), фиксируется по базовому окну и переиспользуется."""
    raw = base.raw
    q1, q3 = raw.quantile(0.25), raw.quantile(0.75)
    iqr = (q3 - q1).where(lambda s: s > 1e-12, raw.std() + 1e-12)
    w = {}
    for b, cols in base.blocks.items():
        for c in cols:
            w[c] = block_weights[b] / np.sqrt(len(cols))
    return Scaler(center=raw.median(), scale=iqr, weights=pd.Series(w)[raw.columns])


def window_starts(n_months: int, length: int, step: int) -> list[int]:
    return list(range(0, n_months - length + 1, step))
