"""
Stock Market Agentic Analysis System
=====================================
Multi-agent pipeline built with LangGraph + LangChain tooling.

Usage:
    python main.py AAPL
    python main.py MSFT GOOGL TSLA
"""

import sys, json, logging, os
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()  # load .env for optional API keys

# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

from graph.builder import build_graph

# Compile graph once at module level
_graph = build_graph()

# ---------------------------------------------------------------------------
# Core execution function
# ---------------------------------------------------------------------------

def run_analysis(ticker: str, portfolio_value: float = 100_000) -> dict:
    """Run the full multi-agent analysis pipeline for a single ticker.

    Args:
        ticker: Stock symbol (e.g. "AAPL")
        portfolio_value: Total portfolio size for position sizing

    Returns a JSON-serialisable result dict.
    """
    ticker = ticker.upper().strip()
    logger.info(f"{'='*60}")
    logger.info(f"  STARTING ANALYSIS: {ticker}")
    logger.info(f"{'='*60}")

    initial_state = {
        "ticker": ticker,
        "market_data": {},
        "technicals": {},
        "fundamentals": {},
        "sentiment": {},
        "risk": {},
        "decision": "",
        "confidence": 0.0,
        "logs": [],
        "portfolio_value": portfolio_value,
    }

    # Execute the LangGraph pipeline
    final_state = _graph.invoke(initial_state)

    # Build clean output
    risk = final_state.get("risk", {})
    market = final_state.get("market_data", {})
    technicals = final_state.get("technicals", {})
    fundamentals = final_state.get("fundamentals", {})
    sentiment = final_state.get("sentiment", {})

    result = {
        "ticker": ticker,
        "name": market.get("name", ticker),
        "decision": final_state.get("decision", "HOLD"),
        "confidence": final_state.get("confidence", 0.0),
        "risk_level": risk.get("level", "unknown"),
        "summary": _build_summary(final_state),
        "details": {
            "price": market.get("current_price"),
            "trend": market.get("trend"),
            "rsi": technicals.get("rsi"),
            "macd_direction": technicals.get("macd_direction"),
            "technical_signal": technicals.get("overall_signal"),
            "fundamental_rating": fundamentals.get("overall"),
            "pe_ratio": fundamentals.get("pe_ratio"),
            "sentiment_label": sentiment.get("label"),
            "sentiment_score": sentiment.get("score"),
            "volatility": risk.get("annual_volatility"),
            "stop_loss": risk.get("stop_loss"),
            "position_size": risk.get("position_size"),
        },
        "logs": final_state.get("logs", []),
        "timestamp": datetime.now().isoformat(),
    }
    return result


def _build_summary(state: dict) -> str:
    """Generate a human-readable one-paragraph summary."""
    d = state.get("decision", "HOLD")
    t = state.get("ticker", "?")
    market = state.get("market_data", {})
    tech = state.get("technicals", {})
    fund = state.get("fundamentals", {})
    sent = state.get("sentiment", {})
    risk = state.get("risk", {})

    parts = [f"Recommendation for {t}: **{d}**"]
    if market.get("current_price"):
        parts.append(f"at ${market['current_price']:.2f} ({market.get('trend', 'n/a')} trend)")
    if tech.get("overall_signal"):
        parts.append(f"Technical outlook is {tech['overall_signal']} (RSI {tech.get('rsi', '?')})")
    if fund.get("overall"):
        parts.append(f"Fundamentals rated {fund['overall']}")
    if sent.get("label"):
        parts.append(f"Market sentiment is {sent['label']}")
    if risk.get("level"):
        parts.append(f"Risk level: {risk['level']} (vol {risk.get('annual_volatility', '?')})")
    if risk.get("stop_loss"):
        parts.append(f"Suggested stop-loss: ${risk['stop_loss']}")

    return ". ".join(parts) + "."

# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    tickers = sys.argv[1:] if len(sys.argv) > 1 else ["AAPL"]
    all_results = []

    for t in tickers:
        try:
            result = run_analysis(t)
            all_results.append(result)
            print(f"\n{'='*60}")
            print(f"  RESULT: {t}")
            print(f"{'='*60}")
            # Print without logs for cleaner output
            clean = {k: v for k, v in result.items() if k != "logs"}
            print(json.dumps(clean, indent=2, default=str))
        except Exception as e:
            logger.error(f"Analysis failed for {t}: {e}", exc_info=True)
            all_results.append({"ticker": t, "decision": "ERROR", "error": str(e)})

    if len(all_results) > 1:
        print(f"\n{'='*60}")
        print("  PORTFOLIO SUMMARY")
        print(f"{'='*60}")
        for r in all_results:
            print(f"  {r['ticker']:6s} -> {r.get('decision', 'ERROR'):5s}  "
                  f"(confidence: {r.get('confidence', 0):.0%}, risk: {r.get('risk_level', '?')})")


if __name__ == "__main__":
    main()
