"""Backtesting engine — simulates the analysis pipeline on historical data.

Runs the agent pipeline at each point in a date range, records decisions,
and compares against actual future price movement to compute win rate,
Sharpe ratio, and equity curve.
"""

import logging
from datetime import datetime, timedelta

import numpy as np
import yfinance as yf

from tools.indicators import compute_indicators
from tools.data_fetcher import fetch_fundamentals_av
import config

logger = logging.getLogger(__name__)


def run_backtest(ticker: str, days_back: int = 120, hold_days: int = 5) -> dict:
    """Run a backtest for *ticker* over the last *days_back* trading days.

    At each evaluation point (every 5 trading days), the engine:
      1. Computes technical indicators on data available up to that date
      2. Generates a BUY/SELL/HOLD signal
      3. Measures actual return over the next *hold_days* trading days

    Returns a dict with trades, equity curve, and performance metrics.
    """
    ticker = ticker.upper()
    logger.info(f"[Backtest] Starting for {ticker}, {days_back} days back, hold={hold_days}d")

    # Fetch extended history (need extra buffer for indicators)
    end = datetime.now()
    start = end - timedelta(days=days_back + 250)  # extra for SMA-200
    hist = yf.Ticker(ticker).history(start=start.strftime("%Y-%m-%d"), end=end.strftime("%Y-%m-%d"))
    if hist.empty or len(hist) < 100:
        return {"error": f"Insufficient data for {ticker}"}

    closes = hist["Close"].values.astype(float)
    dates = hist.index

    # Find the evaluation window (last N trading days)
    eval_start_idx = max(60, len(hist) - days_back)  # need at least 60 bars for indicators
    eval_step = max(1, hold_days)

    trades = []
    equity = [10000.0]  # start with $10k
    buy_hold_start = float(closes[eval_start_idx])

    fundamentals = fetch_fundamentals_av(ticker) or {}
    fund_score = _score_fundamentals(fundamentals)

    for i in range(eval_start_idx, len(hist) - hold_days, eval_step):
        # Slice history up to this point
        hist_slice = hist.iloc[:i + 1]
        try:
            indicators = compute_indicators(hist_slice)
        except Exception:
            continue

        # Generate signal (simplified version of the full pipeline)
        signal, score = _generate_signal(indicators, fund_score, closes[:i + 1])

        # Measure actual outcome
        entry_price = float(closes[i])
        exit_price = float(closes[min(i + hold_days, len(closes) - 1)])
        actual_return = (exit_price - entry_price) / entry_price

        # Was the signal correct?
        correct = (signal == "BUY" and actual_return > 0) or \
                  (signal == "SELL" and actual_return < 0) or \
                  signal == "HOLD"

        # Update equity
        if signal == "BUY":
            pnl = equity[-1] * actual_return * 0.5  # invest 50% of equity
        elif signal == "SELL":
            pnl = equity[-1] * (-actual_return) * 0.3  # short 30%
        else:
            pnl = 0
        equity.append(equity[-1] + pnl)

        trades.append({
            "date": dates[i].strftime("%Y-%m-%d"),
            "signal": signal,
            "score": round(score, 4),
            "entry_price": round(entry_price, 2),
            "exit_price": round(exit_price, 2),
            "return_pct": round(actual_return * 100, 2),
            "correct": correct,
            "equity": round(equity[-1], 2),
        })

    if not trades:
        return {"error": "No trades generated"}

    # Performance metrics
    returns = [t["return_pct"] / 100 for t in trades if t["signal"] != "HOLD"]
    buy_hold_end = float(closes[-1])
    buy_hold_return = (buy_hold_end - buy_hold_start) / buy_hold_start

    total_trades = len([t for t in trades if t["signal"] != "HOLD"])
    wins = len([t for t in trades if t["correct"] and t["signal"] != "HOLD"])
    win_rate = wins / max(total_trades, 1)

    sharpe = 0.0
    if returns:
        avg_ret = np.mean(returns)
        std_ret = np.std(returns)
        sharpe = round((avg_ret / max(std_ret, 1e-9)) * np.sqrt(252 / hold_days), 2)

    equity_arr = np.array(equity)
    peak = np.maximum.accumulate(equity_arr)
    drawdowns = (equity_arr - peak) / peak
    max_dd = round(float(drawdowns.min()) * 100, 2)

    strategy_return = (equity[-1] - equity[0]) / equity[0]

    return {
        "ticker": ticker,
        "days_back": days_back,
        "hold_days": hold_days,
        "total_signals": len(trades),
        "total_trades": total_trades,
        "wins": wins,
        "win_rate": round(win_rate * 100, 1),
        "sharpe_ratio": sharpe,
        "max_drawdown_pct": max_dd,
        "strategy_return_pct": round(strategy_return * 100, 2),
        "buy_hold_return_pct": round(buy_hold_return * 100, 2),
        "final_equity": round(equity[-1], 2),
        "trades": trades,
        "equity_curve": [round(e, 2) for e in equity],
        "equity_dates": [trades[0]["date"]] + [t["date"] for t in trades],
    }


def _generate_signal(indicators: dict, fund_score: float, closes: np.ndarray) -> tuple:
    """Simplified signal generator matching the decision agent logic."""
    buy_thresh = config.get("decision", "buy_threshold", 0.15)
    sell_thresh = config.get("decision", "sell_threshold", -0.15)

    # Technical score
    signals = [
        1 if indicators["rsi_signal"] == "oversold" else (-1 if indicators["rsi_signal"] == "overbought" else 0),
        1 if indicators["macd_direction"] == "bullish" else -1,
        1 if indicators["price_vs_sma50"] == "bullish" else -1,
    ]
    tech_score = sum(signals) / 3

    # Trend
    sma20 = np.convolve(closes, np.ones(min(20, len(closes))) / min(20, len(closes)), mode="valid")
    slope = (sma20[-1] - sma20[-min(5, len(sma20))]) / max(sma20[-min(5, len(sma20))], 1e-9)
    trend_score = 1 if slope > 0.01 else (-1 if slope < -0.01 else 0)

    # Composite
    score = 0.30 * tech_score + 0.25 * fund_score + 0.15 * trend_score

    if score > buy_thresh:
        return "BUY", score
    elif score < sell_thresh:
        return "SELL", score
    return "HOLD", score


def _score_fundamentals(data: dict) -> float:
    """Score fundamentals -1 to +1 (simplified)."""
    scores = []
    pe = data.get("pe_ratio")
    if pe is not None:
        scores.append(1 if pe < 15 else (-1 if pe > 30 else 0))
    margin = data.get("profit_margin")
    if margin is not None:
        scores.append(1 if margin > 0.15 else (-1 if margin < 0 else 0))
    growth = data.get("revenue_growth")
    if growth is not None:
        scores.append(1 if growth > 0.10 else (-1 if growth < 0 else 0))
    return (sum(scores) / max(len(scores), 1)) / 4  # normalise to small range
