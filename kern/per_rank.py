"""Eén model per rank, met het algemene model als vangnet.

Per rank met genoeg data wordt een eigen model getraind en eerlijk (per wedstrijd) vergeleken met het
algemene model op dezelfde schoten/balcontacten. Het eigen model wordt alleen gebruikt als het daar
beter voorspelt: lagere logloss, of even scherp (≤1% verschil) en beter gekalibreerd. Ranks met te weinig data gebruiken het algemene model.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.metrics import log_loss, roc_auc_score
from sklearn.model_selection import GroupKFold

MIN_N = 2000          # minimaal aantal voorbeelden voor een eigen model
MIN_WEDSTRIJDEN = 40


def ece(p, y, bins=(0, .05, .1, .2, .3, .5, .7, 1)) -> float:
    """Gemiddelde kalibratiefout in kanspunten, gewogen naar aantal per bak."""
    d = pd.DataFrame({"p": p, "y": y})
    t = d.groupby(pd.cut(d.p, bins, include_lowest=True), observed=True).agg(n=("y", "size"), v=("p", "mean"), e=("y", "mean"))
    return float((t.n * (t.v - t.e).abs()).sum() / t.n.sum())


def _scores(p, y) -> dict:
    p = np.clip(p, 1e-4, 1 - 1e-4)
    return {"logloss": round(float(log_loss(y, p)), 4), "auc": round(float(roc_auc_score(y, p)), 4) if len(set(y)) > 1 else None,
            "ece": round(ece(p, y), 4), "verwacht": round(float(p.sum()), 1)}


def train_en_vergelijk(X, y, groep, rank, maak_model, oof_algemeen, rank_naam):
    """→ (modellen per rank, eerlijke OOF-voorspelling met de gekozen modellen, rapport per rank)."""
    modellen, rapport = {}, []
    oof_gekozen = oof_algemeen.copy()
    for r in sorted(set(int(x) for x in rank)):
        m = rank == r
        rij = {"rank": rank_naam(r), "n": int(m.sum()), "wedstrijden": int(len(set(groep[m]))), "echt": int(y[m].sum()),
               "algemeen": _scores(oof_algemeen[m], y[m]), "eigen": None, "keuze": "algemeen (te weinig data)"}
        if m.sum() >= MIN_N and rij["wedstrijden"] >= MIN_WEDSTRIJDEN and len(set(y[m])) > 1:
            Xm, ym, gm = X[m], y[m], groep[m]
            eigen = np.zeros(int(m.sum()))
            for tr, te in GroupKFold(5).split(Xm, ym, gm):
                eigen[te] = maak_model().fit(Xm[tr], ym[tr]).predict_proba(Xm[te])[:, 1]
            rij["eigen"] = _scores(eigen, ym)
            e, a = rij["eigen"], rij["algemeen"]
            # Eigen model wint als het even scherp is (logloss max 1% slechter) én beter gekalibreerd,
            # want voor xG-totalen en goals − xG per speler telt kalibratie het zwaarst.
            if e["logloss"] < a["logloss"] or (e["logloss"] <= a["logloss"] * 1.01 and e["ece"] < a["ece"]):
                rij["keuze"] = "eigen"
                modellen[r] = maak_model().fit(Xm, ym)
                oof_gekozen[m] = eigen
            else:
                rij["keuze"] = "algemeen (eigen niet beter)"
        rapport.append(rij)
    return modellen, oof_gekozen, rapport


def voorspel(pakket: dict, X: np.ndarray, rank) -> np.ndarray:
    """Kans per rij: eigen rank-model als dat er is, anders het algemene."""
    p = pakket["model"].predict_proba(X)[:, 1]
    rank = np.broadcast_to(np.asarray(rank), p.shape)
    for r, mdl in (pakket.get("per_rank") or {}).items():
        sel = rank == int(r)
        if sel.any():
            p[sel] = mdl.predict_proba(X[sel])[:, 1]
    return p


def print_rapport(rapport: list[dict], eenheid: str) -> None:
    print(f"\nPer rank: algemeen model vs eigen model ({eenheid}; eerlijk getest per wedstrijd)")
    for r in rapport:
        a, e = r["algemeen"], r["eigen"]
        tekst = f"  {r['rank']:9s} n={r['n']:6d}  algemeen: logloss {a['logloss']:.4f} auc {a['auc']} fout {100 * a['ece']:.2f}pt verwacht {a['verwacht']:.0f}"
        if e:
            tekst += f"  | eigen: logloss {e['logloss']:.4f} auc {e['auc']} fout {100 * e['ece']:.2f}pt verwacht {e['verwacht']:.0f}"
        print(tekst + f"  | echt {r['echt']}  -> {r['keuze']}")
