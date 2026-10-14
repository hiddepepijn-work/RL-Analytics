"""Kalibratie van de 'kans vóór de touch': ruwe kans (perfect gericht denkbeeldig schot) → verwachte xG van een echt schot.

Fit op echte schoten uit de rating-cache (kern.rating_norm): xG ≈ a · ruw + b (kleinste kwadraten).

Gebruik:
    uv run python -m kern.kans_kalibratie
Uitvoer: data/modellen/kans_kalibratie.json
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from kern.kansen import KALIBRATIE_PAD

CACHE = Path(__file__).resolve().parent.parent / "data" / "features" / "cache" / "rating"


def main() -> None:
    paren = []
    for f in CACHE.glob("*.json"):
        inv = json.loads(f.read_text(encoding="utf-8"))
        for s in inv.get("schoten", []) if isinstance(inv, dict) else []:
            ruw = s.get("kans_ruw", s.get("kans"))
            if ruw is not None and s.get("xg") is not None:
                paren.append((ruw, s["xg"]))
    if len(paren) < 500:
        raise SystemExit(f"te weinig schoten ({len(paren)})")
    x, y = np.array(paren).T
    a, b = np.polyfit(x, y, 1)
    print(f"{len(paren)} schoten · xG ≈ {a:.3f} · ruw + {b:+.3f}")
    print(" ruw-bak   n   gem xG   fit")
    for lo in np.arange(0, 1, 0.1):
        m = (x >= lo) & (x < lo + 0.1)
        if m.sum():
            print(f" {lo:.1f}–{lo + 0.1:.1f} {m.sum():5d}  {y[m].mean():.3f}   {a * (lo + 0.05) + b:.3f}")
    print(f"gem. uitvoering (xG − verwacht): {np.mean(y - np.clip(a * x + b, 0.001, 0.99)):+.4f}")
    KALIBRATIE_PAD.write_text(json.dumps({"a": round(float(a), 4), "b": round(float(b), 4), "n": len(paren)}), encoding="utf-8")


if __name__ == "__main__":
    main()
