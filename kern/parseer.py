"""Replay → compact JSON voor de 3D-viewer.

Gebruik:
    uv run python -m kern.parseer data/replays/*.replay [--rank champion]
Schrijft data/verwerkt/<naam>.json en werkt data/verwerkt/index.json bij.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import subtr_actor as sa

from kern import passen as passmodule, schoten as schotmodule, statistieken

XG_MODEL = Path(__file__).resolve().parent.parent / 'data' / 'modellen' / 'xg.joblib'

FPS = 30
BAL_KOLOMMEN = ["BallRigidBody", "BallRigidBodyQuaternions", "CurrentTime", "SecondsRemaining"]
SPELER_KOLOMMEN = ["PlayerRigidBody", "PlayerRigidBodyQuaternions", "PlayerBoost", "PlayerDemolishedBy"]

# Events die de viewer toont; de rest blijft voor de analyse-laag.
EVENT_STREAMS = {
    "touch", "goal_context", "timeline", "demolition", "fifty_fifty",
    "pass", "kickoff", "backboard", "one_timer", "half_volley", "wall_aerial_shot",
    "flip_reset", "air_dribble", "ceiling_shot", "double_tap",
}

MAP_UIT = Path(__file__).resolve().parent.parent / "data" / "verwerkt"


def speler_sleutel(remote_id: dict | None) -> str | None:
    """{'Steam': '765…'} → 'Steam:765…' zodat events en spelers te koppelen zijn."""
    if not remote_id:
        return None
    (platform, waarde), = remote_id.items()
    return f"{platform}:{waarde}"


def kolom(headers: list[str], naam: str) -> int:
    return headers.index(naam)


def parseer(pad: Path, rank: int | None = None) -> dict:
    """rank = index in RANK_ORDE (bv. 5 = Champion) → rank-specifieke modellen; None = algemeen model."""
    meta, arr = sa.get_ndarray_with_info_from_replay_filepath(
        str(pad), BAL_KOLOMMEN, SPELER_KOLOMMEN, fps=FPS
    )
    gh = meta["column_headers"]["global_headers"]
    ph = meta["column_headers"]["player_headers"]
    rm = meta["replay_meta"]
    kop = dict(rm["all_headers"])

    n_g, n_p = len(gh), len(ph)
    spelers_meta = rm["team_zero"] + rm["team_one"]  # volgorde = volgorde in ndarray
    assert arr.shape[1] == n_g + n_p * len(spelers_meta), "kolomtelling klopt niet"

    # Ball: positie + quaternion; tijd + klok
    bi = [kolom(gh, f"Ball - position {a}") for a in "xyz"] + \
         [kolom(gh, f"Ball - quaternion {a}") for a in "xyzw"]
    bv = [kolom(gh, f"Ball - linear velocity {a}") for a in "xyz"]
    t = arr[:, kolom(gh, "current time")]
    klok = arr[:, kolom(gh, "seconds remaining")]

    pi = [kolom(ph, f"position {a}") for a in "xyz"] + \
         [kolom(ph, f"quaternion {a}") for a in "xyzw"] + \
         [kolom(ph, "boost level (raw replay units)"), kolom(ph, "player demolished by")]

    def afronden(blok: np.ndarray, decimalen: list[int]) -> list:
        uit = np.empty_like(blok, dtype=object)
        for j, d in enumerate(decimalen):
            kol = np.nan_to_num(blok[:, j], nan=0.0)
            uit[:, j] = [round(float(v), d) if d else int(round(float(v))) for v in kol]
        return uit.ravel().tolist()

    bal = afronden(arr[:, bi], [0, 0, 0, 3, 3, 3, 3])
    bal_snelheid = np.linalg.norm(arr[:, bv], axis=1)

    spelers = []
    for k, sm in enumerate(spelers_meta):
        start = n_g + k * n_p
        blok = arr[:, [start + i for i in pi]].copy()
        blok[:, 7] = blok[:, 7] / 255 * 100  # boost 0–255 → 0–100
        spelers.append({
            "naam": sm["name"],
            "team": 0 if k < len(rm["team_zero"]) else 1,
            "id": speler_sleutel(sm.get("remote_id")),
            "auto": sm.get("car_hitbox_family") or "Octane",
            "stats": {s: (sm.get("stats") or {}).get(s, 0) for s in ("Score", "Goals", "Assists", "Saves", "Shots")},
            "frames": afronden(blok, [0, 0, 0, 3, 3, 3, 3, 0, 0]),
        })

    events = []
    for e in sa.get_stats_events(str(pad))["events"]:
        m = e["meta"]
        stroom = m["stream"]
        if stroom not in EVENT_STREAMS:
            continue
        timing = m["timing"]
        tijd = timing.get("time", timing.get("end_time"))
        payload = e["payload"]["payload"]
        soort = payload.get("kind", stroom) if stroom == "timeline" else stroom
        ev = {
            "soort": soort,
            "tijd": round(tijd, 3),
            "team": 0 if m.get("team_is_team_0") else 1,
            "speler": speler_sleutel(m.get("primary_player")),
        }
        if m.get("secondary_player"):
            ev["speler2"] = speler_sleutel(m["secondary_player"])
        if stroom == "goal_context":
            ev["balsnelheid"] = round(payload.get("ball_speed_at_goal", 0))
            ev["opbouw"] = payload.get("goal_buildup")
        if stroom == "touch":
            bw = payload.get("ball_movement") or {}
            ev["opschuiving"] = round(bw.get("advance_distance", 0))
        events.append(ev)
    events.sort(key=lambda e: e["tijd"])

    data = {
        "versie": 2,
        "naam": pad.stem,
        "fps": FPS,
        "meta": {
            "speltype": rm.get("game_type", {}).get("game_type"),
            "playlist": rm.get("game_type", {}).get("playlist_id"),
            "seizoen": rm.get("season", {}).get("number"),
            "teamgrootte": kop.get("TeamSize"),
            "score": [kop.get("Team0Score", 0), kop.get("Team1Score", 0)],
            "duur": round(float(kop.get("TotalSecondsPlayed", 0)), 1),
            "datum": kop.get("Date"),
            "map": kop.get("MapName"),
        },
        "t": [round(float(v), 3) for v in t],
        "klok": [int(v) for v in np.nan_to_num(klok)],
        "bal": bal,
        "balSnelheid": [int(v) for v in np.nan_to_num(bal_snelheid)],
        "spelers": spelers,
        "events": events,
    }
    data["stats"] = statistieken.bereken(str(pad), data)
    data["schoten"] = schoten_met_xg(pad, rank)
    voeg_xg_toe(data)
    data["passen"] = []
    if passmodule.MODEL_PAD.exists():
        data["passen"], pst = passmodule.passen_met_model(pad, rank)
        for s in data["spelers"]:
            data["stats"]["spelers"][s["id"]]["passen"].update(pst.get(s["id"], {}))
    # Gemiste kansen (whiff), gecreëerde kansen (xA) en fouten voor tegengoal
    from kern import events as eventcache, kansen, rating
    from kern.xg_model import RANK_ORDE
    ev = eventcache.lijst(pad)
    gemist = []
    if XG_MODEL.exists():
        import joblib
        gemist = kansen.kans_xg(data, ev, joblib.load(XG_MODEL), rank)
    data["kansen"] = {"gemist": gemist, "creaties": kansen.creaties(data, ev, gemist), "fouten": kansen.fouten_voor_tegengoal(data, ev)}
    voeg_kansen_toe(data)
    # Live rating per speler (acties → cijfer t.o.v. de rank-norm)
    band = None
    if rank is not None and 0 <= rank < len(RANK_ORDE):
        laag = RANK_ORDE[rank]
        band = "ranked-doubles_grand-champion-1_supersonic-legend" if laag == "grand-champion" else f"ranked-doubles_{laag}-1_{laag}-3"
    data["rating"] = rating.bereken(data, ev, band)
    for sid, r in data["rating"]["spelers"].items():
        if sid in data["stats"]["spelers"]:
            data["stats"]["spelers"][sid]["impact"] = {"rating": r["eind"], "impact": r["impact"],
                                                        **{o: v["cijfer"] for o, v in r["onderdelen"].items()}}
    return data


def schoten_met_xg(pad: Path, rank: int | None = None) -> list[dict]:
    """Schoten uit de replay + xG uit het getrainde model (als dat er is)."""
    rijen = schotmodule.schoten_uit_replay(pad, "onbekend")
    if not rijen or not XG_MODEL.exists():
        return [{"tijd": r["tijd"], "team": r["team"], "speler": r["speler"], "plek": [r["bal_x"], r["bal_y"]], "goal": r["goal"], "xg": None} for r in rijen]
    import joblib
    pakket = joblib.load(XG_MODEL)
    from kern.per_rank import voorspel
    rk = 3 if rank is None else rank  # rank onbekend → midden, algemeen model
    X = np.array([[r.get(f, 3) if f != "rank" else rk for f in pakket["features"]] for r in rijen], dtype=float)
    xg = voorspel(pakket, X, rk) if rank is not None else pakket["model"].predict_proba(X)[:, 1]
    return [{"tijd": r["tijd"], "team": r["team"], "speler": r["speler"], "plek": [r["bal_x"], r["bal_y"]],
             "goal": r["goal"], "xg": round(float(x), 3), "op_doel": r["op_doel"]} for r, x in zip(rijen, xg)]


def voeg_xg_toe(data: dict) -> None:
    """xG-sommen per speler in data.stats, zodat catalogus/tabellen ze kunnen tonen."""
    for s in data["spelers"]:
        mijn = [x for x in data["schoten"] if x["speler"] == s["id"]]
        xg = sum(x["xg"] or 0 for x in mijn)
        a = data["stats"]["spelers"][s["id"]]["aanval"]
        a["xg"] = round(xg, 2)
        a["xg_per_schot"] = round(xg / len(mijn), 3) if mijn else None
        a["goals_min_xg"] = round(a["goals"] - xg, 2)
        a["schot_pogingen"] = len(mijn)


def voeg_kansen_toe(data: dict) -> None:
    """Grote kansen, gemiste kansen door whiffs, xA en fouten voor tegengoal per speler in data.stats."""
    from kern.kansen import GROTE_KANS
    k = data["kansen"]
    for s in data["spelers"]:
        i, st = s["id"], data["stats"]["spelers"][s["id"]]
        groot = [x for x in data["schoten"] if x["speler"] == i and (x["xg"] or 0) >= GROTE_KANS]
        whiff = [x for x in k["gemist"] if x["speler"] == i]
        a = st["aanval"]
        a["grote_kansen"] = len(groot) + sum(1 for x in whiff if x["kans_xg"] >= GROTE_KANS)
        a["grote_kansen_gemist"] = sum(1 for x in groot if not x["goal"]) + sum(1 for x in whiff if x["kans_xg"] >= GROTE_KANS)
        a["kansen_gewhifft"] = len(whiff)
        a["kans_xg_gewhifft"] = round(sum(x["kans_xg"] for x in whiff), 2)
        mijn = [c for c in k["creaties"] if c["speler"] == i]
        st["passen"]["kansen_gecreeerd"] = len(mijn)
        st["passen"]["xa"] = round(sum(c["xg"] for c in mijn), 2)
        st["passen"]["grote_kansen_gecreeerd"] = sum(1 for c in mijn if c["xg"] >= GROTE_KANS)
        st["verdedigen"]["fouten_voor_tegengoal"] = sum(1 for f in k["fouten"] if f["speler"] == i)


def werk_index_bij() -> None:
    items = []
    for f in sorted(MAP_UIT.glob("*.json")):
        if f.name in ("index.json", "profiel.json"):
            continue
        d = json.loads(f.read_text(encoding="utf-8"))
        items.append({"bestand": f.name, "naam": d["naam"], **d["meta"],
                      "spelers": [{"naam": s["naam"], "team": s["team"]} for s in d["spelers"]]})
    (MAP_UIT / "index.json").write_text(json.dumps(items, ensure_ascii=False), encoding="utf-8")


def main(args: list[str]) -> None:
    import argparse
    from kern.xg_model import RANK_ORDE
    ap = argparse.ArgumentParser()
    ap.add_argument("replays", nargs="+")
    ap.add_argument("--rank", choices=RANK_ORDE, help="rank van de lobby → rank-specifieke modellen (bv. champion)")
    ap.add_argument("--ik", help="spelernaam van de gebruiker → wedstrijd wordt gemarkeerd als eigen wedstrijd")
    ap.add_argument("--categorie", choices=["mee", "apart"], help="eigen wedstrijd telt mee voor profiel/benchmarks of niet")
    a = ap.parse_args(args)
    rank = RANK_ORDE.index(a.rank) if a.rank else None
    MAP_UIT.mkdir(parents=True, exist_ok=True)
    for p in map(Path, a.replays):
        try:
            d = parseer(p, rank)
        except Exception as e:  # één kapotte/afwijkende replay mag de rest niet tegenhouden
            print(f"{p.name}: overgeslagen ({type(e).__name__}: {str(e)[:80]})")
            continue
        d["meta"]["rank"] = a.rank
        if a.ik:
            # Op platform-ID als --ik een bekend account is, anders op naam
            from kern import accounts
            account = accounts.vind(a.ik)
            ik = next((s for s in d["spelers"] if (s["id"] in account["ids"] if account else s["naam"] == a.ik)), None)
            d["meta"]["eigen"] = ik is not None
            if ik:
                sc = d["meta"]["score"]
                d["meta"]["ik"] = ik["id"]
                d["meta"]["account"] = account["naam"] if account else ik["naam"]
                d["meta"]["categorie"] = a.categorie or "mee"
                d["meta"]["uitslag"] = "W" if sc[ik["team"]] > sc[1 - ik["team"]] else "V"
        uit = MAP_UIT / f"{p.stem}.json"
        uit.write_text(json.dumps(d, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        print(f"{p.name}: {len(d['t'])} frames, {len(d['spelers'])} spelers, "
              f"{len(d['events'])} events -> {uit.name} ({uit.stat().st_size / 1e6:.1f} MB)")
    werk_index_bij()


if __name__ == "__main__":
    main(sys.argv[1:])
