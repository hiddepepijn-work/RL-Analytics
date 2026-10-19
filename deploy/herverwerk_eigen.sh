#!/usr/bin/env bash
# Eigen wedstrijden + testreplays opnieuw verwerken (na een wijziging in parser/rating) en profiel bijwerken.
# Draaien op de server als rlanalytics vanuit /srv/rl-analytics.
export PYTHONIOENCODING=utf-8
P=.venv/bin/python
# Eerst de subrank schatten uit de huidige verwerkte wedstrijden: de ratings hieronder gebruiken die norm
nice -n 10 $P -m kern.subrank --account Sand || true
[ "$1" = "--vanaf-apart" ] || nice -n 10 $P -m kern.parseer data/eigen/mee/*.replay --rank champion --ik Sand --categorie mee
nice -n 10 $P -m kern.parseer data/eigen/apart/*.replay --rank champion --ik Sand --categorie apart
nice -n 10 $P -m kern.parseer data/replays/*.replay
nice -n 10 $P -m kern.profiel --naam Sand
echo HERVERWERKT-KLAAR
