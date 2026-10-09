"""Конвейер «Типы локальных экономик России»: данные -> признаки -> сети -> сравнение методов ->
выбор -> динамика -> профили типов -> данные для лендинга.

    python run.py --config configs/default.yaml            # всё
    python run.py --config configs/default.yaml --fast     # без бутстрепа устойчивости
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import yaml
from sklearn.metrics import adjusted_rand_score, normalized_mutual_info_score

sys.path.insert(0, str(Path(__file__).parent / "src"))

from smc import clustering as C  # noqa: E402
from smc import dynamics as D  # noqa: E402
from smc import graphs as G  # noqa: E402
from smc import interpret as I  # noqa: E402
from smc import metrics as M  # noqa: E402
from smc import external as E  # noqa: E402
from smc.data import load_panel, load_road_distances  # noqa: E402
from smc.features import fit_scaler, window_features, window_starts  # noqa: E402

LOG: list[str] = []


def log(msg: str) -> None:
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    LOG.append(line)


def copeland(df: pd.DataFrame, directions: dict[str, int]) -> pd.Series:
    """Правило Коупленда: конфигурация A побеждает B, если лучше по большинству метрик.
    Счёт = победы - поражения. Метрики — «избиратели», конфигурации — «кандидаты»."""
    cols = [c for c in directions if c in df and df[c].notna().all()]
    V = np.column_stack([df[c].to_numpy() * directions[c] for c in cols])
    n = len(df)
    score = np.zeros(n)
    for a in range(n):
        for b in range(n):
            if a == b:
                continue
            better = (V[a] > V[b]).sum()
            worse = (V[a] < V[b]).sum()
            score[a] += np.sign(better - worse)
    return pd.Series(score, index=df.index, name="copeland")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="configs/default.yaml")
    ap.add_argument("--fast", action="store_true", help="без бутстрепа устойчивости")
    args = ap.parse_args()
    cfg = yaml.safe_load(open(args.config, encoding="utf-8"))
    seed = cfg["seed"]
    out = Path(cfg["output"]["results_dir"])
    out.mkdir(parents=True, exist_ok=True)
    k_nn = cfg["graphs"]["k"]
    cl = cfg["clustering"]

    # 1. Панель и признаки ------------------------------------------------------------
    p = load_panel(cfg)
    n, T = p.total.shape
    log(f"панель: {n} МО x {T} мес.; исключено неполных рядов: {len(p.dropped)}")
    full = window_features(p, 0, T, cfg["features"]["summer_months"])
    scaler = fit_scaler(full, cfg["features"]["block_weights"])
    X = scaler.transform(full.raw)
    road = load_road_distances(cfg, p.ids)
    region = p.meta.region.to_numpy()
    full.raw.join(p.meta[["name", "region"]]).to_csv(out / "features_full_period.csv", encoding="utf-8")

    # 2. Пять правил рёбер ----------------------------------------------------------------
    mean_spend = p.cats.mean(1)
    graphs = {}
    diag = {}
    for r in cfg["graphs"]["rules"]:
        t0 = time.time()
        graphs[r] = G.build_graph(r, X=X, series=full.series, mean_spend=mean_spend, road=road,
                                  k=k_nn, dtw_band=cfg["graphs"]["dtw_band"])
        diag[r] = G.diagnostics(graphs[r], X, region, road) | {"build_sec": round(time.time() - t0, 1)}
    pd.DataFrame(diag).T.to_csv(out / "graphs_diagnostics.csv")
    rules = list(graphs)
    pd.DataFrame([[G.jaccard_edges(graphs[a], graphs[b]) for b in rules] for a in rules],
                 index=rules, columns=rules).to_csv(out / "graphs_jaccard.csv")
    log("сети построены: " + ", ".join(f"{r}: {d['edges']} рёбер" for r, d in diag.items()))
    A_net = graphs[cfg["graphs"]["main_rule"]]
    A_attr = graphs["attr"]

    # 3a. Развёртка доли сети в KEFRiN при финальном k; доля выбирается правилом допуска по силуэту ------
    fk_ = cfg["final"]["k"]
    sweep = []
    for share in cl["net_share_grid"]:
        lab = C.kefrin(X, A_net, fk_, seed, share, cl["n_init"])
        r = {"net_share": share, "min_size": int(np.bincount(lab).min())} | M.icvi(X, A_net, lab)
        if not args.fast:
            r["stability_ARI"] = M.bootstrap_ari(
                lambda idx, sh=share: C.kefrin(X[idx], A_net[idx][:, idx], fk_, seed, sh, 5),
                n, cl["bootstrap"], cl["bootstrap_frac"], seed)
        sweep.append(r)
    pd.DataFrame(sweep).set_index("net_share").to_csv(out / "kefrin_share_sweep.csv")
    # правило: наибольшая доля сети, при которой силуэт теряет не больше допуска относительно k-means (доля 0)
    sw0 = sweep[0]["SW"]
    chosen = max(r["net_share"] for r in sweep if r["SW"] >= sw0 - cl["net_share_sw_tolerance"])
    if chosen != cl["kefrin_net_share"]:
        log(f"ВНИМАНИЕ: правило выбрало долю сети {chosen}, в конфиге {cl['kefrin_net_share']} — используется {chosen}")
    cl["kefrin_net_share"] = chosen
    log("развёртка доли сети KEFRiN: " + ", ".join(f"{r['net_share']}: SW={r['SW']:.3f} MQ={r['MQ']:.3f}" for r in sweep))

    # 3. Сравнение методов x k -----------------------------------------------------------
    rows = []
    labels = {}
    for k in cl["k_range"]:
        for m in cl["methods"]:
            lab = C.run_method(m, k, X=X, A_net=A_net, A_attr=A_attr, cfg_cl=cl, seed=seed)
            labels[(m, k)] = lab
            r = {"method": m, "k": k, "min_size": int(np.bincount(lab).min())} | M.icvi(X, A_net, lab)
            if not args.fast:
                def refit(idx, m=m, k=k):
                    sub = {"n_init": 5} if m in ("kmeans", "kefrin") else {}
                    return C.run_method(m, k, X=X[idx], A_net=A_net[idx][:, idx], A_attr=A_attr[idx][:, idx],
                                        cfg_cl=cl | sub, seed=seed)
                r["stability_ARI"] = M.bootstrap_ari(refit, n, cl["bootstrap"], cl["bootstrap_frac"], seed)
            rows.append(r)
        log(f"k={k}: методы посчитаны")
    comp = pd.DataFrame(rows).set_index(["method", "k"])
    # внешняя валидность каждой конфигурации по официальным меткам (не голосует — независимая проверка)
    Lab = E.load_labels(cfg["data"]["external_labels"], p.ids)
    ext_rows = {key: E.official_validity(lab, Lab) for key, lab in labels.items()}
    comp = comp.join(pd.DataFrame(ext_rows).T.rename_axis(["method", "k"]))
    # «избиратели» Коупленда: ANUI не голосует — он выводится из AVI и AVU (двойной счёт)
    directions = {m: M.DIRECTIONS[m] for m in ("SW", "CH", "S_Dbw", "MQ", "AVI", "AVU", "stability_ARI")}
    eligible = comp[comp.min_size >= 0.01 * n]
    comp["copeland"] = copeland(eligible, directions).reindex(comp.index)
    comp.to_csv(out / "methods_icvi.csv")
    # победитель среди методов при каждом k
    wins = eligible.groupby(level="k").apply(lambda d: copeland(d.droplevel("k"), directions).idxmax())
    wins.rename("best_method").to_csv(out / "best_method_by_k.csv")
    log("победители Коупленда по k: " + wins.to_dict().__repr__())

    # Правило выбора: метод и макроуровень — глобальный максимум Коупленда; детальный уровень — тот же
    # метод при наименьшем k >= min_k_detailed с устойчивостью ARI >= min_stability (уровни вложены).
    sel = cfg["selection"]
    el = comp[comp.min_size >= 0.01 * n]

    def detailed_for(method, min_k, min_stab):
        """Тот же метод, что на макроуровне (иначе уровни не вложены), наименьшее k >= min_k с ARI >= min_stab."""
        c = el.xs(method, level="method")
        c = c[c.index >= min_k]
        if "stability_ARI" in c:
            c = c[c.stability_ARI >= min_stab]
        return (method, int(c.index.min())) if len(c) else None

    rule_macro = el["copeland"].idxmax()
    rule_detailed = detailed_for(rule_macro[0], sel["min_k_detailed"], sel["min_stability"])
    if "stability_ARI" in el:
        sens = []
        for thr in (0.65, 0.70, 0.75, 0.80):
            for mk_ in (5, 6, 7):
                d = detailed_for(rule_macro[0], mk_, thr)
                alt = el[(el.index.get_level_values("k") >= mk_) & (el.stability_ARI >= thr)]
                sens.append({"min_stability": thr, "min_k": mk_, "detailed_same_method": None if d is None else f"{d[0]} k={d[1]}",
                             "alt_copeland_any_method": None if alt.empty else "{} k={}".format(*alt["copeland"].idxmax())})
        pd.DataFrame(sens).to_csv(out / "selection_sensitivity.csv", index=False)
    fm, fk, mk = cfg["final"]["method"], cfg["final"]["k"], cfg["final"]["macro_k"]
    selection = {"rule_detailed": None if rule_detailed is None else list(rule_detailed), "rule_macro": [str(rule_macro[0]), int(rule_macro[1])],
                 "config_detailed": [fm, fk], "config_macro": [fm, mk],
                 "match": rule_detailed is not None and [fm, fk] == list(rule_detailed) and [fm, mk] == list(rule_macro), **sel,
                 "valid": not args.fast}  # без бутстрепа устойчивость не голосует и правило неприменимо
    json.dump(selection, open(out / "selection.json", "w", encoding="utf-8"), ensure_ascii=False, indent=2, default=int)
    main_lab = labels[(fm, fk)]
    macro_lab = labels[(fm, mk)]
    nest = pd.crosstab(main_lab, macro_lab)
    nestedness = float(nest.max(axis=1).sum() / n)
    log(f"выбор по правилу: детальный {rule_detailed}, макро {tuple(map(str, rule_macro))}; конфиг: {fm} k={fk}/{mk}; "
        f"совпадает: {selection['match']}; вложенность уровней {nestedness:.3f}")
    final_icvi = M.icvi(X, A_net, main_lab)
    base = M.permutation_baseline(X, A_net, main_lab, cl["permutation_reps"], seed)
    # z ориентирован по направлению индекса: > 0 — итог лучше случайного разбиения
    final_icvi["vs_random_z"] = {k: M.DIRECTIONS[k] * (final_icvi[k] - m) / s if s > 0 else None for k, (m, s) in base.items()}
    final_icvi["random_mean"] = {k: m for k, (m, s) in base.items()}
    final_icvi["CH_per_N"] = final_icvi["CH"] / n
    final_icvi["nestedness_detailed_in_macro"] = nestedness
    final_icvi["macro"] = M.icvi(X, A_net, macro_lab)
    json.dump(final_icvi, open(out / "final_icvi.json", "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    log("ICVI итога: " + ", ".join(f"{k}={final_icvi[k]:.3f}" for k in ("SW", "CH", "S_Dbw", "MQ", "AVI", "AVU", "ANUI")))

    # 4. Чувствительность к правилу рёбер ------------------------------------------------
    rule_rows = []
    for r, A in graphs.items():
        lab_r = C.kefrin(X, A, fk, seed, cl["kefrin_net_share"], cl["n_init"])
        comm = C.leiden(A, seed)
        rule_rows.append({
            "rule": r, "ARI_vs_main": adjusted_rand_score(main_lab, lab_r),
            "SW": M.icvi(X, A, lab_r)["SW"], "MQ_own_graph": M.modularity(A, lab_r),
            "leiden_communities": int(len(np.unique(comm))),
            "leiden_NMI_with_region": normalized_mutual_info_score(region, comm),
        })
    pd.DataFrame(rule_rows).set_index("rule").to_csv(out / "rules_sensitivity.csv")
    # чувствительность к числу соседей k в основной сети
    knn_rows = []
    for kk in cfg["graphs"]["k_sensitivity"]:
        A_k = G.build_graph(cfg["graphs"]["main_rule"], series=full.series, k=kk)
        lab_k = C.kefrin(X, A_k, fk, seed, cl["kefrin_net_share"], cl["n_init"])
        d = G.diagnostics(A_k, X, region, road)
        knn_rows.append({"k_nn": kk, "components": d["components"], "mean_degree": d["mean_degree"],
                         "ARI_vs_main": adjusted_rand_score(main_lab, lab_k), "SW": M.icvi(X, A_k, lab_k)["SW"],
                         "MQ_own_graph": M.modularity(A_k, lab_k)})
    pd.DataFrame(knn_rows).set_index("k_nn").to_csv(out / "knn_sensitivity.csv")
    log("чувствительность к правилу рёбер посчитана")

    # 4b. Обоснование выбора --------------------------------------------------------------
    # (а) что меняет сеть: KEFRiN против k-means при том же k. Синхронность внутри типа — доля веса
    #     рёбер основной сети, соединяющих МО одного типа; считаем для всех МО и для переназначенных.
    from sklearn.metrics import silhouette_samples, silhouette_score
    km_lab, _ = D.match_to_reference(main_lab, labels[("kmeans", fk)], fk)
    Acoo = A_net.tocoo()

    def sync_within(lab_, mask=None):
        same, w = lab_[Acoo.row] == lab_[Acoo.col], Acoo.data
        if mask is not None:
            same, w = same[mask[Acoo.row]], w[mask[Acoo.row]]
        return float(w[same].sum() / w.sum())

    moved_by_net = km_lab != main_lab
    sil_km, sil_kf = silhouette_samples(X, km_lab), silhouette_samples(X, main_lab)
    just = {"network": {
        "ari_kefrin_vs_kmeans": adjusted_rand_score(main_lab, km_lab), "reassigned": int(moved_by_net.sum()),
        "sync_within_kmeans": sync_within(km_lab), "sync_within_kefrin": sync_within(main_lab),
        "sync_within_reassigned_kmeans": sync_within(km_lab, moved_by_net),
        "sync_within_reassigned_kefrin": sync_within(main_lab, moved_by_net),
        "silhouette_reassigned_kmeans": float(sil_km[moved_by_net].mean()),
        "silhouette_reassigned_kefrin": float(sil_kf[moved_by_net].mean()),
    }}
    # (б) веса блоков признаков. Итоговые веса дают блокам примерно равные доли общего разброса;
    #     проверка: меняем вес одного блока, остальное как в итоге; смотрим оба уровня и каждый тип отдельно
    var_f = ((X - X.mean(0)) ** 2).sum(0)
    cols_f = list(full.raw.columns)
    just["block_variance_share"] = {b: float(var_f[[cols_f.index(c) for c in cs]].sum() / var_f.sum()) for b, cs in full.blocks.items()}
    ws_rows = []
    for blk, vals in cfg["features"]["weight_sensitivity"].items():
        for v in vals:
            Xs = fit_scaler(full, cfg["features"]["block_weights"] | {blk: v}).transform(full.raw)
            lab_s = C.kefrin(Xs, A_net, fk, seed, cl["kefrin_net_share"], cl["n_init"])
            lab_s4 = C.kefrin(Xs, A_net, mk, seed, cl["kefrin_net_share"], cl["n_init"])
            _, jac_s = D.match_to_reference(main_lab, lab_s, fk)
            vs = ((Xs - Xs.mean(0)) ** 2).sum(0)
            ws_rows.append({"block": blk, "weight": v, "ARI_vs_main": adjusted_rand_score(main_lab, lab_s),
                            "ARI_macro_vs_main": adjusted_rand_score(macro_lab, lab_s4),
                            "block_share": float(vs[[cols_f.index(c) for c in full.blocks[blk]]].sum() / vs.sum()),
                            "SW": float(silhouette_score(Xs, lab_s)), "external_mean": E.official_validity(lab_s, Lab)["external_mean"],
                            **{f"jaccard_type{i}": float(jac_s[i]) for i in range(fk)}})
    pd.DataFrame(ws_rows).to_csv(out / "weights_sensitivity.csv", index=False)
    # (в) типы против административного деления «вид МО» на тех же внешних метках, которых модель не видела
    kind_codes = pd.factorize(p.meta.mo_type)[0]
    ma = p.meta.market_access.to_numpy(dtype=float)
    just["admin"] = {name: E.official_validity(lab_, Lab) | {"eta2_market_access": M.eta_squared(ma, lab_), "groups": int(lab_.max() + 1)}
                     for name, lab_ in (("types", main_lab), ("mo_kind", kind_codes))}
    json.dump(just, open(out / "justification.json", "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    log(f"обоснование: сеть переназначила {just['network']['reassigned']} МО; веса блоков — ARI "
        + ", ".join(f"{r['block']}={r['weight']}: {r['ARI_vs_main']:.2f}" for r in ws_rows))

    # 5. Динамика: 13 скользящих окон -----------------------------------------------------
    L = cfg["windows"]["length"]
    starts = window_starts(T, L, cfg["windows"]["step"])
    P_main = C.kefrin_network_block(A_net)
    rho = C.rho_for_share(X, P_main, cl["kefrin_net_share"])
    prev = main_lab
    win_labels, win_conf, win_rows, win_feats = [], [], [], []
    for s in starts:
        wf = window_features(p, s, L, cfg["features"]["summer_months"])
        Xw = scaler.transform(wf.raw)
        Aw = G.build_graph(cfg["graphs"]["main_rule"], series=wf.series, k=k_nn)
        # старт от основных типов (якорь), а не от предыдущего окна: ошибки не накапливаются
        lab_w, conf_w = D.warm_kmeans(D.kefrin_space(Xw, Aw, rho), main_lab, fk)
        lab_w, jac = D.match_to_reference(main_lab, lab_w, fk)
        win_labels.append(lab_w)
        win_conf.append(conf_w)
        win_feats.append(wf.raw)
        win_rows.append({"window_end": wf.months[-1], "SW": M.icvi(Xw, Aw, lab_w)["SW"],
                         "MQ": M.modularity(Aw, lab_w), "ARI_prev": adjusted_rand_score(prev, lab_w),
                         "min_jaccard_to_main": float(jac.min()), "mean_jaccard_to_main": float(jac.mean())})
        prev = lab_w
    WL = np.column_stack(win_labels)
    ends = [r["window_end"] for r in win_rows]
    pd.DataFrame(win_rows).set_index("window_end").to_csv(out / "dynamics_windows.csv")
    tr = D.transitions(WL[:, 0], WL[:, -1], fk)
    tr.to_csv(out / "transitions_first_last.csv")
    CONF = np.column_stack(win_conf)
    # значимые переходы: уверенная принадлежность в непересекающихся окнах 2023 и 2024
    tau = cfg["windows"]["confidence_tau"]
    moved = D.confident_moves(WL[:, 0], WL[:, -1], CONF[:, 0], CONF[:, -1], tau)
    sens = [{"tau": t, "changed_type": int((WL[:, 0] != WL[:, -1]).sum()),
             "confident_moves": int(D.confident_moves(WL[:, 0], WL[:, -1], CONF[:, 0], CONF[:, -1], t).sum()),
             "persistent_3_windows": int(D.persistent_moves(WL, run=3).sum())} for t in (0.0, 0.05, 0.1, 0.15, 0.2, 0.25, 0.3)]
    pd.DataFrame(sens).to_csv(out / "moves_sensitivity.csv", index=False)
    TCm = D.transitions(WL[:, 0][moved], WL[:, -1][moved], fk)
    TCm.to_csv(out / "transitions_confident.csv")
    # асимметрия встречных значимых потоков: при чистом «шуме на границе» потоки A->B и B->A равновероятны
    from scipy.stats import binomtest
    asym = []
    for a_ in range(fk):
        for b_ in range(a_ + 1, fk):
            x, y = int(TCm.iloc[a_, b_]), int(TCm.iloc[b_, a_])
            if x + y >= 10:
                asym.append({"from": a_, "to": b_, "forward": x, "backward": y,
                             "p_binomial_two_sided": float(binomtest(x, x + y, 0.5).pvalue)})
    json.dump(asym, open(out / "dynamics_asymmetry.json", "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    log(f"динамика: {len(starts)} окон; сменили тип {int((WL[:, 0] != WL[:, -1]).sum())}, значимо (tau={tau}) {int(moved.sum())} МО")

    # 6. Профили типов и выгрузки ---------------------------------------------------------
    prof = I.cluster_profiles(p, full.raw, X, main_lab).join(E.type_label_profile(main_lab, Lab).add_prefix("official:"))
    prof.to_csv(out / "types_profiles.csv", encoding="utf-8")
    prof_macro = I.cluster_profiles(p, full.raw, X, macro_lab).join(E.type_label_profile(macro_lab, Lab).add_prefix("official:"))
    prof_macro.to_csv(out / "macro_profiles.csv", encoding="utf-8")
    assign = p.meta[["name", "region", "mo_type", "oktmo"]].copy()
    assign["type_main"] = main_lab
    assign["macro_type"] = macro_lab
    for j, e in enumerate(ends):
        assign[f"type_{e}"] = WL[:, j]
    assign["confidence_2023"] = CONF[:, 0]
    assign["confidence_2024"] = CONF[:, -1]
    assign["significant_move"] = moved
    assign.to_csv(out / "assignments.csv", encoding="utf-8")

    ext = {
        "cramers_v_mo_type": M.cramers_v(main_lab, p.meta.mo_type.to_numpy()),
        "cramers_v_region": M.cramers_v(main_lab, region),
        "eta2_market_access": M.eta_squared(p.meta.market_access.to_numpy(dtype=float), main_lab),
        **E.official_validity(main_lab, Lab),
    }
    json.dump(ext, open(out / "external_validation.json", "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    log("внешняя проверка: " + json.dumps({k: round(v, 3) for k, v in ext.items()}, ensure_ascii=False))

    state = {"panel": p, "full": full, "X": X, "graphs": graphs, "main_lab": main_lab, "WL": WL,
             "macro_lab": macro_lab, "prof_macro": prof_macro, "labels_official": Lab, "selection": selection,
             "ends": ends, "win_feats": win_feats, "moved": moved, "conf": CONF, "prof": prof, "comp": comp, "cfg": cfg}
    if cfg["output"].get("site_data_dir"):
        from smc.export_web import export_site
        export_site(state)
        log("данные лендинга выгружены")
    (out / "run_log.txt").write_text("\n".join(LOG), encoding="utf-8")


if __name__ == "__main__":
    main()
