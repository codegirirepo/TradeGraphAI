"""Vector memory using ChromaDB — stores past analyses and retrieves similar contexts.

Enables the decision agent to learn from historical outcomes by querying
for similar past signals and adjusting confidence accordingly.
"""

import logging
from pathlib import Path
from datetime import datetime

import chromadb

logger = logging.getLogger(__name__)

_CHROMA_DIR = Path(__file__).resolve().parent.parent / ".cache" / "memory"
_client = None
_collection = None


def _get_collection():
    global _client, _collection
    if _collection is None:
        _client = chromadb.PersistentClient(path=str(_CHROMA_DIR))
        _collection = _client.get_or_create_collection(
            name="analysis_memory",
            metadata={"hnsw:space": "cosine"},
        )
    return _collection


def store_analysis(ticker: str, result: dict, state: dict):
    """Store an analysis result as a vector document for future retrieval."""
    col = _get_collection()
    details = result.get("details", {})
    doc_id = f"{ticker}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    # Build a text document from the analysis signals
    doc_text = (
        f"{ticker} {result.get('decision', 'HOLD')} "
        f"rsi={details.get('rsi', 'na')} "
        f"trend={details.get('trend', 'na')} "
        f"macd={details.get('macd_direction', 'na')} "
        f"technical={details.get('technical_signal', 'na')} "
        f"fundamental={details.get('fundamental_rating', 'na')} "
        f"pe={details.get('pe_ratio', 'na')} "
        f"sentiment={details.get('sentiment_label', 'na')} "
        f"volatility={details.get('volatility', 'na')} "
        f"risk={result.get('risk_level', 'na')}"
    )

    metadata = {
        "ticker": ticker,
        "decision": result.get("decision", "HOLD"),
        "confidence": float(result.get("confidence", 0)),
        "risk_level": result.get("risk_level", "unknown"),
        "price": float(details.get("price", 0) or 0),
        "rsi": float(details.get("rsi", 0) or 0),
        "volatility": float(details.get("volatility", 0) or 0),
        "date": datetime.now().isoformat(),
        "outcome_5d": 0.0,   # to be filled later by outcome tracker
        "outcome_20d": 0.0,
        "was_correct": False,
        "outcome_tracked": False,
    }

    try:
        col.add(documents=[doc_text], metadatas=[metadata], ids=[doc_id])
        logger.info(f"[Memory] Stored analysis for {ticker}: {result.get('decision')}")
    except Exception as e:
        logger.warning(f"[Memory] Failed to store: {e}")


def query_similar(ticker: str, details: dict, n_results: int = 5) -> list[dict]:
    """Find similar past analyses to inform the current decision."""
    col = _get_collection()

    query_text = (
        f"{ticker} "
        f"rsi={details.get('rsi', 'na')} "
        f"trend={details.get('trend', 'na')} "
        f"macd={details.get('macd_direction', 'na')} "
        f"technical={details.get('technical_signal', 'na')} "
        f"fundamental={details.get('fundamental_rating', 'na')} "
        f"sentiment={details.get('sentiment_label', 'na')} "
        f"risk={details.get('risk_level', 'na')}"
    )

    try:
        results = col.query(query_texts=[query_text], n_results=n_results)
        if not results or not results["metadatas"]:
            return []

        similar = []
        for meta, dist in zip(results["metadatas"][0], results["distances"][0]):
            similar.append({**meta, "similarity": round(1 - dist, 3)})
        return similar
    except Exception as e:
        logger.warning(f"[Memory] Query failed: {e}")
        return []


def update_outcome(doc_id: str, outcome_5d: float, outcome_20d: float, was_correct: bool):
    """Update a stored analysis with actual price outcome."""
    col = _get_collection()
    try:
        col.update(
            ids=[doc_id],
            metadatas=[{
                "outcome_5d": outcome_5d,
                "outcome_20d": outcome_20d,
                "was_correct": was_correct,
                "outcome_tracked": True,
            }],
        )
        logger.info(f"[Memory] Updated outcome for {doc_id}: 5d={outcome_5d:.2%}, correct={was_correct}")
    except Exception as e:
        logger.warning(f"[Memory] Outcome update failed: {e}")


def get_memory_stats() -> dict:
    """Return stats about the memory store."""
    col = _get_collection()
    try:
        count = col.count()
        return {"total_memories": count}
    except Exception:
        return {"total_memories": 0}
