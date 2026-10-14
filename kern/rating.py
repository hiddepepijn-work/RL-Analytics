"""Live wedstrijdrating per speler, opgebouwd uit acties (zoals SofaScore/HLTV, maar met onze eigen modellen).

Elke actie levert impact op in 'goal-equivalenten' (1,0 = één goal), ingedeeld per onderdeel:
  Schieten   schot +xG · goal +(1 − xG) (afwerking) · grote kans (xG ≥ 0,35) gemist −0,5 × xG
             kans gemist door whiff −0,4 × kans-xG (denkbeeldig schot, zie kern/kansen.py)
  Passen     aangekomen pass +0,04 · assist +0,25 · kans gecreëerd +0,3 × xG van het schot/de kans (xA)
             goede pass naar jou niet geraakt −0,03
  Verdedigen redding +xGOT van het tegengehouden schot (min. 0,15) · fout voor tegengoal −0,10
             tegengoal als laatste man −0,12, of −0,06 als een ander de fout maakte
  Duels      50/50 ±0,03 · eerder/later bij de bal ±0,02 · whiff −0,04 (zonder kans) · demo +0,05 / −0,03
  Kickoffs   kickoff gewonnen/verloren ±0,06
  Balbezit   dreiging opbouwen met de bal (xT): bij elke touch binnen je balbezit de stijging van de zonewaarde
             (kans dat je team binnen 10 s scoort vanaf die plek) boven het hoogste punt tot dan toe in dit bezit.
             Live per touch, dus niet pas aan het eind. Terug met de bal (boost pakken, opnieuw opzetten) kost niets;
             balverlies wordt elders afgerekend.
Per onderdeel wordt de som vergeleken met wat een gemiddelde speler van de rank op dat moment heeft (normen uit de
benchmark) → z-score → cijfer per onderdeel.

Totaalcijfer in twee lagen (DELEN):
  Doelbijdrage  alles wat direct met goals te maken heeft (schoten, goals, gemiste kansen, assists, xA, reddingen,
                fouten, tegengoals), in één munt vergeleken: een goal weegt dus altijd zwaarder dan een assist.
  Proces        passes, duels, kickoffs en balbezit, elk tegen de eigen norm (anders verdwijnen ze naast goals).
rating = 6,5 + 1,0 · gewogen z, begrensd op 3,0–10,0.
De spreiding groeit met de wortel van de speeltijd, dus vroeg in de wedstrijd beweegt het cijfer minder snel uit.
"""
from __future__ import annotations

import json
import math
from functools import cache
from pathlib import Path

from kern import zonewaarde

WORTEL = Path(__file__).resolve().parent.parent
NORM_PAD = WORTEL / "data" / "modellen" / "rating_norm.json"
ONDERDELEN = ["Schieten", "Passen", "Verdedigen", "Duels", "Kickoffs", "Balbezit"]
BASIS, SCHAAL, MIN, MAX = 6.5, 1.0, 3.0, 10.0  # schaal 1,0: ~80% van de Champions tussen 5,3 en 8,3; 8+ is bijzonder
START_NA = 60  # seconden speeltijd voordat er een cijfer getoond wordt
# Terugval als er nog geen benchmark-normen zijn (ruwe schatting; per 5 min, gemiddeld en spreiding)
STANDAARD_NORM = {"totaal": {"gem": 0.9, "sd": 0.55}, **{o: {"gem": 0.15, "sd": 0.12} for o in ONDERDELEN},
                  "Doelbijdrage": {"gem": 2.2, "sd": 1.5}, "Passen_proces": {"gem": 0.1, "sd": 0.1}}
# Totaalcijfer: doelbijdrage in één munt + procesonderdelen elk t.o.v. de eigen norm
DELEN = {"Doelbijdrage": 0.55, "Passen_proces": 0.12, "Balbezit": 0.13, "Duels": 0.12, "Kickoffs": 0.08}


def sleutel(pid):
    if not pid:
        return None
    (k, v), = pid.items()
    return f"{k}:{v}"


