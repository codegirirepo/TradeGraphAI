"""Risk Management Agent — volatility, stop-loss, position sizing."""

import logging
import numpy as np
import config

logger = logging.getLogger(__name__)

PORTFOLIO_VALUE = config.get("portfolio", "default_value", 100_000)


def risk_management_agent(state: dict) -> dict:
    ticker = state["ticker"]
    portfolio_value = state.get("portfolio_value", PORTFOLIO_VALUE)
    logger.info(f"[RiskAgent] Evaluating risk for {ticker} (portfolio=${portfolio_value:,})")

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
    high_vol = config.get("risk", "high_volatility", 0.50)
    med_vol = config.get("risk", "medium_volatility", 0.30)
    high_dd = config.get("risk", "high_drawdown", -0.30)
    med_dd = config.get("risk", "medium_drawdown", -0.15)

    if annual_vol > high_vol or max_dd < high_dd:
        level = "high"
    elif annual_vol > med_vol or max_dd < med_dd:
        level = "medium"
    else:
        level = "low"

    current = float(closes[-1])
    # Stop-loss: 2× daily vol below current price
    stop_loss_mult = config.get("risk", "stop_loss_multiplier", 2)
    stop_loss = round(current * (1 - stop_loss_mult * daily_vol), 2)
    risk_pct = config.get("portfolio", "risk_per_trade_pct", 0.01)
    risk_per_share = current - stop_loss
    position_size = int(portfolio_value * risk_pct / max(risk_per_share, 0.01))

    state["risk"] = {
        "level": level,
        "annual_volatility": annual_vol,
        "daily_volatility": round(daily_vol, 4),
        "max_drawdown": max_dd,
        "var_95": var_95,
        "stop_loss": stop_loss,
        "position_size": position_size,
        "portfolio_value": portfolio_value,
    }
    state["logs"].append(f"[RiskAgent] vol={annual_vol}, dd={max_dd}, level={level}, stop={stop_loss}")
    return state
