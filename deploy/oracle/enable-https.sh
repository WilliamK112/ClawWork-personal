#!/usr/bin/env bash
set -euo pipefail

if [ $# -lt 1 ]; then
  echo "Usage: $0 <domain> [email]"
  exit 1
fi

DOMAIN="$1"
EMAIL="${2:-}"

sudo apt update
sudo apt install -y certbot python3-certbot-nginx

if [ -n "$EMAIL" ]; then
  sudo certbot --nginx -d "$DOMAIN" --non-interactive --agree-tos -m "$EMAIL" --redirect
else
  sudo certbot --nginx -d "$DOMAIN" --non-interactive --agree-tos --register-unsafely-without-email --redirect
fi

echo "[OK] HTTPS enabled for $DOMAIN"
