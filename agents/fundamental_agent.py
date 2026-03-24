"""Fundamental Analysis Agent — evaluates valuation, profitability, growth."""

import logging
from tools.data_fetcher import fetch_fundamentals_av

logger = logging.getLogger(__name__)


def fundamental_analysis_agent(state: dict) -> dict:
    ticker = state["ticker"]
    logger.info(f"[FundamentalAgent] Fetching fundamentals for {ticker}")

    data = fetch_fundamentals_av(ticker)
    if data is None:
        state["fundamentals"] = {"error": "fetch_failed"}
        state["logs"].append("[FundamentalAgent] FAILED to fetch fundamentals")
        return state

    # Score each dimension -1 / 0 / +1
    scores = {}

    pe = data.get("pe_ratio")
    if pe is not None:
        scores["valuation"] = 1 if pe < 15 else (-1 if pe > 30 else 0)
    else:
        scores["valuation"] = 0

    margin = data.get("profit_margin")
    if margin is not None:
        scores["profitability"] = 1 if margin > 0.15 else (-1 if margin < 0 else 0)
    else:
        scores["profitability"] = 0

    growth = data.get("revenue_growth")
    if growth is not None:
        scores["growth"] = 1 if growth > 0.10 else (-1 if growth < 0 else 0)
    else:
        scores["growth"] = 0

    dte = data.get("debt_to_equity")
    if dte is not None:
        scores["leverage"] = 1 if dte < 50 else (-1 if dte > 150 else 0)
    else:
        scores["leverage"] = 0

    net = sum(scores.values())
    overall = "strong" if net >= 2 else ("weak" if net <= -2 else "mixed")

    state["fundamentals"] = {**data, "scores": scores, "overall": overall, "net_score": net}
    state["logs"].append(f"[FundamentalAgent] P/E={pe}, margin={margin}, overall={overall}")
    return state
