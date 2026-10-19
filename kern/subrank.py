"""Subranks (Champion I/II/III enz.): wie speelde op welke subrank, normen per subrank en een rank-schatter.

- Bron: ballchasing geeft per speler rank + divisie mee (data/replays/<band>/lijst.jsonl). Koppeling aan onze spelers op
  platform-ID, met de naam als terugval (PlayStation-ID's verschillen van vorm).
- Niveau als getal: tier (Bronze I = 1 … Supersonic Legend = 22) + (divisie − 1) / 4.
- Rank-schatter: een model dat uit iemands spel (stats per 5 min) het niveau schat. Matchmaking zet spelers van gelijk
  niveau bij elkaar, dus het gemiddelde van alle vier spelers is een goede schatting van het lobbyniveau; over de laatste
  wedstrijden van een account geeft dat zijn huidige subrank. Replays bevatten zelf geen ranks, en ballchasing krijgt
  sinds de anti-cheat (april 2026) nauwelijks nieuwe uploads, dus zo schatten we de rank van eigen wedstrijden.

Gebruik:
    uv run python -m kern.subrank --train            # rank-schatter trainen + valideren → data/modellen/rankschatter.joblib
    uv run python -m kern.subrank --normen           # rating-normen per subrank (≥ MIN_SPELERS) → rating_norm.json
    uv run python -m kern.subrank --account Sand     # subrank van een account schatten uit zijn recente wedstrijden
"""
from __future__ import annotations

import argparse
import json
from functools import cache
from pathlib import Path

import numpy as np

WORTEL = Path(__file__).resolve().parent.parent
MODEL_PAD = WORTEL / "data" / "modellen" / "rankschatter.joblib"
SPELERSTATS = WORTEL / "data" / "features" / "cache" / "spelerstats"
MIN_SPELERS = 300
TIERNAMEN = ["bronze-1", "bronze-2", "bronze-3", "silver-1", "silver-2", "silver-3", "gold-1", "gold-2", "gold-3",
             "platinum-1", "platinum-2", "platinum-3", "diamond-1", "diamond-2", "diamond-3", "champion-1", "champion-2",
             "champion-3", "grand-champion-1", "grand-champion-2", "grand-champion-3", "supersonic-legend"]
# Stats die niets met speelniveau te maken hebben of uit de rating zelf komen (zou rondzingen)
NIET = ("impact.", "speeltijd")


def naam_niveau(niveau: float) -> str:
    t = int(min(22, max(1, np.floor(niveau + 1e-9))))
    d = int(min(4, max(1, round((niveau - t) * 4) + 1)))
    naam = TIERNAMEN[t - 1].replace("-", " ").title().replace("Grand Champion", "GC").replace("Supersonic Legend", "SSL")
    naam = naam.replace(" 1", " I").replace(" 2", " II").replace(" 3", " III")
    return f"{naam} div {d}" if t < 22 else naam


def _sleutel_bc(p: dict) -> str | None:
    pid = p.get("id") or {}
    plat = {"epic": "Epic", "steam": "Steam", "xbox": "Xbox", "switch": "Switch", "psynet": "PsyNet"}.get(pid.get("platform", ""))
    return f"{plat}:{pid.get('id')}" if plat and pid.get("id") else None


@cache
def ranks_per_replay() -> dict[str, dict]:
    """replay-id → {'ids': {onze sleutel: (tier, divisie, rank-id)}, 'namen': {naam: (…)}}"""
    uit = {}
    for f in (WORTEL / "data" / "replays").glob("*/lijst.jsonl"):
        for regel in f.open(encoding="utf-8"):
            r = json.loads(regel)
            ids, namen = {}, {}
            for t in ("blue", "orange"):
                for p in r.get(t, {}).get("players", []):
                    rk = p.get("rank")
                    if not rk or not rk.get("tier"):
                        continue
                    waarde = (int(rk["tier"]), int(rk.get("division") or 1), rk.get("id"))
                    if (k := _sleutel_bc(p)):
                        ids[k] = waarde
                    if p.get("name"):
                        namen[p["name"]] = waarde
            uit[r["id"]] = {"ids": ids, "namen": namen}
    return uit


