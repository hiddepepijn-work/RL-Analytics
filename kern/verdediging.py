"""Verdedigende touches beoordelen met het dreigingsmodel (kern/dreiging.py).

Per touch van een speler: dreiging van de tegenstander vlak vóór de touch tegenover kort erna. 'Erna' = 1 s later,
of vlak vóór de volgende touch als die eerder komt (dan zie je waar de bal terechtkwam, bv. recht op een
tegenstander). Valt er binnen die tijd een tegengoal, dan is de dreiging erna 1.

Alleen touches waar iets op het spel stond (dreiging vóór of erna ≥ DREMPEL) worden bewaard.
"""
from __future__ import annotations

import bisect
from functools import cache

import numpy as np

from kern import dreiging
from kern.kansen import _stand, _tijd, sleutel

DREMPEL = 0.05
NA = 1.0


@cache
def _model():
    import joblib
    return joblib.load(dreiging.MODEL_PAD) if dreiging.MODEL_PAD.exists() else None


def _bal_snelheid(data: dict, t: float) -> np.ndarray:
    ts = data["t"]
    f = min(len(ts) - 1, max(0, bisect.bisect_left(ts, t)))
    g = max(0, f - 2)
    a, b = data["bal"][g * 7: g * 7 + 3], data["bal"][f * 7: f * 7 + 3]
    if not any(a) or not any(b) or f == g:
        return np.zeros(3)
    v = (np.array(b, float) - np.array(a, float)) / max(ts[f] - ts[g], 1e-3)
    return v if np.linalg.norm(v) < 7000 else np.zeros(3)


def _situatie(data: dict, t: float, aanvaller: int) -> dict | None:
    bp, autos = _stand(data, t)
    if not np.any(bp):
        return None
    autos = autos.copy(); autos[:, 6] /= 2.55  # dreigingsmodel verwacht boost in %
    teams = [s["team"] for s in data["spelers"]]
    return dreiging.features(bp, _bal_snelheid(data, t), autos, teams, aanvaller)


def beoordeel(data: dict, events: list[dict]) -> list[dict]:
    """→ [{tijd, speler, voor, na}] voor touches waar dreiging (van de tegenstander) op het spel stond."""
    pakket = _model()
    if pakket is None:
        return []
    team = {s["id"]: s["team"] for s in data["spelers"]}
    touches = sorted((_tijd(e), sleutel(e["meta"].get("primary_player"))) for e in events if e["meta"]["stream"] == "touch")
    goals = [(_tijd(e), 0 if e["meta"].get("team_is_team_0") else 1) for e in events if e["meta"]["stream"] == "goal_context"]
    kandidaten = []
    for k, (t, wie) in enumerate(touches):
        if wie not in team:
            continue
        a = 1 - team[wie]
        volgende = next((x for x, _ in touches[k + 1:] if x > t + 0.1), t + NA)
        t1 = max(t + 0.15, min(t + NA, volgende - 0.05))
        voor, na = _situatie(data, t - 0.05, a), _situatie(data, t1, a)
        if voor is None or na is None:
            continue
        goal_na = any(gt == a and t < g <= t1 + 0.3 for g, gt in goals)
        kandidaten.append((t, wie, voor, na, goal_na))
    if not kandidaten:
        return []
    p = dreiging.voorspel(pakket, [x for _, _, v, n, _ in kandidaten for x in (v, n)]).reshape(-1, 2)
    uit = []
    for (t, wie, _, _, goal_na), (pv, pn) in zip(kandidaten, p):
        pn = 1.0 if goal_na else pn
        if pv >= DREMPEL or pn >= DREMPEL:
            uit.append({"tijd": round(t, 2), "speler": wie, "voor": round(float(pv), 3), "na": round(float(pn), 3)})
    return uit
