"""Data hervatbaar naar de VPS kopiëren (geen rsync op Windows).

Vergelijkt per bestand de grootte met de server, stuurt alleen wat ontbreekt of afwijkt, in porties van
~50 MB per ssh-sessie, met nieuwe pogingen bij een verbroken verbinding.

Gebruik:
    uv run python deploy/sync_naar_vps.py [map ...]     # standaard: replays features modellen verwerkt eigen
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
import time
from pathlib import Path

WORTEL = Path(__file__).resolve().parent.parent
DATA = WORTEL / "data"
HOST = "ubuntu@51.75.74.94"
DOEL = "/srv/rl-analytics/data"
PORTIE = 50 * 1024 * 1024
MAX_BESTANDEN = 800
SSH = ["ssh", "-o", "BatchMode=yes", "-o", "ServerAliveInterval=15", "-o", "ConnectTimeout=20", HOST]


def server_lijst() -> dict[str, int]:
    for poging in range(5):
        r = subprocess.run(SSH + [f"sudo find {DOEL} -type f -printf '%P\\t%s\\n'"], capture_output=True, text=True, encoding="utf-8")
        if r.returncode == 0:
            return {regel.split("\t")[0]: int(regel.split("\t")[1]) for regel in r.stdout.splitlines() if "\t" in regel}
        time.sleep(10 * (poging + 1))
    raise SystemExit("server niet bereikbaar")


def main(mappen: list[str]) -> None:
    op_server = server_lijst()
    lokaal = [p for m in mappen for p in (DATA / m).rglob("*") if p.is_file() and not p.name.endswith(".part")]
    nodig = [p for p in lokaal if op_server.get(p.relative_to(DATA).as_posix()) != p.stat().st_size]
    totaal = sum(p.stat().st_size for p in nodig)
    print(f"{len(nodig)} bestanden ({totaal / 1e6:.0f} MB) te versturen, {len(lokaal) - len(nodig)} staan er al", flush=True)
    porties, huidig, grootte = [], [], 0
    for p in nodig:
        huidig.append(p); grootte += p.stat().st_size
        if grootte >= PORTIE or len(huidig) >= MAX_BESTANDEN:
            porties.append(huidig); huidig, grootte = [], 0
    if huidig:
        porties.append(huidig)
    verstuurd = 0
    for i, portie in enumerate(porties, 1):
        namen = [p.relative_to(DATA).as_posix() for p in portie]
        for poging in range(6):
            with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8", newline="\n") as lijst:
                lijst.write("\n".join(namen) + "\n")
            tar = subprocess.Popen(["tar", "cf", "-", "-C", str(DATA), "-T", Path(lijst.name).as_posix()], stdout=subprocess.PIPE)
            r = subprocess.run(SSH + [f"sudo -u rlanalytics tar xf - -C {DOEL}"], stdin=tar.stdout, capture_output=True)
            tar.wait()
            Path(lijst.name).unlink(missing_ok=True)
            if r.returncode == 0:
                break
            print(f"  portie {i}: poging {poging + 1} mislukt, opnieuw over {15 * (poging + 1)} s", flush=True)
            time.sleep(15 * (poging + 1))
        else:
            raise SystemExit(f"portie {i} blijft mislukken; later opnieuw draaien hervat vanaf hier")
        verstuurd += sum(p.stat().st_size for p in portie)
        print(f"  {i}/{len(porties)} porties, {verstuurd / 1e6:.0f}/{totaal / 1e6:.0f} MB", flush=True)
    print("KLAAR", flush=True)


if __name__ == "__main__":
    main(sys.argv[1:] or ["replays", "features", "modellen", "verwerkt", "eigen"])
