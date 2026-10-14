"""Eigen replays gecontroleerd importeren. Zonder --akkoord wordt NIETS gekopieerd: je krijgt alleen het voorstel.

Controles per replay:
  - leesbaar door de parser
  - speler zit in de wedstrijd (op naam)
  - Ranked Doubles (andere modi apart, niet voor benchmarks)
  - volledige wedstrijd (≥ 290 s gespeeld, anders 'opgegeven' → alleen eigen overzicht)
  - geen dubbele wedstrijd

Gebruik:
    uv run python -m kern.eigen_import --naam "Sand ツ"              # voorstel tonen
    uv run python -m kern.eigen_import --naam "Sand ツ" --akkoord    # goedgekeurde kopiëren naar data/eigen/
"""
from __future__ import annotations

import argparse
from datetime import datetime
import json
import shutil
from pathlib import Path

import subtr_actor as sa

from kern import accounts

WORTEL = Path(__file__).resolve().parent.parent
BRONNEN = [Path.home() / "Documents/My Games/Rocket League/TAGame/DemosEpic",
           Path.home() / "Documents/My Games/Rocket League/TAGame/Demos"]
PLAYLIST = {10: "Ranked Duel", 11: "Ranked Doubles", 13: "Ranked Standard", 6: "Privé", 1: "Casual Duel", 2: "Casual Doubles", 3: "Casual Standard"}


def beoordeel(p: Path, naam: str, gezien: set) -> dict:
    r = {"bestand": p.name, "pad": str(p)}
    try:
        m = sa.get_replay_meta(str(p))["replay_meta"]
    except Exception as e:
        return r | {"oordeel": "weg", "reden": f"onleesbaar ({type(e).__name__})"}
    k = dict(m["all_headers"])
    spelers = [s["name"] for s in m["team_zero"] + m["team_one"]]
    pl = m.get("game_type", {}).get("playlist_id")
    duur = float(k.get("TotalSecondsPlayed", 0))
    schatting = False
    if not duur and k.get("NumFrames") and k.get("RecordFPS"):
        # Oude replays (< ~2024) missen TotalSecondsPlayed: schatten uit frames. Dit telt ook aftellen en
        # goal-herhalingen mee, dus de grens voor 'volledig' ligt dan hoger (zie onder).
        duur, schatting = float(k["NumFrames"]) / float(k["RecordFPS"]), True
    ts = k.get("TeamSize")
    mid = k.get("MatchGuid") or k.get("Id") or p.stem
    r |= {"datum": str(k.get("Date", ""))[:10], "modus": PLAYLIST.get(pl, f"playlist {pl}"), "teamgrootte": ts,
          "score": f"{k.get('Team0Score', 0)}-{k.get('Team1Score', 0)}", "duur": round(duur), "spelers": spelers}
    if mid in gezien:
        return r | {"oordeel": "weg", "reden": "dubbel"}
    gezien.add(mid)
    # Herkennen op platform-ID (account), met de naam alleen als terugval voor onbekende accounts
    account = accounts.vind(naam)
    if account:
        ik = next((s for s in m["team_zero"] + m["team_one"] if accounts.is_ik(account, s)), None)
        if not ik:
            return r | {"oordeel": "weg", "reden": f"account '{account['naam']}' speelt niet mee"}
        r["ik_naam"] = ik["name"]
    elif naam not in spelers:
        return r | {"oordeel": "weg", "reden": f"'{naam}' speelt niet mee"}
    if ts != 2:
        return r | {"oordeel": "apart", "reden": f"{ts}v{ts}, niet voor 2v2-benchmarks"}
    if pl not in (11, None):
        return r | {"oordeel": "apart", "reden": f"modus onduidelijk ({r['modus']})"}
    try:
        leeftijd = (datetime.now() - datetime.strptime(str(k.get("Date", ""))[:10], "%Y-%m-%d")).days
    except ValueError:
        leeftijd = 0
    if leeftijd > 365:
        return r | {"oordeel": "apart", "reden": f"ouder dan een jaar ({r['datum']}): ander niveau/spelversie, niet in huidig profiel"}
    if duur < (330 if schatting else 290):
        return r | {"oordeel": "apart", "reden": f"kort ({'±' if schatting else ''}{round(duur)} s): opgegeven of half opgeslagen"}
    return r | {"oordeel": "mee", "reden": "volledige Ranked Doubles"}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--naam", required=True)
    ap.add_argument("--akkoord", action="store_true")
    a = ap.parse_args()
    gezien, lijst = set(), []
    for bron in BRONNEN:
        for p in sorted(bron.glob("*.replay")):
            lijst.append(beoordeel(p, a.naam, gezien))
    for o in ("mee", "apart", "weg"):
        groep = [r for r in lijst if r["oordeel"] == o]
        print(f"\n== {o.upper()} ({len(groep)})")
        for r in groep:
            print(f"  {r.get('datum', '?'):10s} {r.get('modus', '?'):16s} {r.get('score', ''):5s} {r.get('duur', '')!s:>4s}s  {r['reden']}")
    uit = WORTEL / "data" / "eigen"
    (WORTEL / "data").mkdir(exist_ok=True)
    (WORTEL / "data" / "eigen_voorstel.json").write_text(json.dumps(lijst, ensure_ascii=False, indent=1), encoding="utf-8")
    if a.akkoord:
        for o in ("mee", "apart"):
            (uit / o).mkdir(parents=True, exist_ok=True)
            for r in lijst:
                if r["oordeel"] == o:
                    shutil.copy2(r["pad"], uit / o / r["bestand"])
        print(f"\nGekopieerd naar {uit} (origineel blijft staan).")
    else:
        print("\nNiets gekopieerd. Draai opnieuw met --akkoord als het voorstel klopt.")


if __name__ == "__main__":
    main()
