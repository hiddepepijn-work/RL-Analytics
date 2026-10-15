"""Kansen die geen schot werden, gecreëerde kansen en fouten die tot een tegengoal leiden.

Kans-xG: bij een whiff op de aanvalshelft schieten we een denkbeeldig schot vanaf de bal richting doelmidden
(1800 uu/s, boog die het doel haalt) en laten het xG-model beoordelen hoe groot die kans was, met de echte
posities van verdedigers en aanvallers op dat moment. Een open-net-whiff krijgt zo een hoge kans-xG.

Kans vóór de touch: hetzelfde denkbeeldige schot, maar dan vanaf waar de bal lag vlak vóór een echt schot. Het verschil
met de xG ná de touch is de uitvoering van de schutter (hard, goed geplaatst = xG omhoog).

Gecreëerde kans (xA): laatste teamgenoot die de bal raakte binnen 4 s vóór een schot of kans-whiff. xA = de kans vóór
de touch van de schutter, zodat een goed uitgevoerd schot niet aan de passer wordt toegerekend.

Fout voor tegengoal (Opta: 'error leading to goal'): de laatste whiff of het laatste balverlies van het verdedigende
team vóór de aanval waaruit de goal valt (max. 12 s ervoor, na de laatste kickoff). Niet als fout: een touch in de
eigen derde (wegwerken onder druk), een geblokt/gered eigen schot, en een whiff in de laatste seconde (mislukte redding).
"""
from __future__ import annotations

import bisect
import json
from functools import cache
from pathlib import Path

import numpy as np

from kern.schoten import DOEL_Y, ZWAARTEKRACHT, schot_features

KANS_SNELHEID = 1800.0
KANS_MIN_XG = 0.10      # whiff telt pas als gemiste kans vanaf deze kans-xG
GROTE_KANS = 0.35       # 'big chance' (Opta gebruikt ~0,35–0,4)
CREATIE_VENSTER = 4.0
FOUT_VENSTER = 12.0
SPELER_STRIDE = 9
KALIBRATIE_PAD = Path(__file__).resolve().parent.parent / "data" / "modellen" / "kans_kalibratie.json"


@cache
def _kalibratie() -> tuple[float, float]:
    if KALIBRATIE_PAD.exists():
        k = json.loads(KALIBRATIE_PAD.read_text(encoding="utf-8"))
        return k["a"], k["b"]
    return 1.0, 0.0


def verwacht(ruw: float) -> float:
    """Ruwe kans (perfect gericht denkbeeldig schot) → verwachte xG van een echt schot uit die situatie.
    Lineaire fit op echte schoten (kern/kans_kalibratie.py); het denkbeeldige schot is te optimistisch."""
    a, b = _kalibratie()
    return round(float(min(0.99, max(0.001, a * ruw + b))), 3)


def sleutel(pid):
    if not pid:
        return None
    (k, v), = pid.items()
    return f"{k}:{v}"


def _tijd(e):
    tm = e["meta"]["timing"]
    return tm.get("time", tm.get("start_time", tm.get("end_time", 0)))


def _stand(data: dict, t: float):
    """Bal + auto's ([speler, 7] zoals in schoten.py: pos, snelheid, boost ruw) op tijd t.
    Snelheid uit het verschil met 2 frames eerder (de JSON bewaart geen snelheden)."""
    f = min(len(data["t"]) - 1, max(0, bisect.bisect_left(data["t"], t)))
    g = max(0, f - 2)
    dt = max(data["t"][f] - data["t"][g], 1e-3)
    bal = np.array(data["bal"][f * 7: f * 7 + 3], dtype=float)
    autos = np.zeros((len(data["spelers"]), 7))
    for i, s in enumerate(data["spelers"]):
        r = s["frames"][f * SPELER_STRIDE: (f + 1) * SPELER_STRIDE]
        q = s["frames"][g * SPELER_STRIDE: g * SPELER_STRIDE + 3]
        autos[i, :3] = r[:3]
        if any(r[:3]) and any(q) and f > g:
            v = (np.array(r[:3], float) - np.array(q, float)) / dt
            autos[i, 3:6] = v if np.linalg.norm(v) < 3000 else 0  # sprong (respawn) → geen snelheid
        autos[i, 6] = r[7] * 2.55
    return bal, autos


