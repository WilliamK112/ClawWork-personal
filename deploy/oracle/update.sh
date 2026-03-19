#!/usr/bin/env bash
set -euo pipefail

APP_DIR="/opt/clawwork"
APP_USER="claw"

cd "$APP_DIR"

sudo -u "$APP_USER" git fetch --all --prune
sudo -u "$APP_USER" git pull --ff-only

sudo -u "$APP_USER" bash <<'EOF'
set -euo pipefail
cd /opt/clawwork
source livebench/.venv/bin/activate
pip install -r livebench/requirements.txt || true
pip install fastapi uvicorn requests python-dotenv
cd frontend
npm install
npm run build
EOF

sudo systemctl restart clawwork-api
sudo systemctl restart clawwork-tournament
sudo systemctl reload nginx || true

echo "== quick checks =="
curl -fsS http://127.0.0.1:8000/api/alpaca/health
curl -fsS http://127.0.0.1:8000/api/agents

echo "[OK] update complete"
