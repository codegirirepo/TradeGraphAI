"""Technical Analysis Agent — computes RSI, MACD, SMA and derives signals."""

import logging
from tools.indicators import compute_indicators

logger = logging.getLogger(__name__)


def technical_analysis_agent(state: dict) -> dict:
    ticker = state["ticker"]
    logger.info(f"[TechnicalAgent] Computing indicators for {ticker}")

    hist = state.get("market_data", {}).get("history")
    if hist is None or (hasattr(hist, "empty") and hist.empty):
        state["technicals"] = {"error": "no_market_data"}
        state["logs"].append("[TechnicalAgent] Skipped — no market data available")
        return state

    try:
        indicators = compute_indicators(hist)

        # Aggregate signal: count bullish vs bearish signals
        signals = [
            1 if indicators["rsi_signal"] == "oversold" else (-1 if indicators["rsi_signal"] == "overbought" else 0),
            1 if indicators["macd_direction"] == "bullish" else -1,
            1 if indicators["price_vs_sma50"] == "bullish" else -1,
        ]
        net = sum(signals)
        overall = "bullish" if net > 0 else ("bearish" if net < 0 else "neutral")
        indicators["overall_signal"] = overall
        indicators["signal_score"] = net

        state["technicals"] = indicators
        state["logs"].append(f"[TechnicalAgent] RSI={indicators['rsi']}, MACD dir={indicators['macd_direction']}, overall={overall}")
    except Exception as e:
        logger.error(f"[TechnicalAgent] Error: {e}")
        state["technicals"] = {"error": str(e)}
        state["logs"].append(f"[TechnicalAgent] Error: {e}")

    return state
