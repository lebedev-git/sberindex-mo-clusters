"""Реестр утверждений: каждое число и сравнение из отчёта, README и лендинга проверяется по результатам конвейера.

    python scripts/check_claims.py            # после run.py; код выхода 1, если хоть одно утверждение разошлось с данными

Утверждение = (что сказано, где сказано, проверка). Проверка пересчитывает значение из results/ и site/data/
и сравнивает с текстом с учётом округления. Поле «где» дополнительно сверяет, что одинаковое число стоит во всех
документах, где оно упомянуто: текст и данные не расходятся тихо при пересчёте или правке формулировок.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
R, S = ROOT / "results", ROOT / "site" / "data"
sys.stdout.reconfigure(encoding="utf-8")

load = lambda p: json.load(open(p, encoding="utf-8"))  # noqa: E731
types, macro, mo, meta = load(S / "types.json"), load(S / "macro.json"), load(S / "mo.json"), load(S / "meta.json")
series = load(S / "series.json")
fin, ext, just = load(R / "final_icvi.json"), load(R / "external_validation.json"), load(R / "justification.json")
sel, asym, us = load(R / "selection.json"), load(R / "dynamics_asymmetry.json"), load(R / "us_check.json")
methods = pd.read_csv(R / "methods_icvi.csv").set_index(["method", "k"])
ws = pd.read_csv(R / "weights_sensitivity.csv")
a = pd.read_csv(R / "assignments.csv")
ok = [m for m in mo if m["status"] == "ok"]
T = {t["short"]: t for t in types}
M = {m["name"]: m for m in macro}
CAT = ["Продукты", "Здоровье", "Общепит", "Транспорт", "Маркетплейсы"]
nat_share = {c: float(np.median([m["shares"][j] for m in ok])) for j, c in enumerate(CAT)}
share = lambda t, c: T[t]["shares"][CAT.index(c)]  # noqa: E731
argmax = lambda f: max(types, key=f)["short"]  # noqa: E731
argmin = lambda f: min(types, key=f)["short"]  # noqa: E731
near = lambda x, y, tol: abs(x - y) <= tol  # noqa: E731


def macro_split(type_short):
    """Доли МО типа по макротипам (переходный тип)."""
    ids = [m for m in ok if m["type"] == T[type_short]["id"]]
    return {macro[k]["name"]: sum(m["macro"] == k for m in ids) / len(ids) for k in range(len(macro))}


def fs_summer(m, y):
    """Летний избыток трат в общепите к стране в году y — как признак модели (июнь–август минус среднее года)."""
    i = meta["categories"].index("Общественное питание")
    sr, nat = np.array(series[str(m["id"])][1 + i][y * 12:(y + 1) * 12]), np.array(meta["national"]["cats"][i][y * 12:(y + 1) * 12])
    rel = np.log(sr) - np.log(nat)
    return math.expm1(rel[5:8].mean() - rel.mean())


flow = [m for m in ok if m["moved"] and m["types"][0] == T["Аграрная периферия"]["id"] and m["types"][-1] == T["Глубинка"]["id"]]
stay = [m for m in ok if m["types"][0] == T["Аграрная периферия"]["id"] and m["types"][-1] == T["Аграрная периферия"]["id"]]
ws_main = ws[~((ws.block == "season") & (ws.weight >= 1))]
admin_wins = sum(just["admin"]["types"][k] > just["admin"]["mo_kind"][k] for k in
                 ("eta2:log_pop", "eta2_market_access", "V:arctic_any", "V:far_north_or_equated", "V:monotown", "V:onp_agglomeration_core", "V:regional_capital"))
moved = a.significant_move.sum()
changed = int((a["type_2023-12"] != a["type_2024-12"]).sum())
labels = pd.read_csv(ROOT / "data" / "external" / "ru_official_labels.csv")[["territory_id", "regional_capital"]]
caps = a.merge(labels, on="territory_id").query("regional_capital == 1")
k6 = methods.xs(6, level="k")
second = methods.copeland.sort_values(ascending=False).iloc[1:4]
win = pd.read_csv(R / "dynamics_windows.csv")
absent_in = [m for m in mo if m["status"] == "absent" and m["region"] not in meta["missing_regions"]]
incomplete_regions = {m["region"] for m in mo if m["status"] == "incomplete"}
sib_macro4 = macro_split("Удалённая Сибирь")

DOCS = {"README": ROOT / "README.md", "отчёт": ROOT / "docs" / "report.md", "лендинг": ROOT / "site" / "index.html",
        "типы": ROOT / "configs" / "type_names.yaml", "форма": ROOT.parent / "Форма-заявки.md", "скрипт лендинга": ROOT / "site" / "app.js"}
TEXT = {k: p.read_text(encoding="utf-8") if p.exists() else None for k, p in DOCS.items()}

# (утверждение, проверка -> bool, пересчитанное значение для отчёта, [(документ, фрагмент текста), ...])
CLAIMS = [
    ("2 016 МО в панели, 174 исключены", meta["n_panel"] == 2016 and meta["n_dropped"] == 174, f'{meta["n_panel"]} / {meta["n_dropped"]}',
     [("README", "2 016"), ("отчёт", "174 МО из 52 регионов исключены"), ("форма", "2 016 муниципалитетов")]),
    ("Макротипы 330 / 610 / 991 / 85 МО", [M[n]["size"] for n in ("Столицы и центры высоких трат", "Городская Россия", "Сельская Россия", "Север")] == [330, 610, 991, 85],
     str({n: M[n]["size"] for n in M}), [("отчёт", "(330 МО), «Городская Россия» (610), «Сельская Россия» (991), «Север» (85)")]),
    ("Типы 318 / 495 / 484 / 560 / 113 / 46 МО", [T[s]["size"] for s in ("Столичные", "Города", "Глубинка", "Аграрная периферия", "Удалённая Сибирь", "Арктика")] == [318, 495, 484, 560, 113, 46],
     str({s: T[s]["size"] for s in T}), []),
    ("Вложенность уровней 92,7%", near(fin["nestedness_detailed_in_macro"], 0.927, 0.0005), f'{fin["nestedness_detailed_in_macro"]:.4f}',
     [("README", "92,7%"), ("отчёт", "92,7%")]),
    ("«Удалённая Сибирь» — переходный тип: Городская Россия 57%, Север 25%, Сельская 19%",
     all(near(macro_split("Удалённая Сибирь")[n], v, 0.006) for n, v in (("Городская Россия", .57), ("Север", .25), ("Сельская Россия", .19))),
     str({k: round(v, 3) for k, v in macro_split("Удалённая Сибирь").items()}), [("отчёт", "«Городской Россией» (57%), «Севером» (25%) и «Сельской Россией» (19%)")]),
    ("Правило выбора совпало с конфигурацией (полный режим)", sel["match"] and sel["valid"], f'match={sel["match"]}, valid={sel["valid"]}', []),
    ("KEFRiN k=4 — максимум Коупленда (+26), устойчивость 0,975", methods.copeland.idxmax() == ("kefrin", 4) and methods.loc[("kefrin", 4), "copeland"] == 26
     and near(methods.loc[("kefrin", 4), "stability_ARI"], 0.975, 0.0006), f'{methods.copeland.idxmax()}, {methods.loc[("kefrin", 4), "copeland"]}', [("отчёт", "0,975")]),
    ("KEFRiN k=6: Коупленд +20, устойчивость 0,778", methods.loc[("kefrin", 6), "copeland"] == 20 and near(methods.loc[("kefrin", 6), "stability_ARI"], 0.778, 0.0006),
     f'{methods.loc[("kefrin", 6), "copeland"]}, {methods.loc[("kefrin", 6), "stability_ARI"]:.3f}', []),
    ("«Арктика»: 100% Крайний Север, 67% Арктическая зона", near(T["Арктика"]["official"]["far_north_or_equated"], 1, 1e-9) and near(T["Арктика"]["official"]["arctic_any"], .67, .006),
     str(T["Арктика"]["official"]), [("README", "100% районов Крайнего Севера"), ("форма", "две трети — Арктическая зона")]),
    ("V Крамера: Арктика 0,59, Крайний Север 0,52", near(ext["V:arctic_any"], .59, .005) and near(ext["V:far_north_or_equated"], .52, .005), f'{ext["V:arctic_any"]:.3f}, {ext["V:far_north_or_equated"]:.3f}', []),
    ("η²: население 43%, доступность рынков 40%", near(ext["eta2:log_pop"], .43, .005) and near(ext["eta2_market_access"], .40, .005), f'{ext["eta2:log_pop"]:.3f}, {ext["eta2_market_access"]:.3f}',
     [("README", "43% разброса численности населения и 40%"), ("форма", "43% разброса численности населения и 40%")]),
    ("656 формальных смен, 116 значимых", changed == 656 and moved == 116, f"{changed} / {moved}", [("README", "Из 656 формальных смен"), ("форма", "значимы 116"), ("отчёт", "значимы 116")]),
    ("Главный поток 84, обратно 23, p ≈ 2·10⁻⁹", (asym[0]["backward"], asym[0]["forward"]) == (84, 23) and 1e-9 < asym[0]["p_binomial_two_sided"] < 3e-9,
     f'{asym[0]["backward"]} / {asym[0]["forward"]}, p={asym[0]["p_binomial_two_sided"]:.1e}', [("README", "у 84 МО «Аграрной периферии»"), ("форма", "обратно — 23")]),
    ("Летний избыток общепита: перешедшие +1% → −5%, оставшиеся +5% → +10%",
     near(np.median([fs_summer(m, 0) for m in flow]), .01, .006) and near(np.median([fs_summer(m, 1) for m in flow]), -.05, .006)
     and near(np.median([fs_summer(m, 0) for m in stay]), .05, .006) and near(np.median([fs_summer(m, 1) for m in stay]), .10, .006),
     f"{np.median([fs_summer(m, 0) for m in flow]):+.3f}→{np.median([fs_summer(m, 1) for m in flow]):+.3f}; {np.median([fs_summer(m, 0) for m in stay]):+.3f}→{np.median([fs_summer(m, 1) for m in stay]):+.3f}",
     [("отчёт", "+1% в 2023 → −5% в 2024")]),
    ("Сеть переводит 136 МО; синхронность их связей 35% → 57%, по всем 61% → 64%; ARI с k-means 0,83",
     just["network"]["reassigned"] == 136 and near(just["network"]["sync_within_reassigned_kmeans"], .35, .005) and near(just["network"]["sync_within_reassigned_kefrin"], .57, .005)
     and near(just["network"]["sync_within_kmeans"], .61, .005) and near(just["network"]["sync_within_kefrin"], .64, .005) and near(just["network"]["ari_kefrin_vs_kmeans"], .83, .005),
     str({k: round(v, 3) for k, v in just["network"].items()}), [("README", "136 МО, доля синхронных связей 35% → 57%"), ("отчёт", "136 МО из 2 016")]),
    ("Доли разброса блоков 31 / 36 / 33%; при весе сезонности 1,0 — 50%",
     all(near(just["block_variance_share"][b], v, .005) for b, v in (("level", .31), ("profile", .36), ("season", .33)))
     and near(ws[(ws.block == "season") & (ws.weight >= 1)].block_share.iloc[0], .50, .005),
     str({k: round(v, 3) for k, v in just["block_variance_share"].items()}), [("отчёт", "31%, 36% и 33%")]),
    ("Веса ±30%: макроуровень ARI 0,87–0,93, шесть типов 0,53–0,84",
     near(ws_main.ARI_macro_vs_main.min(), .87, .005) and near(ws_main.ARI_macro_vs_main.max(), .93, .005) and near(ws.ARI_vs_main.min(), .53, .005) and near(ws.ARI_vs_main.max(), .84, .005),
     f"{ws_main.ARI_macro_vs_main.min():.3f}–{ws_main.ARI_macro_vs_main.max():.3f}; {ws.ARI_vs_main.min():.3f}–{ws.ARI_vs_main.max():.3f}", [("отчёт", "(ARI 0,87–0,93)")]),
    ("Типы сильнее вида МО по 5 показателям из 7", admin_wins == 5, f"{admin_wins} из 7", [("отчёт", "по пяти показателям из семи"), ("README", "сильнее по 5 метрикам из 7")]),
    ("США: ARI 0,03, NMI 0,02", near(us["kmeans6_ARI"], .03, .005) and near(us["kmeans6_NMI"], .02, .005), f'{us["kmeans6_ARI"]:.3f}, {us["kmeans6_NMI"]:.3f}',
     [("README", "ARI 0,03"), ("форма", "ARI 0,03"), ("отчёт", "ARI = 0,029, NMI = 0,020")]),
    # сравнения в описаниях типов (configs/type_names.yaml, лендинг, отчёт)
    ("Самые высокие траты на жителя — «Столичные»", argmax(lambda t: t["spend"]) == "Столичные", argmax(lambda t: t["spend"]), [("типы", "Самые высокие траты на жителя")]),
    ("Лучший доступ к рынкам — «Столичные»", argmax(lambda t: t["ma"]) == "Столичные", argmax(lambda t: t["ma"]), [("типы", "лучший доступ к рынкам")]),
    ("Общепит у «Столичных» вдвое выше среднего по МО", T["Столичные"]["mirkin"]["Общепит"] >= 1.0, f'{T["Столичные"]["mirkin"]["Общепит"]:+.2f}', []),
    ("Максимальная доля маркетплейсов — «Глубинка»", argmax(lambda t: share(t["short"], "Маркетплейсы")) == "Глубинка", argmax(lambda t: share(t["short"], "Маркетплейсы")),
     [("типы", "максимальная среди типов доля маркетплейсов")]),
    ("Самые низкие траты — «Аграрная периферия»", argmin(lambda t: t["spend"]) == "Аграрная периферия", argmin(lambda t: t["spend"]), [("типы", "Самые низкие траты")]),
    ("У «Аграрной периферии» продукты — почти половина корзины, общепит минимален", near(share("Аграрная периферия", "Продукты"), .48, .02) and argmin(lambda t: share(t["short"], "Общепит")) == "Аграрная периферия",
     f'{share("Аграрная периферия", "Продукты"):.3f}', [("типы", "продукты — почти половина корзины, общепит минимален")]),
    ("Летний избыток общепита: «Аграрная» +3%, «Глубинка» −2,5%", near(math.expm1(T["Аграрная периферия"]["summer_fs"]), .03, .005) and near(math.expm1(T["Глубинка"]["summer_fs"]), -.025, .005),
     f'{math.expm1(T["Аграрная периферия"]["summer_fs"]):+.3f}, {math.expm1(T["Глубинка"]["summer_fs"]):+.3f}', [("отчёт", "(летний избыток общепита +3%)")]),
    ("Минимальная доля маркетплейсов и сильнейшая сезонность — «Арктика»", argmin(lambda t: share(t["short"], "Маркетплейсы")) == "Арктика" and argmax(lambda t: t["mirkin"]["Сезонность"]) == "Арктика",
     argmin(lambda t: share(t["short"], "Маркетплейсы")), [("типы", "минимальная доля маркетплейсов, сильнейшая сезонность")]),
    ("«Удалённая Сибирь»: доля транспорта выше России, ≈40% — Крайний Север", share("Удалённая Сибирь", "Транспорт") > nat_share["Транспорт"] and near(T["Удалённая Сибирь"]["official"]["far_north_or_equated"], .40, .01),
     f'{share("Удалённая Сибирь", "Транспорт"):.3f} против {nat_share["Транспорт"]:.3f}', [("типы", "Высокая доля транспорта")]),
    ("Самая высокая доля транспорта — «Столичные» (а не «Удалённая Сибирь»)", argmax(lambda t: share(t["short"], "Транспорт")) == "Столичные", argmax(lambda t: share(t["short"], "Транспорт")), []),
    ("Больше всего моногородов — «Города» (около четверти)", argmax(lambda t: t["official"]["monotown"]) == "Города" and near(T["Города"]["official"]["monotown"], .24, .01),
     f'{T["Города"]["official"]["monotown"]:.3f}', [("типы", "больше всего моногородов — около четверти типа")]),
]
CLAIMS += [
    ("44 из 64 МО со статусом «административный центр субъекта» — в «Городах»", len(caps) == 64 and int((caps.type_main == T["Города"]["id"]).sum()) == 44,
     f'{len(caps)}, в «Городах» {int((caps.type_main == T["Города"]["id"]).sum())}', [("отчёт", "44 из 64 МО со статусом")]),
    ("Спектральный при k = 6: лучший по AVU, S_Dbw и устойчивости, второй после Leiden по MQ и AVI",
     k6.AVU.idxmin() == "spectral" and k6.S_Dbw.idxmin() == "spectral" and k6.stability_ARI.idxmax() == "spectral" and k6.MQ.idxmax() == "leiden" and k6.AVI.idxmax() == "leiden"
     and k6.MQ.drop("leiden").idxmax() == "spectral", f'MQ {k6.MQ.idxmax()}, AVI {k6.AVI.idxmax()}, AVU {k6.AVU.idxmin()}', [("отчёт", "второй после Leiden по MQ и AVI")]),
    ("AVU при k = 6: 0,48–0,50, случайный 0,47", near(k6.AVU.min(), .48, .005) and near(k6.AVU.max(), .50, .005) and near(fin["random_mean"]["AVU"], .47, .005),
     f'{k6.AVU.min():.3f}–{k6.AVU.max():.3f}, случайный {fin["random_mean"]["AVU"]:.3f}', [("отчёт", "(0,48–0,50)")]),
    ("Следующие по Коупленду: k-means 8 (+24), спектральный 8 и KEFRiN 9 (+22)",
     list(second.index) == [("kmeans", 8), ("spectral", 8), ("kefrin", 9)] and list(second.values) == [24, 22, 22], str(list(second.items())), [("отчёт", "KEFRiN k = 9 (по +22)")]),
    ("KEFRiN держит силуэт k-means только при k ≤ 8", all(methods.loc[("kefrin", k), "SW"] >= methods.loc[("kmeans", k), "SW"] - 0.03 for k in range(4, 9))
     and methods.loc[("kefrin", 9), "SW"] < methods.loc[("kmeans", 9), "SW"] - 0.03, f'k=9: {methods.loc[("kefrin", 9), "SW"]:.3f} против {methods.loc[("kmeans", 9), "SW"]:.3f}', [("отчёт", "при k ≤ 8")]),
    ("ARI соседних окон 0,57–0,87", near(win.ARI_prev.iloc[1:].min(), .57, .005) and near(win.ARI_prev.iloc[1:].max(), .87, .005),
     f'{win.ARI_prev.iloc[1:].min():.3f}–{win.ARI_prev.iloc[1:].max():.3f}', [("отчёт", "0,57–0,87")]),
    ("174 исключённых МО из 52 регионов; ещё 151 МО регионов набора нет в данных", len(incomplete_regions) == 52 and len(absent_in) - 59 == 151,
     f'{len(incomplete_regions)} регионов; нет в данных {len(absent_in)} (из них 59 в четырёх регионах без полных рядов)', [("отчёт", "Ещё 151 МО")]),
    ("При 4 типах «Удалённая Сибирь» не входит целиком в «Север»", sib_macro4["Север"] < 0.5, str({k: round(v, 2) for k, v in sib_macro4.items()}), []),
    ("Доступность рынков: на севере вдвое ниже медианы, в удалённой Сибири — на 40%",
     near(T["Арктика"]["ma"] / np.median([m["ma"] for m in ok if m["ma"] is not None]), .5, .05) and near(T["Удалённая Сибирь"]["ma"] / np.median([m["ma"] for m in ok if m["ma"] is not None]), .6, .05),
     f'{T["Арктика"]["ma"]:.0f} и {T["Удалённая Сибирь"]["ma"]:.0f} при медиане {np.median([m["ma"] for m in ok if m["ma"] is not None]):.0f}', [("отчёт", "в удалённой Сибири — на 40%")]),
    ("Маркетплейсы: на севере 8,7% против 13,9%, в удалённой Сибири 12,4%", near(share("Арктика", "Маркетплейсы"), .087, .0006) and near(nat_share["Маркетплейсы"], .139, .0006)
     and near(share("Удалённая Сибирь", "Маркетплейсы"), .124, .0006), f'{share("Арктика", "Маркетплейсы"):.4f}, {nat_share["Маркетплейсы"]:.4f}, {share("Удалённая Сибирь", "Маркетплейсы"):.4f}',
     [("отчёт", "8,7% против 13,9%"), ("лендинг", "8,7% против 13,9%")]),
    ("«Города»: траты примерно на пятую часть выше медианы России", near(T["Города"]["spend"] / np.median([m["spend"] for m in ok]), 1.2, .03),
     f'{T["Города"]["spend"] / np.median([m["spend"] for m in ok]):.3f}', [("типы", "примерно на пятую часть выше медианы России")]),
    ("Силуэт итога не выше 0,25 — по шкале Kaufman & Rousseeuw обособленных кластеров нет", fin["SW"] <= 0.25, f'{fin["SW"]:.3f}', [("отчёт", "Kaufman & Rousseeuw (1990)")]),
    ("«Столичные»: доля общепита почти втрое выше медианы России", 2.6 <= share("Столичные", "Общепит") / nat_share["Общепит"] < 3.0,
     f'{share("Столичные", "Общепит") / nat_share["Общепит"]:.2f}', [("типы", "почти втрое выше медианы России")]),
]

sys.path.insert(0, str(ROOT / "scripts"))
import cash_check  # noqa: E402
import contextlib, io  # noqa: E401,E402
with contextlib.redirect_stdout(io.StringIO()):
    CASH = cash_check.main()
CLAIMS += [
    ("Маркетплейсы и наличные: ρ −0,19 по всем типам, −0,40 / −0,28 / −0,59 в сельских типах",
     near(CASH["rho_marketplaces"], -0.19, .005) and near(CASH["by_type"]["Аграрная периферия"], -0.40, .005) and near(CASH["by_type"]["Глубинка"], -0.28, .005)
     and near(CASH["by_type"]["Удалённая Сибирь"], -0.59, .005), f'{CASH["rho_marketplaces"]:+.3f}; ' + ", ".join(f"{k} {v:+.2f}" for k, v in CASH["by_type"].items()),
     [("отчёт", "ρ Спирмена −0,19 по всем типам"), ("скрипт лендинга", "ρ = −0,19")]),
]

# --- дополнительные проверки (агрегирование, IMM, Росстат, синтетика, динамика типов, география) ---
sys.path.insert(0, str(ROOT / "src"))
from smc.export_web import num, pct, v2_summaries, _round  # noqa: E402

agg = pd.read_csv(R / "aggregation.csv").set_index("rule_name")
imm, ros, ll = load(R / "imm_rules.json"), load(R / "rosstat_validation.json"), load(R / "leadlag.json")
spa, syn, gmm, mob = load(R / "spatial_autocorr.json"), load(R / "synthetic_summary.json"), load(R / "gmm_check.json"), load(R / "mobility_check.json")
evs, rtypes, v2 = pd.read_csv(R / "cluster_events.csv"), pd.read_csv(R / "rosstat_types.csv", index_col=0), load(S / "v2.json")
net = load(S / "net.json")
SHORT = {t["id"]: t["short"] for t in types}
IMM = {SHORT[t["type"]]: t for t in imm["types"]}
r23, r24 = ros["years"]["2023"], ros["years"]["2024"]
RT = {SHORT[int(i)]: r for i, r in rtypes.iterrows()}
cells = pd.DataFrame(syn["rows"]).pivot_table(index=["attr", "net"], columns="method", values="ari")
LV = ["слабый", "средний", "сильный"]
syn_row = lambda m: " | ".join(num(cells.loc[(a_, n_), m]) for a_ in LV for n_ in LV)  # noqa: E731
lead = [x for x in ll["leaders"] if x["share"] is not None]
split = evs[evs.event == "split"]
mob_r = mob["periods"][mob["main_period"]]
mob_t = {SHORT[t["type"]]: t for t in mob_r["types"]}
from smc.metrics import DIRECTIONS  # noqa: E402
dirs7 = {m: DIRECTIONS[m] for m in ("SW", "CH", "S_Dbw", "MQ", "AVI", "AVU", "stability_ARI")}
el = methods[methods.min_size >= 0.01 * meta["n_panel"]]
Vg = np.column_stack([el[c].to_numpy() * d for c, d in dirs7.items()])
grade3 = np.minimum(Vg.argsort(0).argsort(0) * 3 // len(Vg), 2)[list(el.index).index(("kefrin", 4))]
worst_k4 = [c for c, g in zip(dirs7, grade3) if g == 0]
v2_fresh = json.loads(json.dumps(_round(v2_summaries(R, {t["id"]: t for t in types}), 4)))

CLAIMS += [
    ("Агрегирование: Коупленд и Борда — единственный победитель KEFRiN k = 4, детальный KEFRiN k = 6",
     all(agg.loc[r, "macro_winners"] == "kefrin k=4" and agg.loc[r, "detailed"] == "kefrin k=6" for r in ("Коупленд", "Борда")),
     agg.loc[["Коупленд", "Борда"], "macro_winners"].tolist(), [("отчёт", "| Борда | KEFRiN, k = 4 | 1 | KEFRiN, k = 6 |")]),
    ("Шульце: ничья KEFRiN k = 4 и спектрального k = 6", agg.loc["Шульце", "macro_winners"] == "kefrin k=4; spectral k=6",
     agg.loc["Шульце", "macro_winners"], [("отчёт", "| Шульце | KEFRiN, k = 4 и спектральный, k = 6 (ничья) | 1 |")]),
    ("Пороговое m = 3: ничья пяти, место KEFRiN k = 4 — 11; m = 5: KEFRiN k = 9, место 17",
     agg.loc["Пороговое (m = 3)", "ties"] == 5 and agg.loc["Пороговое (m = 3)", "final_rank"] == 11
     and agg.loc["Пороговое (m = 5)", "macro_winners"] == "kefrin k=9" and agg.loc["Пороговое (m = 5)", "final_rank"] == 17,
     f'{agg.loc["Пороговое (m = 3)", "macro_winners"]}; {agg.loc["Пороговое (m = 5)", "macro_winners"]}',
     [("отчёт", "| Пороговое, m = 3 | ничья пяти: спектральный k = 5, 6, 8; KEFRiN k = 6, 8 | 11 |"), ("отчёт", "| Пороговое, m = 5 | KEFRiN, k = 9 | 17 | KEFRiN, k = 6 |")]),
    ("KEFRiN среди победителей при всех правилах; KEFRiN k = 6 — в детальном уровне всех вариантов",
     all("kefrin" in w for w in agg.macro_winners) and all("kefrin k=6" in d for d in agg.detailed), len(agg),
     [("README", "KEFRiN — победитель или среди равных победителей при всех"), ("отчёт", "KEFRiN — победитель или среди равных победителей при всех четырёх правилах")]),
    ("Пороговое m = 3: у KEFRiN k = 4 худшие оценки по S_Dbw и AVU", worst_k4 == ["S_Dbw", "AVU"], worst_k4, [("отчёт", "две худшие оценки, по S_Dbw и AVU")]),
    ("IMM: 5 порогов, совпадение 80%; CART глубины 3 — тоже 80%", imm["thresholds"] == 5 and round(imm["fidelity"], 2) == 0.80 and round(imm["cart_fidelity"]["depth3"], 2) == 0.80,
     f'{imm["fidelity"]:.4f} / {imm["cart_fidelity"]["depth3"]:.4f}', [("отчёт", "Пять порогов дерева IMM воспроизводят 80% назначений"), ("отчёт", "Пять порогов воспроизводят 80% назначений (дерево решений CART глубины 3 — тоже 80%"),
                                                                       ("README", "5 порогов воспроизводят 80% назначений")]),
    ("IMM по типам: Арктика 93%, Столичные 97%, Города 80%, Удалённая Сибирь 40%, Глубинка 75%, Аграрная периферия 81%",
     [round(100 * IMM[s]["fidelity"]) for s in ("Арктика", "Столичные", "Города", "Удалённая Сибирь", "Глубинка", "Аграрная периферия")] == [93, 97, 80, 40, 75, 81],
     {s: round(IMM[s]["fidelity"], 3) for s in IMM}, [("отчёт", "| Удалённая Сибирь и горы | летний прирост не больше +6,5%; траты не выше 154% медианы; вес транспорта выше 133% медианы | 40% |")]),
    ("IMM: пороги +6,5% лета, 106% и 154% трат, 96% и 133% транспорта", IMM["Арктика"]["rules"] == ["летний прирост трат сверх общероссийского больше +6,5%"]
     and "траты на жителя выше 154% медианы России" in IMM["Столичные"]["rules"] and "вес транспорта в корзине — от 96% до 133% медианы России" in IMM["Аграрная периферия"]["rules"]
     and "траты на жителя — от 106% до 154% медианы России" in IMM["Города"]["rules"], IMM["Города"]["rules"],
     [("отчёт", "| Арктика и Крайний Север | летний прирост трат сверх общероссийского больше +6,5% | 93% |")]),
    ("Росстат: сопоставлено 2 016 МО (2023) и 1 866 (2024)", r23["coverage"] == 2016 and r24["coverage"] == 1866, f'{r23["coverage"]} / {r24["coverage"]}',
     [("отчёт", "Сопоставлены все 2 016 МО панели (2023 год; в 2024 году — 1 866)")]),
    ("Росстат: η² лог-зарплаты 0,69 (2023 и 2024), занятость: промышленность 23%, бюджет 29%, торговля 30%, добыча 12%, сельское хозяйство 10%",
     round(r23["eta2"]["log_wage"], 2) == 0.69 == round(r24["eta2"]["log_wage"], 2)
     and [round(100 * r23["eta2"][g]) for g in ("ind", "pub", "trade", "min", "agr")] == [23, 29, 30, 12, 10],
     {k: round(v, 3) for k, v in r23["eta2"].items()},
     [("отчёт", "Типы объясняют **69% разброса логарифма зарплаты** (η² = 0,69; в 2024 году — тоже 0,69), долей занятых в\nпромышленности — 23%, в бюджетной сфере — 29%, в торговле — 30%, в добыче — 12%, в сельском хозяйстве — 10%."),
      ("отчёт", "отраслевая структура занятости связана с типами умеренно (η² 0,10–0,30)"), ("README", "η² логарифма зарплаты 0,69")]),
    ("Росстат: ρ Спирмена зарплаты и трат 0,86; сверх уровня трат типы объясняют 6%",
     round(r23["spearman_wage_spend"], 2) == 0.86 and round(100 * r23["eta2_log_wage_resid_level"]) == 6,
     f'{r23["spearman_wage_spend"]:.3f}, {r23["eta2_log_wage_resid_level"]:.3f}', [("отчёт", "(ρ Спирмена 0,86)"), ("отчёт", "типы объясняют лишь 6% остатка")]),
    ("Вторая линза: ARI 0,17, NMI 0,25", round(r23["lens"]["ari"], 2) == 0.17 and round(r23["lens"]["nmi"], 2) == 0.25, f'{r23["lens"]["ari"]:.3f}, {r23["lens"]["nmi"]:.3f}',
     [("отчёт", "совпадает с нашей слабо: ARI 0,17, NMI 0,25"), ("README", "типология по занятости с нашей совпадает слабо (ARI 0,17)")]),
    ("Росстат: медианы зарплат типов 126 763 / 108 492 / 60 049 / 53 785 / 44 994 / 41 048 ₽",
     [round(RT[s].wage) for s in ("Арктика", "Столичные", "Города", "Удалённая Сибирь", "Глубинка", "Аграрная периферия")] == [126763, 108492, 60049, 53785, 44994, 41048],
     {s: round(r.wage) for s, r in RT.items()}, [("отчёт", "| Арктика и Крайний Север | 126 763 | 27,7% | 17,2% | 0,6% | 29,0% | 1,2% |"),
                                                ("отчёт", "| Удалённая Сибирь и горы | 53 785 | 3,3% | 0,0% | 1,6% | 66,2% | 1,5% |")]),
    ("Росстат: таблица долей занятости по типам совпадает с results/rosstat_types.csv",
     all(f'| {pct(r.ind, 1)} | {pct(r["min"], 1)} | {pct(r.agr, 1)} | {pct(r.pub, 1)} | {pct(r.trade, 1)} |' in TEXT["отчёт"] for r in RT.values()),
     {s: [round(r[g], 3) for g in ("ind", "min", "agr", "pub", "trade")] for s, r in RT.items()}, []),
    ("Join count: 5 042 пары соседей, тип совпадает у 56% против 22%; рёбра сети 2,8% — соседи, тип по ним 57%; внутри региона 27% против 80%",
     spa["types"]["geo"]["pairs"] == 5042 and round(100 * spa["types"]["geo"]["same"]) == 56 and round(100 * spa["types"]["geo"]["null"]) == 22
     and round(100 * spa["net_edges_between_neighbours_share"], 1) == 2.8 and round(100 * spa["types"]["net"]["same"]) == 57
     and round(100 * spa["region"]["net"]["same"]) == 27 and round(100 * spa["region"]["geo"]["same"]) == 80 and spa["types"]["net"]["same"] > spa["types"]["geo"]["same"]
     and round(spa["types"]["geo"]["z"], -1) == 60,
     f'{spa["types"]["geo"]["same"]:.3f} / {spa["types"]["geo"]["null"]:.3f} / {spa["types"]["net"]["same"]:.3f}; z {spa["types"]["geo"]["z"]:.1f}',
     [("отчёт", "(5 042 пары)"), ("отчёт", "совпадает у 56% соседних пар против 22%"), ("отчёт", "лишь в 2,8% случаев соединяют"), ("отчёт", "внутри одного региона лежат только 27% рёбер (у соседей по границе — 80%)"),
      ("отчёт", "у 57% пар"), ("README", "рёбра сети лишь в 2,8% случаев соединяют соседей по границе")]),
    ("Опережение: 25 176 рёбер, 85% без сдвига против 7% в нулевой модели, ни один из 20 повторов не ниже",
     ll["edges"] == 25176 and round(100 * (1 - ll["share_lagged"])) == 85 and round(100 * (1 - ll["null_share"])) == 7 and ll["reps"] == 20 and math.isclose(ll["p"], 1 / 21),
     f'{1 - ll["share_lagged"]:.3f} / {1 - ll["null_share"]:.3f}, p {ll["p"]:.3f}',
     [("отчёт", "У 85% рёбер корреляция максимальна без сдвига; в нулевой модели\nтаких было бы 7%"), ("README", "85% рёбер синхронны без сдвига"), ("отчёт", "85% рёбер\n  сети синхронны без сдвига")]),
    ("Опережение по группам: доли от 0,42 до 0,54, все p > 0,2",
     num(min(x["share"] for x in lead)) == "0,42" and num(max(x["share"] for x in lead)) == "0,54" and min(x["p_binomial"] for x in lead) > 0.2,
     [(x["from"], x["to"], round(x["share"], 3), round(x["p_binomial"], 3)) for x in lead], [("отчёт", "от 0,42 до 0,54 при\nожидаемой 0,5 без опережения (биномиальный критерий, все p > 0,2)")]),
    ("MONIC: 12 переходов, 72 случая, 70 «выжил», 2 раскола «Удалённой Сибири» (июнь, июль 2024) на «Города» и «Глубинку», 17 ростов и 17 сжатий",
     evs.window.nunique() == 12 and (evs.event != "emerge").sum() == 72 and (evs.event == "survive").sum() == 70 and len(split) == 2
     and set(split.type) == {T["Удалённая Сибирь"]["id"]} and list(split.window) == ["2024-06", "2024-07"]
     and {t for s in split.to for t in json.loads(s)} - {T["Удалённая Сибирь"]["id"]} == {T["Города"]["id"], T["Глубинка"]["id"]}
     and (evs.internal == "grow").sum() == 17 and (evs.internal == "shrink").sum() == 17 and set(evs.event) <= {"survive", "split"},
     evs.event.value_counts().to_dict(), [("отчёт", "За 12 переходов между соседними окнами из 72 случаев 70 — «выжил»"), ("отчёт", "Внутренних переходов «рост» и «сжатие» — по 17"),
                                          ("README", "из 72 случаев 70 — «выжил», 2 раскола «Удалённой Сибири»")]),
    ("Синтетика: таблица ARI совпадает с results/synthetic.csv",
     all(f"| {lbl} | {syn_row(m)} |" in TEXT["отчёт"] for m, lbl in (("k-means", "k-means"), ("Leiden", "Leiden"), ("Спектральный", "Спектральный"), ("KEFRiN", "KEFRiN (доля сети 0,4)"))),
     {m: syn_row(m) for m in cells.columns}, []),
    ("Синтетика: KEFRiN не хуже k-means во всех 9 ячейках; средний ARI 0,39 против 0,38; развёртка 0,377 → 0,385 → 0,398, отставание 0,013",
     syn["cells"] == 9 and bool((cells["KEFRiN"] >= cells["k-means"] - syn.get("tie_tol", 0.01)).all())
     and num(syn["mean_ari"]["KEFRiN"]) == "0,39" and num(syn["mean_ari"]["k-means"]) == "0,38"
     and [num(x["ari"], 3) for x in syn["share_sweep"] if x["share"] in (0.0, 0.4, 0.8)] == ["0,377", "0,385", "0,398"] and num(syn["share_config_gap_to_best"], 3) == "0,013",
     f'{syn["mean_ari"]}', [("отчёт", "не хуже k-means во всех девяти\nячейках, но выигрыш мал (средний ARI 0,39 против 0,38)"), ("отчёт", "ARI 0,377 при доле 0 → 0,385 при 0,4 →\n0,398 при 0,8; доля 0,4 отстаёт от лучшей на 0,013 ARI"),
                            ("README", "KEFRiN не хуже k-means во всех ячейках")]),
    ("GMM: 53 кандидата, победитель прежний, лучшая GMM k = 4 — 27-я (силуэт 0,17, устойчивость 0,86)",
     gmm["candidates"] == 53 and gmm["winner_unchanged"] and gmm["best_gmm_k"] == 4 and gmm["best_gmm_rank"] == 27
     and num(pd.read_csv(R / "gmm_check.csv").set_index("k").loc[4, "SW"]) == "0,17" and num(pd.read_csv(R / "gmm_check.csv").set_index("k").loc[4, "stability_ARI"]) == "0,86",
     gmm, [("отчёт", "С ней кандидатов 53"), ("отчёт", "лучшая GMM (k = 4: силуэт 0,17, устойчивость 0,86) — на 27-м месте"), ("README", "GMM как шестой метод победителя не меняет")]),
    ("Мобильность СЗФО: 274 МО, η² 70%; «Столичные» 112 МО (97 — Петербург), медиана 5,0 км, остальные 0,5–1,3 км; без Петербурга 36% (177 МО)",
     mob_r["n"] == 274 and round(100 * mob_r["eta2_log"]) == 70 and mob_t["Столичные"]["n"] == 112 and mob_r["n"] - mob_r["n_without_spb"] == 97
     and num(mob_t["Столичные"]["median_km"], 1) == "5,0" and num(min(t["median_km"] for s, t in mob_t.items() if s != "Столичные"), 1) == "0,5"
     and num(max(t["median_km"] for s, t in mob_t.items() if s != "Столичные"), 1) == "1,3" and round(100 * mob_r["eta2_log_without_spb"]) == 36 and mob_r["n_without_spb"] == 177,
     f'{mob_r["eta2_log"]:.3f}, {mob_r["eta2_log_without_spb"]:.3f}', [("отчёт", "274 МО Северо-Западного федерального округа"), ("отчёт", "(112 МО, из них 97 —\nокруга Петербурга; медиана 5,0 км) и остальными типами (медианы 0,5–1,3 км); без округов Петербурга — 36% (177 МО)")]),
    ("site/data/v2.json собран из текущих results/ (тексты summary — из тех же чисел)", v2 == v2_fresh, [k for k in v2 if v2.get(k) != v2_fresh.get(k)], []),
    ("mo.json: у всех МО панели есть зарплата и доли занятости Росстата", all(m.get("wage") and m.get("emp") for m in ok), sum(bool(m.get("wage")) for m in ok), []),
    ("net.json: 2 016 узлов, рёбер не больше 20 000, координаты в [0, 1]", len(net["ids"]) == 2016 and len(net["edges"]) <= 20000
     and 0 <= min(min(p) for p in net["xy"]) and max(max(p) for p in net["xy"]) <= 1, f'{len(net["ids"])} узлов, {len(net["edges"])} рёбер', []),
]

_n = len(CLAIMS) + 1
CLAIMS.append(("Число утверждений реестра в README и отчёте", True, _n, [("README", f"реестр утверждений: {_n} чисел"), ("отчёт", f"({_n} утверждений)")]))

# запрещённые формулировки: были ошибками и не должны вернуться в тексты
FORBIDDEN = [("самая высокая доля транспорта", "у «Столичных» 7,3% выше, чем у «Удалённой Сибири»"),
             ("на севере и в удалённой Сибири высока доля транспорта", "у «Арктики» доля транспорта ниже российской"),
             ("Север → **Удалённая Сибирь", "«Удалённая Сибирь» — переходный тип"),
             ("ослаб летний рост трат относительно страны", "сдвиг — в летних тратах на общепит"),
             ("Типы совпадают с", "с моногородами, агломерациями и столицами связь умеренная (V 0,22–0,27)"),
             ("самостоятельная потребительская оптика", "в США проверялась только динамика общего индекса трат"),
             ("выигрывает по графовым индексам", "по MQ и AVI лучше Leiden"),
             ("при 4–5 типах сливаются север", "при 4 типах «Удалённая Сибирь» делится между тремя макротипами"),
             ("44 из 64 столиц регионов", "три МО с меткой — муниципальные районы; писать по статусу в справочнике"),
             ("7 индексов", "голосуют 6 индексов качества и устойчивость"),
             ("семь индексов качества «голосуют»", "голосуют 6 индексов качества и устойчивость"),
             ("крупнейшие города лежат на границе", "верно для городов-миллионников, Владивосток и Хабаровск выше порога"),
             ("среди них все МО Бурятии", "59 МО этих регионов в данных нет совсем"),
             ("всегда городской округ", "три помеченных МО — муниципальные районы"),
             ("AVU у всех методов (0,45–0,50)", "по всем конфигурациям 0,43–0,56, при k = 6 — 0,48–0,50"),
             ("Регион отсутствует в наборе данных", "у 151 МО регион в наборе есть"),
             ("с первым типом", "на лендинге первым идёт другой тип — называть тип по имени"),
             ("CH/N ≥ 1", "такого ориентира в литературе нет"),
             ("Структура умеренная", "по шкале Kaufman & Rousseeuw силуэт ≤ 0,25 — обособленных кластеров нет"),
             ("Структура типов умеренная", "по шкале Kaufman & Rousseeuw силуэт ≤ 0,25 — обособленных кластеров нет"),
             ("ни в одной стране", "проверены только рассмотренные страны"),
             ("с 0,69 до 0,44", "пилот не воспроизводится; воспроизводимо — scripts/anchor_check.py"),
             ("(Столичные агломерации, Города", "макротип переименован: «Столицы и центры высоких трат» — в нём 42 МО вне Москвы, Петербурга и их областей"),
             ("Макротипы: «Столичные агломерации»", "макротип переименован: «Столицы и центры высоких трат»"),
             ("Столичные агломерации →", "макротип переименован: «Столицы и центры высоких трат»")]


def main() -> int:
    bad = 0
    for text, ok_, value, where in CLAIMS:
        miss = [f"{d}: «{frag}»" for d, frag in where if TEXT.get(d) is not None and frag not in TEXT[d]]
        status = "ок " if ok_ and not miss else "ОШИБКА"
        bad += status != "ок "
        print(f"[{status}] {text}  —  данные: {value}" + (f"  —  в тексте нет: {'; '.join(miss)}" if miss else ""))
    for frag, why in FORBIDDEN:
        hits = [d for d, t in TEXT.items() if t and frag in t]
        if hits:
            bad += 1
            print(f"[ОШИБКА] запрещённая формулировка «{frag}» в: {', '.join(hits)} — {why}")
    print(f"\nПроверено утверждений: {len(CLAIMS)} + запретов: {len(FORBIDDEN)}; расхождений: {bad}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
