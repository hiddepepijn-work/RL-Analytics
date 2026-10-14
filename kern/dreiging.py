"""Dreigingsmodel: kans dat een team binnen 10 s scoort, gegeven de hele spelsituatie (niet alleen de balplek).

Anders dan de zonewaarde kijkt dit ook naar wie erbij kan: een bal midden voor het doel is ongevaarlijk als alleen
verdedigers erbij kunnen, en een clearance recht op een vrijstaande tegenstander is wél gevaarlijk.
Gebruikt voor de verdedigende stats (kern/verdediging.py): dreiging vlak vóór een verdedigende touch tegenover
~1 s erna.

Features (vanuit het aanvallende team A): balplek (|x|, y richting A's doel, hoogte), balsnelheid en snelheid richting
het doel, aankomstmarge van de snelste aanvaller en verdediger op de balbaan (rijrichting + boost, kern/fysica.py),
aantal verdedigers tussen bal en doel en in het doel, aanvallers dichtbij.

Gebruik:
    uv run python -m kern.dreiging --max 1000      # trainen → data/modellen/dreiging.joblib + dreiging.json
"""
from __future__ import annotations

import argparse
import json
import random
from multiprocessing import Pool
from pathlib import Path

import numpy as np

from kern.fysica import aankomst_richting, baan

WORTEL = Path(__file__).resolve().parent.parent
MODEL_PAD = WORTEL / "data" / "modellen" / "dreiging.joblib"
DOEL_Y = 5120.0
VENSTER = 10.0
STAP = 1 / 3  # s tussen trainingsmomenten
FEATURES = ["bal_x", "bal_y", "bal_z", "bal_snelheid", "v_naar_doel", "afstand_doel",
            "aanvaller_marge", "verdediger_marge", "verdediger_2e_marge", "verdedigers_tussen", "verdedigers_in_doel",
            "aanvallers_dichtbij", "aanvaller_boost", "verdediger_boost"]


def features(bal_pos, bal_vel, autos, teams, aanvaller: int) -> dict:
    """autos [spelers, 7] = pos, snelheid, boost (%); teams [spelers] = 0/1. Alles in veldcoördinaten."""
    r = 1 if aanvaller == 0 else -1  # team 0 valt aan richting +y
    punten = baan(bal_pos, bal_vel, duur=1.5, dt=1 / 15)

    def marges(ids):
        uit = []
        for i in ids:
            if not np.any(autos[i, :3]):
                continue
            uit.append(float(np.min(aankomst_richting(autos[i, :3], autos[i, 3:6], autos[i, 6], punten) - punten[:, 0])))
        return sorted(uit)

    a_ids = [i for i, t in enumerate(teams) if t == aanvaller]
    v_ids = [i for i, t in enumerate(teams) if t != aanvaller]
    am, vm = marges(a_ids), marges(v_ids)
    doel = np.array([0.0, r * DOEL_Y])
    return {
        "bal_x": abs(float(bal_pos[0])), "bal_y": float(bal_pos[1]) * r, "bal_z": float(bal_pos[2]),
        "bal_snelheid": float(np.linalg.norm(bal_vel)),
        "v_naar_doel": float(np.dot(bal_vel[:2], (doel - bal_pos[:2]) / (np.linalg.norm(doel - bal_pos[:2]) or 1))),
        "afstand_doel": float(np.linalg.norm(doel - bal_pos[:2])),
        "aanvaller_marge": am[0] if am else 9.0,
        "verdediger_marge": vm[0] if vm else 9.0,
        "verdediger_2e_marge": vm[1] if len(vm) > 1 else 9.0,
        "verdedigers_tussen": sum(1 for i in v_ids if autos[i, 1] * r > bal_pos[1] * r),
        "verdedigers_in_doel": sum(1 for i in v_ids if autos[i, 1] * r > DOEL_Y - 900 and abs(autos[i, 0]) < 1200),
        "aanvallers_dichtbij": sum(1 for i in a_ids if np.linalg.norm(autos[i, :2] - bal_pos[:2]) < 2000),
        "aanvaller_boost": float(np.mean([autos[i, 6] for i in a_ids])) if a_ids else 0.0,
        "verdediger_boost": float(np.mean([autos[i, 6] for i in v_ids])) if v_ids else 0.0,
    }


