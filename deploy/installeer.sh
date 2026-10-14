#!/usr/bin/env bash
# RL Analytics op de VPS installeren/bijwerken. Veilig om opnieuw te draaien.
# Gebruik (vanaf de pc):  ssh ubuntu@51.75.74.94 'sudo bash -s' < deploy/installeer.sh
# Verwacht: code + data al in /srv/rl-analytics, deploy-bestanden in /tmp/rl-deploy.
set -euo pipefail
D=/tmp/rl-deploy
INBOX=/var/lib/rl-analytics-inbox

# 1. Inbox voor eigen replays: ubuntu (scp vanaf de pc) schrijft, rlanalytics leest en ruimt op
install -d -o ubuntu -g rlanalytics -m 2775 "$INBOX"

# 2. Caddy mag de app en de data-JSON lezen (ACL; geen groepswijziging = geen Caddy-herstart nodig)
command -v setfacl >/dev/null || apt-get install -y acl >/dev/null
setfacl -m u:caddy:x /srv/rl-analytics /srv/rl-analytics/data /srv/rl-analytics/app
for m in /srv/rl-analytics/app/dist /srv/rl-analytics/data/verwerkt /srv/rl-analytics/data/modellen; do
  mkdir -p "$m"; chown rlanalytics:rlanalytics "$m"
  setfacl -R -m u:caddy:rX "$m"; setfacl -R -d -m u:caddy:rX "$m"
done

# 3. Systemd-diensten (begrensd in rl-analytics.slice)
cp "$D"/rl-analytics.slice "$D"/rl-*.service /etc/systemd/system/
systemctl daemon-reload

# 4. Caddy: eigen bestand + één import-regel; eerst valideren, bij fout terugzetten
cp /etc/caddy/Caddyfile "/etc/caddy/Caddyfile.voor-rl-analytics-$(date +%F-%H%M)"
cp "$D"/rl-analytics.caddy /etc/caddy/rl-analytics.caddy
grep -q '^import /etc/caddy/rl-analytics.caddy' /etc/caddy/Caddyfile || printf '\nimport /etc/caddy/rl-analytics.caddy\n' >> /etc/caddy/Caddyfile
if caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile >/dev/null 2>&1; then
  systemctl reload caddy
  echo "caddy: herladen"
else
  echo "caddy: VALIDATIE MISLUKT, oude configuratie terug" >&2
  cp "$(ls -t /etc/caddy/Caddyfile.voor-rl-analytics-* | head -1)" /etc/caddy/Caddyfile
  rm -f /etc/caddy/rl-analytics.caddy
  exit 1
fi

# 5. Diensten aan. De downloader alleen als er een ballchasing-token staat.
systemctl enable --now rl-bijwerken.service rl-inbox.service
if grep -q '^BALLCHASING_TOKEN=.\+' /srv/rl-analytics/.env 2>/dev/null; then
  systemctl enable --now rl-downloader.service
else
  echo "downloader: wacht op /srv/rl-analytics/.env met BALLCHASING_TOKEN"
fi
systemctl --no-pager --lines=0 status rl-bijwerken rl-inbox rl-downloader 2>/dev/null | grep -E "●|Active" || true
