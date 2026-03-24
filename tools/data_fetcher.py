"""Data fetching utilities — yfinance, news APIs, Alpha Vantage.

All functions include retry logic and graceful failure handling.
"""

import os, time, logging
from datetime import datetime, timedelta
from functools import wraps

import yfinance as yf
import requests
import pandas as pd

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Retry decorator
# ---------------------------------------------------------------------------

def retry(max_retries: int = 3, delay: float = 1.0):
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            last_exc = None
            for attempt in range(1, max_retries + 1):
                try:
                    return fn(*args, **kwargs)
                except Exception as e:
                    last_exc = e
                    logger.warning(f"{fn.__name__} attempt {attempt} failed: {e}")
                    time.sleep(delay * attempt)
            logger.error(f"{fn.__name__} failed after {max_retries} retries")
            return None
        return wrapper
    return decorator

# ---------------------------------------------------------------------------
# Stock price data via yfinance
# ---------------------------------------------------------------------------

@retry()
def fetch_stock_data(ticker: str, period: str = "6mo") -> dict:
    """Return OHLCV history + basic info for *ticker*."""
    stock = yf.Ticker(ticker)
    hist = stock.history(period=period)
    if hist.empty:
        raise ValueError(f"No data returned for {ticker}")
    info = stock.info or {}
    return {
        "history": hist,
        "current_price": float(hist["Close"].iloc[-1]),
        "currency": info.get("currency", "USD"),
        "name": info.get("shortName", ticker),
        "sector": info.get("sector", "Unknown"),
        "industry": info.get("industry", "Unknown"),
    }

# ---------------------------------------------------------------------------
# Fundamental data — yfinance first, Alpha Vantage as fallback
# ---------------------------------------------------------------------------

@retry()
def fetch_fundamentals_av(ticker: str) -> dict:
    """Pull fundamental metrics. Uses yfinance; falls back to Alpha Vantage."""
    stock = yf.Ticker(ticker)
    info = stock.info or {}

    fundamentals = {
        "pe_ratio": info.get("trailingPE"),
        "forward_pe": info.get("forwardPE"),
        "peg_ratio": info.get("pegRatio"),
        "price_to_book": info.get("priceToBook"),
        "revenue": info.get("totalRevenue"),
        "revenue_growth": info.get("revenueGrowth"),
        "profit_margin": info.get("profitMargins"),
        "operating_margin": info.get("operatingMargins"),
        "roe": info.get("returnOnEquity"),
        "debt_to_equity": info.get("debtToEquity"),
        "free_cash_flow": info.get("freeCashflow"),
        "dividend_yield": info.get("dividendYield"),
        "market_cap": info.get("marketCap"),
        "beta": info.get("beta"),
    }

    # Alpha Vantage fallback for missing P/E
    av_key = os.getenv("ALPHA_VANTAGE_API_KEY")
    if fundamentals["pe_ratio"] is None and av_key and av_key != "your_key_here":
        try:
            url = (
                f"https://www.alphavantage.co/query?function=OVERVIEW"
                f"&symbol={ticker}&apikey={av_key}"
            )
            data = requests.get(url, timeout=10).json()
            fundamentals["pe_ratio"] = _safe_float(data.get("TrailingPE"))
            fundamentals["forward_pe"] = _safe_float(data.get("ForwardPE"))
            fundamentals["peg_ratio"] = _safe_float(data.get("PEGRatio"))
            fundamentals["profit_margin"] = _safe_float(data.get("ProfitMargin"))
            fundamentals["roe"] = _safe_float(data.get("ReturnOnEquityTTM"))
        except Exception as e:
            logger.warning(f"Alpha Vantage fallback failed: {e}")

    return fundamentals


def _safe_float(val):
    try:
        return float(val) if val and val != "None" else None
    except (ValueError, TypeError):
        return None

# ---------------------------------------------------------------------------
# News headlines — Finnhub → NewsAPI → yfinance fallback
# ---------------------------------------------------------------------------

@retry()
def fetch_news_headlines(ticker: str, max_articles: int = 20) -> list[dict]:
    """Return list of {title, source, url, published} dicts."""
    headlines = _try_finnhub(ticker, max_articles)
    if not headlines:
        headlines = _try_newsapi(ticker, max_articles)
    if not headlines:
        headlines = _try_yfinance_news(ticker, max_articles)
    return headlines or []


def _try_finnhub(ticker: str, limit: int) -> list[dict] | None:
    key = os.getenv("FINNHUB_API_KEY")
    if not key or key == "your_key_here":
        return None
    try:
        today = datetime.now().strftime("%Y-%m-%d")
        week_ago = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
        url = (
            f"https://finnhub.io/api/v1/company-news"
            f"?symbol={ticker}&from={week_ago}&to={today}&token={key}"
        )
        resp = requests.get(url, timeout=10).json()
        return [
            {"title": a["headline"], "source": a.get("source", ""), "url": a.get("url", ""),
             "published": a.get("datetime", "")}
            for a in resp[:limit]
        ] if resp else None
    except Exception as e:
        logger.warning(f"Finnhub failed: {e}")
        return None


def _try_newsapi(ticker: str, limit: int) -> list[dict] | None:
    key = os.getenv("NEWSAPI_KEY")
    if not key or key == "your_key_here":
        return None
    try:
        url = (
            f"https://newsapi.org/v2/everything"
            f"?q={ticker}+stock&sortBy=publishedAt&pageSize={limit}&apiKey={key}"
        )
        data = requests.get(url, timeout=10).json()
        articles = data.get("articles", [])
        return [
            {"title": a["title"], "source": a["source"]["name"],
             "url": a["url"], "published": a["publishedAt"]}
            for a in articles
        ] if articles else None
    except Exception as e:
        logger.warning(f"NewsAPI failed: {e}")
        return None


def _try_yfinance_news(ticker: str, limit: int) -> list[dict] | None:
    """Last-resort: pull news from yfinance (always available)."""
    try:
        stock = yf.Ticker(ticker)
        news = stock.news or []
        return [
            {"title": n.get("title", ""), "source": n.get("publisher", ""),
             "url": n.get("link", ""), "published": n.get("providerPublishTime", "")}
            for n in news[:limit]
        ]
    except Exception as e:
        logger.warning(f"yfinance news failed: {e}")
        return None
