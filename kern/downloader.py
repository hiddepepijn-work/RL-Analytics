"""Onafgebroken 2v2-replays downloaden voor alle ranks, tot elk doel bereikt is of de gebruiker stopt.

Doelen (gekozen door de gebruiker): elke rank 500 wedstrijden, Champion 5000.
Elke keer wordt de rank aangevuld die procentueel het verst achterloopt.

Stoppen: maak data/STOP_DOWNLOAD aan (of data/STOP voor alles).
Veiligheid: pauzeert (niet stoppen) zolang er minder dan MIN_VRIJ_GB vrij is op de schijf.
Logboek: data/downloader.log

Gebruik:
    uv run python -m kern.downloader
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

WORTEL = Path(__file__).resolve().parent.parent
STOP = [WORTEL / "data" / "STOP_DOWNLOAD", WORTEL / "data" / "STOP"]
MIN_VRIJ_GB = 5
PER_KEER = 50
PLAYLIST = "ranked-doubles"
# (laagste rank, hoogste rank, doel)
BANDEN = [
    ("bronze-1", "bronze-3", 500),
    ("silver-1", "silver-3", 500),
    ("gold-1", "gold-3", 500),
    ("platinum-1", "platinum-3", 500),
    ("diamond-1", "diamond-3", 500),
    ("champion-1", "champion-3", 5000),
    ("grand-champion-1", "supersonic-legend", 500),
]
os.environ["PYTHONIOENCODING"] = "utf-8"


def log(tekst: str) -> None:
    with (WORTEL / "data" / "downloader.log").open("a", encoding="utf-8") as f:
        f.write(f"[{datetime.now():%Y-%m-%d %H:%M}] {tekst}\n")


def aantal(lo: str, hi: str) -> int:
    return len(list((WORTEL / "data" / "replays" / f"{PLAYLIST}_{lo}_{hi}").glob("*.replay")))


def stand() -> str:
    return ", ".join(f"{lo.rsplit('-', 1)[0]} {aantal(lo, hi)}/{doel}" for lo, hi, doel in BANDEN)


def main() -> None:
    log(f"start: {stand()}")
    leeg = {}  # band → tijdstip waarop er geen nieuwe replays waren (even overslaan)
    while not any(p.exists() for p in STOP):
        vrij = shutil.disk_usage(WORTEL).free / 1e9
        if vrij < MIN_VRIJ_GB:
            log(f"pauze: nog maar {vrij:.1f} GB vrij (grens {MIN_VRIJ_GB} GB)")
            time.sleep(1800)
            continue
        open_ = [(aantal(lo, hi) / doel, lo, hi, doel) for lo, hi, doel in BANDEN
                 if aantal(lo, hi) < doel and time.time() - leeg.get(lo, 0) > 1800]
        if not open_:
            if all(aantal(lo, hi) >= doel for lo, hi, doel in BANDEN):
                log(f"alle doelen bereikt: {stand()}. Klaar.")
                return
            time.sleep(600)
            continue
        _, lo, hi, doel = min(open_)
        voor = aantal(lo, hi)
        subprocess.run([sys.executable, "-m", "kern.ballchasing", "--playlist", PLAYLIST, "--min-rank", lo, "--max-rank", hi,
                        "--aantal", str(min(PER_KEER, doel - voor))], cwd=WORTEL, check=False,
                       stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        na = aantal(lo, hi)
        if na == voor:
            leeg[lo] = time.time()
        log(f"{lo.rsplit('-', 1)[0]}: +{na - voor} ({na}/{doel}) | {vrij:.1f} GB vrij")
        time.sleep(30)
    log(f"gestopt op verzoek (STOP-bestand): {stand()}")


if __name__ == "__main__":
    main()
