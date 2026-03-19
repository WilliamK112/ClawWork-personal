#!/usr/bin/env bash
set -euo pipefail

APP_DIR="/opt/clawwork"

sudo install -m 0644 "${APP_DIR}/deploy/oracle/nginx/clawwork.conf" /etc/nginx/sites-available/clawwork.conf
sudo ln -sf /etc/nginx/sites-available/clawwork.conf /etc/nginx/sites-enabled/clawwork.conf
sudo rm -f /etc/nginx/sites-enabled/default

sudo nginx -t
sudo systemctl enable --now nginx
sudo systemctl reload nginx

echo "[OK] Nginx configured"
echo "Try: curl -I http://127.0.0.1/"
