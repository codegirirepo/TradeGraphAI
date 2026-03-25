"""Macro Intelligence Agent — analyzes global news, geopolitics, and macro factors
to recommend stocks and sectors.

Uses free data sources:
  - yfinance market indices (S&P 500, VIX, Treasury yields, Oil, Gold, USD)
  - News headlines via existing fetcher
  - FinBERT for macro sentiment scoring
"""

import logging
from datetime import datetime

import yfinance as yf
import numpy as np

from tools.data_fetcher import retry
from tools.sentiment_scorer import score_sentiment

logger = logging.getLogger(__name__)

# Macro indicators to track
MACRO_TICKERS = {
    "^GSPC": "S&P 500",
    "^VIX": "VIX (Fear Index)",
    "^TNX": "10Y Treasury Yield",
    "CL=F": "Crude Oil",
    "GC=F": "Gold",
    "DX-Y.NYB": "US Dollar Index",
    "^IXIC": "NASDAQ",
    "^DJI": "Dow Jones",
}

# Theme -> sector/stock mapping
THEME_MAP = {
    "rate_cut": {
        "label": "Interest Rate Cut Expected",
        "bullish": ["Technology", "Real Estate", "Consumer Cyclical"],
        "bearish": ["Financial Services"],
        "stocks": ["AAPL", "MSFT", "GOOGL", "AMZN", "META", "CRM", "ADBE"],
        "reason": "Lower rates boost growth stocks and reduce borrowing costs",
    },
    "rate_hike": {
        "label": "Interest Rate Hike Expected",
        "bullish": ["Financial Services", "Energy"],
        "bearish": ["Technology", "Real Estate"],
        "stocks": ["JPM", "GS", "BAC", "WFC", "XOM", "CVX"],
        "reason": "Higher rates benefit banks via wider margins",
    },
    "recession_fear": {
        "label": "Recession Fears Rising",
        "bullish": ["Consumer Defensive", "Healthcare", "Utilities"],
        "bearish": ["Consumer Cyclical", "Technology"],
        "stocks": ["JNJ", "PG", "KO", "PEP", "WMT", "COST", "UNH"],
        "reason": "Defensive sectors outperform during economic downturns",
    },
    "oil_spike": {
        "label": "Oil Price Surge",
        "bullish": ["Energy"],
        "bearish": ["Consumer Cyclical", "Industrials"],
        "stocks": ["XOM", "CVX", "COP", "SLB", "EOG"],
        "reason": "Energy companies benefit directly from higher oil prices",
    },
    "tech_rally": {
        "label": "Technology Sector Rally",
        "bullish": ["Technology", "Communication Services"],
        "bearish": [],
        "stocks": ["NVDA", "AAPL", "MSFT", "GOOGL", "META", "AMD", "AVGO"],
        "reason": "Strong tech earnings and AI momentum driving sector higher",
    },
    "geopolitical_tension": {
        "label": "Geopolitical Tensions Elevated",
        "bullish": ["Energy", "Industrials"],
        "bearish": ["Consumer Cyclical"],
        "stocks": ["LMT", "RTX", "NOC", "GD", "XOM", "GC=F"],
        "reason": "Defense stocks and commodities rise during geopolitical uncertainty",
    },
    "dollar_weakness": {
        "label": "US Dollar Weakening",
        "bullish": ["Technology", "Industrials"],
        "bearish": [],
        "stocks": ["AAPL", "MSFT", "CAT", "DE", "BA"],
        "reason": "Weak dollar boosts multinational earnings and exports",
    },
    "inflation_high": {
        "label": "Inflation Running Hot",
        "bullish": ["Energy", "Real Estate"],
        "bearish": ["Technology", "Consumer Cyclical"],
        "stocks": ["XOM", "CVX", "AMT", "PLD", "GLD"],
        "reason": "Hard assets and commodities hedge against inflation",
    },
    "market_fear": {
        "label": "Market Fear Elevated (High VIX)",
        "bullish": ["Consumer Defensive", "Utilities", "Healthcare"],
        "bearish": ["Technology", "Consumer Cyclical"],
        "stocks": ["JNJ", "PG", "KO", "NEE", "DUK", "SO"],
        "reason": "Safe-haven sectors outperform when volatility spikes",
    },
    "ai_momentum": {
        "label": "AI / Semiconductor Momentum",
        "bullish": ["Technology"],
        "bearish": [],
        "stocks": ["NVDA", "AMD", "AVGO", "MRVL", "MSFT", "GOOGL", "META"],
        "reason": "AI infrastructure spending accelerating across the industry",
    },
}


@retry(max_retries=2)
def _fetch_macro_data() -> dict:
    """Fetch current macro indicator values and recent changes."""
    data = {}
    for ticker, name in MACRO_TICKERS.items():
        try:
            hist = yf.Ticker(ticker).history(period="1mo")
            if hist.empty:
                continue
            current = float(hist["Close"].iloc[-1])
            prev_5d = float(hist["Close"].iloc[-min(6, len(hist))])
            prev_20d = float(hist["Close"].iloc[0])
            change_5d = (current - prev_5d) / prev_5d
            change_20d = (current - prev_20d) / prev_20d
            data[ticker] = {
                "name": name,
                "current": round(current, 2),
                "change_5d_pct": round(change_5d * 100, 2),
                "change_20d_pct": round(change_20d * 100, 2),
            }
        except Exception as e:
            logger.warning(f"Failed to fetch {ticker}: {e}")
    return data


