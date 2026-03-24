"""Market Research Agent — fetches price history and detects trend."""

import logging
import numpy as np
from tools.data_fetcher import fetch_stock_data

logger = logging.getLogger(__name__)


def market_research_agent(state: dict) -> dict:
    ticker = state["ticker"]
    logger.info(f"[MarketAgent] Fetching data for {ticker}")

    data = fetch_stock_data(ticker)
    if data is None:
        state["logs"].append(f"[MarketAgent] FAILED to fetch data for {ticker}")
        state["market_data"] = {"error": "data_fetch_failed"}
        return state

    hist = data["history"]
    closes = hist["Close"].values

    # Trend detection via 20-day vs 50-day SMA slope
    sma20 = np.convolve(closes, np.ones(min(20, len(closes))) / min(20, len(closes)), mode="valid")
    recent_slope = (sma20[-1] - sma20[-min(5, len(sma20))]) / max(sma20[-min(5, len(sma20))], 1e-9)
    trend = "bullish" if recent_slope > 0.01 else ("bearish" if recent_slope < -0.01 else "sideways")

    # 52-week high/low
    high_52w = float(closes.max())
    low_52w = float(closes.min())
    current = data["current_price"]
    pct_from_high = round((current - high_52w) / high_52w * 100, 2)

    state["market_data"] = {
        "history": hist,
        "current_price": current,
        "trend": trend,
        "trend_slope": round(float(recent_slope), 4),
        "high_52w": round(high_52w, 2),
        "low_52w": round(low_52w, 2),
        "pct_from_high": pct_from_high,
        "name": data["name"],
        "sector": data["sector"],
        "currency": data["currency"],
    }
    state["logs"].append(f"[MarketAgent] {ticker}: price={current}, trend={trend}")
    return state
