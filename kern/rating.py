"""Live wedstrijdrating per speler, opgebouwd uit acties (zoals SofaScore/HLTV, maar met onze eigen modellen).

Elke actie levert impact op in 'goal-equivalenten' (1,0 = één goal), ingedeeld per onderdeel:
  Schieten   schot +xG · goal +(1 − xG) (afwerking) · grote kans (xG ≥ 0,35) gemist −0,5 × xG
             kans gemist door whiff −0,4 × kans-xG (denkbeeldig schot, zie kern/kansen.py)
  Passen     aangekomen pass +0,04 · assist +0,25 · kans gecreëerd +0,3 × xG van het schot/de kans (xA)
             goede pass naar jou niet geraakt −0,03
  Verdedigen redding +xGOT van het tegengehouden schot (min. 0,15) · fout voor tegengoal −0,10
             tegengoal als laatste man −0,12, of −0,06 als een ander de fout maakte
  Duels      50/50 ±0,03 · eerder/later bij de bal ±0,02 · whiff −0,04 (zonder kans) · demo +0,05 / −0,03
  Kickoffs   kickoff-50/50 gewonnen/verloren ±0,06
  Balbezit   betrokkenheid (+0,01 per touch en per seconde in balbezit), alleen voor het onderdeelcijfer
  Balacties  alleen als straf: 0,5 × de waarde van een touch die de situatie slechter maakt (balverlies, gevaarlijke
             balbehandeling), met het dreigingsmodel (kern/verdediging.py): (eigen dreiging erna − ervoor) +
             (dreiging tegenstander ervoor − erna). Pakt ballchasers aan. Positieve touch-waarden tellen niet: te ruisig.
             Schoten, reddingen en gecreëerde kansen hebben een eigen waarde en tellen hier niet.
Verwachting = wat een gemiddelde Champion in dezelfde speeltijd oplevert. Getoetst op 196 spelers in 49 Champion-
wedstrijden tegen blinde analistencijfers (14 okt): per tijd r 0,85 / zelfde MVP 38 van 49; per balcontact (straft
betrokken spelers) r 0,74–0,80; positieve touch-waarden meetellen maakte het slechter.
Per onderdeel → z-score → cijfer per onderdeel.

Totaalcijfer in twee lagen (DELEN):
  Doelbijdrage  alles wat direct met goals te maken heeft (schoten, goals, gemiste kansen, assists, xA, reddingen,
                fouten, tegengoals), in één munt vergeleken: een goal weegt dus altijd zwaarder dan een assist.
  Proces        passes, duels en kickoffs, elk tegen de eigen norm (anders verdwijnen ze naast goals).
rating = 6,5 + 1,0 · gewogen z, begrensd op 3,0–10,0.
Spreiding = die van een hele wedstrijd (minstens 300 s): elke actie weegt in elke minuut even zwaar.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

WORTEL = Path(__file__).resolve().parent.parent
NORM_PAD = WORTEL / "data" / "modellen" / "rating_norm.json"
ONDERDELEN = ["Schieten", "Passen", "Verdedigen", "Duels", "Kickoffs", "Balbezit"]
BASIS, SCHAAL, MIN, MAX = 6.5, 1.0, 3.0, 10.0  # schaal 1,0: ~80% van de Champions tussen 5,3 en 8,3; 8+ is bijzonder
START_NA = 60  # seconden speeltijd voordat er een cijfer getoond wordt
# Terugval als er nog geen benchmark-normen zijn (ruwe schatting; per 5 min, gemiddeld en spreiding)
STANDAARD_NORM = {"totaal": {"gem": 0.9, "sd": 0.55}, **{o: {"gem": 0.15, "sd": 0.12} for o in ONDERDELEN},
                  "Doelbijdrage": {"gem": 2.2, "sd": 1.5}, "Passen_proces": {"gem": 0.1, "sd": 0.1}}
# Totaalcijfer: doelbijdrage in één munt + procesonderdelen elk t.o.v. de eigen norm
# (balacties tellen in de doelbijdrage: dezelfde munt als goals, dus Balbezit is geen apart deel meer)
DELEN = {"Doelbijdrage": 0.65, "Passen_proces": 0.12, "Duels": 0.14, "Kickoffs": 0.09}


def sleutel(pid):
    if not pid:
        return None
    (k, v), = pid.items()
    return f"{k}:{v}"


GROTE_KANS = 0.35


def acties(events: list[dict], schoten: list[dict], passen: list[dict], team: dict[str, int], kansen: dict | None = None) -> list[tuple]:
    """→ [(tijd, speler, onderdeel, impact, omschrijving)] gesorteerd op tijd. kansen = data['kansen'] (kern/kansen.py)."""
    uit = []
    kansen = kansen or {}
    team_goals = [(e["meta"]["timing"].get("time", 0), 0 if e["meta"].get("team_is_team_0") else 1) for e in events if e["meta"]["stream"] == "goal_context"]

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
        elif xg >= GROTE_KANS and not any(gt == team.get(s["speler"]) and s["tijd"] < g <= s["tijd"] + 4 for g, gt in team_goals):
            voeg(s["tijd"] + 0.01, s["speler"], "Schieten", -0.5 * xg, f"Grote kans gemist (xG {xg:.2f})")
    kans_whiffs = [(k["tijd"], k["speler"]) for k in kansen.get("gemist", [])]
    for k in kansen.get("gemist", []):
        voeg(k["tijd"], k["speler"], "Schieten", -0.4 * k["kans_xg"], f"Kans gemist door whiff (kans-xG {k['kans_xg']:.2f})")
    for c in kansen.get("creaties", []):
        voeg(c["tijd"], c["speler"], "Passen", 0.3 * c["xg"], f"Kans gecreëerd (xA {c['xg']:.2f})", bijdrage=True)
    saves = [(_t, rating_sleutel) for _t, rating_sleutel in (
        ((e["payload"]["payload"] or {}).get("time", 0), sleutel((e["payload"]["payload"] or {}).get("player_id")))
        for e in events if e["meta"]["stream"] == "timeline" and ((e.get("payload") or {}).get("payload") or {}).get("kind") == "Save")]
    # Balacties (alleen straf): touches die de situatie slechter maken volgens het dreigingsmodel. Touches met een
    # eigen waarde (schot, redding, gecreëerde kans) slaan we over, anders telt hetzelfde moment dubbel.
    eigen_waarde = [(s["tijd"], s["speler"]) for s in schoten] + [(c["tijd"], c["speler"]) for c in kansen.get("creaties", [])]
    for x in kansen.get("verdediging", []):
        if "eigen_voor" not in x or any(s == x["speler"] and abs(st - x["tijd"]) < 0.6 for st, s in saves) \
                or any(s == x["speler"] and abs(st - x["tijd"]) < 0.15 for st, s in eigen_waarde):
            continue
        v = (x["eigen_na"] - x["eigen_voor"]) + (x["voor"] - x["na"])
        if v > -0.01:
            continue  # alleen touches die het slechter maken tellen (zie docstring)
        if x["voor"] >= x["eigen_voor"]:  # verdedigende situatie
            voeg(x["tijd"], x["speler"], "Verdedigen", 0.5 * v,
                 f"Gevaarlijke balbehandeling (dreiging {100 * x['voor']:.0f}% → {100 * x['na']:.0f}%)")
        else:
            voeg(x["tijd"], x["speler"], "Balbezit", 0.5 * v,
                 f"Balverlies (kans {100 * x['eigen_voor']:.0f}% → {100 * x['eigen_na']:.0f}%, tegenstander {100 * x['na']:.0f}%)", bijdrage=True)
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
            # Winnaar staat in winning_team_is_team_0 (possession_team_is_team_0 = wie daarna de bal had; was een bug)
            winnaar0 = pl.get("winning_team_is_team_0")
            if winnaar0 is None or not p0 or not p1:
                continue
            (w, v) = (p0, p1) if winnaar0 else (p1, p0)
            if pl.get("is_kickoff"):  # kickoff = de 50/50 op de middenstip (de kickoff-stroom mist er soms een)
                voeg(t, w, "Kickoffs", 0.06, "Kickoff gewonnen"); voeg(t, v, "Kickoffs", -0.06, "Kickoff verloren")
            else:
                voeg(t, w, "Duels", 0.03, "50/50 gewonnen"); voeg(t, v, "Duels", -0.03, "50/50 verloren")
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
            # Betrokkenheid en controle, alleen voor het onderdeelcijfer Balbezit (geen deel van het totaal): zonder dit
            # bestond Balbezit alleen uit balverlies-straffen en scoorde wie veel aan de bal is juist laag.
            n, duur = pl.get("touch_count") or 0, pl.get("duration") or 0
            if n >= 2:
                voeg(pl.get("end_time", t), sleutel(pl.get("player_id")), "Balbezit", 0.01 * n + 0.01 * duur,
                     f"Balbezit ({n} touches, {duur:.1f} s)", bijdrage=False)
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


# Live verloop (14 okt, feedback gebruiker: "je verliest steeds punten, een 10 haal je alleen als je aan het eind scoort"):
# - Verwachting: AANDEEL_TIJD per speeltijd, de rest per balcontact. Per balcontact geeft een vlakkere lijn, maar
#   straft betrokken spelers; getoetst tegen analisten won volledig per tijd (zie docstring bovenaan).
# - Spreiding van een hele wedstrijd (minstens 300 s) in plaats van √(gespeelde tijd): een goal in minuut 1 weegt even
#   zwaar als in minuut 5, dus geen vroege 10 die daarna wegzakt.
# - Zachte grenzen: boven 9 en onder 4 wordt het steeds moeilijker, maar geen hard plafond.
AANDEEL_TIJD = 1.0  # 14 okt: getoetst tegen analisten, per tijd het best (zie docstring); 0 = volledig per balcontact


def verwacht(n: dict, speeltijd: float, touches: float | None = None, touch_norm: float | None = None) -> float:
    tijd = speeltijd / 300
    if touches is None or not touch_norm:
        return n["gem"] * tijd
    return n["gem"] * (AANDEEL_TIJD * tijd + (1 - AANDEEL_TIJD) * touches / touch_norm)


def zacht(r: float) -> float:
    if r > 9:
        r = 9 + (1 - math.exp(-(r - 9)))
    elif r < 4:
        r = 4 - (1 - math.exp(-(4 - r)))
    return round(min(MAX, max(MIN, r)), 2)


def z_score(impact: float, speeltijd: float, n: dict, touches: float | None = None, touch_norm: float | None = None) -> float:
    spreiding = max(1e-6, n["sd"] * math.sqrt(max(speeltijd, 300) / 300))
    return (impact - verwacht(n, speeltijd, touches, touch_norm)) / spreiding


def cijfer(impact: float, speeltijd: float, n: dict, touches: float | None = None, touch_norm: float | None = None) -> float:
    return zacht(BASIS + SCHAAL * z_score(impact, speeltijd, n, touches, touch_norm))


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


def totaal_cijfer(cum: dict, speeltijd: float, n: dict, touches: float | None = None) -> float:
    """cum = impact per deel (DELEN); touches = balcontacten van de speler tot nu toe."""
    tn = (n.get("touches") or {}).get("gem")
    z = sum(w * z_score(cum[d], speeltijd, n.get(d, STANDAARD_NORM[d]), touches, tn) for d, w in DELEN.items())
    z /= math.sqrt(sum(w * w for w in DELEN.values()))  # onafhankelijke delen → spreiding weer ~1
    return zacht(BASIS + SCHAAL * z)


def touch_tijden(events: list[dict]) -> dict[str, list[float]]:
    uit: dict[str, list[float]] = {}
    for e in events:
        if e["meta"]["stream"] == "touch":
            tm = e["meta"]["timing"]
            uit.setdefault(sleutel(e["meta"].get("primary_player")), []).append(tm.get("start_time", tm.get("time", 0)))
    return {k: sorted(v) for k, v in uit.items()}


def bereken(data: dict, events: list[dict], band: str | None = None) -> dict:
    team = {s["id"]: s["team"] for s in data["spelers"]}
    lijst = acties(events, data.get("schoten", []), data.get("passen", []), team, data.get("kansen"))
    speeltijd = speeltijd_functie(data["t"], data["klok"])
    n = norm(band)
    t_eind = data["t"][-1]
    uit = {"norm_band": band if NORM_PAD.exists() else None, "start_na": START_NA, "spelers": {}}
    tt = touch_tijden(events)
    tn = (n.get("touches") or {}).get("gem")
    import bisect
    for sid in team:
        mijn = [a for a in lijst if a[1] == sid]
        mijn_t = tt.get(sid, [])
        tijdlijn, cum, j = [], {d: 0.0 for d in DELEN}, 0
        stappen = [t for t in data["t"][:: max(1, int(data.get("fps", 30) * 2))]] + [t_eind]  # elke ~2 s
        for t in stappen:
            while j < len(mijn) and mijn[j][0] <= t:
                d_ = deel(mijn[j]); cum[d_] = cum.get(d_, 0.0) + mijn[j][3]; j += 1
            st = speeltijd(t)
            if st >= START_NA:
                tijdlijn.append([round(t, 2), totaal_cijfer(cum, st, n, bisect.bisect_right(mijn_t, t) if tn else None)])
        totaal_tijd = speeltijd(t_eind)
        per_onderdeel = {o: round(sum(a[3] for a in mijn if a[2] == o), 3) for o in ONDERDELEN}
        uit["spelers"][sid] = {
            "eind": tijdlijn[-1][1] if tijdlijn else None,
            "impact": round(sum(a[3] for a in mijn), 3),
            "speeltijd": round(totaal_tijd),
            "onderdelen": {o: {"impact": v, "cijfer": cijfer(v, totaal_tijd, n.get(o, STANDAARD_NORM[o]), len(mijn_t) if tn else None, tn)}
                           for o, v in per_onderdeel.items()},
            "tijdlijn": tijdlijn,
            "acties": [[a[0], a[2], a[3], a[4]] for a in mijn],
        }
    return uit
