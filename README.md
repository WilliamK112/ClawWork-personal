# ClawWork

A production-oriented AI coworker platform for **task execution benchmarking**, **economic tracking**, and **paper-trading agent operations**.

This repository is configured for:
- LiveBench-style agent evaluation loops
- Multi-agent paper trading orchestration (Alpaca paper only)
- Frontend dashboard + FastAPI backend
- Long-running deployment with systemd (Oracle Ubuntu ARM)

---

## Why this project

ClawWork is designed to answer a practical question:

> Can autonomous agents produce useful work continuously while staying cost-aware and operationally safe?

To support that, the system combines:
- task execution + artifact generation
- quality and economic accounting
- real-time monitoring UI
- strict paper-trading safeguards for financial experiments

---

## Core capabilities

### 1) Agent work/economic loop
- Task assignment, execution, logging, and result storage
- Cost tracking (token/runtime) and balance updates
- Longitudinal performance history in local data store

### 2) Dashboard + API
- FastAPI backend (`livebench.api.server`)
- React/Vite frontend (`frontend/`)
- Leaderboard, agent status, task history, terminal logs, artifacts

### 3) Paper trading tournament (safe mode)
- Worker process: `livebench.trading.paper_tournament`
- Multi-agent account mapping via config
- Active roster control via `active_trading_agents.json`
- Paper-only guarded trade endpoint

### 4) Deployment-ready operations
- systemd services for API and worker
- health checks and quick restart/log commands
- optional nginx reverse proxy + HTTPS script

---

## Project structure

```text
ClawWork/
├─ livebench/
│  ├─ api/                 # FastAPI endpoints
│  ├─ trading/             # paper_tournament, Alpaca client
│  ├─ configs/             # active agents, account mappings
│  └─ data/                # runtime data (local)
├─ frontend/               # React dashboard (Vite)
├─ deploy/oracle/          # Oracle ARM deploy scripts + systemd units
├─ scripts/                # utility scripts (static generation, checks)
└─ README.md
```

---

## Quick start (local)

### Prerequisites
- Python 3.10+
- Node.js 20+
- npm

### 1) Backend setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2) Frontend setup

```bash
cd frontend
npm install
cd ..
```

### 3) Environment

Create `.env` at repo root:

```env
# Core
OPENAI_API_KEY=...

# Alpaca paper only
ALPACA_API_KEY_ID=...
ALPACA_API_SECRET_KEY=...
ALPACA_BASE_URL=https://paper-api.alpaca.markets
ALPACA_DATA_BASE_URL=https://data.alpaca.markets
LIVEBENCH_ALLOW_SIM_FALLBACK=0
```

### 4) Run services locally

```bash
# API
python -m livebench.api.server

# Worker (separate terminal)
python -m livebench.trading.paper_tournament --interval 15 --cooldown 20

# Frontend (separate terminal)
cd frontend && npm run dev
```

Open: `http://127.0.0.1:3000`

---

## Trading safety controls

This repo is configured for **paper-trading only** by default.

Implemented safeguards include:
- `ALPACA_BASE_URL` defaulting to paper endpoint
- `/api/alpaca/paper-order` rejects non-paper base URLs
- active trading roster filter to prevent accidental multi-agent interference

Active roster config:
- `livebench/configs/active_trading_agents.json`

Per-agent account map:
- `livebench/configs/alpaca_agent_accounts.json`

> Never commit real keys/secrets to public repositories.

---

## Oracle deployment (systemd)

Deployment bundle is under:
- `deploy/oracle/`

Includes:
- `setup-oracle.sh`
- `install-services.sh`
- `healthcheck.sh`
- systemd units for API + tournament worker
- optional nginx + HTTPS helper

Typical flow:

```bash
bash /opt/clawwork/deploy/oracle/setup-oracle.sh
sudo -u claw nano /opt/clawwork/.env
sudo bash /opt/clawwork/deploy/oracle/install-services.sh
bash /opt/clawwork/deploy/oracle/healthcheck.sh
```

---

## Frontend deployment

### Vercel
`frontend/vercel.json` is configured for SPA rewrites.

Deploy from `frontend/`:

```bash
vercel --prod
```

### Static mode
A static data generator is available:

```bash
python3 scripts/generate_static_data.py
cd frontend && VITE_STATIC_DATA=true npm run build
```

---

## UI/quality checks

From `frontend/`:

```bash
npm run audit:ui       # static wiring checks (buttons/routes)
npm run smoke:buttons  # runtime click smoke test
npm run build
```

CI workflow includes UI audit + route smoke checks before deploy.

---

## Professional usage notes

This repository can be used in two modes:
1. **Benchmark/research mode**: evaluate agent quality/cost/survival
2. **Operational mode**: run a constrained set of paper-trading agents continuously

For production-like usage, keep code and runtime data separated:
- commit code/config/docs
- exclude logs, large artifacts, backup snapshots, and private keys

---

## Author and Portfolio

This project is by [William Kang (Ching-Wei Kang)](https://williamkang.com/about-william-kang.html), a UW-Madison Computer Science and Data Science student building AI products, backend systems, and developer tools.

See the William Kang official profile at [williamkang.com/william-kang.html](https://williamkang.com/william-kang.html).

See the exact-name identity page at [williamkang.com/ching-wei-kang.html](https://williamkang.com/ching-wei-kang.html).

See the canonical project profile at [williamkang.com/william-kang-projects.html](https://williamkang.com/william-kang-projects.html).
## License

MIT License (see `LICENSE`).
