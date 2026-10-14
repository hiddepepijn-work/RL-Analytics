"""xGOT-model (expected goals on target, ook wel post-shot xG): kans op een goal voor een schot dat op doel gaat,
alleen op basis van het schot zelf — plaatsing (waar de bal het doel binnenkomt), snelheid, tijd tot het doel, afstand.

Bewust ZONDER verdedigers: net als in voetbal meet xGOT hoe goed het schot is, niet waar de keeper staat. Daardoor is
'goals voorkomen' (xGOT van de schoten die je redde) eerlijk: een redding op een bovenhoek-knal telt zwaar, ook als je er
goed voor stond. Training op schoten met een balbaan op doel plus alle goals (afgeweken ballen zitten daar ook in).

Gebruik:
    uv run python -m kern.xgot_model      # na kern.schoten; leest data/features/schoten.csv
Uitvoer: data/modellen/xgot.joblib + xgot.json
"""
from __future__ import annotations

import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.model_selection import GroupKFold

from kern.xg_model import meet, model, rank_nummer

WORTEL = Path(__file__).resolve().parent.parent
FEATURES = ["afstand", "hoek", "bal_z", "bal_snelheid", "snelheid_naar_doel", "t_doel", "ingang_x", "ingang_z", "rank"]


def main() -> None:
    d = pd.read_csv(WORTEL / "data" / "features" / "schoten.csv")
    d = d[(d.op_doel == 1) | (d.goal == 1)].reset_index(drop=True)
    d["rank"] = d["band"].map(rank_nummer)
    X, y, groep = d[FEATURES].to_numpy(float), d["goal"].to_numpy(), d["replay"].to_numpy()
    print(f"{len(d)} schoten op doel, {y.sum()} goals ({y.mean():.1%}), {d.replay.nunique()} wedstrijden")

    oof, basis = np.zeros(len(d)), np.zeros(len(d))
    for train, test in GroupKFold(n_splits=5).split(X, y, groep):
        oof[test] = model().fit(X[train], y[train]).predict_proba(X[test])[:, 1]
        basis[test] = y[train].mean()
    res = {"basis": meet(y, basis), "xGOT": meet(y, oof)}
    for k, v in res.items():
        print(f"{k:8s} logloss {v['logloss']:.4f}  brier {v['brier']:.4f}  auc {v['auc']:.3f}")
    d["xgot"] = oof
    d["bak"] = pd.cut(d.xgot, [0, .1, .2, .3, .5, .7, .9, 1.0], include_lowest=True)
    kal = d.groupby("bak", observed=True).agg(schoten=("goal", "size"), voorspeld=("xgot", "mean"), echt=("goal", "mean"))
    print("\nKalibratie (buiten-de-steekproef):\n" + kal.round(3).to_string())

    uit = WORTEL / "data" / "modellen"
    joblib.dump({"model": model().fit(X, y), "features": FEATURES}, uit / "xgot.joblib")
    (uit / "xgot.json").write_text(json.dumps({
        "schoten": int(len(d)), "goals": int(y.sum()),
        "validatie": {k: {m: round(v, 4) for m, v in r.items()} for k, r in res.items()},
        "kalibratie": kal.reset_index().astype({"bak": str}).round(4).to_dict("records"),
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nOpgeslagen: {uit / 'xgot.joblib'}")


if __name__ == "__main__":
    main()
