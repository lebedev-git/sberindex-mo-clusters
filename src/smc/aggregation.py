"""Правила агрегирования индексов качества: какая конфигурация «метод × k» лучше по совокупности ICVI.

Конфигурации — кандидаты, индексы (SW, CH, S_Dbw, MQ, AVI, AVU, устойчивость) — избиратели. Каждый
индекс упорядочивает кандидатов; правило сводит семь порядков в один. Если победитель не зависит от
правила, выбор не является артефактом способа голосования.

  copeland  — Коупленд: попарные сравнения большинством, счёт = победы − поражения;
  borda     — Борда: сумма мест (кандидат получает число соперников, которых индекс ставит ниже;
              при равенстве — половина), учитывает не только знак, но и глубину перевеса;
  schulze   — Шульце (Schulze, Social Choice and Welfare 36:267–303, 2011): сила сильнейшего пути в
              графе попарных перевесов, победитель не проигрывает никому по силе пути;
  threshold — пороговое правило (Aleskerov, Yakuba, Yuzbashev, Math. Social Sciences 53:106–110, 2007;
              Aleskerov, Chistyakov, Kalyagin, Economics Letters 107:261–262, 2010): каждый индекс
              ставит кандидату оценку из m градаций; лучше тот, у кого меньше худших оценок, при
              равенстве — меньше вторых с конца и т. д. Некомпенсаторное: высокий балл по одному индексу
              не покупает провал по другому. Градации — равные по числу кандидатов части порядка индекса.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def _scores(df: pd.DataFrame, directions: dict[str, int]) -> np.ndarray:
    """Матрица [кандидат, избиратель]: больше — лучше для всех индексов."""
    cols = [c for c in directions if c in df and df[c].notna().all()]
    return np.column_stack([df[c].to_numpy(dtype=float) * directions[c] for c in cols])


def _pairwise(V: np.ndarray) -> np.ndarray:
    """d[a, b] — число избирателей, ставящих a строго выше b."""
    return (V[:, None, :] > V[None, :, :]).sum(2)


def copeland(df: pd.DataFrame, directions: dict[str, int]) -> pd.Series:
    """Правило Коупленда: конфигурация A побеждает B, если лучше по большинству метрик.
    Счёт = победы − поражения. Метрики — «избиратели», конфигурации — «кандидаты»."""
    d = _pairwise(_scores(df, directions))
    return pd.Series(np.sign(d - d.T).sum(1).astype(float), index=df.index, name="copeland")


def borda(df: pd.DataFrame, directions: dict[str, int]) -> pd.Series:
    V = _scores(df, directions)
    pts = (V[:, None, :] > V[None, :, :]).sum(1) + 0.5 * ((V[:, None, :] == V[None, :, :]).sum(1) - 1)
    return pd.Series(pts.sum(1), index=df.index, name="borda")


def schulze(df: pd.DataFrame, directions: dict[str, int]) -> pd.Series:
    """Счёт Шульце = число соперников, которых кандидат бьёт по силе сильнейшего пути (победитель — максимум)."""
    d = _pairwise(_scores(df, directions)).astype(float)
    p = np.where(d > d.T, d, 0.0)
    for i in range(len(p)):  # Флойд–Уоршелл для путей наибольшей ширины
        p = np.maximum(p, np.minimum(p[:, [i]], p[[i], :]))
    np.fill_diagonal(p, 0)
    return pd.Series((p > p.T).sum(1).astype(float), index=df.index, name="schulze")


def threshold(df: pd.DataFrame, directions: dict[str, int], grades: int = 3) -> pd.Series:
    """Пороговое правило: лексикографическое сравнение векторов (v_1, …, v_{m−1}), v_j — число индексов,
    давших кандидату j-ю снизу оценку; меньше — лучше. Возвращает счёт: больше — лучше (ранг по порядку)."""
    V = _scores(df, directions)
    n = len(V)
    rank = V.argsort(0).argsort(0)                       # 0 — худший у данного индекса
    g = np.minimum(rank * grades // n, grades - 1)       # оценка 0 (худшая) … m−1 (лучшая)
    counts = np.stack([(g == j).sum(1) for j in range(grades - 1)], 1)
    order = np.lexsort(counts.T[::-1])                   # по v_1, затем v_2, …: первый — лучший
    score = np.empty(n)
    score[order] = np.arange(n, 0, -1)
    # равные векторы — равный счёт
    keys = [tuple(r) for r in counts]
    best = {}
    for i in order:
        best.setdefault(keys[i], score[i])
    return pd.Series([float(best[k]) for k in keys], index=df.index, name="threshold")


RULES = {"copeland": copeland, "borda": borda, "schulze": schulze, "threshold": threshold}
RULE_NAMES = {"copeland": "Коупленд", "borda": "Борда", "schulze": "Шульце", "threshold": "Пороговое"}


def table(el: pd.DataFrame, directions: dict[str, int], detailed_for, final_macro: tuple, threshold_grades=(3, 5)) -> pd.DataFrame:
    """Правило × (победители макроуровня с учётом ничьих, детальный уровень по тому же правилу выбора,
    место итоговой конфигурации). detailed_for(method) -> (method, k) | None."""
    runs = [(r, None) for r in ("copeland", "borda", "schulze")] + [("threshold", g) for g in threshold_grades]
    rows = []
    for r, g in runs:
        s = RULES[r](el, directions) if g is None else threshold(el, directions, g)
        top = [tuple(x) for x in s[s == s.max()].index]
        det = [detailed_for(m) for m, _ in top]
        rank = int((s > s.loc[final_macro]).sum() + 1)
        rows.append({"rule": r, "grades": g, "rule_name": RULE_NAMES[r] + ("" if g is None else f" (m = {g})"),
                     "macro_winners": "; ".join(f"{m} k={k}" for m, k in top),
                     "detailed": "; ".join("—" if d is None else f"{d[0]} k={d[1]}" for d in det),
                     "ties": len(top), "final_rank": rank, "final_is_winner": tuple(final_macro) in top,
                     "final_unique_winner": top == [tuple(final_macro)]})
    return pd.DataFrame(rows)


def _selftest() -> None:
    # кондорсе-победитель A: все правила должны выбрать его
    df = pd.DataFrame({"x": [3, 2, 1], "y": [3, 1, 2], "z": [2, 3, 1]}, index=list("ABC"))
    dirs = {"x": 1, "y": 1, "z": 1}
    for f in RULES.values():
        assert f(df, dirs).idxmax() == "A", f.__name__
    # пороговое правило некомпенсаторно: B без худших оценок лучше A с одной худшей
    df2 = pd.DataFrame({"x": [9, 5, 1], "y": [9, 5, 1], "z": [0, 5, 9]}, index=list("ABC"))
    assert threshold(df2, dirs).idxmax() == "B"
    print("aggregation: самотест пройден")


if __name__ == "__main__":
    _selftest()
