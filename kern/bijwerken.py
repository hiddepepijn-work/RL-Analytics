"""Doorlopend bijwerken: nieuwe Champion-replays ophalen → features (met cache) → xG en xPass opnieuw trainen.

Gebruik:
    uv run python -m kern.bijwerken                 # één ronde
    uv run python -m kern.bijwerken --doorlopend    # ronde na ronde, pauze ertussen

Stoppen: maak het bestand data/STOP aan (de lopende ronde wordt eerst afgemaakt).
Logboek:  data/modellen/geschiedenis.jsonl (één regel per ronde met scores).
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import subtr_actor as sa

from kern import passen, schoten

WORTEL = Path(__file__).resolve().parent.parent
PY = sys.executable
# Draait vaak verborgen zonder console-instellingen: altijd UTF-8, ook voor de download-subprocessen
os.environ["PYTHONIOENCODING"] = "utf-8"
for stroom in (sys.stdout, sys.stderr):
    try:
        stroom.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
CACHE = WORTEL / "data" / "features" / "cache"
STOP = WORTEL / "data" / "STOP"
LOG = WORTEL / "data" / "modellen" / "geschiedenis.jsonl"
CHAMP = ("ranked-doubles", "champion-1", "champion-3")


def log(tekst: str) -> None:
    regel = f"[{datetime.now():%Y-%m-%d %H:%M}] {tekst}"
    print(regel, flush=True)
    with (WORTEL / "data" / "bijwerken.log").open("a", encoding="utf-8") as f:
        f.write(regel + "\n")


def download(aantal: int) -> None:
    pl, lo, hi = CHAMP
    subprocess.run([PY, "-m", "kern.ballchasing", "--playlist", pl, "--min-rank", lo, "--max-rank", hi, "--aantal", str(aantal)],
                   cwd=WORTEL, check=False)


def features_bijwerken() -> tuple[int, int]:
    """Verwerk alleen replays zonder cache; bouw daarna schoten.csv en passen.csv opnieuw op uit de cache."""
    for soort in ("schoten", "passen"):
        (CACHE / soort).mkdir(parents=True, exist_ok=True)
    index_pad = CACHE / "match_ids.json"
    index = json.loads(index_pad.read_text(encoding="utf-8")) if index_pad.exists() else {}
    nieuw = 0
    for p in sorted((WORTEL / "data" / "replays").glob("*/*.replay")):
        if p.stem in index:
            continue
        try:
            kop = dict(sa.get_replay_meta(str(p))["replay_meta"]["all_headers"])
            mid = kop.get("MatchGuid") or kop.get("Id") or p.stem
            if mid in index.values():
                index[p.stem] = mid  # dubbel: wel onthouden, niet opnieuw tellen
                continue
            for soort, fn in (("schoten", schoten.schoten_uit_replay), ("passen", passen.kandidaten_uit_replay)):
                rijen = fn(p, p.parent.name)
                with (CACHE / soort / f"{p.stem}.csv").open("w", newline="", encoding="utf-8") as f:
                    if rijen:
                        w = csv.DictWriter(f, fieldnames=list(rijen[0].keys())); w.writeheader(); w.writerows(rijen)
            index[p.stem] = mid
            nieuw += 1
        except Exception as e:
            log(f"overslaan {p.name}: {type(e).__name__}: {str(e)[:80]}")
            index[p.stem] = f"fout:{p.stem}"
        if nieuw and nieuw % 25 == 0:
            index_pad.write_text(json.dumps(index), encoding="utf-8")
    index_pad.write_text(json.dumps(index), encoding="utf-8")

    # Cache van een oudere featureversie (mist de nieuwste kolom) → opnieuw berekenen
    for soort, mod, fn in (("schoten", schoten, schoten.schoten_uit_replay), ("passen", passen, passen.kandidaten_uit_replay)):
        for stem, mid in index.items():
            f = CACHE / soort / f"{stem}.csv"
            if mid.startswith("fout:") or not f.exists() or not f.stat().st_size:
                continue
            with f.open(encoding="utf-8") as h:
                if mod.NIEUWSTE_KOLOM in h.readline():
                    continue
            p = next((WORTEL / "data" / "replays").glob(f"*/{stem}.replay"), None)
            if p is None:
                continue
            try:
                rijen = fn(p, p.parent.name)
                with f.open("w", newline="", encoding="utf-8") as h:
                    if rijen:
                        w = csv.DictWriter(h, fieldnames=list(rijen[0].keys())); w.writeheader(); w.writerows(rijen)
                nieuw += 1
            except Exception as e:
                log(f"{soort} opnieuw {stem}: {type(e).__name__}")

    for soort in ("schoten", "passen"):
        delen, uniek = [], set()
        for stem, mid in index.items():
            if mid.startswith("fout:") or mid in uniek:
                continue
            uniek.add(mid)
            f = CACHE / soort / f"{stem}.csv"
            if f.exists() and f.stat().st_size:
                delen.append(f)
        uit = WORTEL / "data" / "features" / f"{soort}.csv"
        with uit.open("w", newline="", encoding="utf-8") as o:
            kop_geschreven = False
            for f in delen:
                regels = f.read_text(encoding="utf-8").splitlines()
                if not regels:
                    continue
                if not kop_geschreven:
                    o.write(regels[0] + "\n"); kop_geschreven = True
                o.write("\n".join(regels[1:]) + "\n")
    return nieuw, len(index)


def trainen() -> dict:
    uit = {}
    for mod, bestand in (("kern.xg_model", "xg.json"), ("kern.xgot_model", "xgot.json"), ("kern.xpass_model", "xpass.json")):
        r = subprocess.run([PY, "-m", mod], cwd=WORTEL, check=False, capture_output=True, text=True, encoding="utf-8", errors="replace")
        if r.returncode:
            log(f"training {mod} mislukt: " + r.stderr[-1500:].replace("\n", " | "))
        pad = WORTEL / "data" / "modellen" / bestand
        if pad.exists():
            j = json.loads(pad.read_text(encoding="utf-8"))
            uit[bestand.split(".")[0]] = j.get("validatie", {}).get("xG-model") or {"auc": j.get("auc"), "n": j.get("n")}
    # Dreigingsmodel (verdedigende stats): zware training (~1,8 mln momenten), dus hooguit één keer per dag
    dm = WORTEL / "data" / "modellen" / "dreiging.joblib"
    if not dm.exists() or time.time() - dm.stat().st_mtime > 24 * 3600:
        r = subprocess.run([PY, "-m", "kern.dreiging", "--processen", "2"], cwd=WORTEL, check=False, capture_output=True,
                           text=True, encoding="utf-8", errors="replace")
        if r.returncode:
            log("training kern.dreiging mislukt: " + r.stderr[-1500:].replace("\n", " | "))
    return uit


def aantal_champ() -> int:
    pl, lo, hi = CHAMP
    return len(list((WORTEL / "data" / "replays" / f"{pl}_{lo}_{hi}").glob("*.replay")))


def ronde(per_ronde: int, maximum: int, downloaden: bool = True) -> None:
    # Eerst verwerken + trainen (nieuwe cijfers zo snel mogelijk), daarna downloaden voor de volgende ronde
    nieuw, totaal = features_bijwerken()
    scores = trainen() if nieuw else {}
    log(f"verwerkt {nieuw} nieuw, getraind: {scores}")
    voor = aantal_champ()
    if downloaden and voor < maximum:
        download(min(per_ronde, maximum - voor))
    na = aantal_champ()
    regel = {"tijd": datetime.now().isoformat(timespec="minutes"), "champion_replays": na, "nieuw_verwerkt": nieuw,
             "replays_totaal": totaal, "scores": scores}
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(regel) + "\n")
    log(f"ronde klaar: champion {voor}→{na}, {nieuw} nieuw verwerkt, scores {scores}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--doorlopend", action="store_true")
    ap.add_argument("--per-ronde", type=int, default=100)
    ap.add_argument("--max", type=int, default=3000, help="plafond Champion-replays (≈1 MB per stuk)")
    ap.add_argument("--pauze-min", type=int, default=60)
    ap.add_argument("--zonder-download", action="store_true", help="alleen verwerken + trainen (downloaden doet kern.downloader)")
    a = ap.parse_args()
    log(f"start (doorlopend={a.doorlopend}, per ronde {a.per_ronde}, max {a.max})")
    while True:
        if STOP.exists():
            log("STOP-bestand gevonden, klaar."); break
        try:
            ronde(a.per_ronde, a.max, downloaden=not a.zonder_download)
        except Exception:
            import traceback
            log("FOUT in ronde, volgende ronde probeer ik opnieuw: " + traceback.format_exc().replace("\n", " | "))
        if not a.doorlopend:
            break
        if not a.zonder_download and aantal_champ() >= a.max:
            log(f"plafond {a.max} bereikt; alleen nog opnieuw trainen bij nieuwe data. Klaar."); break
        for _ in range(a.pauze_min):
            if STOP.exists():
                break
            time.sleep(60)


if __name__ == "__main__":
    main()
