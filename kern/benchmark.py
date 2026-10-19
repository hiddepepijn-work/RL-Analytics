"""Benchmarks per rank: alle stats per speler per wedstrijd, als vergelijkingsbasis voor het spelerprofiel.

Tellingen worden genormaliseerd naar per 5 minuten speeltijd (zoals 'per 90' in voetbal); percentages,
gemiddelden en verhoudingen blijven zoals ze zijn.

Gebruik:
    uv run python -m kern.benchmark --band ranked-doubles_champion-1_champion-3 --max 300
Uitvoer: data/features/cache/spelerstats/<replay>.json en data/modellen/benchmark_<band>.json
"""
from __future__ import annotations

import argparse
import json
import random
from multiprocessing import Pool
from pathlib import Path
from kern.events import replay_fout

WORTEL = Path(__file__).resolve().parent.parent
CACHE = WORTEL / "data" / "features" / "cache" / "spelerstats"
NIET_NORMALISEREN = {
    "aanval.schotrendement", "aanval.xg_per_schot", "beweging.gem_snelheid", "positie.afstand_bal", "positie.afstand_teamgenoot",
    "boost.per_minuut", "boost.gemiddeld", "mechanics.speedflip_kwaliteit", "speeltijd",
}


def plat(stats: dict, speeltijd: float) -> dict:
    """Geneste stats → {'groep.sleutel': waarde}; tellingen per 5 minuten."""
    uit = {}
    for groep, waarden in stats.items():
        if not isinstance(waarden, dict):
            continue
        for k, v in waarden.items():
            pad = f"{groep}.{k}"
            if k == "heatmap":
                continue
            if isinstance(v, list) and len(v) <= 4 and all(isinstance(x, (int, float)) for x in v):
                for i, x in enumerate(v):
                    uit[f"{pad}.{i}"] = x
            elif isinstance(v, (int, float)) and not isinstance(v, bool):
                normaal = pad in NIET_NORMALISEREN or k.endswith("_pct") or (groep == "impact" and k != "impact")
                uit[pad] = v if normaal or not speeltijd else v * 300 / speeltijd
    return uit


def spelers_uit_data(d: dict) -> list[dict]:
    rijen = []
    for s in d["spelers"]:
        st = d["stats"]["spelers"].get(s["id"])
        if not st:
            continue
        tijd = st.get("speeltijd") or 300
        rijen.append({"id": s["id"], "naam": s["naam"], "team": s["team"], "speeltijd": tijd,
                      "gewonnen": int(d["meta"]["score"][s["team"]] > d["meta"]["score"][1 - s["team"]]),
                      "stats": plat(st, tijd)})
    return rijen


def verwerk(args) -> int:
    """Eén keer parsen voor twee caches: spelerstats (benchmark, rank-schatter) én rating-invoer (kern.rating_norm)."""
    from kern import rating_norm
    pad, rank = args
    uit, uit_rating = CACHE / f"{pad.stem}.json", rating_norm.CACHE / f"{pad.stem}.json"
    if uit.exists() and uit_rating.exists():
        return 0
    try:
        from kern.parseer import parseer
        d = parseer(pad, rank)
        uit.write_text(json.dumps(spelers_uit_data(d), ensure_ascii=False), encoding="utf-8")
        if not uit_rating.exists():
            rating_norm.CACHE.mkdir(parents=True, exist_ok=True)
            uit_rating.write_text(json.dumps(rating_norm.rating_invoer(d)), encoding="utf-8")
        return 1
    except BaseException as e:
        if not replay_fout(e):  # Ctrl+C / afsluiten: doorlaten; Rust-panic: als fout behandelen
            raise
        uit.write_text("[]", encoding="utf-8")
        print(f"overslaan {pad.name}: {type(e).__name__}", flush=True)
        return 0


def main() -> None:
    from kern.xg_model import rank_nummer
    ap = argparse.ArgumentParser()
    ap.add_argument("--band", default="ranked-doubles_champion-1_champion-3")
    ap.add_argument("--max", type=int, default=300)
    ap.add_argument("--processen", type=int, default=3)
    a = ap.parse_args()
    CACHE.mkdir(parents=True, exist_ok=True)
    replays = sorted((WORTEL / "data" / "replays" / a.band).glob("*.replay"))
    random.Random(0).shuffle(replays)
    replays = replays[: a.max]
    rank = rank_nummer(a.band)
    with Pool(a.processen) as pool:
        for i, _ in enumerate(pool.imap_unordered(verwerk, [(p, rank) for p in replays]), 1):
            if i % 25 == 0:
                print(f"{i}/{len(replays)}", flush=True)
    rijen = []
    for p in replays:
        f = CACHE / f"{p.stem}.json"
        if f.exists():
            rijen += [r | {"replay": p.stem} for r in json.loads(f.read_text(encoding="utf-8"))]
    (WORTEL / "data" / "modellen" / f"benchmark_{a.band}.json").write_text(
        json.dumps({"band": a.band, "wedstrijden": len({r["replay"] for r in rijen}), "rijen": rijen}, ensure_ascii=False),
        encoding="utf-8")
    print(f"Klaar: {len(rijen)} speler-wedstrijden uit {len({r['replay'] for r in rijen})} wedstrijden")


if __name__ == "__main__":
    main()
