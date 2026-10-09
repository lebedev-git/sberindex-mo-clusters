"""Объяснимые типы: пороговое дерево IMM (Dasgupta, Frost, Moshkovitz, Rashtchian,
«Explainable k-Means and k-Medians Clustering», ICML 2020).

Дерево с k листьями и k − 1 порогами вида «признак ≤ θ». Строится сверху вниз: в узле с набором
центров (≥ 2) выбирается признак и порог, которые разделяют хотя бы два центра и дают наименьшее
число «ошибок» — МО, которые уходят в другую сторону, чем центр их типа. Ошибочные МО дальше не
рассматриваются (как в статье). Лист = один центр = один тип. Центры — средние типов KEFRiN в
пространстве девяти признаков; эталонные метки — сами типы KEFRiN (в статье — ближайший центр k-means).
Точность совпадения (fidelity) — доля МО, которых дерево относит к их типу.
"""
from __future__ import annotations

import numpy as np


def _best_split(X: np.ndarray, y: np.ndarray, centers: np.ndarray, cids: list[int]):
    """(ошибки, признак, порог) с наименьшим числом ошибок; порог — середина между соседними значениями."""
    best = None
    C = centers[cids]
    cy = centers[y]                                    # координаты центра своего типа для каждой точки
    for f in range(X.shape[1]):
        lo, hi = C[:, f].min(), C[:, f].max()
        if hi <= lo:
            continue
        vals = np.unique(np.concatenate([X[:, f], C[:, f]]))
        cand = (vals[:-1] + vals[1:]) / 2
        cand = cand[(cand >= lo) & (cand < hi)]       # порог обязан разделить центры
        if not len(cand):
            continue
        # ошибки(θ) = #{x_f ≤ θ < c_f} + #{c_f ≤ θ < x_f} — через отсортированные массивы
        xs, cs = X[:, f], cy[:, f]
        lo_pt, hi_pt = np.minimum(xs, cs), np.maximum(xs, cs)
        mis = np.searchsorted(np.sort(lo_pt), cand, side="right") - np.searchsorted(np.sort(hi_pt), cand, side="right")
        i = int(np.argmin(mis))
        if best is None or mis[i] < best[0]:
            best = (int(mis[i]), f, float(cand[i]))
    return best


def imm_tree(X: np.ndarray, y: np.ndarray, centers: np.ndarray) -> dict:
    """Узел: {"leaf": тип} или {"feature": f, "threshold": θ, "le": узел, "gt": узел, "mistakes": m}."""
    def build(idx: np.ndarray, cids: list[int]) -> dict:
        if len(cids) == 1:
            return {"leaf": cids[0]}
        sub = idx[np.isin(y[idx], cids)]
        m, f, t = _best_split(X[sub], y[sub], centers, cids)
        left = [c for c in cids if centers[c, f] <= t]
        right = [c for c in cids if centers[c, f] > t]
        ok = (X[sub, f] <= t) == (centers[y[sub], f] <= t)   # ошибки дальше не участвуют
        keep = sub[ok]
        return {"feature": f, "threshold": t, "mistakes": m,
                "le": build(keep[X[keep, f] <= t], left), "gt": build(keep[X[keep, f] > t], right)}
    return build(np.arange(len(X)), sorted(set(int(c) for c in np.unique(y))))


def predict(tree: dict, X: np.ndarray) -> np.ndarray:
    out = np.empty(len(X), dtype=int)
    for i, x in enumerate(X):
        node = tree
        while "leaf" not in node:
            node = node["le"] if x[node["feature"]] <= node["threshold"] else node["gt"]
        out[i] = node["leaf"]
    return out


def paths(tree: dict) -> dict[int, list[tuple[int, str, float]]]:
    """Тип -> список условий (признак, '<=' | '>', порог) от корня к листу."""
    out = {}

    def walk(node, cond):
        if "leaf" in node:
            out[node["leaf"]] = cond
            return
        walk(node["le"], cond + [(node["feature"], "<=", node["threshold"])])
        walk(node["gt"], cond + [(node["feature"], ">", node["threshold"])])
    walk(tree, [])
    return out


def depth(tree: dict) -> int:
    return 0 if "leaf" in tree else 1 + max(depth(tree["le"]), depth(tree["gt"]))


