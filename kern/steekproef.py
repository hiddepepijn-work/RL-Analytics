"""Hoeveel data is nodig per rank? Rekent met de eigen data (OOF-voorspellingen), niet met vuistregels.

Vier vragen, elk met eigen benodigde steekproef (α = 0,05, power 80%):
  1. verschil tussen twee ranks in raakkans bij halve kansen (10–30% xG), effect 4 procentpunt
  2. goals − xG per rank op ±2% nauwkeurig (95%-interval)
  3. eigen model per rank: leercurve tot het eigen model het algemene evenaart
  4. per speler: afwerking (goals − xG per schot) op ±5 procentpunt nauwkeurig

Gebruik:
    uv run python -m kern.steekproef
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import log_loss
from sklearn.model_selection import GroupShuffleSplit

from kern.xg_model import FEATURES, model, rank_naam, rank_nummer

WORTEL = Path(__file__).resolve().parent.parent
Z = 1.96 + 0.84  # α 0,05 tweezijdig + power 80%


def main() -> None:
    d = pd.read_csv(WORTEL / "data" / "features" / "schoten.csv")
    o = pd.read_csv(WORTEL / "data" / "modellen" / "xg_oof.csv")
    d["p"] = o["xg_algemeen"].to_numpy()
    d["rank"] = d["band"].map(rank_nummer)
    d = d[d["rank"] >= 0]
    uit = {"per_rank": [], "leercurve": []}

    print("1+2+4. Per rank (per wedstrijd)")
    for r, g in d.groupby("rank"):
        w = g.replay.nunique()
        half = g[(g.p >= 0.1) & (g.p < 0.3)]
        half_pw = len(half) / w
        # 1. twee-proportietoets: halve kansen per groep voor 4 pt verschil rond de waargenomen raakkans
        p1 = half.goal.mean(); p2 = p1 + 0.04
        n_half = Z ** 2 * (p1 * (1 - p1) + p2 * (1 - p2)) / 0.04 ** 2
        w_vergelijk = n_half / half_pw
        # 2. goals − xG per rank op ±2%: variantie van (G − xG) per wedstrijd ≈ Σ p(1−p)
        var_w = (g.p * (1 - g.p)).sum() / w
        xg_w = g.p.sum() / w
        w_kalibratie = (1.96 * np.sqrt(var_w) / (0.02 * xg_w)) ** 2
        # 4. per speler: afwerking op ±5 pt per schot (95%) → schoten nodig, omgerekend naar wedstrijden
        spelers_per_team = 2
        schoten_speler_w = len(g) / w / (2 * spelers_per_team)
        var_schot = (g.p * (1 - g.p)).mean()
        n_schoten_speler = (1.96 ** 2) * var_schot / 0.05 ** 2
        rij = {"rank": rank_naam(int(r)), "wedstrijden_nu": int(w), "halve_kansen_per_wedstrijd": round(half_pw, 2),
               "raak_halve_kans": round(p1, 3), "nodig_rank_vergelijken": int(np.ceil(w_vergelijk)),
               "nodig_goals_min_xg_2pct": int(np.ceil(w_kalibratie)),
               "schoten_per_speler_per_wedstrijd": round(schoten_speler_w, 1), "nodig_speler_afwerking": int(np.ceil(n_schoten_speler / schoten_speler_w))}
        uit["per_rank"].append(rij)
        print(f"  {rij['rank']:9s} nu {w:4d} wedstr | rank-vergelijking: {rij['nodig_rank_vergelijken']:4d} | goals−xG ±2%: {rij['nodig_goals_min_xg_2pct']:4d} | "
              f"speler-afwerking: {rij['nodig_speler_afwerking']:3d} eigen wedstr")

    # 3. Leercurve: eigen model op k wedstrijden van één rank vs algemeen model (alle andere data + dezelfde k)
    print("\n3. Leercurve eigen model (logloss op vaste testset, lager = beter)")
    for r, g in d.groupby("rank"):
        if g.replay.nunique() < 150:
            continue
        test_idx, _ = next(GroupShuffleSplit(n_splits=1, train_size=60, random_state=1).split(g, groups=g.replay))
        test = g.iloc[test_idx]
        rest = g[~g.replay.isin(test.replay)]
        anderen = d[(d["rank"] != r)]
        wedstr = rest.replay.unique()
        rng = np.random.default_rng(0)
        for k in [25, 50, 100, 200, 300, 400, 600]:
            if k > len(wedstr):
                break
            kies = rest[rest.replay.isin(rng.choice(wedstr, k, replace=False))]
            eigen = model().fit(kies[FEATURES].to_numpy(float), kies.goal)
            alg_data = pd.concat([anderen, kies])
            alg = model().fit(alg_data[FEATURES].to_numpy(float), alg_data.goal)
            Xt, yt = test[FEATURES].to_numpy(float), test.goal
            ll_e = log_loss(yt, np.clip(eigen.predict_proba(Xt)[:, 1], 1e-4, 1 - 1e-4))
            ll_a = log_loss(yt, np.clip(alg.predict_proba(Xt)[:, 1], 1e-4, 1 - 1e-4))
            uit["leercurve"].append({"rank": rank_naam(int(r)), "wedstrijden": k, "eigen": round(ll_e, 4), "algemeen": round(ll_a, 4)})
            print(f"  {rank_naam(int(r)):9s} k={k:4d}  eigen {ll_e:.4f}  algemeen {ll_a:.4f}  {'eigen beter' if ll_e < ll_a else ''}")

    (WORTEL / "data" / "modellen" / "steekproef.json").write_text(json.dumps(uit, indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