def rank_van(replay: str, speler_id: str, naam: str):
    r = ranks_per_replay().get(replay)
    if not r:
        return None
    return r["ids"].get(speler_id) or r["namen"].get(naam)


def _rijen():
    """Alle speler-wedstrijden met bekende rank: (replay, stats per 5 min, niveau, rank-id)."""
    for f in SPELERSTATS.glob("*.json"):
        for row in json.loads(f.read_text(encoding="utf-8")) or []:
            rk = rank_van(f.stem, row["id"], row["naam"])
            if rk and row.get("speeltijd", 0) >= 180:
                yield f.stem, row["stats"], rk[0] + (rk[1] - 1) / 4, rk[2]


def train() -> None:
    import joblib
    from sklearn.ensemble import HistGradientBoostingRegressor
    from sklearn.model_selection import GroupKFold
    data = list(_rijen())
    kolommen = sorted({k for _, st, _, _ in data for k in st if not k.startswith(NIET)})
    X = np.array([[st.get(k, np.nan) for k in kolommen] for _, st, _, _ in data], float)
    y = np.array([n for *_, n, _ in data]); g = np.array([r for r, *_ in data])
    print(f"{len(y)} speler-wedstrijden uit {len(set(g))} wedstrijden, {len(kolommen)} stats")
    model = lambda: HistGradientBoostingRegressor(max_depth=5, learning_rate=0.05, max_iter=400, min_samples_leaf=40, random_state=0)
    oof = np.zeros(len(y))
    for tr, te in GroupKFold(5).split(X, y, g):
        oof[te] = model().fit(X[tr], y[tr]).predict(X[te])
    print(f"per speler: fout {np.mean(np.abs(oof - y)):.2f} tier (≈ {4 * np.mean(np.abs(oof - y)):.1f} divisies), r = {np.corrcoef(oof, y)[0, 1]:.3f}")
    # Lobby: gemiddelde van de 4 spelers tegen het echte lobbygemiddelde
    lob = {}
    for r, p, t in zip(g, oof, y):
        lob.setdefault(r, ([], []))[0].append(p); lob[r][1].append(t)
    lp = np.array([np.mean(a) for a, _ in lob.values()]); lt = np.array([np.mean(b) for _, b in lob.values()])
    print(f"per lobby (4 spelers): fout {np.mean(np.abs(lp - lt)):.2f} tier, binnen 1 tier {np.mean(np.abs(lp - lt) < 1) * 100:.0f}%")
    # Over 10 wedstrijden van hetzelfde niveau: spreiding van het gemiddelde (bootstrap per niveau-band)
    rng = np.random.default_rng(0); fouten = []
    for _ in range(2000):
        t = rng.choice(np.unique(np.round(lt)))
        kand = np.flatnonzero(np.abs(lt - t) < 0.5)
        if len(kand) >= 10:
            k = rng.choice(kand, 10, replace=False); fouten.append(abs(lp[k].mean() - lt[k].mean()))
    print(f"over 10 wedstrijden: fout {np.mean(fouten):.2f} tier (≈ {4 * np.mean(fouten):.1f} divisies)")
    joblib.dump({"model": model().fit(X, y), "kolommen": kolommen}, MODEL_PAD)
    MODEL_PAD.with_suffix(".json").write_text(json.dumps({
        "speler_wedstrijden": int(len(y)), "fout_speler_tier": round(float(np.mean(np.abs(oof - y))), 3),
        "fout_lobby_tier": round(float(np.mean(np.abs(lp - lt))), 3), "fout_10_wedstrijden_tier": round(float(np.mean(fouten)), 3)}, indent=1), encoding="utf-8")
    print("Opgeslagen:", MODEL_PAD)


def schat_lobby(d: dict) -> float | None:
    """Geschat niveau van een wedstrijd (gemiddelde van alle spelers) uit verwerkte wedstrijddata."""
    import joblib
    if not MODEL_PAD.exists():
        return None
    from kern.benchmark import spelers_uit_data
    pakket = joblib.load(MODEL_PAD)
    rows = [r for r in spelers_uit_data(d) if r.get("speeltijd", 0) >= 120]
    if not rows:
        return None
    X = np.array([[r["stats"].get(k, np.nan) for k in pakket["kolommen"]] for r in rows], float)
    return float(np.mean(pakket["model"].predict(X)))