def denkbeeldig_schot(bp: np.ndarray, team: int) -> np.ndarray:
    """Balsnelheid voor een schot vanaf bp naar doelmidden (z ≈ 300) met vaste horizontale snelheid."""
    richting = 1 if team == 0 else -1
    doel = np.array([0.0, richting * (DOEL_Y + 50), 300.0])
    vlak = doel[:2] - bp[:2]
    d = float(np.linalg.norm(vlak)) or 1.0
    t = d / KANS_SNELHEID
    vz = (doel[2] - bp[2]) / t - 0.5 * ZWAARTEKRACHT * t
    return np.array([*(vlak / d * KANS_SNELHEID), vz])


def _features_kans(data: dict, t: float, wie: str) -> tuple[np.ndarray, dict] | None:
    """Features van een denkbeeldig schot door speler wie vanaf de balpositie op tijd t."""
    idx = {s["id"]: i for i, s in enumerate(data["spelers"])}
    team = {s["id"]: s["team"] for s in data["spelers"]}
    tm = team[wie]
    bp, autos = _stand(data, t)
    if not np.any(bp):
        return None
    verdedigers = [idx[s] for s in team if team[s] != tm]
    aanvallers = [idx[s] for s in team if team[s] == tm and s != wie]
    f = schot_features(bp, denkbeeldig_schot(bp, tm), tm, autos, idx[wie], verdedigers, aanvallers)
    f["teamgrootte"] = data["meta"].get("teamgrootte") or len(data["spelers"]) // 2
    return bp, f


def _voorspel(pakket, rank: int | None, feats: list[dict]) -> np.ndarray:
    from kern.per_rank import voorspel
    rk = 3 if rank is None else rank
    X = np.array([[f.get(k, 3) if k != "rank" else rk for k in pakket["features"]] for f in feats], dtype=float)
    return voorspel(pakket, X, rk) if rank is not None else pakket["model"].predict_proba(X)[:, 1]


def kans_voor_touch(data: dict, pakket, rank: int | None) -> None:
    """Zet per schot in data['schoten'] de 'kans': xG van een standaardschot vanaf waar de bal lag vlak vóór de touch."""
    team = {s["id"]: s["team"] for s in data["spelers"]}
    rijen = [(s, _features_kans(data, s["tijd"] - 0.05, s["speler"])) for s in data.get("schoten", []) if s["speler"] in team]
    rijen = [(s, r[1]) for s, r in rijen if r]
    if rijen:
        for (s, _), x in zip(rijen, _voorspel(pakket, rank, [f for _, f in rijen])):
            s["kans_ruw"] = round(float(x), 3)
            s["kans"] = verwacht(s["kans_ruw"])


def kans_xg(data: dict, events: list[dict], pakket, rank: int | None) -> list[dict]:
    """Gemiste kansen door whiffs → [{tijd, speler, team, plek, kans_xg}]."""
    team = {s["id"]: s["team"] for s in data["spelers"]}
    schoten = data.get("schoten", [])
    kandidaten = []
    for e in events:
        if e["meta"]["stream"] != "whiff":
            continue
        pl = e["payload"]["payload"]
        wie = sleutel(pl.get("player")) or sleutel(e["meta"].get("primary_player"))
        if wie not in team:
            continue
        t = pl.get("time") or _tijd(e)
        tm = team[wie]
        richting = 1 if tm == 0 else -1
        r = _features_kans(data, t, wie)
        if r is None:
            continue
        bp, f = r
        if bp[1] * richting < 0 or np.hypot(bp[0], DOEL_Y - bp[1] * richting) > 5000:
            continue  # alleen op de aanvalshelft, binnen ~50 m van het doel
        # De kans ging niet verloren als het team direct daarna alsnog schoot
        if any(team.get(s["speler"]) == tm and t <= s["tijd"] <= t + 1.5 for s in schoten):
            continue
        kandidaten.append(({"tijd": round(t, 2), "speler": wie, "team": tm, "plek": [round(float(bp[0])), round(float(bp[1]))]}, f))
    if not kandidaten:
        return []
    p = _voorspel(pakket, rank, [f for _, f in kandidaten])
    uit = [k | {"kans_ruw": round(float(x), 3), "kans_xg": verwacht(float(x))} for (k, _), x in zip(kandidaten, p)]
    return [k for k in uit if k["kans_xg"] >= KANS_MIN_XG]


def herkalibreer(invoer: dict, events: list[dict]) -> None:
    """Gecachte rating-invoer (rating_norm) opnieuw door de huidige kalibratie halen, incl. creaties."""
    for s in invoer.get("schoten", []):
        ruw = s.get("kans_ruw", s.get("kans"))
        if ruw is not None:
            s["kans_ruw"], s["kans"] = ruw, verwacht(ruw)
    k = invoer.get("kansen") or {}
    gemist = []
    for x in k.get("gemist", []):
        x["kans_ruw"] = x.get("kans_ruw", x["kans_xg"])
        x["kans_xg"] = verwacht(x["kans_ruw"])
        if x["kans_xg"] >= KANS_MIN_XG:
            gemist.append(x)
    data = {"spelers": [{"id": i, "team": t} for i, t in invoer["team"].items()], "schoten": invoer.get("schoten", [])}
    invoer["kansen"] = {**k, "gemist": gemist, "creaties": creaties(data, events, gemist)}


