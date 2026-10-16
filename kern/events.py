"""Gedeelde, gecachte replay-events.

subtr_actor.get_stats_events rekent alle ~55 stat-modules uit (~8 s per replay). Schoten, passen en zonewaarde
gebruiken alleen touch-, goal_context- en timeline-events. Die worden één keer berekend en bewaard
in data/features/cache/events/<replay>.json (en in het geheugen voor dezelfde run).
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import subtr_actor as sa

WORTEL = Path(__file__).resolve().parent.parent
MAP = WORTEL / "data" / "features" / "cache" / "events"
STROMEN = {"touch", "goal_context", "timeline", "fifty_fifty", "kickoff", "whiff", "beaten_to_ball", "demolition", "player_possession"}
VERSIE = "v2"  # ophogen als STROMEN verandert: oude cachebestanden worden dan opnieuw berekend

# Fouten bij het lezen van één replay. subtr-actor (Rust) gooit bij sommige replays een PanicException, die géén
# Exception-subklasse is: 'except Exception' liet die door en de updater op de server bleef daardoor crashen.
try:
    from pyo3_runtime import PanicException as _Paniek  # bestaat zodra pyo3 een panic heeft gezien
except ImportError:
    _Paniek = None


def replay_fout(e: BaseException) -> bool:
    """True voor gewone fouten én Rust-panics; False voor Ctrl+C / afsluiten (die moeten doorgaan)."""
    return isinstance(e, Exception) or type(e).__name__ == "PanicException" or (_Paniek is not None and isinstance(e, _Paniek))


@lru_cache(maxsize=8)
def _laad(pad_str: str) -> tuple:
    pad = Path(pad_str)
    cache = MAP / f"{pad.stem}.{VERSIE}.json"
    if cache.exists() and cache.stat().st_mtime >= pad.stat().st_mtime:
        return tuple(json.loads(cache.read_text(encoding="utf-8")))
    ev = [e for e in sa.get_stats_events(pad_str)["events"] if e["meta"]["stream"] in STROMEN]
    MAP.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(ev, separators=(",", ":")), encoding="utf-8")
    return tuple(ev)


def lijst(pad) -> list[dict]:
    """Touch-, goal_context- en timeline-events van een replay (zelfde vorm als get_stats_events)."""
    return list(_laad(str(Path(pad).resolve())))
