"""Balacties beoordelen met het dreigingsmodel (kern/dreiging.py): waarde van elke touch + verdedigende stats.

Per touch van een speler: dreiging van de tegenstander vlak vóór de touch tegenover kort erna. 'Erna' = 1 s later,
of vlak vóór de volgende touch als die eerder komt (dan zie je waar de bal terechtkwam, bv. recht op een
tegenstander). Valt er binnen die tijd een tegengoal, dan is de dreiging erna 1.

Alle touches worden bewaard, met de dreiging voor beide teams; de verdedigende stats tellen alleen touches waar
iets op het spel stond (dreiging ≥ DREMPEL).
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


def _situatie(data: dict, t: float, aanvaller: int, zonder: int | None = None) -> dict | None:
    """Features van de spelsituatie op tijd t; zonder = index van een speler die we weghalen (demo-tegenfeitelijk)."""
    bp, autos = _stand(data, t)
    if not np.any(bp):
        return None
    autos = autos.copy(); autos[:, 6] /= 2.55  # dreigingsmodel verwacht boost in %
    if zonder is not None:
        autos[zonder] = 0  # afwezig: het model kent dat uit de training (gedemode spelers)
    teams = [s["team"] for s in data["spelers"]]
    return dreiging.features(bp, _bal_snelheid(data, t), autos, teams, aanvaller)


def beoordeel(data: dict, events: list[dict]) -> list[dict]:
    """→ per touch [{tijd, speler, voor, na, eigen_voor, eigen_na}]: dreiging van de tegenstander (voor/na) en van
    het eigen team (eigen_voor/eigen_na) vlak vóór de touch en kort erna. Basis voor de waarde van elke balactie
    (kern/rating.py) en de verdedigende stats (alleen touches met dreiging ≥ DREMPEL)."""
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
        eigen, a = team[wie], 1 - team[wie]
        volgende = next((x for x, _ in touches[k + 1:] if x > t + 0.1), t + NA)
        t1 = max(t + 0.15, min(t + NA, volgende - 0.05))
        sit = [_situatie(data, t - 0.05, a), _situatie(data, t1, a), _situatie(data, t - 0.05, eigen), _situatie(data, t1, eigen)]
        if any(x is None for x in sit):
            continue
        goal = {g_t: any(gt == g_t and t < g <= t1 + 0.3 for g, gt in goals) for g_t in (eigen, a)}
        kandidaten.append((t, wie, sit, goal[a], goal[eigen]))
    if not kandidaten:
        return []
    p = dreiging.voorspel(pakket, [x for _, _, sit, _, _ in kandidaten for x in sit]).reshape(-1, 4)
    uit = []
    for (t, wie, _, goal_tegen, goal_eigen), (pv, pn, ev, en) in zip(kandidaten, p):
        uit.append({"tijd": round(t, 2), "speler": wie, "voor": round(float(pv), 3), "na": round(1.0 if goal_tegen else float(pn), 3),
                    "eigen_voor": round(float(ev), 3), "eigen_na": round(1.0 if goal_eigen else float(en), 3)})
    return uit


def fysiek(data: dict, ruwe_events: list[dict]) -> list[dict]:
    """Demo's en bumps op een tegenstander, met hun tactische waarde volgens het dreigingsmodel.

    Demo: tegenfeitelijk op het moment van de demo — (dreiging eigen team zonder slachtoffer − met slachtoffer) +
    (dreiging tegenstander met − zonder). Een demo op de keeper tijdens je aanval of op de aanvaller die op de bal
    afgaat is veel waard; een demo op het middenveld zonder bal in de buurt bijna niets.
    Bump: haalt niemand weg maar duwt uit positie; waarde = verandering van dezelfde balans in de seconde erna.
    → [{tijd, speler, slachtoffer, soort, waarde}]"""
    pakket = _model()
    if pakket is None:
        return []
    idx = {s["id"]: i for i, s in enumerate(data["spelers"])}
    team = {s["id"]: s["team"] for s in data["spelers"]}
    kand = []
    for e in ruwe_events:
        st, pl = e["meta"]["stream"], (e.get("payload") or {}).get("payload") or {}
        t = pl.get("time") or e["meta"]["timing"].get("time", 0)
        if st == "demolition":
            a, v = sleutel(pl.get("attacker")), sleutel(pl.get("victim"))
        elif st == "bump" and not pl.get("is_team_bump") and (pl.get("confidence") or 0) >= 0.5:
            a, v = sleutel(pl.get("initiator")), sleutel(pl.get("victim"))
        else:
            continue
        if a not in team or v not in team or team[a] == team[v]:
            continue
        eigen, tegen = team[a], 1 - team[a]
        if st == "demolition":
            sit = [_situatie(data, t - 0.1, eigen), _situatie(data, t - 0.1, eigen, idx[v]),
                   _situatie(data, t - 0.1, tegen), _situatie(data, t - 0.1, tegen, idx[v])]
        else:
            sit = [_situatie(data, t - 0.1, eigen), _situatie(data, t + NA, eigen),
                   _situatie(data, t - 0.1, tegen), _situatie(data, t + NA, tegen)]
        if any(x is None for x in sit):
            continue
        kand.append((t, a, v, "demo" if st == "demolition" else "bump", sit))
    if not kand:
        return []
    p = dreiging.voorspel(pakket, [x for *_, sit in kand for x in sit]).reshape(-1, 4)
    # [eigen met/voor, eigen zonder/na, tegen met/voor, tegen zonder/na] → winst eigen + verlies tegenstander
    return [{"tijd": round(t, 2), "speler": a, "slachtoffer": v, "soort": soort,
             "waarde": round(float((q[1] - q[0]) + (q[2] - q[3])), 3)} for (t, a, v, soort, _), q in zip(kand, p)]