GROTE_KANS = 0.35
ZONE_PAD = WORTEL / "data" / "modellen" / "zonewaarde.json"


@cache
def _zone():
    return json.loads(ZONE_PAD.read_text(encoding="utf-8"))["grid"] if ZONE_PAD.exists() else None


def acties(events: list[dict], schoten: list[dict], passen: list[dict], team: dict[str, int], kansen: dict | None = None) -> list[tuple]:
    """→ [(tijd, speler, onderdeel, impact, omschrijving)] gesorteerd op tijd. kansen = data['kansen'] (kern/kansen.py)."""
    uit = []
    kansen = kansen or {}

    def voeg(t, s, o, w, oms, bijdrage=None):
        """bijdrage: telt mee in de doelbijdrage-laag (standaard: alles in Schieten en Verdedigen)."""
        if s in team:
            uit.append((round(t, 2), s, o, round(w, 4), oms, o in ("Schieten", "Verdedigen") if bijdrage is None else bijdrage))

    # Schieten (xG uit ons model)
    for s in schoten:
        xg = s.get("xg") or 0
        kans = s.get("kans")
        voeg(s["tijd"], s["speler"], "Schieten", xg, f"Schot (kans {kans:.2f} → xG {xg:.2f})" if kans is not None else f"Schot (xG {xg:.2f})")
        if s.get("goal"):
            voeg(s["tijd"] + 0.01, s["speler"], "Schieten", 1 - xg, "Goal (afwerking)")
        elif xg >= GROTE_KANS:
            voeg(s["tijd"] + 0.01, s["speler"], "Schieten", -0.5 * xg, f"Grote kans gemist (xG {xg:.2f})")
    kans_whiffs = [(k["tijd"], k["speler"]) for k in kansen.get("gemist", [])]
    for k in kansen.get("gemist", []):
        voeg(k["tijd"], k["speler"], "Schieten", -0.4 * k["kans_xg"], f"Kans gemist door whiff (kans-xG {k['kans_xg']:.2f})")
    for c in kansen.get("creaties", []):
        voeg(c["tijd"], c["speler"], "Passen", 0.3 * c["xg"], f"Kans gecreëerd (xA {c['xg']:.2f})", bijdrage=True)
    fout_bij_goal = {}
    for f in kansen.get("fouten", []):
        fout_bij_goal[f["goal_tijd"]] = f["speler"]
        voeg(f["tijd"], f["speler"], "Verdedigen", -0.10, "Fout voor tegengoal" + (" (whiff)" if f["soort"] == "whiff" else " (balverlies)"))
    # Passen (xPass-model)
    for p in passen:
        if p.get("compleet"):
            voeg(p["tijd"], p["passer"], "Passen", 0.04, "Pass aangekomen")
        elif p.get("p", 0) >= 0.5 and p.get("ontvanger"):
            voeg(p["tijd"], p["ontvanger"], "Passen", -0.03, "Goede pass niet geraakt")

    opp_schoten = sorted(schoten, key=lambda s: s["tijd"])
    zone = _zone()
    touches = sorted(((e["meta"]["timing"].get("start_time", e["meta"]["timing"].get("time", 0)), sleutel(e["meta"].get("primary_player")),
                       ((e.get("payload") or {}).get("payload") or {}).get("ball_position")) for e in events if e["meta"]["stream"] == "touch"),
                     key=lambda x: x[0])
    for e in events:
        m, pl = e["meta"], (e.get("payload") or {}).get("payload") or {}
        st, t = m["stream"], m["timing"].get("time", m["timing"].get("start_time", m["timing"].get("end_time", 0)))
        if st == "timeline":
            soort, wie = pl.get("kind"), sleutel(pl.get("player_id"))
            if soort == "Assist":
                voeg(t, wie, "Passen", 0.25, "Assist", bijdrage=True)
            elif soort == "Save" and wie in team:
                # xG van het laatste tegenstander-schot vlak ervoor = wat er voorkomen werd
                kandidaat = [s for s in opp_schoten if team.get(s["speler"]) not in (None, team[wie]) and t - 3 <= s["tijd"] <= t + 0.3]
                xg = max([s.get("xgot") or s.get("xg") or 0 for s in kandidaat], default=0)  # xGOT: schotkwaliteit, los van waar jij stond
                voeg(t, wie, "Verdedigen", max(0.15, xg), f"Redding{f' (xGOT {xg:.2f})' if xg else ''}")
        elif st == "goal_context":
            laatste = sleutel(pl.get("defending_team_most_back_player"))
            ander_fout = fout_bij_goal.get(round(t, 2)) not in (None, laatste)
            voeg(t, laatste, "Verdedigen", -0.06 if ander_fout else -0.12, "Tegengoal als laatste man")
        elif st == "fifty_fifty":
            p0, p1 = sleutel(pl.get("team_zero_player")), sleutel(pl.get("team_one_player"))
            winnaar0 = pl.get("possession_team_is_team_0")
            if winnaar0 is None or not p0 or not p1:
                continue
            onderdeel = "Kickoffs" if pl.get("is_kickoff") else "Duels"
            if onderdeel == "Kickoffs":
                continue  # kickoffs via de kickoff-stroom (voorkomt dubbel tellen)
            (w, v) = (p0, p1) if winnaar0 else (p1, p0)
            voeg(t, w, "Duels", 0.03, "50/50 gewonnen"); voeg(t, v, "Duels", -0.03, "50/50 verloren")
        elif st == "kickoff":
            taker, adv_team = sleutel(m.get("primary_player")), pl.get("advantage_team_is_team_0")
            if taker in team and adv_team is not None:
                gewonnen = (team[taker] == 0) == adv_team
                voeg(t, taker, "Kickoffs", 0.06 if gewonnen else -0.06, "Kickoff gewonnen" if gewonnen else "Kickoff verloren")
        elif st == "beaten_to_ball":
            voeg(t, sleutel(pl.get("player")), "Duels", -0.02, "Te laat bij de bal")
            voeg(t, sleutel(pl.get("winner")), "Duels", 0.02, "Eerder bij de bal")
        elif st == "whiff":
            wie = sleutel(pl.get("player"))
            if not any(k_s == wie and abs(k_t - (pl.get("time") or t)) < 0.5 for k_t, k_s in kans_whiffs):  # kans-whiff telt al bij Schieten
                voeg(t, wie, "Duels", -0.04, "Whiff (bal gemist)")
        elif st == "demolition":
            voeg(t, sleutel(pl.get("attacker")), "Duels", 0.05, "Demo gemaakt")
            voeg(t, sleutel(pl.get("victim")), "Duels", -0.03, "Gedemoed")
        elif st == "player_possession":
            wie = sleutel(pl.get("player_id"))
            if wie not in team or zone is None:
                continue
            richting = 1 if team[wie] == 0 else -1
            t0, t1 = pl.get("start_time", t), pl.get("end_time", t)
            hoogste = None
            for tt, ts, bp in touches:
                if ts != wie or not bp or tt < t0 - 0.05 or tt > t1 + 0.05:
                    continue
                w = float(zonewaarde.waarde(zone, bp[0], bp[1] * richting))
                if hoogste is not None and w > hoogste + 0.003:
                    voeg(tt, wie, "Balbezit", w - hoogste, f"Dreiging opgebouwd (xT +{100 * (w - hoogste):.1f}%)")
                hoogste = w if hoogste is None else max(hoogste, w)
    uit.sort(key=lambda a: a[0])
    return uit


