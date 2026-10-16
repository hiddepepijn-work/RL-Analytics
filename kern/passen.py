"""Pass-model: beoordeelt de pass los van wat de ontvanger ermee doet.

Stap 1 (kandidaten): per touch de balbaan (3 s) doorrekenen en per speler de aankomsttijd op elk baanpunt
schatten (baan 5,5 s, met stuiters op muren en plafond). Daaruit features: hoeveel eerder kan een teamgenoot erbij
zijn dan de tegenstander, hoe hoog, hoe ver, hoe gevaarlijk is de plek. Label = raakt een teamgenoot de bal als
volgende (binnen 6 s, zodat lange muur- en plafondpasses meetellen)?
Stap 2 (kern/xpass_model.py): model leert uit die labels een eerlijke kans (xPass), zoals xG.
Stap 3 (hier, met model): credits verdelen.
  passer    : xPass, pass-waarde (xPass × zonewaarde), passes boven verwachting, ballen naar niemand
  ontvanger : verwacht ontvangen, gemiste ontvangsten (xPass ≥ 0,6 maar niet geraakt),
              aanspeelbaar % (stond hij op een plek waar hij een pass kon krijgen terwijl een teamgenoot de bal had)

Gebruik:
    uv run python -m kern.passen            # kandidaten uit alle data/replays/<band>/ → data/features/passen.csv
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import numpy as np
import subtr_actor as sa

from kern import events
from kern.fysica import aankomst, baan
from kern.events import replay_fout

WORTEL = Path(__file__).resolve().parent.parent
FPS = 30
MIN_SNELHEID = 500
# Lange passes via muur of plafond zijn 4–5,5 s onderweg: baan en 'aangekomen'-venster daarop afgestemd (was 3 / 3,5 s)
BAAN_S = 5.5
PASS_VENSTER = 6.0
NIEUWSTE_KOLOM = "venster6"  # cache zonder deze kolom is van een oudere versie (kern/bijwerken.py)
ZONE_PAD = WORTEL / "data" / "modellen" / "zonewaarde.json"
MODEL_PAD = WORTEL / "data" / "modellen" / "xpass.joblib"
FEATURES = ["marge", "marge_vroeg", "maat_tijd", "tegen_tijd", "t_punt", "z_punt", "afstand_punt",
            "bal_snelheid", "vooruit", "zone_punt", "zone_nu", "n_maten_haalbaar", "bewust", "maat_afstand_bal", "tegen_afstand_bal"]


def sleutel(pid):
    if not pid:
        return None
    (k, v), = pid.items()
    return f"{k}:{v}"


def _zone():
    if ZONE_PAD.exists():
        z = json.loads(ZONE_PAD.read_text(encoding="utf-8"))
        return np.array(z["grid"]), z["nx"], z["ny"]
    return np.full((8, 10), 0.05), 8, 10


def _zw(grid, nx, ny, x, y_aanval):
    i = int(np.clip((x + 4096) / 8192 * nx, 0, nx - 1))
    j = int(np.clip((y_aanval + 5120) / 10240 * ny, 0, ny - 1))
    return float(grid[i, j])


def _laad(pad: Path):
    meta, arr = sa.get_ndarray_with_info_from_replay_filepath(
        str(pad), ["BallRigidBody", "CurrentTime"], ["PlayerRigidBody", "PlayerBoost"], fps=FPS)
    gh, ph = meta["column_headers"]["global_headers"], meta["column_headers"]["player_headers"]
    rm = meta["replay_meta"]
    spelers = rm["team_zero"] + rm["team_one"]
    ids = [sleutel(s.get("remote_id")) for s in spelers]
    team = {i: (0 if k < len(rm["team_zero"]) else 1) for k, i in enumerate(ids)}
    ng, npk = len(gh), len(ph)
    t = arr[:, gh.index("current time")]
    bal = arr[:, [gh.index(f"Ball - position {a}") for a in "xyz"] + [gh.index(f"Ball - linear velocity {a}") for a in "xyz"]]
    pk = [ph.index(f"position {a}") for a in "xyz"] + [ph.index(f"linear velocity {a}") for a in "xyz"] + [ph.index("boost level (raw replay units)")]
    auto = np.stack([arr[:, [ng + k * npk + c for c in pk]] for k in range(len(ids))], axis=1)
    touches = sorted(((e["meta"]["timing"].get("start_time", e["meta"]["timing"].get("time")), sleutel(e["meta"].get("primary_player")))
                      for e in events.lijst(pad) if e["meta"]["stream"] == "touch"), key=lambda x: x[0])
    return ids, team, t, bal, auto, touches


def kandidaten_uit_replay(pad: Path, band: str = "") -> list[dict]:
    ids, team, t, bal, auto, touches = _laad(pad)
    grid, nx, ny = _zone()
    frame = lambda tt: int(min(len(t) - 1, max(0, np.searchsorted(t, tt))))
    rijen = []
    for n, (tt, passer) in enumerate(touches):
        if passer not in team:
            continue
        f = frame(tt + 0.1)
        bp, bv = bal[f, :3], bal[f, 3:]
        if not np.any(bp) or np.linalg.norm(bv) < MIN_SNELHEID:
            continue
        T, teken = team[passer], (1 if team[passer] == 0 else -1)
        punten = baan(bp, bv, duur=BAAN_S)
        tijden = {i: aankomst(auto[f, k, :3], auto[f, k, 3:6], auto[f, k, 6] / 2.55, punten)
                  for k, i in enumerate(ids) if i != passer and np.any(auto[f, k, :3])}
        maten = [i for i in tijden if team[i] == T]
        tegen = [i for i in tijden if team[i] != T]
        if not maten or not tegen:
            continue
        maat_tijd = np.min([tijden[i] for i in maten], axis=0)
        tegen_tijd = np.min([tijden[i] for i in tegen], axis=0)
        haalbaar = maat_tijd <= punten[:, 0] + 0.15
        marge = np.where(haalbaar, tegen_tijd - maat_tijd, -9)
        zones = np.array([_zw(grid, nx, ny, x * teken, y * teken) for _, x, y, _ in punten])
        k = int(np.argmax(np.minimum(marge, 1.0) + 2 * zones * (marge > 0)))
        ontvanger = min(maten, key=lambda i: tijden[i][k])
        vorige = touches[n - 1] if n else (None, None)
        volgende = touches[n + 1] if n + 1 < len(touches) else (np.inf, None)
        kk = {i: c for c, i in enumerate(ids)}
        rijen.append({
            "replay": pad.stem, "band": band, "tijd": round(tt, 2), "passer": passer, "ontvanger": ontvanger, "team": T,
            "marge": round(float(marge[k]), 3), "marge_vroeg": round(float(np.max(marge[:30])), 3),
            "maat_tijd": round(float(maat_tijd[k]), 3), "tegen_tijd": round(float(tegen_tijd[k]), 3),
            "t_punt": round(float(punten[k, 0]), 2), "z_punt": round(float(punten[k, 3])),
            "afstand_punt": round(float(np.linalg.norm(punten[k, 1:3] - bp[:2]))),
            "bal_snelheid": round(float(np.linalg.norm(bv))), "vooruit": round(float(bv[1] * teken)),
            "zone_punt": round(float(zones[k]), 4), "zone_nu": round(_zw(grid, nx, ny, bp[0] * teken, bp[1] * teken), 4),
            "n_maten_haalbaar": int(sum(np.any((tijden[i] <= punten[:, 0] + 0.15) & (tijden[i] < tegen_tijd)) for i in maten)),
            "bewust": int(vorige[1] == passer and tt - vorige[0] < 1.5),
            "maat_afstand_bal": round(float(min(np.linalg.norm(auto[f, kk[i], :2] - bp[:2]) for i in maten))),
            "tegen_afstand_bal": round(float(min(np.linalg.norm(auto[f, kk[i], :2] - bp[:2]) for i in tegen))),
            "doel_x": round(float(punten[k, 1])), "doel_y": round(float(punten[k, 2])),
            "van_x": round(float(bp[0])), "van_y": round(float(bp[1])),
            "compleet": int(volgende[1] in maten and volgende[0] - tt < PASS_VENSTER),
            "door_ontvanger": int(volgende[1] == ontvanger and volgende[0] - tt < PASS_VENSTER),
            "venster6": 1,
        })
    return rijen


def aanspeelbaar(pad: Path) -> dict[str, float | None]:
    """% van de touches van een teamgenoot waarbij deze speler binnen 2 s op een steunplek kon zijn.
    Steunplekken = waaier van 9 punten op 1000/1800/2600 uu van de bal, recht vooruit en 45° links/rechts."""
    ids, team, t, bal, auto, touches = _laad(pad)
    frame = lambda tt: int(min(len(t) - 1, max(0, np.searchsorted(t, tt))))
    kans = {i: [0, 0] for i in ids}
    for n in range(1, len(touches)):
        tt, s = touches[n]
        if s not in team:
            continue
        f = frame(tt)
        bp = bal[f, :3]
        if not np.any(bp):
            continue
        teken = 1 if team[s] == 0 else -1
        steun = np.array([[0, bp[0] + r * np.sin(a), bp[1] + r * np.cos(a) * teken, 100]
                          for r in (1000, 1800, 2600) for a in (-np.pi / 4, 0, np.pi / 4)], float)
        steun[:, 1] = np.clip(steun[:, 1], -3900, 3900); steun[:, 2] = np.clip(steun[:, 2], -5000, 5000)
        for k, i in enumerate(ids):
            if i == s or team[i] != team[s] or not np.any(auto[f, k, :3]):
                continue
            tijd = aankomst(auto[f, k, :3], auto[f, k, 3:6], auto[f, k, 6] / 2.55, steun)
            kans[i][1] += 1
            kans[i][0] += int(np.min(tijd) <= 2.0)
    return {i: (round(100 * a / b, 1) if b >= 5 else None) for i, (a, b) in kans.items()}


def passen_met_model(pad: Path, rank: int | None = None) -> tuple[list[dict], dict]:
    """Pass-acties + credits per speler (vereist getraind xPass-model)."""
    import joblib
    pakket = joblib.load(MODEL_PAD)
    rijen = kandidaten_uit_replay(pad)
    ids = _laad(pad)[0]
    stats = {i: {"pass_pogingen": 0, "xpass": 0.0, "passes_compleet": 0, "pass_waarde": 0.0, "naar_niemand": 0,
                 "verwacht_ontvangen": 0.0, "ontvangen": 0, "gemiste_ontvangsten": 0} for i in ids}
    passes = []
    if rijen:
        from kern.per_rank import voorspel
        X = np.array([[r[f] for f in pakket["features"]] for r in rijen], float)
        p = voorspel(pakket, X, rank) if rank is not None else pakket["model"].predict_proba(X)[:, 1]
        for r, pi in zip(rijen, p):
            s, o = stats[r["passer"]], stats[r["ontvanger"]]
            if pi >= 0.25:
                s["pass_pogingen"] += 1; s["xpass"] += pi; s["passes_compleet"] += r["compleet"]; s["pass_waarde"] += pi * r["zone_punt"]
                o["verwacht_ontvangen"] += pi; o["ontvangen"] += r["door_ontvanger"]
                o["gemiste_ontvangsten"] += int(pi >= 0.5 and not r["door_ontvanger"])
                passes.append({"tijd": r["tijd"], "passer": r["passer"], "ontvanger": r["ontvanger"], "team": r["team"], "p": round(float(pi), 3),
                               "van": [r["van_x"], r["van_y"]], "doel": [r["doel_x"], r["doel_y"]], "compleet": r["compleet"]})
            elif r["bewust"] and pi < 0.1 and r["vooruit"] > 0:
                s["naar_niemand"] += 1
    asp = aanspeelbaar(pad)
    for i, s in stats.items():
        s["xpass"] = round(s["xpass"], 2); s["pass_waarde"] = round(s["pass_waarde"], 3)
        s["verwacht_ontvangen"] = round(s["verwacht_ontvangen"], 2)
        s["pass_boven_verwachting"] = round(s["passes_compleet"] - s["xpass"], 2)
        s["ontvangst_boven_verwachting"] = round(s["ontvangen"] - s["verwacht_ontvangen"], 2)
        s["aanspeelbaar_pct"] = asp.get(i)
    return passes, stats


def main() -> None:
    uit = WORTEL / "data" / "features" / "passen.csv"
    uit.parent.mkdir(parents=True, exist_ok=True)
    alle, gezien = [], set()
    replays = sorted((WORTEL / "data" / "replays").glob("*/*.replay"))
    for k, p in enumerate(replays):
        try:
            kop = dict(sa.get_replay_meta(str(p))["replay_meta"]["all_headers"])
            mid = kop.get("MatchGuid") or kop.get("Id") or p.stem
            if mid in gezien:
                continue
            gezien.add(mid)
            alle += kandidaten_uit_replay(p, p.parent.name)
        except BaseException as e:
            if not replay_fout(e):  # Ctrl+C / afsluiten: doorlaten; Rust-panic: als fout behandelen
                raise
            print(f"  overslaan {p.name}: {type(e).__name__}: {str(e)[:80]}")
        if (k + 1) % 50 == 0:
            print(f"{k + 1}/{len(replays)} replays, {len(alle)} kandidaten")
    with uit.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(alle[0].keys())); w.writeheader(); w.writerows(alle)
    c = sum(r["compleet"] for r in alle)
    print(f"Klaar: {len(alle)} kandidaten, {c} keer raakte een teamgenoot als volgende ({100 * c / len(alle):.1f}%) -> {uit}")


if __name__ == "__main__":
    main()
