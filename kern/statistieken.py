"""Wedstrijdstatistieken per speler en per team, uit subtr-actor's stat-modules + eigen frame-berekeningen.

Boost-bedragen staan in de replay op 0–255; alles wordt hier omgerekend naar 0–100 (zoals in-game).
Tijden worden ook als percentage van de actieve speeltijd gegeven, zodat spelers vergelijkbaar zijn.
"""
from __future__ import annotations

from collections import defaultdict

import numpy as np
import subtr_actor as sa

BOOST = 100 / 255
SPELER_STRIDE = 9
# Heatmap-raster: 24 vakken over de breedte (x), 30 over de lengte (y), daarna gladgestreken
HM_X, HM_Y = 24, 30
_KERN = np.array([1, 4, 6, 4, 1], dtype=float) / 16


def _glad(h: np.ndarray, keer: int = 2) -> np.ndarray:
    for _ in range(keer):
        h = np.apply_along_axis(lambda r: np.convolve(r, _KERN, mode='same'), 0, h)
        h = np.apply_along_axis(lambda r: np.convolve(r, _KERN, mode='same'), 1, h)
    return h


def sleutel(pid: dict | None) -> str | None:
    if not pid:
        return None
    (k, v), = pid.items()
    return f"{k}:{v}"


def _per_speler(module: dict) -> dict[str, dict]:
    return {sleutel(p["player_id"]): p["stats"] for p in module.get("player_stats") or []}


def _labels_som(entries: list, **filter_) -> float:
    tot = 0.0
    for e in entries:
        lab = {l["key"]: l["value"] for l in e["labels"]}
        if all(lab.get(k) == v for k, v in filter_.items()):
            tot += e.get("value", e.get("count", 0))
    return tot


def _r(v, d=1):
    return round(float(v), d) if v is not None else None


