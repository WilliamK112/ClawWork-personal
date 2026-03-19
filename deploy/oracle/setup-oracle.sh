#!/usr/bin/env bash
set -euo pipefail

APP_USER="claw"
APP_DIR="/opt/clawwork"

sudo apt update
sudo apt install -y git curl build-essential python3 python3-venv python3-pip nginx

# Node 20
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs

# app user + dir
sudo useradd -m -s /bin/bash "${APP_USER}" || true
sudo mkdir -p "${APP_DIR}"
sudo chown -R "${APP_USER}:${APP_USER}" "${APP_DIR}"

if [ ! -d "${APP_DIR}/.git" ]; then
  echo "[ERROR] Repo not present in ${APP_DIR}. Clone it first:" >&2
  echo "  sudo -u ${APP_USER} git clone <YOUR_REPO_URL> ${APP_DIR}" >&2
  exit 1
fi

sudo -u "${APP_USER}" bash <<'EOF'
set -euo pipefail
cd /opt/clawwork

python3 -m venv livebench/.venv
source livebench/.venv/bin/activate

pip install --upgrade pip
pip install -r livebench/requirements.txt || true
pip install fastapi uvicorn requests python-dotenv

cd frontend
npm install
npm run build
EOF

if [ ! -f "${APP_DIR}/.env" ]; then
  sudo -u "${APP_USER}" cp "${APP_DIR}/deploy/oracle/.env.example" "${APP_DIR}/.env"
  echo "[INFO] Created ${APP_DIR}/.env from template. Please edit with real keys."
fi

echo "[OK] Server bootstrap complete. Next: sudo bash /opt/clawwork/deploy/oracle/install-services.sh"
