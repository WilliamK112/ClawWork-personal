#!/usr/bin/env bash
set -euo pipefail

echo "== API health =="
curl -fsS http://127.0.0.1:8000/api/alpaca/health

echo "\n== Active agents =="
curl -fsS http://127.0.0.1:8000/api/agents

echo "\n== Service status =="
systemctl --no-pager --full status clawwork-api | sed -n '1,20p'
systemctl --no-pager --full status clawwork-tournament | sed -n '1,20p'

echo "\n[OK] healthcheck finished"
