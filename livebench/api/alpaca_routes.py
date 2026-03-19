"""FastAPI routes for Alpaca account/positions and a minimal paper-order helper.

These routes are intentionally thin wrappers around `AlpacaClient` and are
primarily for internal dashboard/agent use. Higher-level risk controls should
live in agents or dedicated strategy modules.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Any, Dict, List

from livebench.trading.alpaca_client import AlpacaAuthError, AlpacaClient, AlpacaConfigError


router = APIRouter(prefix="/api/alpaca", tags=["alpaca"])


def _paper_order_log_path() -> Path:
    return Path(__file__).resolve().parents[2] / "data" / "alpaca_paper_orders.jsonl"


def _append_paper_order_log(entry: Dict[str, Any]) -> None:
    """Append paper-order attempts/results to local JSONL for auditability."""

    log_path = _paper_order_log_path()
    log_path.parent.mkdir(parents=True, exist_ok=True)

    enriched = {
        "ts": datetime.now(timezone.utc).isoformat(),
        **entry,
    }
    with log_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(enriched, ensure_ascii=False) + "\n")


class PaperOrderRequest(BaseModel):
    symbol: str
    qty: int = 1
    side: str = "buy"  # "buy" or "sell"
    agent_id: str | None = None  # optional strategy/worker identifier for audit logs


@router.get("/account")
async def get_alpaca_account() -> Dict[str, Any]:
    """Return raw Alpaca account info (paper/live depending on BASE_URL).

    This exposes the full Alpaca response for power users and debugging.
    For dashboards and agents, prefer `/api/alpaca/account/summary` which
    returns a stable, normalized shape.
    """

    try:
        client = AlpacaClient()
        return client.get_account()
    except AlpacaConfigError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:  # pragma: no cover - surface upstream error text
        raise HTTPException(status_code=502, detail=f"Alpaca account error: {e}")


@router.get("/account/summary")
async def get_alpaca_account_summary() -> Dict[str, Any]:
    """Return a normalized, dashboard-friendly Alpaca account summary.

    This endpoint is safe to depend on from the frontend; it keeps the
    returned fields small and stable even if Alpaca's raw payload evolves.
    """

    try:
        client = AlpacaClient()
        return client.get_account_summary()
    except AlpacaConfigError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:  # pragma: no cover - surface upstream error text
        raise HTTPException(status_code=502, detail=f"Alpaca account summary error: {e}")


@router.get("/account/identity")
async def get_alpaca_account_identity() -> Dict[str, Any]:
    """Return stable identity fields for the currently connected Alpaca account.

    Useful to quickly detect key/account mismatches when UI and backend seem to
    point to different accounts.
    """

    try:
        client = AlpacaClient()
        raw = client.get_account()
        summary = client.get_account_summary()
        return {
            "id": raw.get("id"),
            "account_number": raw.get("account_number"),
            "status": summary.get("status"),
            "currency": summary.get("currency"),
            "cash": summary.get("cash"),
            "buying_power": summary.get("buying_power"),
            "base_url": client.config.base_url,
            "paper_endpoint": "paper-api.alpaca.markets" in client.config.base_url,
        }
    except AlpacaConfigError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:  # pragma: no cover
        raise HTTPException(status_code=502, detail=f"Alpaca account identity error: {e}")


@router.get("/positions")
async def get_alpaca_positions() -> List[Dict[str, Any]]:
    """Return open positions from Alpaca (raw payload).

    Returns an empty list if there are no positions. For dashboards and
    agents, prefer `/api/alpaca/positions/summary` which returns a
    normalized, stable shape.
    """

    try:
        client = AlpacaClient()
        return client.get_positions()
    except AlpacaConfigError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:  # pragma: no cover
        raise HTTPException(status_code=502, detail=f"Alpaca positions error: {e}")


@router.get("/positions/summary")
async def get_alpaca_positions_summary() -> List[Dict[str, Any]]:
    """Return a normalized list of open positions for dashboards.

    Uses `AlpacaClient.get_positions_summary()` to keep the response
    small, typed, and stable over time.
    """

    try:
        client = AlpacaClient()
        return client.get_positions_summary()
    except AlpacaConfigError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:  # pragma: no cover
        raise HTTPException(status_code=502, detail=f"Alpaca positions summary error: {e}")


@router.get("/quote/{symbol}")
async def get_alpaca_quote(symbol: str) -> Dict[str, Any]:
    """Return latest quote for a symbol (bid/ask) from Alpaca market data."""

    try:
        client = AlpacaClient()
        return client.get_latest_quote(symbol)
    except AlpacaConfigError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:  # pragma: no cover
        raise HTTPException(status_code=502, detail=f"Alpaca quote error: {e}")


@router.get("/snapshot")
async def get_alpaca_snapshot() -> Dict[str, Any]:
    """Return account + positions summary in one payload for agent polling."""

    try:
        client = AlpacaClient()
        snapshot = client.get_snapshot_summary()
        return {
            "ok": True,
            **snapshot,
        }
    except AlpacaConfigError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:  # pragma: no cover
        raise HTTPException(status_code=502, detail=f"Alpaca snapshot error: {e}")


@router.post("/paper-order")
async def submit_paper_order(req: PaperOrderRequest) -> Dict[str, Any]:
    """Submit a very small, safety-limited market order to Alpaca.

    Safety rules (v1):
    - qty must be between 1 and 5
    - symbol is uppercased but otherwise not validated here
    - "buy" only by default; "sell" allowed but must be small size

    Higher-level agents should implement additional risk controls.
    """

    if req.qty < 1 or req.qty > 5:
        raise HTTPException(status_code=400, detail="qty must be between 1 and 5 for safety")

    side = req.side.lower()
    if side not in {"buy", "sell"}:
        raise HTTPException(status_code=400, detail="side must be 'buy' or 'sell'")

    try:
        client = AlpacaClient()

        # Hard safety guard: never allow this endpoint against live trading base URLs.
        if "paper-api.alpaca.markets" not in client.config.base_url:
            raise HTTPException(
                status_code=403,
                detail="paper-order endpoint is restricted to Alpaca paper base URL only",
            )

        account_number = None
        try:
            account_number = client.get_account().get("account_number")
        except Exception:
            account_number = None

        order = client.place_market_order(symbol=req.symbol, qty=req.qty, side=side)
        _append_paper_order_log(
            {
                "status": "ok",
                "agent_id": req.agent_id,
                "account_number": account_number,
                "symbol": req.symbol.upper().strip(),
                "qty": req.qty,
                "side": side,
                "order_id": order.get("id"),
                "paper_endpoint": "paper-api.alpaca.markets" in client.config.base_url,
            }
        )
        return {"status": "ok", "order": order}
    except AlpacaConfigError as e:
        _append_paper_order_log(
            {
                "status": "error",
                "agent_id": req.agent_id,
                "account_number": None,
                "symbol": req.symbol.upper().strip(),
                "qty": req.qty,
                "side": side,
                "error": str(e),
                "error_type": "config",
            }
        )
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:  # pragma: no cover
        _append_paper_order_log(
            {
                "status": "error",
                "agent_id": req.agent_id,
                "account_number": None,
                "symbol": req.symbol.upper().strip(),
                "qty": req.qty,
                "side": side,
                "error": str(e),
                "error_type": "runtime",
            }
        )
        raise HTTPException(status_code=502, detail=f"Alpaca order error: {e}")


@router.get("/paper-order/{order_id}")
async def get_paper_order(order_id: str) -> Dict[str, Any]:
    """Fetch a single Alpaca order by id for fill/status tracking."""

    try:
        client = AlpacaClient()
        return client.get_order(order_id)
    except AlpacaConfigError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:  # pragma: no cover
        raise HTTPException(status_code=502, detail=f"Alpaca get-order error: {e}")


@router.get("/paper-order/logs")
async def get_paper_order_logs(limit: int = 20) -> Dict[str, Any]:
    """Return recent paper-order audit entries from local JSONL log."""

    safe_limit = max(1, min(limit, 200))
    log_path = _paper_order_log_path()

    if not log_path.exists():
        return {"count": 0, "items": []}

    try:
        lines = log_path.read_text(encoding="utf-8").splitlines()
        recent = lines[-safe_limit:]
        items: List[Dict[str, Any]] = []
        for line in recent:
            if not line.strip():
                continue
            try:
                items.append(json.loads(line))
            except json.JSONDecodeError:
                items.append({"status": "corrupt", "raw": line})

        return {
            "count": len(items),
            "items": items,
        }
    except Exception as e:  # pragma: no cover
        raise HTTPException(status_code=500, detail=f"Failed to read paper-order logs: {e}")


@router.get("/health")
async def alpaca_health() -> Dict[str, Any]:
    """Lightweight health check for Alpaca wiring.

    Returns config presence, base_url, and whether a simple account
    request succeeds. This helps the dashboard/agents quickly see if
    keys are missing, invalid, or pointed at the wrong endpoint.
    """

    try:
        client = AlpacaClient()
    except AlpacaConfigError as e:
        # Config missing or invalid
        return {
            "ok": False,
            "config_error": str(e),
        }

    base_url = client.config.base_url
    try:
        acct = client.get_account_summary()
        return {
            "ok": True,
            "base_url": base_url,
            "paper_endpoint": "paper-api.alpaca.markets" in base_url,
            "status": acct.get("status"),
            "currency": acct.get("currency"),
        }
    except AlpacaAuthError as e:
        return {
            "ok": False,
            "base_url": base_url,
            "paper_endpoint": "paper-api.alpaca.markets" in base_url,
            "error_type": "auth",
            "error": str(e),
            "action": "rotate_or_fix_paper_api_keys",
        }
    except Exception as e:  # pragma: no cover
        return {
            "ok": False,
            "base_url": base_url,
            "paper_endpoint": "paper-api.alpaca.markets" in base_url,
            "error_type": "runtime",
            "error": str(e),
        }
