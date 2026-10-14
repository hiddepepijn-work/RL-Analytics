"""xPass-model: kans dat een teamgenoot de bal als volgende raakt, eerlijk gevalideerd per wedstrijd.

Gebruik:
    uv run python -m kern.xpass_model
"""
from __future__ import annotations

import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score
from sklearn.model_selection import GroupKFold

from kern import per_rank
from kern.passen import FEATURES
from kern.xg_model import rank_naam, rank_nummer

WORTEL = Path(__file__).resolve().parent.parent


def model():
    return HistGradientBoostingClassifier(max_depth=4, learning_rate=0.05, max_iter=300, min_samples_leaf=60,
                                          l2_regularization=1.0, random_state=0)


def main() -> None:
    d = pd.read_csv(WORTEL / "data" / "features" / "passen.csv")
    X, y, g = d[FEATURES].to_numpy(float), d["compleet"].to_numpy(), d["replay"].to_numpy()
    print(f"{len(d)} kandidaten, {y.mean():.1%} kwam bij een teamgenoot, {d.replay.nunique()} wedstrijden\n")
    oof = np.zeros(len(d)); naief = np.zeros(len(d))
    for tr, te in GroupKFold(5).split(X, y, g):
        oof[te] = model().fit(X[tr], y[tr]).predict_proba(X[te])[:, 1]
        # Naïef: alleen de physics-marge, omgezet met een vaste sigmoïde (wat ik eerst deed)
        naief[te] = 1 / (1 + np.exp(-np.clip(d["marge"].to_numpy()[te], -9, 9) / 0.35))
    for naam, p in (("alleen physics-formule", naief), ("xPass-model", oof)):
        p = np.clip(p, 1e-4, 1 - 1e-4)
        print(f"{naam:24s} logloss {log_loss(y, p):.4f}  brier {brier_score_loss(y, p):.4f}  auc {roc_auc_score(y, p):.3f}  verwacht {p.sum():.0f} vs echt {y.sum()}")
    rank = d["band"].map(rank_nummer).to_numpy()
    rank_modellen, oof_gekozen, rank_rapport = per_rank.train_en_vergelijk(X, y, g, rank, model, oof, rank_naam)
    per_rank.print_rapport(rank_rapport, "balcontacten")
    d["p"] = oof_gekozen
    kal = d.groupby(pd.cut(d.p, [0, .1, .3, .5, .7, .9, 1], include_lowest=True), observed=True).agg(n=("compleet", "size"), voorspeld=("p", "mean"), echt=("compleet", "mean"))
    print("\nKalibratie:\n" + kal.round(3).to_string())
    print("\nPer band (echt vs verwacht compleet):\n" + d.groupby("band").agg(n=("compleet", "size"), echt=("compleet", "mean"), verwacht=("p", "mean")).round(3).to_string())
    eind = model().fit(X, y)
    uit = WORTEL / "data" / "modellen"; uit.mkdir(parents=True, exist_ok=True)
    joblib.dump({"model": eind, "features": FEATURES, "per_rank": rank_modellen}, uit / "xpass.joblib")
    pb = d.groupby("band").agg(n=("compleet", "size"), echt=("compleet", "mean"), verwacht=("p", "mean"), wedstrijden=("replay", "nunique"))
    pb["auc"] = [roc_auc_score(g.compleet, g.p) for _, g in d.groupby("band")]
    (uit / "xpass.json").write_text(json.dumps({"n": int(len(d)), "auc": round(float(roc_auc_score(y, oof)), 4),
                                                "naief_auc": round(float(roc_auc_score(y, naief)), 4),
                                                "verwacht": round(float(oof.sum())), "echt": int(y.sum()),
                                                "per_band": pb.reset_index().round(4).to_dict("records"),
                                                "per_rank_model": rank_rapport,
                                                "kalibratie": kal.reset_index().astype({"p": str}).round(4).to_dict("records")}, indent=2), encoding="utf-8")
    print(f"\nOpgeslagen: {uit / 'xpass.joblib'}")


if __name__ == "__main__":
    main()
