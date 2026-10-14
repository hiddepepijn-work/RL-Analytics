"""Gedeelde vereenvoudigde RL-physics: balbaan en aankomsttijd van auto's.

Bewust simpel (geen ronde muren, geen balspin). Later te vervangen door RocketSim.
"""
from __future__ import annotations

import numpy as np

BAL_R = 92.75
ZWAARTEKRACHT = -650.0
MAX_AUTO = 2300.0
REACTIE = 0.25      # s voordat een speler reageert op een nieuwe balbaan
BEREIK = 150.0      # uu: bal + autoneus, je hoeft niet exact op het middelpunt te zijn


def baan(pos, vel, duur=3.0, dt=1 / 30):
    """Ballistische balbaan met stuiteren op vloer, plafond en zijmuren. → array [n, 4] (t, x, y, z)."""
    p, v = np.array(pos, float), np.array(vel, float)
    uit = np.empty((int(duur / dt), 4))
    for k in range(len(uit)):
        v[2] += ZWAARTEKRACHT * dt
        p += v * dt
        if p[2] < BAL_R:
            p[2] = BAL_R; v[2] = -v[2] * 0.6; v[:2] *= 0.95
        if p[2] > 2044 - BAL_R:
            p[2] = 2044 - BAL_R; v[2] = -v[2] * 0.6
        if abs(p[0]) > 4096 - BAL_R:
            p[0] = np.sign(p[0]) * (4096 - BAL_R); v[0] = -v[0] * 0.6
        if abs(p[1]) > 5120 - BAL_R and abs(p[0]) > 893:
            p[1] = np.sign(p[1]) * (5120 - BAL_R); v[1] = -v[1] * 0.6
        uit[k] = ((k + 1) * dt, *p)
    return uit


def aankomst(auto_pos, auto_vel, boost, punten):
    """Geschatte tijd (s) waarop een auto bij elk baanpunt kan zijn.

    Model: reactietijd + afstand / effectieve snelheid. Effectieve snelheid hangt af van boost
    (met boost haal je sneller supersonic) en van hoe hoog de bal is (hoge ballen vragen een aerial).
    Huidige snelheid in de goede richting telt mee als voorsprong.
    """
    rel = punten[:, 1:4] - auto_pos[None, :]
    afstand = np.maximum(np.linalg.norm(rel, axis=1) - BEREIK, 0)
    richting = rel / np.maximum(np.linalg.norm(rel, axis=1, keepdims=True), 1)
    v_mee = np.clip(richting @ auto_vel, 0, MAX_AUTO)
    v_eff = (1750 if boost > 25 else 1350) * np.ones(len(punten))
    v_eff = np.maximum(v_eff, 0.5 * v_eff + 0.5 * v_mee)
    hoog = punten[:, 3] > 350
    if boost < 20:
        v_eff[hoog] *= 0.35  # zonder boost nauwelijks een aerial
    else:
        v_eff[hoog] *= 0.8
    return REACTIE + afstand / v_eff
