"""Spelerprofiel: eigen stats vs benchmark van de eigen rank.

Percentiel: je gemiddelde over k wedstrijden wordt vergeleken met gemiddelden van k willekeurige
wedstrijden uit de benchmark (bootstrap). Een gemiddelde over meerdere potjes schommelt minder dan één potje,
dus vergelijken met losse wedstrijden zou te extreme percentielen geven.
Onzekerheid: 80%-interval door je eigen wedstrijden opnieuw te trekken (bootstrap).

Gebruik:
    uv run python -m kern.profiel --naam "Sand ツ"
Uitvoer: data/verwerkt/profiel.json (de app leest dit)
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from kern.benchmark import plat

WORTEL = Path(__file__).resolve().parent.parent
VERWERKT = WORTEL / "data" / "verwerkt"
BAND = "ranked-doubles_champion-1_champion-3"
B = 3000
BETROUWBAAR_VANAF = 15  # wedstrijden (zie kern/steekproef.py: afwerking per speler ±5 pt ≈ 14)
# Kernset voor de profielscore: (stat, richting)
KERN = [("aanval.xg", 1), ("aanval.goals", 1), ("passen.pass_waarde", 1), ("passen.xpass", 1), ("verdedigen.saves", 1),
        ("duels.5050_gewonnen", 1), ("boost.gestolen", 1), ("balbezit.touches", 1), ("passen.aanspeelbaar_pct", 1),
        ("duels.whiffs", -1), ("boost.tijd_0_pct", -1), ("passen.naar_niemand", -1)]


def percentiel_k(pop: np.ndarray, waarde: float, k: int, rng) -> float:
    gem = rng.choice(pop, size=(B, k), replace=True).mean(axis=1)
    return float(100 * ((gem < waarde).mean() + 0.5 * (gem == waarde).mean()))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--naam", required=True)
    ap.add_argument("--dagen", type=int, default=120, help="alleen wedstrijden van de laatste N dagen (t.o.v. de nieuwste)")
    ap.add_argument("--max", type=int, default=40, help="hooguit de N nieuwste wedstrijden")
    a = ap.parse_args()
    rng = np.random.default_rng(0)
    from kern import accounts
    account = accounts.vind(a.naam)
    ids = set(account["ids"]) if account else None
    weergavenaam = (account.get("bekende_namen") or [account["naam"]])[0] if account else a.naam

    games = []
    for f in sorted(VERWERKT.glob("*.json")):
        if f.name in ("index.json", "profiel.json"):
            continue
        d = json.loads(f.read_text(encoding="utf-8"))
        m = d["meta"]
        if not (m.get("eigen") and m.get("categorie") == "mee"):
            continue
        if ids is not None and m.get("ik") not in ids:
            continue  # wedstrijd van een ander account
        ik = m["ik"]
        st = d["stats"]["spelers"][ik]
        tijd = st.get("speeltijd") or 300
        mijn_schoten = [s for s in d.get("schoten", []) if s["speler"] == ik]
        games.append({"bestand": f.name, "datum": m.get("datum"), "uitslag": m.get("uitslag"), "tijd": tijd,
                      "stats": plat(st, tijd), "heatmap": st["positie"]["heatmap"],
                      "goals": st["aanval"]["goals"], "xg": sum(s["xg"] or 0 for s in mijn_schoten),
                      "xg_var": sum((s["xg"] or 0) * (1 - (s["xg"] or 0)) for s in mijn_schoten),
                      "rating": (d.get("rating") or {}).get("spelers", {}).get(ik)})
    games.sort(key=lambda g: g["datum"] or "")
    if not games:
        raise SystemExit("Geen eigen wedstrijden (categorie 'mee') gevonden.")
    # Huidige vorm: oude wedstrijden (ander niveau, oude gewoontes) niet even zwaar laten wegen als die van nu
    from datetime import datetime, timedelta
    def _dt(g):
        try:
            return datetime.strptime((g["datum"] or "")[:10], "%Y-%m-%d")
        except ValueError:
            return None
    nieuwste = max((_dt(g) for g in games if _dt(g)), default=None)
    alle = len(games)
    if nieuwste:
        games = [g for g in games if _dt(g) is None or _dt(g) >= nieuwste - timedelta(days=a.dagen)]
    games = games[-a.max:]
    weggelaten = alle - len(games)

    bench_pad = WORTEL / "data" / "modellen" / f"benchmark_{BAND}.json"
    bench = json.loads(bench_pad.read_text(encoding="utf-8"))["rijen"] if bench_pad.exists() else []
    k = len(games)
    stats = {}
    for pad in sorted({p for g in games for p in g["stats"]}):
        reeks = [g["stats"].get(pad) for g in games]
        reeks = [x for x in reeks if x is not None]
        if not reeks:
            continue
        waarde = float(np.mean(reeks))
        boot = rng.choice(reeks, size=(B, len(reeks)), replace=True).mean(axis=1)
        rij = {"waarde": round(waarde, 3), "laag": round(float(np.percentile(boot, 10)), 3), "hoog": round(float(np.percentile(boot, 90)), 3),
               "reeks": [round(x, 3) for x in reeks[-10:]]}
        pop = np.array([r["stats"][pad] for r in bench if r["stats"].get(pad) is not None], float)
        if len(pop) >= 50:
            rij["p"] = round(percentiel_k(pop, waarde, len(reeks), rng))
            rij["p_laag"] = round(percentiel_k(pop, rij["laag"], len(reeks), rng))
            rij["p_hoog"] = round(percentiel_k(pop, rij["hoog"], len(reeks), rng))
            rij["mediaan_rank"] = round(float(np.median(pop)), 3)
        stats[pad] = rij

    # Profielscore = gemiddeld percentiel over de kernset (lager-is-beter omgedraaid)
    kern_p = [(stats[s]["p"] if r > 0 else 100 - stats[s]["p"]) for s, r in KERN if s in stats and "p" in stats[s]]
    kern_lo = [(stats[s]["p_laag"] if r > 0 else 100 - stats[s]["p_hoog"]) for s, r in KERN if s in stats and "p" in stats[s]]
    kern_hi = [(stats[s]["p_hoog"] if r > 0 else 100 - stats[s]["p_laag"]) for s, r in KERN if s in stats and "p" in stats[s]]

    cum, cum_var, afwerking = 0.0, 0.0, []
    for g in games:
        cum += g["goals"] - g["xg"]; cum_var += g["xg_var"]
        b = 1.28 * np.sqrt(cum_var)
        afwerking.append([round(cum, 2), round(cum - b, 2), round(cum + b, 2)])

    uit = {
        "naam": weergavenaam, "account": account["naam"] if account else a.naam, "ids": sorted(ids) if ids else [],
        "rank": "Champion", "band": BAND, "wedstrijden": k, "weggelaten": weggelaten, "venster_dagen": a.dagen,
        "uren": round(sum(g["tijd"] for g in games) / 3600, 1),
        "winst": sum(g["uitslag"] == "W" for g in games), "verlies": sum(g["uitslag"] == "V" for g in games),
        "benchmark_wedstrijden": len({r["replay"] for r in bench}), "betrouwbaar_vanaf": BETROUWBAAR_VANAF,
        "profielscore": {"p": round(float(np.mean(kern_p))), "laag": round(float(np.mean(kern_lo))), "hoog": round(float(np.mean(kern_hi)))} if kern_p else None,
        "stats": stats,
        "heatmap": np.round(np.mean([g["heatmap"] for g in games], axis=0), 3).tolist(),
        "afwerking": afwerking,
        # Ratings: gemiddeld wedstrijdcijfer, per onderdeel, en per wedstrijd (voor de vormgrafiek)
        "ratings": {
            "gem": round(float(np.mean([g["rating"]["eind"] for g in games if g["rating"] and g["rating"]["eind"] is not None])), 2)
            if any(g["rating"] and g["rating"]["eind"] is not None for g in games) else None,
            "onderdelen": {o: round(float(np.mean([g["rating"]["onderdelen"][o]["cijfer"] for g in games if g["rating"]])), 2)
                           for o in ["Schieten", "Passen", "Verdedigen", "Duels", "Kickoffs", "Balbezit"]} if any(g["rating"] for g in games) else {},
            "per_wedstrijd": [{"bestand": g["bestand"].removesuffix(".json"), "datum": g["datum"], "uitslag": g["uitslag"],
                               "rating": g["rating"]["eind"] if g["rating"] else None} for g in games],
        },
        "recent": [{"bestand": g["bestand"], "datum": g["datum"], "uitslag": g["uitslag"]} for g in games[-10:]],
    }
    (VERWERKT / "profiel.json").write_text(json.dumps(uit, ensure_ascii=False), encoding="utf-8")
    print(f"Profiel {a.naam}: {k} wedstrijden, {len(stats)} stats, benchmark {uit['benchmark_wedstrijden']} wedstrijden, "
          f"score p{uit['profielscore']['p'] if uit['profielscore'] else '?'}")


if __name__ == "__main__":
    main()