def speeltijd_functie(t_lijst: list[float], klok: list[int]):
    """Replay-tijd → verstreken speeltijd (s), ook in overtime (klok staat dan op 0)."""
    t0_ot = next((t for t, k in zip(t_lijst, klok) if k == 0), None)

    def f(t: float) -> float:
        import bisect
        i = min(len(t_lijst) - 1, max(0, bisect.bisect_left(t_lijst, t)))
        if klok[i] > 0 or t0_ot is None:
            return 300 - klok[i]
        return 300 + max(0.0, t - t0_ot)
    return f


def norm(band: str | None) -> dict:
    if NORM_PAD.exists():
        alle = json.loads(NORM_PAD.read_text(encoding="utf-8"))
        return alle.get(band or "", alle.get("_standaard", STANDAARD_NORM))
    return STANDAARD_NORM


def cijfer(impact: float, speeltijd: float, n: dict) -> float:
    verwacht = n["gem"] * speeltijd / 300
    spreiding = max(1e-6, n["sd"] * math.sqrt(max(speeltijd, 30) / 300))
    return round(min(MAX, max(MIN, BASIS + SCHAAL * (impact - verwacht) / spreiding)), 2)


def z_score(impact: float, speeltijd: float, n: dict) -> float:
    verwacht = n["gem"] * speeltijd / 300
    spreiding = max(1e-6, n["sd"] * math.sqrt(max(speeltijd, 30) / 300))
    return (impact - verwacht) / spreiding