def _replay(p: Path) -> tuple[str, np.ndarray]:
    """Trainingsrijen uit één replay (features + label, float32): elke STAP s, voor beide teams als aanvaller."""
    import subtr_actor as sa
    from kern import events
    try:
        ruw = sa.get_replay_frames_data(str(p))
    except Exception:
        return p.stem, np.zeros((0, len(FEATURES) + 1), np.float32)
    fd, meta = ruw["frame_data"], ruw["meta"]
    t = np.array([float(m["time"]) for m in fd["metadata_frames"]])
    spelers = meta["team_zero"] + meta["team_one"]
    teams = [0 if i < len(meta["team_zero"]) else 1 for i in range(len(spelers))]
    from kern.parseer import speler_sleutel as sleutel
    per_id = {sleutel(pid): pl["frames"] for pid, pl in fd["players"]}
    goals = [(e["meta"]["timing"]["time"], 0 if e["meta"].get("team_is_team_0") else 1)
             for e in events.lijst(p) if e["meta"]["stream"] == "goal_context"]
    rijen, volgende = [], t[0]
    for f in range(len(t)):
        if t[f] < volgende:
            continue
        volgende = t[f] + STAP
        b = fd["ball_data"]["frames"][f].get("Data") if isinstance(fd["ball_data"]["frames"][f], dict) else None
        if not b:
            continue
        rb = b["rigid_body"]; l, v = rb["location"], rb.get("linear_velocity") or {}
        bp, bv = np.array([l["x"], l["y"], l["z"]]), np.array([v.get("x", 0), v.get("y", 0), v.get("z", 0)], float)
        autos = np.zeros((len(spelers), 7))
        for k, s in enumerate(spelers):
            fr = per_id.get(sleutel(s.get("remote_id")))
            d = fr[f].get("Data") if fr and isinstance(fr[f], dict) else None
            if d:
                q, w = d["rigid_body"]["location"], d["rigid_body"].get("linear_velocity") or {}
                autos[k] = [q["x"], q["y"], q["z"], w.get("x", 0), w.get("y", 0), w.get("z", 0), (d.get("boost_amount") or 0) / 2.55]
        for a in (0, 1):
            ft = features(bp, bv, autos, teams, a)
            label = int(any(gt == a and t[f] < g <= t[f] + VENSTER for g, gt in goals))
            rijen.append([ft[k] for k in FEATURES] + [label])
    return p.stem, np.array(rijen, np.float32).reshape(-1, len(FEATURES) + 1)


def voorspel(pakket, rijen: list[dict]) -> np.ndarray:
    if not rijen:
        return np.zeros(0)
    X = np.array([[r[k] for k in pakket["features"]] for r in rijen], dtype=float)
    return pakket["model"].predict_proba(X)[:, 1]


def main() -> None:
    import joblib
    from sklearn.ensemble import HistGradientBoostingClassifier
    from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score
    from sklearn.model_selection import GroupKFold
    ap = argparse.ArgumentParser()
    ap.add_argument("--max", type=int, default=1000)
    ap.add_argument("--processen", type=int, default=8)
    a = ap.parse_args()
    replays = sorted((WORTEL / "data" / "replays").glob("*/*.replay"))
    random.Random(2).shuffle(replays)
    replays = replays[: a.max]
    delen, groepen = [], []
    with Pool(a.processen) as pool:
        for k, (stem, arr) in enumerate(pool.imap_unordered(_replay, replays, chunksize=4), 1):
            delen.append(arr); groepen.append(np.full(len(arr), k, np.int32))
            if k % 100 == 0:
                print(f"{k}/{len(replays)} replays, {sum(len(d) for d in delen)} momenten", flush=True)
    alles = np.concatenate(delen); g = np.concatenate(groepen)
    X, y = alles[:, :-1], alles[:, -1].astype(int)
    del alles, delen
    print(f"{len(y)} momenten, {y.mean():.1%} met goal binnen {VENSTER:.0f} s")
    model = lambda: HistGradientBoostingClassifier(max_depth=5, learning_rate=0.06, max_iter=300, min_samples_leaf=60, random_state=0)
    oof = np.zeros(len(y)); zone = np.zeros(len(y))
    from kern import zonewaarde
    zj = json.loads((WORTEL / "data" / "modellen" / "zonewaarde.json").read_text(encoding="utf-8"))
    for tr, te in GroupKFold(5).split(X, y, g):
        oof[te] = model().fit(X[tr], y[tr]).predict_proba(X[te])[:, 1]
    zone = np.array([float(zonewaarde.waarde3(zj, x[0], x[1], x[2])) for x in X])
    res = {}
    for naam, p in (("zonewaarde (alleen balplek)", zone), ("dreigingsmodel", oof)):
        p = np.clip(p, 1e-4, 1 - 1e-4)
        res[naam] = {"logloss": round(log_loss(y, p), 4), "brier": round(brier_score_loss(y, p), 4), "auc": round(roc_auc_score(y, p), 4)}
        print(f"{naam:28s} logloss {res[naam]['logloss']:.4f}  brier {res[naam]['brier']:.4f}  auc {res[naam]['auc']:.4f}")
    bak = np.digitize(oof, [.02, .05, .1, .2, .35, .5])
    for b in range(7):
        m = bak == b
        if m.sum():
            print(f"  bak {b}: n={m.sum():7d} voorspeld {oof[m].mean():.3f} echt {y[m].mean():.3f}")
    joblib.dump({"model": model().fit(X, y), "features": FEATURES}, MODEL_PAD)
    MODEL_PAD.with_suffix(".json").write_text(json.dumps({"momenten": int(len(y)), "validatie": res}, indent=2), encoding="utf-8")
    print("Opgeslagen:", MODEL_PAD)


if __name__ == "__main__":
    main()