def touches(events: list[dict]) -> list[tuple[float, str, list]]:
    return sorted(((_tijd(e), sleutel(e["meta"].get("primary_player")), (e["payload"]["payload"] or {}).get("ball_position"))
                   for e in events if e["meta"]["stream"] == "touch"), key=lambda x: x[0])


def creaties(data: dict, events: list[dict], kansen: list[dict]) -> list[dict]:
    """Per schot of kans-whiff: de teamgenoot die hem klaarlegde → [{tijd, speler, ontvanger, xg, soort}]."""
    team = {s["id"]: s["team"] for s in data["spelers"]}
    tc = touches(events)
    uit = []
    momenten = [(s["tijd"], s["speler"], s.get("kans", s.get("xg")) or 0, "schot") for s in data.get("schoten", [])] + \
               [(k["tijd"], k["speler"], k["kans_xg"], "kans") for k in kansen]
    for t, wie, xg, soort in momenten:
        if wie not in team or xg <= 0:
            continue
        # Laatste touch vóór het moment, niet van de schutter zelf
        voor = [x for x in tc if t - CREATIE_VENSTER <= x[0] < t - 0.05 and x[1] != wie]
        if not voor or team.get(voor[-1][1]) != team[wie]:
            continue  # laatste andere touch was van de tegenstander → niemand creëerde deze kans
        # Geen tegenstander-touch tussen de pass en het moment
        if any(team.get(x[1]) not in (None, team[wie]) for x in tc if voor[-1][0] < x[0] < t):
            continue
        uit.append({"tijd": round(voor[-1][0], 2), "speler": voor[-1][1], "ontvanger": wie, "xg": round(xg, 3), "soort": soort,
                    "moment": round(t, 2)})  # moment = tijd van het schot/de kans waar deze creatie bij hoort
    return uit


def fouten_voor_tegengoal(data: dict, events: list[dict]) -> list[dict]:
    """→ [{tijd, speler, goal_tijd, soort: 'whiff'|'balverlies'}], hoogstens één per tegengoal."""
    team = {s["id"]: s["team"] for s in data["spelers"]}
    tc = touches(events)
    eigen_schoten = {(round(s["tijd"], 1), s["speler"]) for s in data.get("schoten", [])}
    kickoffs = sorted(_tijd(e) for e in events if e["meta"]["stream"] == "kickoff")
    whiffs = sorted((e["payload"]["payload"].get("time") or _tijd(e), sleutel(e["payload"]["payload"].get("player")))
                    for e in events if e["meta"]["stream"] == "whiff")
    uit = []
    for e in events:
        if e["meta"]["stream"] != "goal_context":
            continue
        tg = _tijd(e)
        g = 0 if e["meta"].get("team_is_team_0") else 1
        d = 1 - g
        ko = max([k for k in kickoffs if k < tg], default=-1)
        ondergrens = max(tg - FOUT_VENSTER, ko + 0.5)
        # Start van de scorende aanval: eerste touch van g na de laatste touch van d
        d_touches = [x for x in tc if ondergrens <= x[0] < tg and team.get(x[1]) == d]
        laatste_d = d_touches[-1] if d_touches else None
        # 1) whiff van het verdedigende team die de bal niet meer terugkreeg
        w = [(t, s) for t, s in whiffs if ondergrens <= t <= tg - 1.0 and team.get(s) == d
             and (laatste_d is None or t >= laatste_d[0])]
        if w:
            uit.append({"tijd": round(w[-1][0], 2), "speler": w[-1][1], "goal_tijd": round(tg, 2), "soort": "whiff"})
            continue
        # 2) balverlies: laatste touch van d buiten de eigen derde, geen geblokt schot
        if laatste_d and laatste_d[2] and tg - laatste_d[0] >= 1.0:
            y = laatste_d[2][1]
            in_eigen_derde = y < -1700 if d == 0 else y > 1700  # blauw (0) verdedigt −y
            if not in_eigen_derde and (round(laatste_d[0], 1), laatste_d[1]) not in eigen_schoten:
                uit.append({"tijd": round(laatste_d[0], 2), "speler": laatste_d[1], "goal_tijd": round(tg, 2), "soort": "balverlies"})
    return uit
