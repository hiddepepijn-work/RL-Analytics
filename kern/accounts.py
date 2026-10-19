"""Accounts: een speler wordt herkend aan zijn platform-ID(s), niet aan zijn (wijzigbare) naam.

data/accounts.json: [{naam, ids: ["Epic:…", "Steam:…"], bekende_namen: [...], rank}]
Later: bij de eerste login koppelt een nieuwe gebruiker zijn Epic- of Steam-account; dat ID komt hier.
"""
from __future__ import annotations

import json
from pathlib import Path

WORTEL = Path(__file__).resolve().parent.parent
PAD = WORTEL / "data" / "accounts.json"


def sleutel(remote_id: dict | None) -> str | None:
    if not remote_id:
        return None
    (k, v), = remote_id.items()
    return f"{k}:{v}"


def alle() -> list[dict]:
    return json.loads(PAD.read_text(encoding="utf-8"))["accounts"] if PAD.exists() else []


def vind(zoek: str) -> dict | None:
    """Account op accountnaam, bekende spelersnaam of platform-ID."""
    for a in alle():
        if zoek == a["naam"] or zoek in a.get("bekende_namen", []) or zoek in a["ids"]:
            return a
    return None


def is_ik(account: dict, speler: dict) -> bool:
    """speler = item uit replay_meta team_zero/team_one (met remote_id en name)."""
    return sleutel(speler.get("remote_id")) in account["ids"]


def zet(zoek: str, sleutel_: str, waarde) -> None:
    """Eén veld van een account opslaan (bv. de geschatte subrank)."""
    data = json.loads(PAD.read_text(encoding="utf-8"))
    for a in data["accounts"]:
        if zoek == a["naam"] or zoek in a.get("bekende_namen", []) or zoek in a["ids"]:
            a[sleutel_] = waarde
    PAD.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


def subrank(account: dict | None) -> str | None:
    """Handmatig ingestelde subrank gaat vóór de geschatte."""
    if not account:
        return None
    return account.get("subrank_handmatig") or (account.get("rank_schatting") or {}).get("subrank")
