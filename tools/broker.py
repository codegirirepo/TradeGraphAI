"""Alpaca broker integration — paper trading execution with safety guards."""

import os, logging
from datetime import datetime

import config

logger = logging.getLogger(__name__)

_api = None


def _get_api():
    """Lazy-init Alpaca API client."""
    global _api
    if _api is not None:
        return _api

    key = os.getenv("ALPACA_API_KEY", "")
    secret = os.getenv("ALPACA_SECRET_KEY", "")
    base_url = os.getenv("ALPACA_BASE_URL", "https://paper-api.alpaca.markets")

    if not key or not secret or key == "your_key_here":
        return None

    try:
        import alpaca_trade_api as tradeapi
        _api = tradeapi.REST(key, secret, base_url, api_version="v2")
        acct = _api.get_account()
        logger.info(f"[Broker] Connected to Alpaca (equity=${float(acct.equity):,.2f}, status={acct.status})")
        return _api
    except Exception as e:
        logger.error(f"[Broker] Alpaca connection failed: {e}")
        return None


def is_enabled() -> bool:
    """Check if execution is enabled in config and credentials are set."""
    enabled = config.get("execution", "enabled", False)
    if not enabled:
        return False
    return _get_api() is not None


def get_account_info() -> dict:
    """Return current account info."""
    api = _get_api()
    if not api:
        return {"error": "Not connected"}
    try:
        acct = api.get_account()
        return {
            "equity": float(acct.equity),
            "cash": float(acct.cash),
            "buying_power": float(acct.buying_power),
            "portfolio_value": float(acct.portfolio_value),
            "status": acct.status,
        }
    except Exception as e:
        return {"error": str(e)}


def get_positions() -> list[dict]:
    """Return current open positions."""
    api = _get_api()
    if not api:
        return []
    try:
        positions = api.list_positions()
        return [{
            "ticker": p.symbol,
            "qty": int(p.qty),
            "avg_entry": float(p.avg_entry_price),
            "current_price": float(p.current_price),
            "market_value": float(p.market_value),
            "unrealized_pl": float(p.unrealized_pl),
            "unrealized_plpc": float(p.unrealized_plpc),
        } for p in positions]
    except Exception as e:
        logger.error(f"[Broker] Failed to get positions: {e}")
        return []


def execute_signal(ticker: str, decision: str, details: dict) -> dict:
    """Execute a trading signal with safety guards.

    Returns order info or reason for skipping.
    """
    if not is_enabled():
        return {"status": "skipped", "reason": "execution_disabled"}

    api = _get_api()
    mode = config.get("execution", "mode", "paper")
    max_pos_pct = config.get("execution", "max_position_pct", 0.10)
    max_daily = config.get("execution", "max_daily_trades", 5)

    # Safety: only paper mode
    if mode != "paper":
        return {"status": "skipped", "reason": "only_paper_mode_supported"}

    if decision == "HOLD":
        return {"status": "skipped", "reason": "HOLD_signal"}

    try:
        acct = api.get_account()
        equity = float(acct.equity)

        # Check daily trade limit
        today = datetime.now().strftime("%Y-%m-%d")
        orders = api.list_orders(status="all", after=today, limit=50)
        today_count = len([o for o in orders if o.created_at.strftime("%Y-%m-%d") == today])
        if today_count >= max_daily:
            return {"status": "skipped", "reason": f"daily_limit_reached ({max_daily})"}

        position_size = details.get("position_size", 0)
        price = details.get("price", 0)

        if decision == "BUY" and position_size > 0 and price > 0:
            # Check max position size
            max_value = equity * max_pos_pct
            order_value = position_size * price
            if order_value > max_value:
                position_size = int(max_value / price)

            if position_size < 1:
                return {"status": "skipped", "reason": "position_too_small"}

            order = api.submit_order(
                symbol=ticker, qty=position_size, side="buy",
                type="market", time_in_force="day",
            )
            logger.info(f"[Broker] BUY {position_size} {ticker} @ market (order {order.id})")
            return {"status": "executed", "side": "buy", "qty": position_size, "order_id": order.id}

        elif decision == "SELL":
            # Only sell if we have a position
            try:
                pos = api.get_position(ticker)
                qty = int(pos.qty)
                if qty > 0:
                    order = api.submit_order(
                        symbol=ticker, qty=qty, side="sell",
                        type="market", time_in_force="day",
                    )
                    logger.info(f"[Broker] SELL {qty} {ticker} @ market (order {order.id})")
                    return {"status": "executed", "side": "sell", "qty": qty, "order_id": order.id}
            except Exception:
                return {"status": "skipped", "reason": "no_position_to_sell"}

    except Exception as e:
        logger.error(f"[Broker] Execution failed: {e}")
        return {"status": "error", "reason": str(e)}

    return {"status": "skipped", "reason": "no_action"}
