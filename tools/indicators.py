"""Technical indicator computation using the *ta* library."""

import logging
import pandas as pd
import ta

logger = logging.getLogger(__name__)


def compute_indicators(hist: pd.DataFrame) -> dict:
    """Compute RSI, MACD, SMA-20/50/200 and return a signal summary."""
    close = hist["Close"]

    rsi = ta.momentum.RSIIndicator(close).rsi().iloc[-1]
    macd_line = ta.trend.MACD(close).macd().iloc[-1]
    macd_signal = ta.trend.MACD(close).macd_signal().iloc[-1]
    sma_20 = ta.trend.SMAIndicator(close, window=20).sma_indicator().iloc[-1]
    sma_50 = ta.trend.SMAIndicator(close, window=50).sma_indicator().iloc[-1]
    sma_200 = ta.trend.SMAIndicator(close, window=200).sma_indicator()
    sma_200_val = sma_200.iloc[-1] if len(sma_200.dropna()) > 0 else None
    current = float(close.iloc[-1])

    # Derive signals
    rsi_signal = "oversold" if rsi < 30 else ("overbought" if rsi > 70 else "neutral")
    macd_signal_dir = "bullish" if macd_line > macd_signal else "bearish"
    sma_trend = "bullish" if current > sma_50 else "bearish"

    return {
        "rsi": round(float(rsi), 2),
        "rsi_signal": rsi_signal,
        "macd": round(float(macd_line), 4),
        "macd_signal": round(float(macd_signal), 4),
        "macd_direction": macd_signal_dir,
        "sma_20": round(float(sma_20), 2),
        "sma_50": round(float(sma_50), 2),
        "sma_200": round(float(sma_200_val), 2) if sma_200_val else None,
        "price_vs_sma50": sma_trend,
        "current_price": round(current, 2),
    }
