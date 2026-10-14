# RL Analytics

Rocket League-analyse naar het voorbeeld van voetbal-analytics: elke wedstrijd in 3D nagebouwd, met eigen modellen voor **xG** (verwachte goals) en **xPass**, ~100 stats in 12 onderdelen, een **live wedstrijdcijfer** per speler en een spelerprofiel tegenover je eigen rank.

- **Wedstrijd:** 3D-replay, momentum, schotkaart (cirkel = xG), xG-verloop, rating-verloop, doelpunten met context
- **Ratings:** elke actie geeft plus- of minpunten; het cijfer (3–10, 6,5 = rank-gemiddelde) beweegt live mee vanaf 1 minuut speeltijd; cijfer per onderdeel
- **Profiel:** je gemiddelde over je eigen wedstrijden, percentielen t.o.v. Champion (bootstrap), vorm, heatmap, afwerking boven verwachting
- **Modellen:** eerlijk gevalideerd per wedstrijd (GroupKFold), kalibratie, per rank een eigen model als dat beter is
- **Uitleg:** elke stat heeft een ⓘ-uitleg (wat, hoe gemeten, hoger of lager beter)

## Onderdelen

| Pad | Wat |
|---|---|
| `kern/` | Python: parser (subtr-actor), stats, xG/xPass, rating, benchmarks, downloader, updater |
| `app/` | Webapp (Vite + Three.js), stijl "Arena" |
| `desktop/` | Electron-app: venster + automatisch inloggen + systeemvak; stuurt nieuwe replays door naar de server |
| `deploy/` | Server: systemd-diensten, Caddy-voorbeeld, installatie- en synchronisatiescripts |
| `ontwerp/` | Logo's en het script dat de app-iconen maakt |

Data (`data/`), wachtwoorden (`toegang.txt`) en de ballchasing-token (`.env`) staan **niet** in git.

## Lokaal draaien

```powershell
uv sync
uv run python -m kern.parseer data/replays/*.replay --rank champion   # replays verwerken
cd app; npm install; npm run dev                                      # http://localhost:8799
```

## Pijplijn

```
ballchasing (per rank) ─► kern.downloader ─► data/replays/<band>/
                                              │
kern.bijwerken (elk uur): schoten + passes (cache) ─► xG / xPass trainen (per rank) ─► data/modellen/
eigen replay (desktop-app) ─► server-inbox ─► kern.eigen_watcher ─► parser + rating ─► kern.profiel
```

## Server (VPS)

```bash
ssh ubuntu@<vps> 'sudo bash -s' < deploy/installeer.sh     # idempotent; Caddy wordt eerst gevalideerd
uv run python deploy/sync_naar_vps.py                        # data hervatbaar overzetten
```

Diensten: `rl-downloader`, `rl-bijwerken`, `rl-inbox`, samen begrensd in `rl-analytics.slice`.

## Valkuilen

- Assen: replay is Unreal (links-handig, z omhoog) → Three: `(x, z, y)`, quaternion `(-qx, -qz, -qy, qw)`.
- Ontbrekende frames komen als `(0,0,0)` uit de parser → verbergen.
- `get_stats_events` kost ~8 s per replay → `kern/events.py` cachet de benodigde stromen.
- Ballchasing filtert rank niet streng → `kern/ballchasing.py` controleert de hele lobby zelf.
- Oude replays missen `TotalSecondsPlayed` → duur uit `NumFrames / RecordFPS`.
- Electron vanuit de VS Code-terminal: `ELECTRON_RUN_AS_NODE=1` laat de app crashen.
