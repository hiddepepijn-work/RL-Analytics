"""Eigen wedstrijdgeschiedenis ophalen van ballchasing via platform-ID(s) van een account.

Ballchasing heeft replays waarin jij meespeelt, geüpload door jou óf door je tegenstanders/teamgenoten.
Ze worden gedownload naar data/eigen/opgehaald/ en doorgestuurd naar de server-inbox, die dezelfde
controles doet als bij nieuwe wedstrijden (account speelt mee, Ranked Doubles, volledig, geen dubbel).

Gebruik:
    uv run python -m kern.geschiedenis --account Sand --upload ubuntu@51.75.74.94:/var/lib/rl-analytics-inbox
"""
from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

from kern import accounts
from kern.ballchasing import Client, token

WORTEL = Path(__file__).resolve().parent.parent
MAP = WORTEL / "data" / "eigen" / "opgehaald"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--account", required=True)
    ap.add_argument("--upload", help="host:map van de server-inbox")
    a = ap.parse_args()
    account = accounts.vind(a.account)
    if not account:
        raise SystemExit(f"onbekend account {a.account}")
    MAP.mkdir(parents=True, exist_ok=True)
    c = Client(token())
    nieuw = 0
    try:
        for pid in account["ids"]:
            platform, waarde = pid.split(":", 1)
            for r in c.lijst(player_id=f"{platform.lower()}:{waarde}", count=200):
                doel = MAP / f"{r['id']}.replay"
                if doel.exists():
                    continue
                tmp = doel.with_suffix(".replay.part")
                tmp.write_bytes(c.download(r["id"]))
                tmp.replace(doel)
                nieuw += 1
                print(f"  {r.get('date', '')[:10]}  {r.get('playlist_id', '?'):18s}  {r['id']}", flush=True)
    except RuntimeError as e:  # afgeknepen door ballchasing: wat binnen is wordt toch doorgestuurd; later opnieuw draaien
        print(f"downloaden onderbroken ({e}); opnieuw draaien gaat verder")
    print(f"{nieuw} nieuw opgehaald ({len(list(MAP.glob('*.replay')))} totaal in {MAP})")
    if a.upload:
        host, map_ = a.upload.split(":", 1)
        verstuurd_pad = MAP / "doorgestuurd.txt"
        verstuurd = set(verstuurd_pad.read_text(encoding="utf-8").split()) if verstuurd_pad.exists() else set()
        te_doen = [p for p in sorted(MAP.glob("*.replay")) if p.name not in verstuurd]
        for p in te_doen:
            subprocess.run(["scp", "-q", "-o", "BatchMode=yes", str(p), f"{host}:{map_.rstrip('/')}/{p.name}.part"], check=True)
            subprocess.run(["ssh", "-o", "BatchMode=yes", host, f"mv {map_.rstrip('/')}/{p.name}.part {map_.rstrip('/')}/{p.name}"], check=True)
            verstuurd.add(p.name)
            verstuurd_pad.write_text("\n".join(sorted(verstuurd)), encoding="utf-8")
        print(f"{len(te_doen)} doorgestuurd naar de server-inbox")


if __name__ == "__main__":
    main()
