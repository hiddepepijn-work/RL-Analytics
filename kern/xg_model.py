"""xG-model trainen en eerlijk beoordelen.

Validatie per WEDSTRIJD (GroupKFold): schoten uit dezelfde wedstrijd zitten nooit tegelijk
in train en test, anders lekt informatie en lijkt het model beter dan het is.

Gebruik:
    uv run python -m kern.xg_model
"""
from __future__ import annotations

import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.inspection import permutation_importance
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score
from sklearn.model_selection import GroupKFold

from kern import per_rank

WORTEL = Path(__file__).resolve().parent.parent
RANK_ORDE = ["bronze", "silver", "gold", "platinum", "diamond", "champion", "grand-champion"]
FEATURES = [
    "afstand", "hoek", "bal_z", "bal_snelheid", "snelheid_naar_doel",
    "op_doel", "t_doel", "ingang_x", "ingang_z", "mis_afstand",
    "verdediger_min_v", "verdediger_2e_v", "verdedigers_tussen", "verdedigers_in_doel", "verdediger_boost",
    "schutter_z", "schutter_boost", "aanvaller_dichtbij", "rank",
]


def rank_nummer(band: str) -> int:
    """'ranked-doubles_gold-1_gold-3' → 2 (index van de laagste rank in de band)."""
    laag = band.split("_")[1]
    return next((i for i, r in enumerate(RANK_ORDE) if laag.startswith(r + "-")), -1)


def rank_naam(i: int) -> str:
    return {-1: "Gemengd", 2: "Gold", 3: "Platinum", 4: "Diamond", 5: "Champion", 6: "GC+"}.get(i, RANK_ORDE[i].title() if 0 <= i < len(RANK_ORDE) else "?")


def model():
    return HistGradientBoostingClassifier(
        max_depth=4, learning_rate=0.05, max_iter=300, min_samples_leaf=40,
        l2_regularization=1.0, random_state=0)


def meet(y, p):
    p = np.clip(p, 1e-4, 1 - 1e-4)
    return {"logloss": log_loss(y, p), "brier": brier_score_loss(y, p), "auc": roc_auc_score(y, p)}


def main() -> None:
    d = pd.read_csv(WORTEL / "data" / "features" / "schoten.csv")
    d["rank"] = d["band"].map(rank_nummer)
    X, y, groep = d[FEATURES].to_numpy(float), d["goal"].to_numpy(), d["replay"].to_numpy()
    print(f"{len(d)} schoten, {y.sum()} goals ({y.mean():.1%}), {d.replay.nunique()} wedstrijden\n")

    oof = np.zeros(len(d)); oof_simpel = np.zeros(len(d)); oof_basis = np.zeros(len(d))
    for train, test in GroupKFold(n_splits=5).split(X, y, groep):
        m = model().fit(X[train], y[train])
        oof[test] = m.predict_proba(X[test])[:, 1]
        # Simpel referentiemodel: alleen afstand, hoek en op-doel (zoals een eerste voetbal-xG)
        cols = [FEATURES.index(c) for c in ("afstand", "hoek", "op_doel")]
        lr = LogisticRegression(max_iter=1000).fit(X[train][:, cols], y[train])
        oof_simpel[test] = lr.predict_proba(X[test][:, cols])[:, 1]
        oof_basis[test] = y[train].mean()

    res = {"basis (altijd gemiddelde)": meet(y, oof_basis), "simpel (afstand+hoek+op doel)": meet(y, oof_simpel), "xG-model": meet(y, oof)}
    print(f"{'model':32s} {'logloss':>8s} {'brier':>7s} {'auc':>6s}   (lager/lager/hoger = beter)")
    for k, v in res.items():
        print(f"{k:32s} {v['logloss']:8.4f} {v['brier']:7.4f} {v['auc']:6.3f}")

    # Eigen model per rank (vangnet: algemeen model)
    rank = d["rank"].to_numpy()
    rank_modellen, oof_gekozen, rank_rapport = per_rank.train_en_vergelijk(X, y, groep, rank, model, oof, rank_naam)
    per_rank.print_rapport(rank_rapport, "schoten")
    d["xg_algemeen"] = oof
    res["xG per rank"] = meet(y, oof_gekozen)
    print(f"{'xG per rank (eindmodel)':32s} {res['xG per rank']['logloss']:8.4f} {res['xG per rank']['brier']:7.4f} {res['xG per rank']['auc']:6.3f}")

    # Kalibratie: klopt 30% voorspeld ook echt met ~30% raak? (met de gekozen modellen)
    d["xg"] = oof_gekozen
    d["bak"] = pd.cut(d.xg, [0, .05, .1, .2, .3, .5, .7, 1.0], include_lowest=True)
    kal = d.groupby("bak", observed=True).agg(schoten=("goal", "size"), voorspeld=("xg", "mean"), echt=("goal", "mean"))
    print("\nKalibratie (buiten-de-steekproef):\n" + kal.round(3).to_string())

    per_band = d.groupby("band").agg(schoten=("goal", "size"), goals=("goal", "sum"), xg=("xg", "sum"),
                                     wedstrijden=("replay", "nunique"), raak=("goal", "mean"))
    per_band["goals_min_xg"] = per_band.goals - per_band.xg
    per_band["auc"] = [roc_auc_score(g.goal, g.xg) if g.goal.nunique() > 1 else None for _, g in d.groupby("band")]
    per_band["schoten_per_wedstrijd"] = per_band.schoten / per_band.wedstrijden
    print("\nPer rank-groep:\n" + per_band.round(1).to_string())

    # Eindmodel op alles + welke features ertoe doen
    eind = model().fit(X, y)
    imp = permutation_importance(eind, X, y, scoring="neg_log_loss", n_repeats=5, random_state=0)
    belang = pd.Series(imp.importances_mean, index=FEATURES).sort_values(ascending=False)
    print("\nBelangrijkste features (stijging logloss als je hem husselt):\n" + belang.head(10).round(4).to_string())

    uit = WORTEL / "data" / "modellen"; uit.mkdir(parents=True, exist_ok=True)
    joblib.dump({"model": eind, "features": FEATURES, "per_rank": rank_modellen}, uit / "xg.joblib")
    (uit / "xg.json").write_text(json.dumps({
        "schoten": int(len(d)), "goals": int(y.sum()), "wedstrijden": int(d.replay.nunique()),
        "validatie": {k: {m: round(v, 4) for m, v in r.items()} for k, r in res.items()},
        "belang": belang.round(4).to_dict(),
        "kalibratie": kal.reset_index().astype({"bak": str}).round(4).to_dict("records"),
        "per_band": per_band.reset_index().round(4).to_dict("records"),
        "per_rank_model": rank_rapport,
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    d[["replay", "tijd", "team", "speler", "xg", "xg_algemeen", "goal"]].to_csv(uit / "xg_oof.csv", index=False)
    print(f"\nOpgeslagen: {uit / 'xg.joblib'}")


if __name__ == "__main__":
    main()
