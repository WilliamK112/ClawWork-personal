#!/usr/bin/env python3
"""
Paper trading tournament loop for 10 strategy agents.

- Each agent starts with virtual $10 bankroll.
- Orders are sent to Alpaca PAPER account (qty=1, market orders).
- If an agent busts (net worth <= bust threshold), it is reset to $10 and mutated.
- Keeps logs under livebench/data/agent_data/STRAT_*/

Run:
  PYTHONPATH=. python -m livebench.trading.paper_tournament --interval 30
"""

from __future__ import annotations

import argparse
import json
import os
import random
import time
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from dotenv import load_dotenv

from livebench.trading.alpaca_client import AlpacaClient, AlpacaConfig

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")

DATA_DIR = ROOT / "livebench" / "data"
AGENT_DATA_DIR = DATA_DIR / "agent_data"
TOURNAMENT_STATE_PATH = DATA_DIR / "trading_tournament_state.json"
AGENT_ACCOUNTS_PATH = ROOT / "livebench" / "configs" / "alpaca_agent_accounts.json"
ACTIVE_TRADING_AGENTS_PATH = ROOT / "livebench" / "configs" / "active_trading_agents.json"


SYMBOL_UNIVERSE = [
    "F", "SOFI", "PFE", "NOK", "PLTR", "KGC", "SNAP", "LCID", "AAL", "CCL", "NIO", "PCG"
]

# If Alpaca paper account is unfunded / temporarily blocked, optionally keep tournament
# evolving with local simulated fills. Default is OFF for real-paper execution.
ALLOW_LOCAL_FALLBACK_FILL = os.getenv("LIVEBENCH_ALLOW_SIM_FALLBACK", "0").strip() == "1"

STRATEGY_TYPES = [
    "mean_revert",
    "momentum",
    "dip_buy",
    "breakout",
    "scalp",
    "regime_hybrid",
]

# Force first 3 live accounts to run intentionally different logic families
AGENT_STRATEGY_OVERRIDES = {
    "STRAT_01_SPY_HODL": {"strategy_type": "momentum", "favorite_symbol": "PLTR"},
    "STRAT_02_PENDING": {"strategy_type": "mean_revert", "favorite_symbol": "SOFI"},
    "STRAT_03_PENDING": {"strategy_type": "regime_hybrid", "favorite_symbol": "NIO"},
}

# Rotation mode fallback: if no config exists, only these agents are allowed to trade.
DEFAULT_ACTIVE_ROTATION_AGENTS = {
    "STRAT_01_SPY_HODL",
    "STRAT_02_PENDING",
    "STRAT_03_PENDING",
}


@dataclass
class StrategyAgentState:
    agent_id: str
    strategy_type: str
    favorite_symbol: str
    cash: float = 10.0
    position_symbol: Optional[str] = None
    position_qty: int = 0
    avg_entry_price: float = 0.0
    generation: int = 1
    resets: int = 0
    last_action_ts: float = 0.0
    trade_count: int = 0


def now_iso() -> str:
    return datetime.utcnow().isoformat() + "Z"


def ensure_agent_dirs(agent_id: str) -> Path:
    base = AGENT_DATA_DIR / agent_id
    (base / "economic").mkdir(parents=True, exist_ok=True)
    (base / "trades").mkdir(parents=True, exist_ok=True)
    (base / "decisions").mkdir(parents=True, exist_ok=True)
    return base


