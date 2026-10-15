"""Teamspel: double commits (beide teamgenoten op dezelfde bal af) en de bal afpakken van je teammate.

Per touch van speler X kijken we 0,4 s eerder (het beslismoment): gingen X én teamgenoot Y allebei op de bal af
(snelheid richting het raakpunt > 700 uu/s, binnen 25 m)? Dan:
  - afgepakt: Y kon er minstens zo snel zijn en kwam met een duidelijk betere hoek richting het vijandelijk doel aan.
  - niemand achter: beide spelers stonden verder van het eigen doel dan de bal.

Onderzoek op 77 Champion-wedstrijden (15 okt): ~19 double commits per wedstrijd. Met iemand achter de bal valt er in
4,1% binnen 6 s een tegengoal (normaal 4,6%); met NIEMAND achter de bal in 12,4% (3×) en zelf scoor je dan bijna nooit.
Afpakken van een beter staande teammate pakte gemiddeld níet slechter uit; dat blijft informatief.
"""
from __future__ import annotations

import numpy as np

from kern.fysica import aankomst_richting
from kern.kansen import _stand, _tijd, sleutel

BESLIS = 0.4
MIN_V = 700
MAX_AFSTAND = 2500


def analyse(data: dict, events: list[dict]) -> list[dict]:
    """→ [{tijd, speler (raakte de bal), maat, afgepakt, niemand_achter}] per double commit."""
    team = {s["id"]: s["team"] for s in data["spelers"]}
    idx = {s["id"]: i for i, s in enumerate(data["spelers"])}
    touches = sorted((_tijd(e), sleutel(e["meta"].get("primary_player"))) for e in events if e["meta"]["stream"] == "touch")
    uit = []
    for k, (t, x) in enumerate(touches):
        if x not in team:
            continue
        if any(s == x and t - 1.0 < tt < t for tt, s in touches[max(0, k - 5):k]):
            continue  # eigen touch kort ervoor = dribbel, geen nieuwe actie
        maats = [s for s in team if team[s] == team[x] and s != x]
        if len(maats) != 1:
            continue  # alleen 2v2 (bij 3v3 is 'de' teamgenoot niet eenduidig)
        y = maats[0]
        bp, _ = _stand(data, t)
        _, autos = _stand(data, t - BESLIS)
        if not np.any(bp) or not np.any(autos[idx[x], :3]) or not np.any(autos[idx[y], :3]):
            continue
        r = 1 if team[x] == 0 else -1
        doel = np.array([0.0, r * 5120.0])
        punt = np.array([[BESLIS, *bp]])

        def info(i):
            pos, vel = autos[i, :3], autos[i, 3:6]
            naar = bp - pos; afst = float(np.linalg.norm(naar)) or 1
            richting = doel - pos[:2]; richting /= (np.linalg.norm(richting) or 1)
            snel = float(np.linalg.norm(vel[:2])) or 1
            return (float(aankomst_richting(pos, vel, autos[i, 6] / 2.55, punt)[0]), float(vel @ naar / afst),
                    float(vel[:2] @ richting / snel), afst)
        ax, vx, hx, dx = info(idx[x]); ay, vy, hy, dy = info(idx[y])
        if not (vx > MIN_V and vy > MIN_V and dx < MAX_AFSTAND and dy < MAX_AFSTAND):
            continue
        eigen_doel_y = -r * 5120.0
        achter = lambda i: abs(autos[i, 1] - eigen_doel_y) < abs(bp[1] - eigen_doel_y) - 300
        uit.append({"tijd": round(t, 2), "speler": x, "maat": y,
                    "afgepakt": bool(ay <= ax + 0.05 and hy > hx + 0.4),
                    "niemand_achter": bool(not achter(idx[x]) and not achter(idx[y]))})
    return uit
