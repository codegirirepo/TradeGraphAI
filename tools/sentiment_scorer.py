"""Sentiment scoring using HuggingFace transformers (FinBERT)."""

import logging
from transformers import pipeline
import config

logger = logging.getLogger(__name__)

_sentiment_pipeline = None


def _get_pipeline():
    global _sentiment_pipeline
    if _sentiment_pipeline is None:
        logger.info("Loading FinBERT sentiment model (first run downloads ~400 MB)…")
        _sentiment_pipeline = pipeline(
            "sentiment-analysis",
            model="ProsusAI/finbert",
            tokenizer="ProsusAI/finbert",
            top_k=None,
        )
    return _sentiment_pipeline


def score_sentiment(headlines: list[dict]) -> dict:
    """Score a list of headline dicts and return aggregate sentiment."""
    if not headlines:
        return {"score": 0.0, "label": "neutral", "count": 0, "details": []}

    pipe = _get_pipeline()
    titles = [h["title"] for h in headlines if h.get("title")]
    if not titles:
        return {"score": 0.0, "label": "neutral", "count": 0, "details": []}

    results = pipe(titles, truncation=True, max_length=512)

    details = []
    total_score = 0.0
    for title, preds in zip(titles, results):
        best = max(preds, key=lambda x: x["score"])
        mapped = {"positive": 1, "negative": -1, "neutral": 0}.get(best["label"], 0)
        weighted = mapped * best["score"]
        total_score += weighted
        details.append({"title": title, "label": best["label"], "score": round(best["score"], 3)})

    avg = total_score / len(titles)
    bull = config.get("sentiment", "bullish_threshold", 0.15)
    bear = config.get("sentiment", "bearish_threshold", -0.15)
    label = "bullish" if avg > bull else ("bearish" if avg < bear else "neutral")

    return {
        "score": round(avg, 4),
        "label": label,
        "count": len(titles),
        "details": details[:10],  # keep top 10 for readability
    }