def deel(actie: tuple) -> str:
    """Actie → deel van het totaalcijfer (DELEN)."""
    if actie[5]:
        return "Doelbijdrage"
    return "Passen_proces" if actie[2] == "Passen" else actie[2]


def sommen(acties_speler: list[tuple]) -> dict:
    """Impact per onderdeel én per deel van het totaal (voor rating_norm)."""
    uit = {k: 0.0 for k in [*ONDERDELEN, *DELEN]}
    for a in acties_speler:
        uit[a[2]] += a[3]
        uit[deel(a)] += a[3]
    return uit


def totaal_cijfer(cum: dict, speeltijd: float, n: dict) -> float:
    """cum = impact per deel (DELEN)."""
    z = sum(w * z_score(cum[d], speeltijd, n.get(d, STANDAARD_NORM[d])) for d, w in DELEN.items())
    z /= math.sqrt(sum(w * w for w in DELEN.values()))  # onafhankelijke delen → spreiding weer ~1
    return round(min(MAX, max(MIN, BASIS + SCHAAL * z)), 2)


def bereken(data: dict, events: list[dict], band: str | None = None) -> dict:
    team = {s["id"]: s["team"] for s in data["spelers"]}
    lijst = acties(events, data.get("schoten", []), data.get("passen", []), team, data.get("kansen"))
    speeltijd = speeltijd_functie(data["t"], data["klok"])
    n = norm(band)
    t_eind = data["t"][-1]
    uit = {"norm_band": band if NORM_PAD.exists() else None, "start_na": START_NA, "spelers": {}}
    for sid in team:
        mijn = [a for a in lijst if a[1] == sid]
        tijdlijn, cum, j = [], {d: 0.0 for d in DELEN}, 0
        stappen = [t for t in data["t"][:: max(1, int(data.get("fps", 30) * 2))]] + [t_eind]  # elke ~2 s
        for t in stappen:
            while j < len(mijn) and mijn[j][0] <= t:
                cum[deel(mijn[j])] += mijn[j][3]; j += 1
            st = speeltijd(t)
            if st >= START_NA:
                tijdlijn.append([round(t, 2), totaal_cijfer(cum, st, n)])
        totaal_tijd = speeltijd(t_eind)
        per_onderdeel = {o: round(sum(a[3] for a in mijn if a[2] == o), 3) for o in ONDERDELEN}
        uit["spelers"][sid] = {
            "eind": tijdlijn[-1][1] if tijdlijn else None,
            "impact": round(sum(a[3] for a in mijn), 3),
            "speeltijd": round(totaal_tijd),
            "onderdelen": {o: {"impact": v, "cijfer": cijfer(v, totaal_tijd, n.get(o, STANDAARD_NORM[o]))} for o, v in per_onderdeel.items()},
            "tijdlijn": tijdlijn,
            "acties": [[a[0], a[2], a[3], a[4]] for a in mijn],
        }
    return uit
