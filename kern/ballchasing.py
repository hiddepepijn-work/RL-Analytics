"""Replays per rank-band ophalen van ballchasing.com.

Token: maak er een aan op https://ballchasing.com/upload (inloggen via Steam/Epic),
zet hem in RL-Analytics/.env als  BALLCHASING_TOKEN=...

Voorbeelden:
    uv run python -m kern.ballchasing --playlist ranked-doubles --min-rank champion-1 --max-rank champion-3 --aantal 200
    uv run python -m kern.ballchasing --playlist ranked-standard --min-rank gold-1 --max-rank gold-3 --aantal 100 --seizoen f23

Bestanden: data/replays/<band>/<id>.replay plus data/replays/<band>/lijst.jsonl
(metadata per replay, inclusief rank per speler). Bestaande ids worden overgeslagen.
"""
from __future__ import annotations

import argparse
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

API = "https://ballchasing.com/api"
WORTEL = Path(__file__).resolve().parent.parent
RANKS = (
    ["unranked"]
    + [f"{r}-{n}" for r in ("bronze", "silver", "gold", "platinum", "diamond", "champion", "grand-champion") for n in (1, 2, 3)]
    + ["supersonic-legend"]
)


def token() -> str:
    if os.environ.get("BALLCHASING_TOKEN"):
        return os.environ["BALLCHASING_TOKEN"]
    env = WORTEL / ".env"
    if env.exists():
        for regel in env.read_text(encoding="utf-8").splitlines():
            if regel.startswith("BALLCHASING_TOKEN="):
                return regel.split("=", 1)[1].strip()
    raise SystemExit("Geen BALLCHASING_TOKEN gevonden (zet hem in .env).")


class Client:
    """Kleine client met eigen tempo: ballchasing knijpt af bij te veel verzoeken (HTTP 429)."""

    def __init__(self, tok: str, pauze: float = 1.1):
        self.tok, self.pauze, self.vorige = tok, pauze, 0.0

    def _get(self, url: str) -> bytes:
        for poging in range(6):
            wacht = self.pauze - (time.monotonic() - self.vorige)
            if wacht > 0:
                time.sleep(wacht)
            self.vorige = time.monotonic()
            req = urllib.request.Request(url, headers={"Authorization": self.tok})
            try:
                with urllib.request.urlopen(req, timeout=60) as r:
                    return r.read()
            except urllib.error.HTTPError as e:
                if e.code == 429:
                    time.sleep(5 * (poging + 1))
                    continue
                raise
        raise RuntimeError(f"Blijft 429 geven: {url}")

    def lijst(self, **filters):
        """Itereert over replays die aan de filters voldoen (volgt de 'next'-links)."""
        url = f"{API}/replays?" + urllib.parse.urlencode({k.replace("_", "-"): v for k, v in filters.items() if v})
        while url:
            data = json.loads(self._get(url))
            yield from data.get("list", [])
            url = data.get("next")

    def download(self, replay_id: str) -> bytes:
        return self._get(f"{API}/replays/{replay_id}/file")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--playlist", default="ranked-doubles",
                    help="ranked-duels | ranked-doubles | ranked-standard | ranked-hoops | ...")
    ap.add_argument("--min-rank", choices=RANKS, required=True)
    ap.add_argument("--max-rank", choices=RANKS, required=True)
    ap.add_argument("--aantal", type=int, default=100)
    ap.add_argument("--seizoen", help="bv. f23 (free-to-play seizoen 23)")
    ap.add_argument("--na", help="alleen replays na datum (RFC3339, bv. 2026-09-01T00:00:00Z)")
    a = ap.parse_args()

    band = f"{a.playlist}_{a.min_rank}_{a.max_rank}"
    map_ = WORTEL / "data" / "replays" / band
    map_.mkdir(parents=True, exist_ok=True)
    meta_pad = map_ / "lijst.jsonl"
    al = {p.stem for p in map_.glob("*.replay")}

    c = Client(token())
    binnen = 0
    with meta_pad.open("a", encoding="utf-8") as meta:
        for r in c.lijst(playlist=a.playlist, min_rank=a.min_rank, max_rank=a.max_rank,
                         season=a.seizoen, replay_date_after=a.na, count=200,
                         sort_by="replay-date", sort_dir="desc"):
            if binnen >= a.aantal:
                break
            if r["id"] in al:
                continue
            # ballchasing filtert niet streng: zelf controleren dat de héle lobby binnen de band valt
            lo, hi = RANKS.index(a.min_rank), RANKS.index(a.max_rank)
            ids = [(r.get(k) or {}).get("id") for k in ("min_rank", "max_rank")]
            if not all(i in RANKS and lo <= RANKS.index(i) <= hi for i in ids):
                continue
            try:
                # eerst naar .part, dan hernoemen: verwerking ziet nooit een half geschreven replay
                tmp = map_ / f"{r['id']}.replay.part"
                tmp.write_bytes(c.download(r["id"]))
                tmp.replace(map_ / f"{r['id']}.replay")
            except urllib.error.HTTPError as e:
                print(f"  overslaan {r['id']}: HTTP {e.code}")
                continue
            meta.write(json.dumps(r, ensure_ascii=False) + "\n")
            binnen += 1
            print(f"[{binnen}/{a.aantal}] {r['id']}  {r.get('min_rank', {}).get('name', '?')} – {r.get('max_rank', {}).get('name', '?')}")
    print(f"Klaar: {binnen} nieuw in {map_}")


if __name__ == "__main__":
    main()
