"""Zonewaarde (eenvoudige xT): kans dat een team binnen 10 s scoort, gegeven waar de bal is.

Altijd vanuit het aanvallende team bekeken (y > 0 = richting vijandelijk doel). Raster 8 (breedte) × 10 (lengte),
licht gladgestreken en naar het gemiddelde getrokken bij weinig data (shrinkage).

Gebruik:
    uv run python -m kern.zonewaarde
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import subtr_actor as sa

from kern import events

WORTEL = Path(__file__).resolve().parent.parent
NX, NY = 8, 10
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


def main() -> None:
    goals_n = np.zeros((NX, NY)); totaal = np.zeros((NX, NY))
    replays = sorted((WORTEL / "data" / "replays").glob("*/*.replay"))
    for k, p in enumerate(replays):
        try:
            meta, arr = sa.get_ndarray_with_info_from_replay_filepath(str(p), ["BallRigidBody", "CurrentTime"], [], fps=STAP_FPS)
        except Exception:
            continue
        gh = meta["column_headers"]["global_headers"]
        t = arr[:, gh.index("current time")]
        bx, by, bz = (arr[:, gh.index(f"Ball - position {a}")] for a in "xyz")
        ok = ~((bx == 0) & (by == 0) & (bz == 0))
        goals = [(e["meta"]["timing"]["time"], 0 if e["meta"].get("team_is_team_0") else 1)
                 for e in events.lijst(p) if e["meta"]["stream"] == "goal_context"]
        for team, teken in ((0, 1), (1, -1)):
            scoort = np.array([any(gt == team and ti < g <= ti + VENSTER for g, gt in goals) for ti in t])
            i, j = bin_index(bx[ok] * teken, by[ok] * teken)
            np.add.at(totaal, (i, j), 1)
            np.add.at(goals_n, (i, j), scoort[ok])
        if (k + 1) % 50 == 0:
            print(f"{k + 1}/{len(replays)}")
    gem = goals_n.sum() / max(totaal.sum(), 1)
    # Shrinkage: elke cel krijgt 50 'neppe' metingen met de gemiddelde waarde erbij
    grid = (goals_n + 50 * gem) / (totaal + 50)
    # Licht gladstrijken over buren
    pad = np.pad(grid, 1, mode="edge")
    glad = sum(pad[1 + di:1 + di + NX, 1 + dj:1 + dj + NY] * w for di, dj, w in
               [(0, 0, .4), (1, 0, .15), (-1, 0, .15), (0, 1, .15), (0, -1, .15)])
    uit = WORTEL / "data" / "modellen" / "zonewaarde.json"
    uit.parent.mkdir(parents=True, exist_ok=True)
    uit.write_text(json.dumps({"nx": NX, "ny": NY, "venster_s": VENSTER, "gemiddelde": gem,
                               "grid": np.round(glad, 4).tolist(), "metingen": int(totaal.sum())}), encoding="utf-8")
    print(f"Klaar: {int(totaal.sum())} metingen, gemiddeld {gem:.3f}")
    print("Waarde per lengte-vak (eigen doel → vijandelijk doel), midden van het veld:")
    print("  " + "  ".join(f"{v:.3f}" for v in glad[NX // 2]))


if __name__ == "__main__":
    main()
