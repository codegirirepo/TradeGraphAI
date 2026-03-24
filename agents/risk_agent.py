"""Risk Management Agent — volatility, stop-loss, position sizing."""

import logging
import numpy as np

logger = logging.getLogger(__name__)

PORTFOLIO_VALUE = 100_000  # default notional portfolio


def risk_management_agent(state: dict) -> dict:
    ticker = state["ticker"]
    logger.info(f"[RiskAgent] Evaluating risk for {ticker}")

    hist = state.get("market_data", {}).get("history")
    if hist is None or (hasattr(hist, "empty") and hist.empty):
        state["risk"] = {"level": "high", "reason": "no_data"}
        state["logs"].append("[RiskAgent] HIGH risk — no market data")
        return state

    closes = hist["Close"].values.astype(float)
    returns = np.diff(closes) / closes[:-1]

    # Annualised volatility
    daily_vol = float(np.std(returns))
    annual_vol = round(daily_vol * np.sqrt(252), 4)

    # Max drawdown over the period
    peak = np.maximum.accumulate(closes)
    drawdown = (closes - peak) / peak
    max_dd = round(float(drawdown.min()), 4)

    # Value-at-Risk (95 %)
    var_95 = round(float(np.percentile(returns, 5)), 4)

    # Risk level classification
    if annual_vol > 0.50 or max_dd < -0.30:
        level = "high"
    elif annual_vol > 0.30 or max_dd < -0.15:
        level = "medium"
    else:
        level = "low"

    current = float(closes[-1])
    # Stop-loss: 2× daily vol below current price
    stop_loss = round(current * (1 - 2 * daily_vol), 2)
    # Position size: risk 1 % of portfolio per trade
    risk_per_share = current - stop_loss
    position_size = int(PORTFOLIO_VALUE * 0.01 / max(risk_per_share, 0.01))

    state["risk"] = {
        "level": level,
        "annual_volatility": annual_vol,
        "daily_volatility": round(daily_vol, 4),
        "max_drawdown": max_dd,
        "var_95": var_95,
        "stop_loss": stop_loss,
        "position_size": position_size,
        "portfolio_value": PORTFOLIO_VALUE,
    }
    state["logs"].append(f"[RiskAgent] vol={annual_vol}, dd={max_dd}, level={level}, stop={stop_loss}")
    return state
