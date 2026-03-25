"""Execution Agent — optionally submits paper trading orders via Alpaca."""

import logging
from tools.broker import execute_signal, is_enabled

logger = logging.getLogger(__name__)


def execution_agent(state: dict) -> dict:
    ticker = state["ticker"]
    decision = state.get("decision", "HOLD")

    if not is_enabled():
        state["logs"].append("[ExecutionAgent] Paper trading disabled — skipping execution")
        return state

    logger.info(f"[ExecutionAgent] Executing {decision} for {ticker}")
    details = {
        "position_size": state.get("risk", {}).get("position_size", 0),
        "price": state.get("market_data", {}).get("current_price", 0),
        "stop_loss": state.get("risk", {}).get("stop_loss", 0),
    }

    result = execute_signal(ticker, decision, details)
    state["execution"] = result
    state["logs"].append(f"[ExecutionAgent] {result.get('status')}: {result.get('reason', result.get('order_id', ''))}")
    return state
