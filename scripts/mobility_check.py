"""Покупательская мобильность СберИндекса (СЗФО) против типов: проверка, не признак.

    python scripts/mobility_check.py      # после run.py; results/mobility_check.json

Набор «Индекс мобильности» (data/external/sberindex_mobility_szfo.csv) — среднее расстояние покупок, км, для 297 МО
Северо-Западного федерального округа за два периода. Названия МО сопоставляются с полным названием из справочника
СберИндекса внутри СЗФО; берутся только однозначные совпадения. Модель эти данные не видела.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from smc.data import load_reference  # noqa: E402
from smc.metrics import eta_squared  # noqa: E402

SZFO = ["Архангельская область", "Вологодская область", "Калининградская область", "Ленинградская область",
        "Мурманская область", "Новгородская область", "Псковская область", "Республика Карелия", "Республика Коми",
        "Ненецкий автономный округ", "Санкт-Петербург"]


def norm(s: pd.Series) -> pd.Series:
    return s.str.replace(r"\s+", " ", regex=True).str.strip().str.lower()


def main() -> None:
    cfg = yaml.safe_load(open(ROOT / "configs" / "default.yaml", encoding="utf-8"))
    ref = load_reference(str(ROOT / cfg["data"]["reference_table"]), cfg["data"]["reference_year"])
    ref = ref[ref.region.isin(SZFO)]
    key = norm(ref.name_full)
    uniq = key[~key.duplicated(keep=False)]
    m = pd.read_csv(ROOT / "data" / "external" / "sberindex_mobility_szfo.csv", sep=";")
    m["key"] = norm(m.ref_area)
    tid = pd.Series(uniq.index, index=uniq.to_numpy())
    m["territory_id"] = m.key.map(tid)
    a = pd.read_csv(ROOT / "results" / "assignments.csv").set_index("territory_id")
    types = json.load(open(ROOT / "site" / "data" / "types.json", encoding="utf-8"))
    out = {"source": "СберИндекс, «Индекс мобильности», СЗФО", "areas": int(m.ref_area.nunique()),
           "matched_names": int(m.drop_duplicates("ref_area").territory_id.notna().sum()), "periods": {}}
    for per, g in m.groupby("period"):
        g = g.dropna(subset=["territory_id"])
        g = g[g.territory_id.isin(a.index)]
        lab = a.loc[g.territory_id, "type_main"].to_numpy()
        lmac = a.loc[g.territory_id, "macro_type"].to_numpy()
        v = np.log(g.value.to_numpy(dtype=float))
        med = pd.Series(g.value.to_numpy()).groupby(lab).agg(["median", "size"])
        spb = (a.loc[g.territory_id, "region"] == "Санкт-Петербург").to_numpy()   # 111 округов Петербурга — почти весь «столичный» тип СЗФО
        out["periods"][per] = {"n": int(len(g)), "eta2_log": eta_squared(v, lab), "eta2_log_macro": eta_squared(v, lmac),
                               "n_without_spb": int((~spb).sum()), "eta2_log_without_spb": eta_squared(v[~spb], lab[~spb]),
                               "types": [{"type": int(t), "median_km": float(r["median"]), "n": int(r["size"])} for t, r in med.iterrows()]}
    last = max(out["periods"])
    out["main_period"] = last
    out["n_types_present"] = len(out["periods"][last]["types"])
    names = {t["id"]: t["short"] for t in types}
    out["note"] = ("Типы в СЗФО представлены неравномерно: " + ", ".join(f"{names[t['type']]} — {t['n']}" for t in out["periods"][last]["types"])
                   + ". Проверка охватывает один федеральный округ и два периода, поэтому годится только как иллюстрация.")
    json.dump(out, open(ROOT / "results" / "mobility_check.json", "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(json.dumps(out, ensure_ascii=False, indent=1))
    from smc.export_web import export_v2
    export_v2(ROOT / "results", ROOT / "site" / "data")   # сводка для лендинга (site/data/v2.json)


if __name__ == "__main__":
    main()
