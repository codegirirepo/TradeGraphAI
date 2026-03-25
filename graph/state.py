"""Shared state schema for the LangGraph stock analysis pipeline."""

from typing import TypedDict


class GraphState(TypedDict, total=False):
    ticker: str
    market_data: dict       # price history, trend info
    technicals: dict        # RSI, MACD, SMA signals
    fundamentals: dict      # P/E, revenue, margins
    sentiment: dict         # news sentiment scores
    risk: dict              # volatility, stop-loss, position sizing
    decision: str           # final BUY / SELL / HOLD output
    confidence: float       # 0-1 confidence score
    logs: list              # per-step audit trail
    _sentiment_retried: bool  # internal flag for retry routing
    portfolio_value: float      # user-configurable portfolio size
    execution: dict              # broker execution result