def account_schatten(naam: str, n: int = 12) -> dict | None:
    """Subrank van een account uit zijn n nieuwste eigen Ranked Doubles-wedstrijden → opgeslagen in data/accounts.json."""
    from kern import accounts
    verwerkt = WORTEL / "data" / "verwerkt"
    acc = accounts.vind(naam)
    if not acc:
        return None
    games = []
    for f in verwerkt.glob("*.json"):
        if f.name in ("index.json", "profiel.json"):
            continue
        d = json.loads(f.read_text(encoding="utf-8"))
        m = d["meta"]
        if m.get("eigen") and m.get("ik") in acc["ids"] and m.get("playlist") == 11:
            games.append((m.get("datum") or "", d))
    games = sorted(games, key=lambda x: x[0])[-n:]
    niveaus = [x for x in (schat_lobby(d) for _, d in games) if x is not None]
    if not niveaus:
        return None
    niveau = float(np.median(niveaus))
    t = int(min(22, max(1, np.floor(niveau + 1e-9))))
    uit = {"niveau": round(niveau, 2), "subrank": TIERNAMEN[t - 1], "naam": naam_niveau(niveau), "wedstrijden": len(niveaus)}
    accounts.zet(naam, "rank_schatting", uit)
    return uit


def normen() -> None:
    """Rating-normen per subrank uit de normcache (alle banden); te weinig spelers → geen eigen norm (terugval op de rank)."""
    from kern import events as eventcache, kansen
    from kern.rating import DELEN, ONDERDELEN, acties, sommen, touch_tijden
    from kern.rating_norm import CACHE, NORM_PAD
    per = {}
    for f in CACHE.glob("*.json"):
        inv = json.loads(f.read_text(encoding="utf-8"))
        st = SPELERSTATS / f.name
        p = next((WORTEL / "data" / "replays").glob(f"*/{f.stem}.replay"), None)
        if not inv.get("team") or not st.exists() or p is None:
            continue
        namen = {r["id"]: r["naam"] for r in json.loads(st.read_text(encoding="utf-8")) or []}
        ev = eventcache.lijst(p); kansen.herkalibreer(inv, ev)
        lijst = acties(ev, inv["schoten"], inv["passen"], inv["team"], inv.get("kansen"))
        tt = touch_tijden(ev)
        for sid, tijd in inv["speeltijd"].items():
            rk = rank_van(f.stem, sid, namen.get(sid, ""))
            if not rk or tijd < 240:
                continue
            som = sommen([x for x in lijst if x[1] == sid])
            per.setdefault(rk[2], []).append({"speeltijd": tijd, "som": som, "touches": len(tt.get(sid, []))})

    def robuust(v):
        q1, q2, q3 = np.percentile(v, [25, 50, 75])
        return {"gem": float(q2), "sd": float(max((q3 - q1) / 1.349, 0.02))}
    alle = json.loads(NORM_PAD.read_text(encoding="utf-8")) if NORM_PAD.exists() else {}
    for sub in TIERNAMEN:
        rijen = per.get(sub, [])
        if len(rijen) < MIN_SPELERS:
            alle.pop(f"sub:{sub}", None)
            print(f"  {sub:18s} {len(rijen):5d} speler-wedstrijden — te weinig, terugval op de rank")
            continue
        p5 = lambda w, r: w * 300 / r["speeltijd"]
        n = {"n": len(rijen)}
        for o in [*ONDERDELEN, *DELEN]:
            n[o] = robuust([p5(r["som"][o], r) for r in rijen])
        n["touches"] = robuust([p5(r["touches"], r) for r in rijen])
        alle[f"sub:{sub}"] = n
        print(f"  {sub:18s} {len(rijen):5d} speler-wedstrijden — doelbijdrage gem {n['Doelbijdrage']['gem']:.2f}")
    NORM_PAD.write_text(json.dumps(alle, indent=1), encoding="utf-8")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--train", action="store_true")
    ap.add_argument("--normen", action="store_true")
    ap.add_argument("--account")
    a = ap.parse_args()
    if a.train:
        train()
    if a.normen:
        normen()
    if a.account:
        print(account_schatten(a.account))
