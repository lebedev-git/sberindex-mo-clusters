"""События кластеров между соседними окнами: внешние переходы MONIC (Spiliopoulou, Ntoutsi, Theodoridis,
Schult, «MONIC — Modeling and Monitoring Cluster Transitions», KDD 2006).

Перекрытие overlap(X, Y) = |X ∩ Y| / |X| (все МО с равным весом). Для кластера X окна t:
  survive   — есть единственный Y в t+1 с overlap(X, Y) ≥ τ, и никакой другой кластер окна t не
              переходит в Y с перекрытием ≥ τ;
  absorb    — overlap(X, Y) ≥ τ, но в тот же Y с перекрытием ≥ τ переходит ещё хотя бы один кластер;
  split     — ни один Y не набирает τ, но части с overlap ≥ τ_split вместе покрывают ≥ τ;
  disappear — ни одно из перечисленного.
Кластер Y окна t+1, не ставший целью survive/absorb/split, — emerge.
Внутренние переходы (MONIC): рост или сжатие кластера, если размер меняется больше чем на size_delta.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def transitions(a: np.ndarray, b: np.ndarray, tau: float, tau_split: float, size_delta: float) -> list[dict]:
    ka, kb = np.unique(a), np.unique(b)
    O = np.array([[np.mean(b[a == x] == y) for y in kb] for x in ka])   # overlap(X, Y)
    out, targets = [], set()
    for xi, x in enumerate(ka):
        strong = np.where(O[xi] >= tau)[0]
        if len(strong):
            y = int(strong[np.argmax(O[xi, strong])])
            others = [int(ka[i]) for i in np.where(O[:, y] >= tau)[0] if i != xi]
            ev = "absorb" if others else "survive"
            targets.add(y)
            sx, sy = int((a == x).sum()), int((b == kb[y]).sum())
            internal = "grow" if sy > sx * (1 + size_delta) else "shrink" if sy < sx * (1 - size_delta) else ""
            out.append({"event": ev, "type": int(x), "to": [int(kb[y])], "overlap": float(O[xi, y]),
                        "size_from": sx, "size_to": sy, "internal": internal, "with": others})
            continue
        parts = np.where(O[xi] >= tau_split)[0]
        if len(parts) >= 2 and O[xi, parts].sum() >= tau:
            targets.update(int(p) for p in parts)
            out.append({"event": "split", "type": int(x), "to": [int(kb[p]) for p in parts],
                        "overlap": float(O[xi, parts].sum()), "size_from": int((a == x).sum()), "size_to": None, "internal": "", "with": []})
        else:
            out.append({"event": "disappear", "type": int(x), "to": [], "overlap": float(O[xi].max()),
                        "size_from": int((a == x).sum()), "size_to": None, "internal": "", "with": []})
    for yi, y in enumerate(kb):
        if yi not in targets:
            out.append({"event": "emerge", "type": int(y), "to": [], "overlap": float(O[:, yi].max()),
                        "size_from": None, "size_to": int((b == y).sum()), "internal": "", "with": []})
    return out


def monic(WL: np.ndarray, ends: list[str], tau: float, tau_split: float, size_delta: float) -> pd.DataFrame:
    rows = []
    for t in range(1, WL.shape[1]):
        for r in transitions(WL[:, t - 1], WL[:, t], tau, tau_split, size_delta):
            rows.append({"window_from": ends[t - 1], "window": ends[t], **r})
    return pd.DataFrame(rows)


def _selftest() -> None:
    a = np.array([0] * 50 + [1] * 50 + [2] * 50)
    b = np.array([0] * 50 + [1] * 17 + [3] * 17 + [4] * 16 + [0] * 50)   # 1 раскололся на три, 2 поглощён нулём
    ev = {r["type"]: r["event"] for r in transitions(a, b, 0.5, 0.25, 0.05) if r["event"] != "emerge"}
    assert ev == {0: "absorb", 1: "split", 2: "absorb"}, ev
    print("events: самотест пройден")


if __name__ == "__main__":
    _selftest()
