# ClawWork on Oracle Free (Ubuntu 22.04 ARM)

This deploy bundle keeps **paper trading only** and runs two long-lived services via `systemd`:

- `livebench.api.server`
- `livebench.trading.paper_tournament`

## 0) Oracle Console

Create ARM Ubuntu 22.04 instance (prefer 2 OCPU / 12 GB if available).

Open inbound ports in Security List / NSG:

- `22` (SSH)
- `8000` (API)
- `3000` (frontend, optional)

## 1) Bootstrap server

```bash
ssh ubuntu@<PUBLIC_IP>
curl -fsSL https://raw.githubusercontent.com/<YOUR_FORK_OR_REPO>/main/deploy/oracle/setup-oracle.sh | bash
```

If not using raw GitHub, copy `setup-oracle.sh` to server and run:

```bash
bash setup-oracle.sh
```

## 2) Configure `.env`

```bash
sudo -u claw cp /opt/clawwork/.env.example /opt/clawwork/.env
sudo -u claw nano /opt/clawwork/.env
```

Set paper keys and keep fallback disabled by default:

- `ALPACA_BASE_URL=https://paper-api.alpaca.markets`
- `LIVEBENCH_ALLOW_SIM_FALLBACK=0`

## 3) Install and start systemd services

```bash
sudo bash /opt/clawwork/deploy/oracle/install-services.sh
```

## 4) Health checks

```bash
bash /opt/clawwork/deploy/oracle/healthcheck.sh
```

Expected: health endpoint returns an `ok/healthy`-style payload and `/api/agents` responds with your active agents.

## 5) Nginx reverse proxy (API + frontend)

```bash
sudo bash /opt/clawwork/deploy/oracle/install-nginx.sh
```

Optional HTTPS (after DNS A record points to this server):

```bash
sudo bash /opt/clawwork/deploy/oracle/enable-https.sh your.domain.com you@example.com
```

## 6) Common operations

```bash
# status
systemctl status clawwork-api --no-pager
systemctl status clawwork-tournament --no-pager
systemctl status nginx --no-pager

# logs
journalctl -u clawwork-api -f
journalctl -u clawwork-tournament -f

# restart
sudo systemctl restart clawwork-api
sudo systemctl restart clawwork-tournament
sudo systemctl reload nginx

# one-command update (pull + rebuild + restart + checks)
sudo bash /opt/clawwork/deploy/oracle/update.sh

# enable on boot
sudo systemctl enable clawwork-api clawwork-tournament nginx
```

## Notes

- Active leaderboard filtering is controlled by:
  - `livebench/configs/active_trading_agents.json`
- This setup intentionally avoids any live Alpaca endpoint.
