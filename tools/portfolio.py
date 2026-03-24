"""Portfolio-level risk analysis — correlation matrix and concentration detection."""

import logging
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


def analyze_portfolio_risk(results: list[dict]) -> dict:
    """Compute portfolio-level risk metrics from multiple analysis results.

    Returns correlation matrix, sector concentration, and warnings.
    """
    if len(results) < 2:
        return {"warnings": [], "correlation": {}, "sector_breakdown": {}}

    # Collect price histories
    histories = {}
    sectors = {}
    for r in results:
        ticker = r.get("ticker", "?")
        hist = r.get("_history")
        if hist is not None and not hist.empty:
            histories[ticker] = hist["Close"].pct_change().dropna()
        sectors[ticker] = r.get("_sector", "Unknown")

    warnings = []

    # Correlation matrix
    correlation = {}
    if len(histories) >= 2:
        df = pd.DataFrame(histories)
        # Align on common dates
        df = df.dropna()
        if len(df) > 10:
            corr = df.corr()
            correlation = {col: {row: round(corr.loc[row, col], 3)
                                 for row in corr.index}
                           for col in corr.columns}

            # Flag highly correlated pairs
            tickers = list(corr.columns)
            for i in range(len(tickers)):
                for j in range(i + 1, len(tickers)):
                    c = corr.iloc[i, j]
                    if c > 0.8:
                        warnings.append(
                            f"High correlation ({c:.2f}) between {tickers[i]} and {tickers[j]} — "
                            f"limited diversification benefit"
                        )

    # Sector concentration
    sector_counts = {}
    for s in sectors.values():
        sector_counts[s] = sector_counts.get(s, 0) + 1

    total = len(sectors)
    for sector, count in sector_counts.items():
        pct = count / total
        if pct > 0.5 and total > 2:
            warnings.append(
                f"Sector concentration: {count}/{total} stocks ({pct:.0%}) in {sector}"
            )

    return {
        "warnings": warnings,
        "correlation": correlation,
        "sector_breakdown": sector_counts,
    }
