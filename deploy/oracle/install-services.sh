#!/usr/bin/env bash
set -euo pipefail

APP_DIR="/opt/clawwork"

sudo install -m 0644 "${APP_DIR}/deploy/oracle/systemd/clawwork-api.service" /etc/systemd/system/clawwork-api.service
sudo install -m 0644 "${APP_DIR}/deploy/oracle/systemd/clawwork-tournament.service" /etc/systemd/system/clawwork-tournament.service

sudo systemctl daemon-reload
sudo systemctl enable --now clawwork-api
sudo systemctl enable --now clawwork-tournament

echo "[OK] Services enabled and started"
systemctl --no-pager --full status clawwork-api | sed -n '1,20p'
systemctl --no-pager --full status clawwork-tournament | sed -n '1,20p'
