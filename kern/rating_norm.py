"""Rating-normen per rank: gemiddelde en spreiding van de impact per 5 minuten (totaal en per onderdeel).

Gebruik:
    uv run python -m kern.rating_norm --band ranked-doubles_champion-1_champion-3 --max 150
Uitvoer: data/modellen/rating_norm.json (per band; '_standaard' = Champion), cache in data/features/cache/rating/

De cache bewaart de invoer van de rating (schoten met kans/xG, passen, kansen, teams, speeltijd), niet de uitkomst:
na een aanpassing van de actiegewichten zijn de normen zo in seconden opnieuw te berekenen zonder te herparsen.
"""
from __future__ import annotations

import argparse
import json
import random
from multiprocessing import Pool
from pathlib import Path

import numpy as np

WORTEL = Path(__file__).resolve().parent.parent
CACHE = WORTEL / "data" / "features" / "cache" / "rating"
NORM_PAD = WORTEL / "data" / "modellen" / "rating_norm.json"


def verwerk(args) -> int:
    pad, rank = args
    uit = CACHE / f"{pad.stem}.json"
    if uit.exists():
        return 0
    try:
        from kern.parseer import parseer
        d = parseer(pad, rank)
        invoer = {"team": {s["id"]: s["team"] for s in d["spelers"]},
                  "speeltijd": {sid: r["speeltijd"] for sid, r in d["rating"]["spelers"].items()},
                  "schoten": d["schoten"], "passen": d["passen"], "kansen": d.get("kansen")}
        uit.write_text(json.dumps(invoer), encoding="utf-8")
        return 1
    except Exception as e:
        uit.write_text("{}", encoding="utf-8")
        print(f"overslaan {pad.name}: {type(e).__name__}: {str(e)[:60]}", flush=True)
        return 0


def main() -> None:
    from kern import events as eventcache, kansen
    from kern.rating import DELEN, ONDERDELEN, acties, sommen
    from kern.xg_model import rank_nummer
    ap = argparse.ArgumentParser()
    ap.add_argument("--band", default="ranked-doubles_champion-1_champion-3")
    ap.add_argument("--max", type=int, default=150)
    ap.add_argument("--processen", type=int, default=3)
    ap.add_argument("--alleen-cache", action="store_true", help="niets parsen, normen opnieuw uit de cache (na gewichtswijziging)")
    a = ap.parse_args()
    CACHE.mkdir(parents=True, exist_ok=True)
    replays = sorted((WORTEL / "data" / "replays" / a.band).glob("*.replay"))
    random.Random(1).shuffle(replays)
    replays = [p for p in replays if (CACHE / f"{p.stem}.json").exists()] if a.alleen_cache else replays[: a.max]
    with Pool(1 if a.alleen_cache else a.processen) as pool:
        for i, _ in enumerate(pool.imap_unordered(verwerk, [] if a.alleen_cache else [(p, rank_nummer(a.band)) for p in replays]), 1):
            if i % 25 == 0:
                print(f"{i}/{len(replays)}", flush=True)
    rijen = []
    for p in replays:
        f = CACHE / f"{p.stem}.json"
        inv = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
        if not inv.get("team"):
            continue
        ev = eventcache.lijst(p)
        kansen.herkalibreer(inv, ev)
        lijst = acties(ev, inv["schoten"], inv["passen"], inv["team"], inv.get("kansen"))
        for sid, tijd in inv["speeltijd"].items():
            som = sommen([x for x in lijst if x[1] == sid])
            rijen.append({"speeltijd": tijd, "impact": sum(som[o] for o in ONDERDELEN), "som": som})
    rijen = [r for r in rijen if r["speeltijd"] >= 240]
    per5 = lambda w, r: w * 300 / r["speeltijd"]
    # Robuust: mediaan als midden (typische speler = 6,5) en kwartielafstand/1,349 als spreiding,
    # want impact is scheef verdeeld (een paar uitschieters met veel goals trekken het gemiddelde omhoog)
    def robuust(v):
        q1, q2, q3 = np.percentile(v, [25, 50, 75])
        return {"gem": float(q2), "sd": float(max((q3 - q1) / 1.349, 0.02))}
    norm = {"n": len(rijen), "totaal": robuust([per5(r["impact"], r) for r in rijen])}
    for o in [*ONDERDELEN, *DELEN]:
        norm[o] = robuust([per5(r["som"][o], r) for r in rijen])
    alle = json.loads(NORM_PAD.read_text(encoding="utf-8")) if NORM_PAD.exists() else {}
    alle[a.band] = norm
    if "champion" in a.band or "_standaard" not in alle:
        alle["_standaard"] = norm
    NORM_PAD.write_text(json.dumps(alle, indent=1), encoding="utf-8")
    print(f"Normen {a.band}: {len(rijen)} speler-wedstrijden")
    for k, v in norm.items():
        if isinstance(v, dict):
            print(f"  {k:11s} gem {v['gem']:+.3f}  sd {v['sd']:.3f} per 5 min")


if __name__ == "__main__":
    main()
