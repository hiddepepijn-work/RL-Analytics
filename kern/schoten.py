"""Schot-dataset voor het xG-model.

Een schot = touch van team T waarna de bal richting het doel van de tegenstander gaat
(projectie op doel, of door de game als 'Shot' gemarkeerd). Label = team T scoort binnen
4 s zonder dat een teamgenoot de bal nog raakt (dan telt die latere touch als nieuw schot).

Gebruik:
    uv run python -m kern.schoten            # alle data/replays/<band>/*.replay → data/features/schoten.csv
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

import numpy as np
import subtr_actor as sa

from kern import events as eventcache
from kern.fysica import aankomst_richting
from kern.events import replay_fout

WORTEL = Path(__file__).resolve().parent.parent
FPS = 30
DOEL_Y, DOEL_X, DOEL_Z = 5120.0, 893.0, 642.775
BAL_R = 92.75
ZWAARTEKRACHT = -650.0
MAX_AUTO = 2300.0
LABEL_VENSTER = 4.0
PROJECTIE_S = 4.0
NIEUWSTE_KOLOM = "bron_ndarray"  # cache zonder deze kolom is van een oudere featureversie (kern/bijwerken.py)

BAL_KOL = ["BallRigidBody", "CurrentTime"]
SPELER_KOL = ["PlayerRigidBody", "PlayerBoost"]


def sleutel(pid):
    if not pid:
        return None
    (k, v), = pid.items()
    return f"{k}:{v}"


def projecteer(pos, vel, dt=1 / 60, duur=PROJECTIE_S):
    """Ballistische balbaan met stuiter op vloer/wanden/plafond.
    Geeft (punten[t,x,y,z], doel_t, ingang_xz, mis) — mis = uu naast/boven het doel bij de eerste kruising (0 = op doel)."""
    p, v = np.array(pos, float), np.array(vel, float)
    punten = []
    richting = np.sign(v[1]) or 1.0
    mis = None
    for k in range(int(duur / dt)):
        v[2] += ZWAARTEKRACHT * dt
        p += v * dt
        if p[2] < BAL_R:
            p[2] = BAL_R; v[2] = -v[2] * 0.6; v[:2] *= 0.95
        if p[2] > 2044 - BAL_R:
            p[2] = 2044 - BAL_R; v[2] = -v[2] * 0.6
        if abs(p[0]) > 4096 - BAL_R:
            p[0] = np.sign(p[0]) * (4096 - BAL_R); v[0] = -v[0] * 0.6
        t = (k + 1) * dt
        punten.append((t, *p))
        if abs(p[1]) >= DOEL_Y:
            if mis is None and np.sign(p[1]) == richting:
                mis = max(0.0, abs(p[0]) - DOEL_X) + max(0.0, p[2] - DOEL_Z)
            if np.sign(p[1]) == richting and abs(p[0]) < DOEL_X and p[2] < DOEL_Z:
                return np.array(punten), t, (p[0], p[2]), 0.0
            if abs(p[0]) > DOEL_X or p[2] > DOEL_Z:
                v[1] = -v[1] * 0.6  # achterwand naast/boven doel
                p[1] = np.sign(p[1]) * (DOEL_Y - 1)
                richting = 0  # na terugkaatsing niet meer "op doel"
    return np.array(punten), None, None, mis


def vereiste_snelheid(auto, punten):
    """Laagste gemiddelde snelheid die een auto nodig heeft om ergens op de baan te zijn (minus bereik)."""
    if len(punten) == 0:
        return np.inf
    d = np.linalg.norm(punten[:, 1:4] - auto[None, :3], axis=1) - 150  # ~bal + autoneus
    return float(np.min(np.maximum(d, 0) / np.maximum(punten[:, 0], 1 / 30)))


def schoten_uit_replay(pad: Path, band: str) -> list[dict]:
    meta, arr = sa.get_ndarray_with_info_from_replay_filepath(str(pad), BAL_KOL, SPELER_KOL, fps=FPS)
    gh, ph = meta["column_headers"]["global_headers"], meta["column_headers"]["player_headers"]
    rm = meta["replay_meta"]
    spelers = rm["team_zero"] + rm["team_one"]
    team_van = {sleutel(s.get("remote_id")): (0 if i < len(rm["team_zero"]) else 1) for i, s in enumerate(spelers)}
    idx_van = {sleutel(s.get("remote_id")): i for i, s in enumerate(spelers)}
    ng, npk = len(gh), len(ph)
    t = arr[:, gh.index("current time")]
    bal = arr[:, [gh.index(f"Ball - position {a}") for a in "xyz"] + [gh.index(f"Ball - linear velocity {a}") for a in "xyz"]]
    pk = [ph.index(f"position {a}") for a in "xyz"] + [ph.index(f"linear velocity {a}") for a in "xyz"] + [ph.index("boost level (raw replay units)")]
    auto = np.stack([arr[:, [ng + i * npk + k for k in pk]] for i in range(len(spelers))], axis=1)  # [frame, speler, 7]

    events = eventcache.lijst(pad)
    touches = sorted(((e["meta"]["timing"].get("start_time", e["meta"]["timing"].get("time")), sleutel(e["meta"].get("primary_player")))
                      for e in events if e["meta"]["stream"] == "touch"), key=lambda x: x[0])
    goals = [(e["meta"]["timing"]["time"], 0 if e["meta"].get("team_is_team_0") else 1, sleutel(e["payload"]["payload"].get("scorer")))
             for e in events if e["meta"]["stream"] == "goal_context"]
    game_shots = [(e["payload"]["payload"]["time"], sleutel(e["payload"]["payload"].get("player_id")))
                  for e in events if e["meta"]["stream"] == "timeline" and e["payload"]["payload"].get("kind") == "Shot"]

    # Scoortouch = laatste touch van de speler die de game als scorer aanwijst (niet blind de laatste teamtouch:
    # raken twee teamgenoten de bal vrijwel tegelijk, dan krijgt de scorer de goal). Geen scorer → laatste teamtouch.
    scoortouches, dubbel = set(), set()
    for g, gt, scorer in goals:
        laatste = [(x, s) for x, s in touches if x < g and team_van.get(s) == gt]
        van_scorer = [(x, s) for x, s in laatste if s == scorer]
        kies = van_scorer[-1] if van_scorer and g - van_scorer[-1][0] < 8 else (laatste[-1] if laatste and g - laatste[-1][0] < 8 else None)
        if kies:
            scoortouches.add(kies)
            dubbel |= {(x, s) for x, s in laatste if s != kies[1] and abs(x - kies[0]) < 0.3}  # gelijktijdige touch teamgenoot
    goal_tijden = [(g, gt) for g, gt, _ in goals]

    def frame(tt):
        return int(min(len(t) - 1, max(0, np.searchsorted(t, tt))))

    rijen = []
    for n, (tt, speler) in enumerate(touches):
        team = team_van.get(speler)
        if team is None or (tt, speler) in dubbel:
            continue
        f = frame(tt + 0.1)  # balsnelheid net ná de touch
        bp, bv = bal[f, :3], bal[f, 3:]
        if not np.any(bp):
            continue
        richting = 1 if team == 0 else -1  # blauw valt aan richting +y
        doel = np.array([0.0, richting * DOEL_Y, DOEL_Z / 3])
        naar_doel = (doel - bp) / (np.linalg.norm(doel - bp) or 1)
        v_doel = float(bv @ naar_doel)
        afstand = float(np.linalg.norm(doel[:2] - bp[:2]))
        punten, t_doel, ingang, mis = projecteer(bp, bv)
        game_shot = any(abs(gs - tt) < 0.4 and sp == speler for gs, sp in game_shots)
        bijna = mis is not None and mis < 1500
        if (tt, speler) not in scoortouches and (not (t_doel is not None or bijna or game_shot) or v_doel < 300 or afstand > 7000):
            continue

        # Label: goal team binnen venster, zonder latere touch van een teamgenoot ervóór
        volgende_eigen = next((x for x, s in touches[n + 1:] if team_van.get(s) == team), np.inf)
        goal = (tt, speler) in scoortouches or any(team == gt and tt < g <= min(tt + LABEL_VENSTER, volgende_eigen + 0.05) for g, gt in goal_tijden)

        f0 = frame(tt)
        verdedigers = [i for s, i in idx_van.items() if team_van[s] != team]
        aanvallers = [i for s, i in idx_van.items() if team_van[s] == team and s != speler]
        feats = schot_features(bp, bv, team, auto[f0], idx_van[speler], verdedigers, aanvallers, (punten, t_doel, ingang, mis))
        rijen.append({
            "replay": pad.stem, "band": band, "tijd": round(tt, 2), "team": team, "speler": speler,
            "bal_x": round(float(bp[0])), "bal_y": round(float(bp[1])),
            **{k: feats[k] for k in list(feats)[:10]},
            "game_shot": int(game_shot),
            **{k: feats[k] for k in list(feats)[10:]},
            "teamgrootte": len(rm["team_zero"]),
            "scoortouch": int((tt, speler) in scoortouches),
            "bron_ndarray": 1,  # cacheversie: ndarray-features (ruwe frames getest 14 okt: logloss 0,1923 → 0,1959, slechter)
            "goal": int(goal),
        })
    return rijen


def schot_features(bp, bv, team, autos, sp, verdedigers, aanvallers, projectie=None) -> dict:
    """Model-features voor een schot vanaf balpositie bp met balsnelheid bv; autos = [speler, 7] op het schotmoment.
    Ook voor een denkbeeldig schot, bv. de kans bij een whiff (kern/kansen.py). Volgorde = kolomvolgorde schoten.csv."""
    richting = 1 if team == 0 else -1  # blauw valt aan richting +y
    doel = np.array([0.0, richting * DOEL_Y, DOEL_Z / 3])
    naar_doel = (doel - bp) / (np.linalg.norm(doel - bp) or 1)
    punten, t_doel, ingang, mis = projectie or projecteer(bp, bv)
    baan = punten if t_doel is None else punten[punten[:, 0] <= t_doel]
    vs = sorted(vereiste_snelheid(autos[i], baan) for i in verdedigers if np.any(autos[i, :3]))
    # Marge = (vroegste aankomst van de verdediger op de baan) − (moment dat de bal daar is), met rijrichting en boost.
    # Negatief = hij kan er vóór de bal zijn. Over de baan tot het doel (of de hele projectie als hij naast gaat).
    marges, terug = [], []
    for i in verdedigers:
        if not np.any(autos[i, :3]) or not len(baan):
            continue
        marges.append(float(np.min(aankomst_richting(autos[i, :3], autos[i, 3:6], autos[i, 6] / 2.55, baan) - baan[:, 0])))
        terug.append(float(autos[i, 4]) * richting)  # snelheid richting het eigen (aangevallen) doel
    marges.sort()
    return {
        "afstand": round(float(np.linalg.norm(doel[:2] - bp[:2]))),
        "hoek": round(float(np.degrees(np.arctan2(abs(bp[0]), max(DOEL_Y - bp[1] * richting, 1)))), 1),
        "bal_z": round(float(bp[2])), "bal_snelheid": round(float(np.linalg.norm(bv))), "snelheid_naar_doel": round(float(bv @ naar_doel)),
        "op_doel": int(t_doel is not None), "t_doel": round(t_doel, 2) if t_doel else -1,
        "ingang_x": round(abs(ingang[0])) if ingang else -1, "ingang_z": round(ingang[1]) if ingang else -1,
        "mis_afstand": round(mis) if mis is not None else -1,
        "verdediger_min_v": round(min(vs[0], 9999)) if vs else 9999,
        "verdediger_2e_v": round(min(vs[1], 9999)) if len(vs) > 1 else 9999,
        "verdedigers_tussen": sum(1 for i in verdedigers if autos[i, 1] * richting > bp[1] * richting),
        "verdedigers_in_doel": sum(1 for i in verdedigers if autos[i, 1] * richting > DOEL_Y - 900 and abs(autos[i, 0]) < 1200),
        "verdediger_boost": round(float(np.mean([autos[i, 6] for i in verdedigers])) / 2.55) if verdedigers else 0,
        "schutter_z": round(float(autos[sp, 2])), "schutter_boost": round(float(autos[sp, 6]) / 2.55),
        "aanvaller_dichtbij": sum(1 for i in aanvallers if np.linalg.norm(autos[i, :2] - bp[:2]) < 2000),
        "verdediger_marge": round(marges[0], 2) if marges else 9.0,
        "verdediger_2e_marge": round(marges[1], 2) if len(marges) > 1 else 9.0,
        "verdediger_terug_max": round(max(terug)) if terug else 0,
        "schutter_snelheid": round(float(np.linalg.norm(autos[sp, 3:6]))),
    }


def main(args: list[str]) -> None:
    uit = WORTEL / "data" / "features" / "schoten.csv"
    uit.parent.mkdir(parents=True, exist_ok=True)
    gezien_match = set()
    alle = []
    replays = sorted((WORTEL / "data" / "replays").glob("*/*.replay"))
    for k, p in enumerate(replays):
        band = p.parent.name
        try:
            kop = dict(sa.get_replay_meta(str(p))["replay_meta"]["all_headers"])
            match_id = kop.get("MatchGuid") or kop.get("Id") or p.stem
            if match_id in gezien_match:
                continue  # dezelfde wedstrijd door meerdere spelers geüpload
            gezien_match.add(match_id)
            alle += schoten_uit_replay(p, band)
        except BaseException as e:  # kapotte of te nieuwe replay: overslaan, niet stoppen
            if not replay_fout(e):  # Ctrl+C / afsluiten: doorlaten; Rust-panic: als fout behandelen
                raise
            print(f"  overslaan {p.name}: {type(e).__name__}: {str(e)[:80]}")
        if (k + 1) % 50 == 0:
            print(f"{k + 1}/{len(replays)} replays, {len(alle)} schoten")
    if not alle:
        sys.exit("Geen schoten gevonden")
    with uit.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(alle[0].keys()))
        w.writeheader(); w.writerows(alle)
    n_goal = sum(r["goal"] for r in alle)
    print(f"Klaar: {len(alle)} schoten uit {len(gezien_match)} wedstrijden, {n_goal} goals ({100 * n_goal / len(alle):.1f}%) -> {uit}")


if __name__ == "__main__":
    main(sys.argv[1:])