# Признаки в исходных единицах (до масштабирования): лог-отношения к медиане страны и сезонные отклонения.
# Пороговое дерево инвариантно к монотонному линейному масштабу признака, поэтому строится прямо на них.
SUBJECT = {
    "level": "траты на жителя",
    "profile:Продовольствие": "вес продуктов в корзине", "profile:Здоровье": "вес трат на здоровье в корзине",
    "profile:Общественное питание": "вес общепита в корзине", "profile:Транспорт": "вес транспорта в корзине",
    "profile:Маркетплейсы": "вес маркетплейсов в корзине",
    "season_amp": "сезонные колебания трат сверх общероссийских",
    "summer_all": "летний прирост трат сверх общероссийского",
    "summer_food_service": "летний прирост трат в общепите сверх общероссийского",
}


def _pct(v: float, signed: bool = False) -> str:
    s = f"{v * 100:{'+' if signed else ''}.{1 if abs(v) < 0.1 else 0}f}%"
    return s.replace(".", ",").replace("-", "−")


def _value(feature: str, t: float) -> str:
    if feature == "level" or feature.startswith("profile:"):
        return f"{np.exp(t) * 100:.0f}% медианы России"     # лог-отношение -> доля от медианы
    if feature == "season_amp":
        return _pct(t) + " (ст. откл. по месяцам)"
    return _pct(np.expm1(t), signed=True)


def describe(path: list[tuple[int, str, float]], cols: list[str]) -> list[str]:
    """Условия пути -> фразы; несколько порогов по одному признаку сводятся в интервал."""
    lo, hi, order = {}, {}, []
    for f, op, t in path:
        name = cols[f]
        order += [name] if name not in order else []
        if op == ">":
            lo[name] = max(lo.get(name, -np.inf), t)
        else:
            hi[name] = min(hi.get(name, np.inf), t)
    out = []
    for name in order:
        s = SUBJECT.get(name, name)
        if name in lo and name in hi:
            out.append(f"{s} — от {_value(name, lo[name]).replace(' медианы России', '')} до {_value(name, hi[name])}")
        elif name in lo:
            out.append(f"{s} выше {_value(name, lo[name])}" if not name.startswith("summer") else f"{s} больше {_value(name, lo[name])}")
        else:
            out.append(f"{s} не выше {_value(name, hi[name])}" if not name.startswith("summer") else f"{s} не больше {_value(name, hi[name])}")
    return out


def explain_types(raw, lab: np.ndarray, seed: int) -> dict:
    """IMM на исходных признаках + сравнение с деревьями CART той же сложности."""
    from sklearn.tree import DecisionTreeClassifier

    cols = list(raw.columns)
    R = raw.to_numpy(dtype=float)
    k = int(lab.max() + 1)
    centers = np.vstack([R[lab == c].mean(0) for c in range(k)])
    tree = imm_tree(R, lab, centers)
    pred = predict(tree, R)
    P = paths(tree)
    types = [{"type": c, "n": int((lab == c).sum()), "fidelity": float((pred[lab == c] == c).mean()),
              "precision": float((lab[pred == c] == c).mean()) if (pred == c).any() else None,
              "rules": describe(P[c], cols),
              "conditions": [{"feature": cols[f], "op": op, "threshold": t} for f, op, t in P[c]]} for c in range(k)]
    cart = {name: float(DecisionTreeClassifier(random_state=seed, **kw).fit(R, lab).score(R, lab))
            for name, kw in (("depth3", {"max_depth": 3}), ("leaves_k", {"max_leaf_nodes": k}))}
    return {"method": "IMM (Dasgupta et al., ICML 2020), k − 1 порогов, центры — средние типов KEFRiN",
            "fidelity": float((pred == lab).mean()), "depth": depth(tree), "thresholds": k - 1,
            "cart_fidelity": cart, "types": types}


def _selftest() -> None:
    rng = np.random.default_rng(0)
    centers = np.array([[0, 0], [5, 0], [0, 5]], dtype=float)
    y = rng.integers(0, 3, 600)
    X = centers[y] + rng.normal(0, 0.5, (600, 2))
    t = imm_tree(X, y, centers)
    assert (predict(t, X) == y).mean() > 0.99 and depth(t) == 2 and len(paths(t)) == 3
    print("explain: самотест пройден")


if __name__ == "__main__":
    _selftest()
