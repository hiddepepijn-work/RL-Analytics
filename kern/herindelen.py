"""Replays opnieuw indelen naar de ECHTE rank van de lobby (ballchasing filtert niet streng).

Per band-map: lobby's die niet volledig binnen de band vallen gaan naar
  - de map van hun eigen band (alle spelers in dezelfde rankgroep), of
  - ranked-doubles_gemengd (lobby met spelers uit verschillende rankgroepen).
Cache-features van verplaatste replays worden gewist, zodat ze met de juiste band opnieuw worden verwerkt.

Gebruik:
    uv run python -m kern.herindelen          # alleen tonen
    uv run python -m kern.herindelen --doen   # echt verplaatsen
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

from kern.ballchasing import RANKS

WORTEL = Path(__file__).resolve().parent.parent
REPLAYS = WORTEL / "data" / "replays"
CACHE = WORTEL / "data" / "features" / "cache"


def groep(rank_id: str) -> str:
    if rank_id in ("grand-champion-1", "grand-champion-2", "grand-champion-3", "supersonic-legend"):
        return "gc+"
    return rank_id.rsplit("-", 1)[0]


def doelmap(playlist: str, ids: list[str]) -> str:
    g = {groep(i) for i in ids}
    if len(g) != 1:
        return f"{playlist}_gemengd"
    g = g.pop()
    return f"{playlist}_grand-champion-1_supersonic-legend" if g == "gc+" else f"{playlist}_{g}-1_{g}-3"


def main(doen: bool) -> None:
    index_pad = CACHE / "match_ids.json"
    index = json.loads(index_pad.read_text(encoding="utf-8")) if index_pad.exists() else {}
    totaal = Counter()
    for map_ in sorted(p for p in REPLAYS.iterdir() if p.is_dir() and (p / "lijst.jsonl").exists()):
        playlist = map_.name.split("_")[0]
        blijf, weg = [], []
        for regel in (map_ / "lijst.jsonl").read_text(encoding="utf-8").splitlines():
            r = json.loads(regel)
            ids = [(r.get(k) or {}).get("id") for k in ("min_rank", "max_rank")]
            doel = doelmap(playlist, ids) if all(i in RANKS for i in ids) else f"{playlist}_gemengd"
            (blijf if doel == map_.name else weg).append((doel, r, regel))
        for doel, r, regel in weg:
            totaal[(map_.name, doel)] += 1
            if not doen:
                continue
            bron = map_ / f"{r['id']}.replay"
            (REPLAYS / doel).mkdir(exist_ok=True)
            if bron.exists():
                bron.replace(REPLAYS / doel / bron.name)
            with (REPLAYS / doel / "lijst.jsonl").open("a", encoding="utf-8") as f:
                f.write(regel + "\n")
            for soort in ("schoten", "passen"):
                (CACHE / soort / f"{r['id']}.csv").unlink(missing_ok=True)
            index.pop(r["id"], None)
        if doen and weg:
            (map_ / "lijst.jsonl").write_text("".join(regel + "\n" for _, _, regel in blijf), encoding="utf-8")
    for (van, naar), n in sorted(totaal.items()):
        print(f"{n:4d}  {van}  ->  {naar}")
    if doen:
        index_pad.write_text(json.dumps(index), encoding="utf-8")
        print("Verplaatst; cache van deze replays gewist.")
    else:
        print("Alleen getoond. Draai met --doen om te verplaatsen.")


if __name__ == "__main__":
    main("--doen" in sys.argv)