def append_jsonl(path: Path, obj: Dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def load_agent_accounts() -> Dict[str, Dict]:
    if not AGENT_ACCOUNTS_PATH.exists():
        return {}
    try:
        return json.loads(AGENT_ACCOUNTS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def load_active_rotation_agents() -> set[str]:
    """Load active trading agents from config, fallback to default trio."""
    if not ACTIVE_TRADING_AGENTS_PATH.exists():
        return set(DEFAULT_ACTIVE_ROTATION_AGENTS)

    try:
        payload = json.loads(ACTIVE_TRADING_AGENTS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return set(DEFAULT_ACTIVE_ROTATION_AGENTS)

    if isinstance(payload, list):
        raw_agents = payload
    elif isinstance(payload, dict):
        raw_agents = payload.get("active_agents", [])
    else:
        return set(DEFAULT_ACTIVE_ROTATION_AGENTS)

    active = {str(a).strip() for a in raw_agents if str(a).strip()}
    return active or set(DEFAULT_ACTIVE_ROTATION_AGENTS)


def make_agent_clients(agent_accounts: Dict[str, Dict]) -> Dict[str, AlpacaClient]:
    clients: Dict[str, AlpacaClient] = {}
    for agent_id, cfg in agent_accounts.items():
        key_id = (cfg or {}).get("key_id")
        secret_key = (cfg or {}).get("secret_key")
        base_url = ((cfg or {}).get("base_url") or "https://paper-api.alpaca.markets").rstrip("/")
        if not key_id or not secret_key:
            continue
        try:
            ac = AlpacaConfig(
                api_key_id=key_id,
                api_secret_key=secret_key,
                base_url=base_url,
                data_base_url="https://data.alpaca.markets",
            )
            clients[agent_id] = AlpacaClient(config=ac)
        except Exception:
            continue
    return clients


def load_state() -> Dict[str, StrategyAgentState]:
    states: Dict[str, StrategyAgentState] = {}

    if TOURNAMENT_STATE_PATH.exists():
        raw = json.loads(TOURNAMENT_STATE_PATH.read_text(encoding="utf-8"))
        for item in raw.get("agents", []):
            s = StrategyAgentState(**item)
            states[s.agent_id] = s

    # Ensure 10 agents exist
    for i in range(1, 11):
        agent_id = f"STRAT_{i:02d}_{'SPY_HODL' if i == 1 else 'PENDING'}"
        if agent_id not in states:
            strategy_type = STRATEGY_TYPES[(i - 1) % len(STRATEGY_TYPES)]
            favorite_symbol = SYMBOL_UNIVERSE[(i - 1) % len(SYMBOL_UNIVERSE)]
            states[agent_id] = StrategyAgentState(
                agent_id=agent_id,
                strategy_type=strategy_type,
                favorite_symbol=favorite_symbol,
            )
        ensure_agent_dirs(agent_id)

    # Apply deterministic overrides for the 3 currently connected accounts.
    for aid, ov in AGENT_STRATEGY_OVERRIDES.items():
        if aid in states:
            states[aid].strategy_type = ov["strategy_type"]
            states[aid].favorite_symbol = ov["favorite_symbol"]

    return states


def save_state(states: Dict[str, StrategyAgentState]) -> None:
    payload = {
        "updated_at": now_iso(),
        "agents": [asdict(v) for v in states.values()],
    }
    TOURNAMENT_STATE_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def quote_price(client: AlpacaClient, symbol: str) -> Optional[float]:
    try:
        q = client.get_latest_quote(symbol)
        bp = q.get("bp")
        ap = q.get("ap")
        if bp and ap:
            return (float(bp) + float(ap)) / 2.0
        if ap:
            return float(ap)
        if bp:
            return float(bp)
    except Exception:
        return None
    return None


def decide_action(
    s: StrategyAgentState,
    prices: List[float],
    affordable: List[str],
) -> str:
    if len(prices) < 2:
        return "hold"

    latest = prices[-1]
    prev = prices[-2]
    change = (latest - prev) / prev if prev > 0 else 0.0

    # If in position, prefer simple exits
    if s.position_qty > 0:
        pnl = (latest - s.avg_entry_price) / s.avg_entry_price if s.avg_entry_price > 0 else 0.0
        if pnl >= 0.02:
            return "sell"
        if pnl <= -0.03:
            return "sell"
        # force some turnover so strategies keep exploring/executing
        if random.random() < 0.12:
            return "sell"
    else:
        # Exploration: sometimes open a starter position so agents actually engage the market
        if affordable and random.random() < 0.25:
            return "buy"

    st = s.strategy_type
    if st == "momentum":
        if change > 0.003 and affordable:
            return "buy"
    elif st == "mean_revert":
        if change < -0.004 and affordable:
            return "buy"
    elif st == "dip_buy":
        if change < -0.007 and affordable:
            return "buy"
    elif st == "breakout":
        if len(prices) >= 5 and latest >= max(prices[-5:]) and affordable:
            return "buy"
    elif st == "scalp":
        if abs(change) > 0.005 and affordable:
            return "buy" if change > 0 else "hold"
    elif st == "regime_hybrid":
        # Lightweight regime switch:
        # - quiet regime: mean-revert dips
        # - directional regime: follow momentum
        if len(prices) >= 10:
            recent = prices[-10:]
            spread = (max(recent) - min(recent)) / max(min(recent), 1e-6)
            if spread < 0.015:  # quiet range regime
                if change < -0.003 and affordable:
                    return "buy"
            else:  # directional regime
                if change > 0.004 and affordable:
                    return "buy"

    return "hold"


def mutate_agent(s: StrategyAgentState) -> None:
    s.resets += 1
    s.generation += 1
    s.cash = 10.0
    s.position_symbol = None
    s.position_qty = 0
    s.avg_entry_price = 0.0
    s.last_action_ts = 0.0
    s.trade_count = 0

    # Mutation: change strategy and favorite symbol
    candidates = [x for x in STRATEGY_TYPES if x != s.strategy_type]
    s.strategy_type = random.choice(candidates)
    s.favorite_symbol = random.choice(SYMBOL_UNIVERSE)


def run_once(
    states: Dict[str, StrategyAgentState],
    default_client: AlpacaClient,
    agent_clients: Dict[str, AlpacaClient],
    active_rotation_agents: set[str],
    price_hist: Dict[str, List[float]],
    cooldown_sec: int,
    bust_threshold: float,
) -> None:
    # Refresh quotes for universe
    quotes: Dict[str, float] = {}
    for sym in SYMBOL_UNIVERSE:
        p = quote_price(default_client, sym)
        if p is not None:
            quotes[sym] = p
            price_hist.setdefault(sym, []).append(p)
            if len(price_hist[sym]) > 40:
                price_hist[sym] = price_hist[sym][-40:]

    for agent_id, s in states.items():
        now_ts = time.time()

        # Park non-rotation agents to avoid account interference.
        if agent_id not in active_rotation_agents:
            append_jsonl(
                AGENT_DATA_DIR / agent_id / "decisions" / "decisions.jsonl",
                {
                    "date": datetime.utcnow().strftime("%Y-%m-%d"),
                    "timestamp": now_iso(),
                    "activity": "parked",
                    "action": "hold",
                    "executed": False,
                    "strategy_type": s.strategy_type,
                    "symbol": s.position_symbol or s.favorite_symbol,
                    "reset": False,
                    "error": None,
                },
            )
            continue

        # If market data is unavailable (overnight / feed issue), still emit a
        # heartbeat decision so UI can show the model is alive and polling.
        if not quotes:
            append_jsonl(
                AGENT_DATA_DIR / agent_id / "decisions" / "decisions.jsonl",
                {
                    "date": datetime.utcnow().strftime("%Y-%m-%d"),
                    "timestamp": now_iso(),
                    "activity": "trading",
                    "action": "hold",
                    "executed": False,
                    "strategy_type": s.strategy_type,
                    "symbol": s.position_symbol or s.favorite_symbol,
                    "reset": False,
                    "error": "no_market_data",
                },
            )
            continue

        if now_ts - s.last_action_ts < cooldown_sec:
            continue

        # Determine symbol to watch
        symbol = s.position_symbol or s.favorite_symbol
        if symbol not in quotes:
            # fallback to any quoted symbol
            if not quotes:
                continue
            symbol = random.choice(list(quotes.keys()))

        price = quotes[symbol]
        affordable = [sym for sym, p in quotes.items() if p <= s.cash]
        action = decide_action(s, price_hist.get(symbol, []), affordable)

        executed = False
        error = None
        agent_client = agent_clients.get(agent_id, default_client)

        # BUY logic (qty=1 only)
        if action == "buy" and s.position_qty == 0:
            buy_symbol = symbol if symbol in affordable else (random.choice(affordable) if affordable else None)
            if buy_symbol:
                buy_price = quotes[buy_symbol]
                try:
                    order = agent_client.place_market_order(buy_symbol, 1, "buy", paper_guard=True)
                    order_id = order.get("id")
                    order_status = None
                    if order_id:
                        try:
                            order_status = agent_client.get_order(order_id).get("status")
                        except Exception:
                            order_status = None
                    s.position_symbol = buy_symbol
                    s.position_qty = 1
                    s.avg_entry_price = buy_price
                    s.cash -= buy_price
                    s.trade_count += 1
                    executed = True
                    append_jsonl(
                        AGENT_DATA_DIR / agent_id / "trades" / "trades.jsonl",
                        {
                            "ts": now_iso(),
                            "agent_id": agent_id,
                            "action": "buy",
                            "symbol": buy_symbol,
                            "qty": 1,
                            "price_ref": buy_price,
                            "strategy_type": s.strategy_type,
                            "order_id": order_id,
                            "order_status": order_status,
                        },
                    )
                except Exception as e:
                    error = str(e)
                    if ALLOW_LOCAL_FALLBACK_FILL:
                        # Fallback virtual fill when Alpaca rejects due to paper account state
                        s.position_symbol = buy_symbol
                        s.position_qty = 1
                        s.avg_entry_price = buy_price
                        s.cash -= buy_price
                        s.trade_count += 1
                        executed = True
                        append_jsonl(
                            AGENT_DATA_DIR / agent_id / "trades" / "trades.jsonl",
                            {
                                "ts": now_iso(),
                                "agent_id": agent_id,
                                "action": "buy",
                                "symbol": buy_symbol,
                                "qty": 1,
                                "price_ref": buy_price,
                                "strategy_type": s.strategy_type,
                                "order_id": None,
                                "simulated_fill": True,
                                "fallback_reason": error,
                            },
                        )

        # SELL logic
        elif action == "sell" and s.position_qty > 0 and s.position_symbol in quotes:
            sell_symbol = s.position_symbol
            sell_price = quotes[sell_symbol]
            try:
                order = agent_client.place_market_order(sell_symbol, 1, "sell", paper_guard=True)
                order_id = order.get("id")
                order_status = None
                if order_id:
                    try:
                        order_status = agent_client.get_order(order_id).get("status")
                    except Exception:
                        order_status = None
                s.cash += sell_price
                s.position_qty = 0
                s.position_symbol = None
                s.avg_entry_price = 0.0
                s.trade_count += 1
                executed = True
                append_jsonl(
                    AGENT_DATA_DIR / agent_id / "trades" / "trades.jsonl",
                    {
                        "ts": now_iso(),
                        "agent_id": agent_id,
                        "action": "sell",
                        "symbol": sell_symbol,
                        "qty": 1,
                        "price_ref": sell_price,
                        "strategy_type": s.strategy_type,
                        "order_id": order_id,
                        "order_status": order_status,
                    },
                )
            except Exception as e:
                error = str(e)
                if ALLOW_LOCAL_FALLBACK_FILL:
                    s.cash += sell_price
                    s.position_qty = 0
                    s.position_symbol = None
                    s.avg_entry_price = 0.0
                    s.trade_count += 1
                    executed = True
                    append_jsonl(
                        AGENT_DATA_DIR / agent_id / "trades" / "trades.jsonl",
                        {
                            "ts": now_iso(),
                            "agent_id": agent_id,
                            "action": "sell",
                            "symbol": sell_symbol,
                            "qty": 1,
                            "price_ref": sell_price,
                            "strategy_type": s.strategy_type,
                            "order_id": None,
                            "simulated_fill": True,
                            "fallback_reason": error,
                        },
                    )

        # Net worth mark-to-market
        mtm = 0.0
        if s.position_qty > 0 and s.position_symbol in quotes:
            mtm = s.position_qty * quotes[s.position_symbol]
        net_worth = s.cash + mtm

        # Bust/reset rule
        reset = False
        if net_worth <= bust_threshold:
            mutate_agent(s)
            net_worth = s.cash
            reset = True

        # Append decision snapshot (used by /api/agents current_activity/current_date)
        append_jsonl(
            AGENT_DATA_DIR / agent_id / "decisions" / "decisions.jsonl",
            {
                "date": datetime.utcnow().strftime("%Y-%m-%d"),
                "timestamp": now_iso(),
                "activity": "trading",
                "action": action,
                "executed": executed,
                "strategy_type": s.strategy_type,
                "symbol": s.position_symbol or symbol,
                "reset": reset,
                "error": error,
            },
        )

        # Append economic snapshot for dashboard
        append_jsonl(
            AGENT_DATA_DIR / agent_id / "economic" / "balance.jsonl",
            {
                "date": datetime.utcnow().strftime("%Y-%m-%d"),
                "timestamp": now_iso(),
                "balance": round(s.cash, 4),
                "net_worth": round(net_worth, 4),
                "survival_status": "alive" if net_worth > bust_threshold else "bankrupt",
                "current_activity": "trading",
                "strategy_type": s.strategy_type,
                "favorite_symbol": s.favorite_symbol,
                "position_symbol": s.position_symbol,
                "position_qty": s.position_qty,
                "avg_entry_price": round(s.avg_entry_price, 4),
                "last_action": action,
                "executed": executed,
                "reset": reset,
                "error": error,
                "total_token_cost": 0.0,
                "total_work_income": 0.0,
            },
        )

        s.last_action_ts = now_ts


def main() -> None:
    parser = argparse.ArgumentParser(description="Run 10-agent paper trading tournament")
    parser.add_argument("--interval", type=int, default=30, help="Loop interval seconds")
    parser.add_argument("--cooldown", type=int, default=90, help="Min seconds between actions per agent")
    parser.add_argument("--bust-threshold", type=float, default=0.5, help="Net worth threshold to reset agent")
    args = parser.parse_args()

    states = load_state()
    save_state(states)

    default_client = AlpacaClient()
    agent_accounts = load_agent_accounts()
    agent_clients = make_agent_clients(agent_accounts)
    price_hist: Dict[str, List[float]] = {}

    print(
        f"[paper_tournament] started {len(states)} agents, interval={args.interval}s, "
        f"dedicated_accounts={len(agent_clients)}"
    )
    while True:
        try:
            active_rotation_agents = load_active_rotation_agents()
            run_once(
                states,
                default_client,
                agent_clients,
                active_rotation_agents,
                price_hist,
                cooldown_sec=args.cooldown,
                bust_threshold=args.bust_threshold,
            )
            save_state(states)
        except Exception as e:
            print(f"[paper_tournament] loop error: {e}")
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
