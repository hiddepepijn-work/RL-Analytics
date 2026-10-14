"""Zonewaarde (eenvoudige xT): kans dat een team binnen 10 s scoort, gegeven waar de bal is.

Altijd vanuit het aanvallende team bekeken (y > 0 = richting vijandelijk doel). Raster 8 (breedte) × 10 (lengte),
licht gladgestreken en naar het gemiddelde getrokken bij weinig data (shrinkage).

Daarnaast een 3D-raster met de hoogte van de bal (grond / laag in de lucht / hoog, grenzen HOOGTE): een hoge bal
voor het doel (air dribble, backboard) is gevaarlijker dan een rollende bal op dezelfde plek. Bij weinig metingen
trekt een 3D-vak naar de 2D-waarde van zijn plek. xPass gebruikt het 2D-raster (feature), de rating het 3D-raster.

Gebruik:
    uv run python -m kern.zonewaarde
"""
from __future__ import annotations

import json
from multiprocessing import Pool
from pathlib import Path

import numpy as np
import subtr_actor as sa

from kern import events

WORTEL = Path(__file__).resolve().parent.parent
NX, NY = 8, 10
HOOGTE = [300.0, 900.0]  # uu: grond < 300 ≤ laag < 900 ≤ hoog
NZ = len(HOOGTE) + 1
VENSTER = 10.0
STAP_FPS = 2


def bin_index(x, y):
    i = np.clip(((np.asarray(x) + 4096) / 8192 * NX).astype(int), 0, NX - 1)
    j = np.clip(((np.asarray(y) + 5120) / 10240 * NY).astype(int), 0, NY - 1)
    return i, j


def waarde(grid, x, y_aanval):
    """Zonewaarde voor een bal op (x, y) vanuit aanvallend perspectief."""
    i, j = bin_index(x, y_aanval)
    return np.asarray(grid)[i, j]


def waarde3(zone: dict, x, y_aanval, z):
    """Zonewaarde met balhoogte (3D-raster); valt terug op 2D als er (nog) geen 3D-raster is."""
    if "grid3" not in zone:
        return waarde(zone["grid"], x, y_aanval)
    i, j = bin_index(x, y_aanval)
    return np.asarray(zone["grid3"])[i, j, np.searchsorted(HOOGTE, z, side="right")]


def _tel(p: Path):
    try:
        meta, arr = sa.get_ndarray_with_info_from_replay_filepath(str(p), ["BallRigidBody", "CurrentTime"], [], fps=STAP_FPS)
    except Exception:
        return None
    gh = meta["column_headers"]["global_headers"]
    t = arr[:, gh.index("current time")]
    bx, by, bz = (arr[:, gh.index(f"Ball - position {a}")] for a in "xyz")
    ok = ~((bx == 0) & (by == 0) & (bz == 0))
    goals = [(e["meta"]["timing"]["time"], 0 if e["meta"].get("team_is_team_0") else 1)
             for e in events.lijst(p) if e["meta"]["stream"] == "goal_context"]
    goals_n, totaal = np.zeros((NX, NY, NZ)), np.zeros((NX, NY, NZ))
    k = np.searchsorted(HOOGTE, bz[ok], side="right")
    for team, teken in ((0, 1), (1, -1)):
        scoort = np.array([any(gt == team and ti < g <= ti + VENSTER for g, gt in goals) for ti in t])
        i, j = bin_index(bx[ok] * teken, by[ok] * teken)
        np.add.at(totaal, (i, j, k), 1)
        np.add.at(goals_n, (i, j, k), scoort[ok])
    return goals_n, totaal


def main() -> None:
    goals_n, totaal = np.zeros((NX, NY, NZ)), np.zeros((NX, NY, NZ))
    replays = sorted((WORTEL / "data" / "replays").glob("*/*.replay"))
    with Pool(8) as pool:
        for k, r in enumerate(pool.imap_unordered(_tel, replays, chunksize=4), 1):
            if r is not None:
                goals_n += r[0]; totaal += r[1]
            if k % 200 == 0:
                print(f"{k}/{len(replays)}", flush=True)
    g2, t2 = goals_n.sum(axis=2), totaal.sum(axis=2)
    gem = g2.sum() / max(t2.sum(), 1)
    # Shrinkage: elke cel krijgt 50 'neppe' metingen met de gemiddelde waarde erbij
    grid = (g2 + 50 * gem) / (t2 + 50)
    # Licht gladstrijken over buren
    pad = np.pad(grid, 1, mode="edge")
    glad = sum(pad[1 + di:1 + di + NX, 1 + dj:1 + dj + NY] * w for di, dj, w in
               [(0, 0, .4), (1, 0, .15), (-1, 0, .15), (0, 1, .15), (0, -1, .15)])
    # 3D: shrinkage naar de 2D-waarde van dezelfde plek
    grid3 = (goals_n + 50 * glad[:, :, None]) / (totaal + 50)
    uit = WORTEL / "data" / "modellen" / "zonewaarde.json"
    uit.parent.mkdir(parents=True, exist_ok=True)
    uit.write_text(json.dumps({"nx": NX, "ny": NY, "venster_s": VENSTER, "gemiddelde": gem,
                               "grid": np.round(glad, 4).tolist(), "metingen": int(totaal.sum()),
                               "hoogte": HOOGTE, "grid3": np.round(grid3, 4).tolist(),
                               "metingen3": totaal.astype(int).tolist()}), encoding="utf-8")
    print(f"Klaar: {int(totaal.sum())} metingen, gemiddeld {gem:.3f}")
    print("Waarde per lengte-vak (eigen doel → vijandelijk doel), midden van het veld, per hoogte:")
    for k, naam in enumerate(["grond", "laag ", "hoog "]):
        print(f"  {naam} " + "  ".join(f"{v:.3f}" for v in grid3[NX // 2, :, k]))


if __name__ == "__main__":
    main()