def _detect_themes(macro: dict) -> list[str]:
    """Detect active macro themes from indicator data."""
    themes = []

    vix = macro.get("^VIX", {})
    tnx = macro.get("^TNX", {})
    oil = macro.get("CL=F", {})
    dollar = macro.get("DX-Y.NYB", {})
    sp500 = macro.get("^GSPC", {})
    nasdaq = macro.get("^IXIC", {})

    # VIX > 25 = fear
    if vix.get("current", 0) > 25:
        themes.append("market_fear")

    # VIX rising fast
    if vix.get("change_5d_pct", 0) > 20:
        themes.append("geopolitical_tension")

    # Treasury yield dropping = rate cut expectations
    if tnx.get("change_20d_pct", 0) < -5:
        themes.append("rate_cut")
    elif tnx.get("change_20d_pct", 0) > 10:
        themes.append("rate_hike")

    # Oil spike
    if oil.get("change_5d_pct", 0) > 8:
        themes.append("oil_spike")
    if oil.get("change_20d_pct", 0) > 15:
        themes.append("inflation_high")

    # Dollar weakness
    if dollar.get("change_20d_pct", 0) < -3:
        themes.append("dollar_weakness")

    # Tech rally
    if nasdaq.get("change_5d_pct", 0) > 3:
        themes.append("tech_rally")
    if nasdaq.get("change_20d_pct", 0) > 8:
        themes.append("ai_momentum")

    # Recession fear: S&P down + VIX up
    if sp500.get("change_20d_pct", 0) < -5 and vix.get("current", 0) > 20:
        themes.append("recession_fear")

    # Default: if no strong themes, suggest broad market
    if not themes:
        if sp500.get("change_5d_pct", 0) > 1:
            themes.append("tech_rally")
        else:
            themes.append("recession_fear")

    return list(set(themes))


def _fetch_macro_news() -> list[dict]:
    """Fetch global macro news headlines."""
    keywords = ["economy", "federal reserve", "inflation", "geopolitical", "trade war", "oil", "recession"]
    headlines = []
    for kw in keywords[:3]:  # limit to avoid rate limits
        try:
            import requests
            url = f"https://newsapi.org/v2/everything?q={kw}&sortBy=publishedAt&pageSize=5&apiKey="
            # Fall back to yfinance market news
            pass
        except Exception:
            pass

    # Use yfinance news for major indices as proxy
    for idx in ["^GSPC", "^IXIC"]:
        try:
            news = yf.Ticker(idx).news or []
            for n in news[:5]:
                headlines.append({
                    "title": n.get("title", ""),
                    "source": n.get("publisher", ""),
                })
        except Exception:
            pass
    return headlines


def get_macro_recommendations() -> dict:
    """Main entry point — analyze macro environment and recommend stocks.

    Returns:
        {
            "macro_indicators": {...},
            "active_themes": [...],
            "recommendations": [...],
            "macro_sentiment": {...},
            "timestamp": "..."
        }
    """
    logger.info("[MacroAgent] Analyzing global macro environment")

    # 1. Fetch macro data
    macro = _fetch_macro_data()

    # 2. Detect themes
    themes = _detect_themes(macro)

    # 3. Fetch and score macro news sentiment
    headlines = _fetch_macro_news()
    macro_sentiment = {"score": 0, "label": "neutral", "count": 0}
    if headlines:
        macro_sentiment = score_sentiment(headlines)

    # 4. Build recommendations
    recommendations = []
    seen_tickers = set()

    for theme_key in themes:
        theme = THEME_MAP.get(theme_key, {})
        if not theme:
            continue

        for ticker in theme.get("stocks", []):
            if ticker in seen_tickers:
                continue
            seen_tickers.add(ticker)

            # Get basic info
            try:
                info = yf.Ticker(ticker).info or {}
                name = info.get("shortName", ticker)
                price = info.get("regularMarketPrice") or info.get("currentPrice", 0)
                sector = info.get("sector", "Unknown")
            except Exception:
                name, price, sector = ticker, 0, "Unknown"

            is_bullish_sector = sector in theme.get("bullish", [])
            action = "BUY" if is_bullish_sector else "WATCH"

            recommendations.append({
                "ticker": ticker,
                "name": name,
                "price": round(float(price), 2) if price else None,
                "sector": sector,
                "action": action,
                "theme": theme.get("label", theme_key),
                "reason": theme.get("reason", ""),
                "theme_key": theme_key,
            })

    # Sort: BUY first, then by theme
    recommendations.sort(key=lambda x: (0 if x["action"] == "BUY" else 1, x["theme"]))

    return {
        "macro_indicators": macro,
        "active_themes": [{"key": t, **THEME_MAP.get(t, {"label": t})} for t in themes],
        "recommendations": recommendations[:15],  # top 15
        "macro_sentiment": macro_sentiment,
        "timestamp": datetime.now().isoformat(),
    }
