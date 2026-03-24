"""Decision Agent — combines all agent signals into a final BUY / SELL / HOLD.

Uses sector-aware weight profiles so tech stocks weight technicals higher
while defensive sectors weight fundamentals/dividends more.
"""

import logging
import config

logger = logging.getLogger(__name__)

# Sector-specific weight profiles
SECTOR_WEIGHTS = {
    "Technology": {"technical": 0.35, "fundamental": 0.20, "sentiment": 0.25, "trend": 0.10, "risk": 0.10},
    "Communication Services": {"technical": 0.35, "fundamental": 0.20, "sentiment": 0.25, "trend": 0.10, "risk": 0.10},
    "Consumer Cyclical": {"technical": 0.30, "fundamental": 0.20, "sentiment": 0.25, "trend": 0.15, "risk": 0.10},
    "Financial Services": {"technical": 0.25, "fundamental": 0.35, "sentiment": 0.15, "trend": 0.10, "risk": 0.15},
    "Healthcare": {"technical": 0.25, "fundamental": 0.30, "sentiment": 0.20, "trend": 0.10, "risk": 0.15},
    "Utilities": {"technical": 0.15, "fundamental": 0.40, "sentiment": 0.10, "trend": 0.10, "risk": 0.25},
    "Consumer Defensive": {"technical": 0.20, "fundamental": 0.35, "sentiment": 0.15, "trend": 0.10, "risk": 0.20},
    "Energy": {"technical": 0.25, "fundamental": 0.25, "sentiment": 0.20, "trend": 0.15, "risk": 0.15},
    "Industrials": {"technical": 0.25, "fundamental": 0.30, "sentiment": 0.15, "trend": 0.15, "risk": 0.15},
    "Real Estate": {"technical": 0.20, "fundamental": 0.35, "sentiment": 0.10, "trend": 0.15, "risk": 0.20},
}
DEFAULT_WEIGHTS = {"technical": 0.30, "fundamental": 0.25, "sentiment": 0.20, "trend": 0.15, "risk": 0.10}


def decision_agent(state: dict) -> dict:
    ticker = state["ticker"]
    logger.info(f"[DecisionAgent] Generating decision for {ticker}")

    risk = state.get("risk", {})
    technicals = state.get("technicals", {})
    fundamentals = state.get("fundamentals", {})
    sentiment = state.get("sentiment", {})
    market = state.get("market_data", {})

    # --- If risk is high, skip trade immediately ---
    if risk.get("level") == "high":
        state["decision"] = "HOLD"
        state["confidence"] = 0.2
        state["logs"].append("[DecisionAgent] HOLD — risk too high")
        return state

    # --- Select sector-aware weights ---
    sector = market.get("sector", "Unknown")
    weights = SECTOR_WEIGHTS.get(sector, DEFAULT_WEIGHTS)

    # --- Weighted scoring system ---
    score = 0.0

    # Technical score (-3 to +3 -> normalise to -1..+1)
    tech_score = technicals.get("signal_score", 0) / 3
    score += weights["technical"] * tech_score

    # Fundamental score (-4 to +4 -> normalise)
    fund_score = fundamentals.get("net_score", 0) / 4
    score += weights["fundamental"] * fund_score

    # Sentiment score (already -1..+1)
    sent_score = sentiment.get("score", 0)
    score += weights["sentiment"] * sent_score

    # Trend
    trend_map = {"bullish": 1, "bearish": -1, "sideways": 0}
    trend_score = trend_map.get(market.get("trend", "sideways"), 0)
    score += weights["trend"] * trend_score

    # Risk bonus (low risk = positive)
    risk_map = {"low": 1, "medium": 0, "high": -1}
    risk_score = risk_map.get(risk.get("level", "medium"), 0)
    score += weights["risk"] * risk_score

    buy_thresh = config.get("decision", "buy_threshold", 0.15)
    sell_thresh = config.get("decision", "sell_threshold", -0.15)
    conf_div = config.get("decision", "confidence_divisor", 0.5)

    if score > buy_thresh:
        decision = "BUY"
    elif score < sell_thresh:
        decision = "SELL"
    else:
        decision = "HOLD"

    confidence = round(min(abs(score) / conf_div, 1.0), 2)

    state["decision"] = decision
    state["confidence"] = confidence
    state["logs"].append(
        f"[DecisionAgent] sector={sector}, weights={weights}, score={round(score, 4)} -> {decision} (confidence={confidence})"
    )
    return state