def bereken(pad: str, data: dict) -> dict:
    sm = sa.get_summed_stats(pad)["modules"]
    core, boost, pos = _per_speler(sm["core"]), _per_speler(sm["boost"]), _per_speler(sm["positioning"])
    rot, mov, touch = _per_speler(sm["rotation"]), _per_speler(sm["movement"]), _per_speler(sm["touch"])
    duel, whiff, demo = _per_speler(sm["fifty_fifty"]), _per_speler(sm["whiff"]), _per_speler(sm["demo"])
    pas, bump = _per_speler(sm["pass"]), _per_speler(sm["bump"])
    mech = {m: _per_speler(sm[m]) for m in ("wavedash", "half_flip", "speed_flip", "flick", "flip_reset", "air_dribble", "wall_aerial")}
    kick = _per_speler(sm["kickoff"])
    extra = {m: _per_speler(sm[m]) for m in ("center", "one_timer", "half_volley", "backboard", "controlled_play")}

    spelers = {}
    bal = np.array(data["bal"], dtype=float).reshape(-1, 7)
    bal_aanwezig = ~((bal[:, 0] == 0) & (bal[:, 1] == 0) & (bal[:, 2] == 0))

    for s in data["spelers"]:
        i = s["id"]
        c, b, p, r, m, t = (d.get(i, {}) for d in (core, boost, pos, rot, mov, touch))
        du, wh, de, pa, bu, ki = (d.get(i, {}) for d in (duel, whiff, demo, pas, bump, kick))
        acties = defaultdict(int)
        for e in (t.get("labeled_action_counts") or {}).get("entries", []):
            acties[{l["key"]: l["value"] for l in e["labels"]}.get("action")] += e["count"]
        ex = {m: extra[m].get(i, {}) for m in extra}
        actief = p.get("active_game_time") or m.get("tracked_time") or 1
        pct = lambda v: _r(100 * (v or 0) / actief)

        f = np.array(s["frames"], dtype=float).reshape(-1, SPELER_STRIDE)
        hier = ~((f[:, 0] == 0) & (f[:, 1] == 0) & (f[:, 2] == 0)) & bal_aanwezig
        afst_bal = np.linalg.norm(f[hier, :3] - bal[hier, :3], axis=1)
        maten = [o for o in data["spelers"] if o["team"] == s["team"] and o["id"] != i]
        afst_maat = []
        for o in maten:
            g = np.array(o["frames"], dtype=float).reshape(-1, SPELER_STRIDE)
            ok = hier & ~((g[:, 0] == 0) & (g[:, 1] == 0))
            afst_maat.append(np.linalg.norm(f[ok, :2] - g[ok, :2], axis=1).mean() if ok.any() else np.nan)

        # Heatmap: altijd vanuit eigen doel → vijandelijk doel (oranje spiegelen)
        xy = f[hier, :2] * (1 if s["team"] == 0 else -1)
        hm, _, _ = np.histogram2d(xy[:, 0], xy[:, 1], bins=[HM_X, HM_Y], range=[[-4096, 4096], [-5120, 5120]])
        hm = _glad(hm)
        hm = hm / max(hm.sum(), 1e-9) * 100

        spelers[i] = {
            "aanval": {
                "goals": c.get("goals", 0), "assists": c.get("assists", 0), "schoten": c.get("shots", 0),
                "saves": c.get("saves", 0), "score": c.get("score", 0),
                "schotrendement": _r(100 * c.get("goals", 0) / c["shots"]) if c.get("shots") else None,
                "harde_schoten": t.get("hard_hit_count", 0),
                "one_timers": ex["one_timer"].get("count", 0), "half_volleys": ex["half_volley"].get("count", 0),
                "backboards": ex["backboard"].get("count", 0),
                "schoten_per_5": _r(c.get("shots", 0) / actief * 300, 2),
            },
            "passen": {
                "assists": c.get("assists", 0),
                "passes": pa.get("completed_pass_count", 0), "passes_ontvangen": pa.get("received_pass_count", 0),
                "centers": ex["center"].get("count", 0),
                "pass_afstand_m": _r(pa.get("total_pass_distance", 0) / 100, 0),
                "pass_winst_m": _r(pa.get("total_pass_advance", 0) / 100, 0),
            },
            "verdedigen": {
                "saves": c.get("saves", 0), "clears": acties.get("clear", 0),
                "achter_bal_pct": pct(p.get("time_behind_ball")),
                "schaduw_pct": pct(p.get("time_shadow_defense")),
                "tegengoal_als_laatste_man": c.get("goals_conceded_while_last_defender", 0),
                "tegengoal_te_ver_voor": c.get("caught_ahead_of_play_on_conceded_goals", 0),
            },
            "balbezit": {
                "touches": t.get("touch_count", 0), "eerste_touches": t.get("first_touch_count", 0),
                "controle_touches": t.get("control_touch_count", 0), "lucht_touches": t.get("aerial_touch_count", 0),
                "hoge_lucht_touches": t.get("high_aerial_touch_count", 0), "muur_touches": t.get("wall_touch_count", 0),
                "bezit_pct": pct(p.get("time_has_possession")),
                "controle_tijd": _r(ex["controlled_play"].get("total_time", 0), 1),
                "bal_vooruit_m": _r((t.get("total_ball_advance_distance", 0) - t.get("total_ball_retreat_distance", 0)) / 100, 0),
            },
            "duels": {
                "5050_gewonnen": du.get("wins", 0), "5050_verloren": du.get("losses", 0), "5050_gelijk": du.get("neutral_outcomes", 0),
                "kickoffs_gewonnen": du.get("kickoff_wins", 0), "kickoffs_verloren": du.get("kickoff_losses", 0),
                "whiffs": wh.get("whiff_count", 0), "te_laat_bij_bal": wh.get("beaten_to_ball_count", 0),
                "demos_gemaakt": de.get("demos_inflicted", 0), "demos_gekregen": de.get("demos_taken", 0),
                "bumps": bu.get("bumps_inflicted", 0),
            },
            "boost": {
                "verzameld": _r(b.get("amount_collected", 0) * BOOST, 0), "gebruikt": _r(b.get("amount_used", 0) * BOOST, 0),
                "gestolen": _r(b.get("amount_stolen", 0) * BOOST, 0),
                "per_minuut": _r(b.get("amount_used", 0) * BOOST / actief * 60, 0),
                "gemiddeld": _r(b.get("boost_integral", 0) * BOOST / (b.get("tracked_time") or actief), 0),
                "grote_pads": b.get("big_pads_collected", 0), "kleine_pads": b.get("small_pads_collected", 0),
                "grote_gestolen": b.get("big_pads_stolen", 0), "kleine_gestolen": b.get("small_pads_stolen", 0),
                "supersonic_verbruik": _r(b.get("amount_used_while_supersonic", 0) * BOOST, 0),
                "overvol": _r(b.get("overfill_total", 0) * BOOST, 0),
                "tijd_0_pct": pct(b.get("time_zero_boost")), "tijd_100_pct": pct(b.get("time_hundred_boost")),
                "banden_pct": [pct(b.get(k)) for k in ("time_boost_0_25", "time_boost_25_50", "time_boost_50_75", "time_boost_75_100")],
            },
            "positie": {
                "derden_pct": [pct(p.get(k)) for k in ("time_defensive_third", "time_neutral_third", "time_offensive_third")],
                "achter_bal_pct": pct(p.get("time_behind_ball")), "voor_bal_pct": pct(p.get("time_in_front_of_ball")),
                "meest_achter_pct": pct(p.get("time_most_back")), "meest_voor_pct": pct(p.get("time_most_forward")),
                "dichtst_bij_bal_pct": pct(p.get("time_closest_to_ball_team")),
                "schaduwverdediging_pct": pct(p.get("time_shadow_defense")),
                "afstand_bal": _r(afst_bal.mean() if afst_bal.size else None, 0),
                "afstand_teamgenoot": _r(np.nanmean(afst_maat) if afst_maat else None, 0),
                "heatmap": [[_r(v, 2) for v in kol] for kol in hm],
            },
            "rotatie": {
                "rollen_pct": [pct(r.get(k)) for k in ("time_first_man", "time_second_man", "time_third_man")],
                "eerste_man_wissels": r.get("became_first_man_count", 0),
            },
            "beweging": {
                "gem_snelheid": _r((m.get("speed_integral", 0) / (m.get("tracked_time") or 1)), 0),
                "afstand_km": _r(m.get("total_distance", 0) / 100000, 2),
                "supersonic_pct": pct(m.get("time_supersonic_speed")),
                "grond_pct": pct(m.get("time_on_ground")), "laag_lucht_pct": pct(m.get("time_low_air")), "hoog_lucht_pct": pct(m.get("time_high_air")),
                "powerslides": _per_speler(sm["powerslide"]).get(i, {}).get("press_count", 0),
            },
            "mechanics": {k: mech[k].get(i, {}).get("count", 0) for k in mech} | {
                "speedflip_kwaliteit": _r(mech["speed_flip"].get(i, {}).get("cumulative_quality", 0) / mech["speed_flip"][i]["count"], 2)
                if mech["speed_flip"].get(i, {}).get("count") else None,
                "kickoff_cheats": ki.get("support_cheats", 0), "kickoff_fakes": ki.get("fakes", 0),
            },
            "speeltijd": _r(actief, 0),
        }

    # Teamniveau: balbezit en terreindruk uit de gelabelde tijden
    bezit = sm["possession"]["stats"]["labeled_time"]["entries"]
    druk = sm["territorial_pressure"]["stats"]["labeled_time"]["entries"]
    bez = [_labels_som(bezit, possession_state=t) for t in ("team_zero", "team_one")]
    drk = [_labels_som(druk, pressure_team=t) for t in ("team_zero", "team_one")]
    teams = []
    for k, naam in enumerate(("team_zero", "team_one")):
        tc = sm["core"][naam]
        teams.append({
            "bezit_pct": _r(100 * bez[k] / (sum(bez) or 1)),
            "druk_pct": _r(100 * drk[k] / (sum(drk) or 1)),
            "goals_opbouw": {o: tc.get(f"{o}_goal_count", 0) for o in ("counter_attack", "sustained_pressure", "kickoff", "other_buildup")},
            "passes": sm["pass"][naam].get("completed_pass_count", 0),
        })

    # Boost-pickups (plek, team, groot/klein, gestolen) voor de padkaart
    pickups = [[_r(e["player_position"][0], 0), _r(e["player_position"][1], 0), 0 if e["is_team_0"] else 1,
                1 if e["pad_type"] == "big" else 0, 1 if e["is_steal"] else 0, sleutel(e["player_id"])]
               for e in sm["boost"]["pickup_events"] if e.get("activity") == "active"]

    # Goal-context: wie stond waar en met hoeveel boost
    goals = []
    for g in sm["core"].get("goal_context", []):
        goals.append({
            "balsnelheid": _r(g["ball_speed_at_goal"] * 0.036, 0),  # uu/s → km/h
            "luchttijd": _r(g.get("ball_air_time_before_goal"), 1), "opbouw": g.get("goal_buildup"),
            "laatste_man": sleutel(g.get("defending_team_most_back_player")),
        })
    return {"spelers": spelers, "teams": teams, "pickups": pickups, "goals": goals}
