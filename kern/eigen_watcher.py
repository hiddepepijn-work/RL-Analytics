"""Houdt de Rocket League-replaymap in de gaten en verwerkt nieuwe eigen wedstrijden automatisch.

Elke 10 s: nieuwe .replay in DemosEpic/Demos → wachten tot het bestand klaar is met schrijven →
dezelfde controles als kern.eigen_import (speler zit erin, Ranked Doubles, volledig) →
kopie naar data/eigen/mee|apart → parser met Champion-modellen → staat in de app.

Stoppen: data/STOP_WATCHER aanmaken. Logboek: data/watcher.log

Gebruik:
    uv run python -m kern.eigen_watcher --naam "Sand ツ"
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

from kern.eigen_import import BRONNEN, beoordeel

WORTEL = Path(__file__).resolve().parent.parent
EIGEN = WORTEL / "data" / "eigen"
GEZIEN = EIGEN / "gezien.json"
STOP = WORTEL / "data" / "STOP_WATCHER"
os.environ["PYTHONIOENCODING"] = "utf-8"


def log(tekst: str) -> None:
    with (WORTEL / "data" / "watcher.log").open("a", encoding="utf-8") as f:
        f.write(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {tekst}\n")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--naam", required=True)
    ap.add_argument("--rank", default="champion")
    ap.add_argument("--bron", action="append", help="map(pen) om te bewaken (standaard: RL-replaymappen)")
    ap.add_argument("--verplaats", action="store_true", help="bronbestand na verwerken weghalen (server-inbox)")
    ap.add_argument("--upload", help="niet zelf verwerken maar doorsturen, bv. ubuntu@51.75.74.94:/var/lib/rl-analytics-inbox/")
    a = ap.parse_args()
    bronnen = [Path(b) for b in a.bron] if a.bron else BRONNEN
    EIGEN.mkdir(parents=True, exist_ok=True)
    gezien = set(json.loads(GEZIEN.read_text(encoding="utf-8"))) if GEZIEN.exists() else set()
    gezien |= {p.name for p in EIGEN.glob("*/*.replay")}  # al eerder geïmporteerd
    # Wedstrijd-ID's van al geïmporteerde replays: dezelfde wedstrijd onder een andere bestandsnaam
    # (bv. van ballchasing) wordt zo als dubbel herkend
    import subtr_actor as sa
    match_ids: set = set()
    for bestaand in EIGEN.glob("*/*.replay"):
        try:
            kop = dict(sa.get_replay_meta(str(bestaand))["replay_meta"]["all_headers"])
            match_ids.add(kop.get("MatchGuid") or kop.get("Id") or bestaand.stem)
        except Exception:
            pass
    log(f"start, bewaakt {', '.join(str(b) for b in bronnen if b.exists())}{' → upload ' + a.upload if a.upload else ''}")
    while not STOP.exists():
        for bron in bronnen:
            for p in sorted(bron.glob("*.replay")) if bron.exists() else []:
                if p.name in gezien:
                    continue
                grootte = p.stat().st_size
                time.sleep(3)
                if p.stat().st_size != grootte:
                    continue  # RL schrijft nog; volgende ronde opnieuw
                r = beoordeel(p, a.naam, match_ids)
                gezien.add(p.name)
                GEZIEN.write_text(json.dumps(sorted(gezien)), encoding="utf-8")
                log(f"{p.name}: {r['oordeel']} ({r['reden']})")
                if r["oordeel"] == "weg":
                    if a.verplaats:
                        p.unlink(missing_ok=True)
                    continue
                if a.upload:
                    # Pc-modus: alleen doorsturen; de server controleert opnieuw en verwerkt
                    tmp_naam = p.name + ".part"
                    host, map_ = a.upload.split(":", 1)
                    res = subprocess.run(["scp", "-q", "-o", "BatchMode=yes", str(p), f"{host}:{map_.rstrip('/')}/{tmp_naam}"], capture_output=True, text=True)
                    if res.returncode == 0:
                        subprocess.run(["ssh", "-o", "BatchMode=yes", host, f"mv {map_.rstrip('/')}/{tmp_naam} {map_.rstrip('/')}/{p.name}"], capture_output=True)
                        log("  geüpload naar server")
                    else:
                        gezien.discard(p.name)  # volgende ronde opnieuw proberen
                        log(f"  upload mislukt: {res.stderr.strip()[-200:]}")
                    continue
                doel = EIGEN / r["oordeel"]
                doel.mkdir(exist_ok=True)
                shutil.copy2(p, doel / p.name)
                if a.verplaats:
                    p.unlink(missing_ok=True)
                res = subprocess.run([sys.executable, "-m", "kern.parseer", str(doel / p.name), "--rank", a.rank,
                                      "--ik", a.naam, "--categorie", r["oordeel"]], cwd=WORTEL, capture_output=True,
                                     text=True, encoding="utf-8", errors="replace")
                log(f"  verwerkt: {res.stdout.strip()[-200:]}" if res.returncode == 0 else f"  FOUT: {res.stderr[-500:]}")
                if r["oordeel"] == "mee":
                    subprocess.run([sys.executable, "-m", "kern.profiel", "--naam", a.naam], cwd=WORTEL, capture_output=True)
        time.sleep(10)
    log("gestopt (STOP_WATCHER)")


if __name__ == "__main__":
    main()
