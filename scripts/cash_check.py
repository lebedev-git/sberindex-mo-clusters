"""Проверка гипотезы о маркетплейсах: доля онлайна среди *безналичных* трат выше там, где больше платят наличными.

    python scripts/cash_check.py      # после run.py, секунды

Внешние данные — доля безналичных платежей по регионам за I полугодие 2025 г. (Центр финансовой аналитики Сбербанка
и «Платформа ОФД», «Безнал взял оборот», https://platformaofd.ru/pdf/beznal-cfa-sber-platformaofd.pdf, стр. 10):
интервалы снесены с карты исследования, точные проценты — из таблицы того же слайда (data/external/cashless_share_regions_2025.csv).
Чтобы не сравнивать разные уклады, сравнение идёт внутри каждого типа: ранговая корреляция интервала с долей маркетплейсов.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
from scipy.stats import spearmanr

ROOT = Path(__file__).resolve().parents[1]
sys.stdout.reconfigure(encoding="utf-8")
ORDER = ["<75", "75-81", "82-88", ">=89"]


def load() -> pd.DataFrame:
    mo = pd.DataFrame(json.load(open(ROOT / "site" / "data" / "mo.json", encoding="utf-8")))
    types = {t["id"]: t.get("short", t["name"]) for t in json.load(open(ROOT / "site" / "data" / "types.json", encoding="utf-8"))}
    bins = pd.read_csv(ROOT / "data" / "external" / "cashless_share_regions_2025.csv").set_index("region").cashless_share_bin_1h2025
    d = mo[mo.status == "ok"].copy()
    d["cash_bin"] = d.region.map(bins)
    d["bin"] = d.cash_bin.map({b: i for i, b in enumerate(ORDER)})
    d["marketplaces"] = d.shares.map(lambda s: s[4])
    d["type"] = d.type.map(types)
    return d


def main() -> dict:
    d = load()
    assert d.cash_bin.notna().all(), f"нет интервала для регионов: {sorted(d[d.cash_bin.isna()].region.unique())}"
    tab = d.groupby(["type", "cash_bin"]).marketplaces.agg(["median", "size"]).unstack().reindex(columns=ORDER, level=1)
    print("Медиана доли маркетплейсов, % (число МО) — по типу и доле безнала в регионе:")
    for t, row in tab.iterrows():
        print(f"  {t:<20}" + "".join(f"{b:>7}: {row[('median', b)] * 100:5.1f} ({int(row[('size', b)])})" if pd.notna(row[("median", b)]) else f"{b:>7}:   —     " for b in ORDER))
    d["mp_rank"] = d.groupby("type").marketplaces.rank(pct=True)
    d["spend_rank"] = d.groupby("type").spend.rank(pct=True)
    out = {"rho_marketplaces": spearmanr(d.bin, d.mp_rank).statistic, "rho_spend": spearmanr(d.bin, d.spend_rank).statistic,
           "p_marketplaces": spearmanr(d.bin, d.mp_rank).pvalue,
           "by_type": {t: spearmanr(g.bin, g.marketplaces).statistic for t, g in d.groupby("type") if g.bin.nunique() > 1}}
    print(f"\nВнутри типов: ρ(доля безнала в регионе, доля маркетплейсов) = {out['rho_marketplaces']:+.2f} (p = {out['p_marketplaces']:.0e}); "
          f"ρ(доля безнала, траты на жителя) = {out['rho_spend']:+.2f}")
    print("По типам: " + "; ".join(f"{t} {r:+.2f}" for t, r in out["by_type"].items()))
    return out


if __name__ == "__main__":
    main()
