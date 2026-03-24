"""Sentiment Analysis Agent — fetches news headlines and scores sentiment."""

import logging
from tools.data_fetcher import fetch_news_headlines
from tools.sentiment_scorer import score_sentiment
import config

logger = logging.getLogger(__name__)


def sentiment_analysis_agent(state: dict) -> dict:
    ticker = state["ticker"]
    logger.info(f"[SentimentAgent] Analysing sentiment for {ticker}")
    max_retries = config.get("sentiment", "max_retries", 2)

    headlines = None
    for attempt in range(1, max_retries + 1):
        headlines = fetch_news_headlines(ticker)
        if headlines:
            break
        logger.warning(f"[SentimentAgent] Retry {attempt} for headlines")

    if not headlines:
        state["sentiment"] = {"score": 0.0, "label": "neutral", "count": 0, "details": [], "missing": True}
        state["logs"].append("[SentimentAgent] No headlines found — defaulting to neutral")
        return state

    result = score_sentiment(headlines)
    result["missing"] = False
    state["sentiment"] = result
    state["logs"].append(f"[SentimentAgent] score={result['score']}, label={result['label']}, articles={result['count']}")
    return state
