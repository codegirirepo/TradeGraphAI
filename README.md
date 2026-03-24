# TradeGraphAI

A production-ready multi-agent stock market analysis system built with **LangGraph** and **LangChain**. Uses a hedge-fund-style pipeline of specialized AI agents to generate BUY / SELL / HOLD recommendations — entirely with open-source tools and free APIs.

![Python](https://img.shields.io/badge/Python-3.10%2B-blue)
![LangGraph](https://img.shields.io/badge/LangGraph-Stateful%20Orchestration-green)
![License](https://img.shields.io/badge/License-MIT-yellow)

## Architecture

```
                        +----------------+
                        |  Orchestrator  |
                        +-------+--------+
                                |
                        +-------v--------+
                        | Market Research|  <-- yfinance (price data, trend detection)
                        +-------+--------+
                                |
                        +-------v--------+
                        |   Technical    |  <-- RSI, MACD, SMA via ta library
                        +-------+--------+
                                |
                        +-------v--------+
                        |  Fundamental   |  <-- P/E, margins, revenue (yfinance + Alpha Vantage)
                        +-------+--------+
                                |
                        +-------v--------+
                        |   Sentiment    |  <-- News headlines + FinBERT scoring
                        +---+---+--------+
                            |   |
               missing?     |   | ok
            +---------------+   +----------+
            | retry once                   |
            +------------------------------+
                                |
                        +-------v--------+
                        |     Risk       |  <-- Volatility, VaR, stop-loss, position sizing
                        +---+---+--------+
                            |   |
               high risk    |   | ok
            (fast-track)    |   |
            +---------------+---+----------+
                                |
                        +-------v--------+
                        |    Decision    |  <-- Weighted signal combination
                        +-------+--------+
                                |
                          BUY / SELL / HOLD
```

### Conditional Routing

- **Sentiment retry**: If no news headlines are found, the sentiment agent retries once before defaulting to neutral
- **High-risk fast-track**: If the risk agent classifies a stock as high risk, the pipeline fast-tracks to the decision agent which forces a HOLD

## Agents

| Agent | Role | Data Source |
|-------|------|-------------|
| **Orchestrator** | Initializes pipeline state, coordinates flow | — |
| **Market Research** | Fetches price history, detects trend (bullish/bearish/sideways) | yfinance |
| **Technical Analysis** | Computes RSI, MACD, SMA-20/50/200, derives aggregate signal | ta library |
| **Fundamental Analysis** | Evaluates P/E, margins, revenue growth, debt-to-equity | yfinance, Alpha Vantage |
| **Sentiment Analysis** | Scores news headlines using FinBERT NLP model | Finnhub, NewsAPI, yfinance news |
| **Risk Management** | Calculates volatility, VaR, max drawdown, stop-loss, position sizing | Computed from price data |
| **Decision** | Combines all signals with weighted scoring into final verdict | All agent outputs |

### Decision Weights

| Signal | Weight |
|--------|--------|
| Technical | 30% |
| Fundamental | 25% |
| Sentiment | 20% |
| Trend | 15% |
| Risk | 10% |

## Project Structure

```
TradeGraphAI/
├── agents/
│   ├── market_agent.py         # Price data + trend detection
│   ├── technical_agent.py      # RSI, MACD, SMA signals
│   ├── fundamental_agent.py    # Valuation & profitability scoring
│   ├── sentiment_agent.py      # News sentiment via FinBERT
│   ├── risk_agent.py           # Volatility, stop-loss, position sizing
│   └── decision_agent.py       # Weighted signal -> BUY/SELL/HOLD
├── tools/
│   ├── data_fetcher.py         # yfinance + API integrations with retry logic
│   ├── indicators.py           # Technical indicator computation (ta library)
│   └── sentiment_scorer.py     # FinBERT pipeline (ProsusAI/finbert)
├── graph/
│   ├── state.py                # GraphState TypedDict
│   └── builder.py              # LangGraph StateGraph with conditional edges
├── main.py                     # CLI entry point + run_analysis()
├── requirements.txt
├── .env.example                # Optional API keys template
└── .gitignore
```

## Quick Start

### 1. Clone & Install

```bash
git clone https://github.com/codegirirepo/TradeGraphAI.git
cd TradeGraphAI
pip install -r requirements.txt
```

### 2. (Optional) Configure API Keys

```bash
cp .env.example .env
```

Edit `.env` to add keys for enhanced data coverage. **The system works fully without any API keys** — yfinance provides all core data for free.

| Key | Source | Benefit |
|-----|--------|---------|
| `FINNHUB_API_KEY` | [finnhub.io](https://finnhub.io/) | More news headlines |
| `NEWSAPI_KEY` | [newsapi.org](https://newsapi.org/) | Additional news sources |
| `ALPHA_VANTAGE_API_KEY` | [alphavantage.co](https://www.alphavantage.co/) | Fallback fundamentals |

### 3. Run

```bash
# Single stock
python main.py AAPL

# Multiple stocks (portfolio scan)
python main.py AAPL MSFT TSLA NVDA GOOGL
```

## Example Output

```json
{
  "ticker": "AAPL",
  "name": "Apple Inc.",
  "decision": "SELL",
  "confidence": 0.37,
  "risk_level": "low",
  "summary": "Recommendation for AAPL: **SELL**. at $253.94 (bearish trend). Technical outlook is bearish (RSI 44.44). Fundamentals rated mixed. Market sentiment is neutral. Risk level: low (vol 0.2106). Suggested stop-loss: $247.2.",
  "details": {
    "price": 253.94,
    "trend": "bearish",
    "rsi": 44.44,
    "macd_direction": "bearish",
    "technical_signal": "bearish",
    "fundamental_rating": "mixed",
    "pe_ratio": 32.14,
    "sentiment_label": "neutral",
    "sentiment_score": 0.0,
    "volatility": 0.2106,
    "stop_loss": 247.2,
    "position_size": 148
  }
}
```

### Portfolio Summary

```
============================================================
  PORTFOLIO SUMMARY
============================================================
  AAPL   -> SELL   (confidence: 37%, risk: low)
  MSFT   -> HOLD   (confidence: 20%, risk: high)
  TSLA   -> SELL   (confidence: 82%, risk: medium)
  NVDA   -> SELL   (confidence: 45%, risk: medium)
  GOOGL  -> HOLD   (confidence: 18%, risk: low)
```

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Orchestration | LangGraph StateGraph |
| Framework | LangChain |
| Stock Data | yfinance |
| Technical Indicators | ta (Technical Analysis library) |
| Sentiment Model | FinBERT (ProsusAI/finbert) via HuggingFace Transformers |
| Data Processing | pandas, numpy |
| API Calls | requests with retry decorator |

## How It Works

1. **Orchestrator** initializes the shared state with the target ticker
2. **Market Research** pulls 6 months of OHLCV data from yfinance and detects the price trend
3. **Technical Analysis** computes RSI, MACD, and SMA indicators, then derives an aggregate bullish/bearish signal
4. **Fundamental Analysis** evaluates valuation (P/E), profitability (margins), growth (revenue), and leverage (debt-to-equity)
5. **Sentiment Analysis** fetches news headlines and scores them using the FinBERT financial NLP model
6. **Risk Management** calculates annualized volatility, Value-at-Risk (95%), max drawdown, stop-loss price, and position size
7. **Decision Agent** combines all signals using weighted scoring to produce a final BUY / SELL / HOLD with confidence level

## Programmatic Usage

```python
from main import run_analysis

result = run_analysis("AAPL")
print(result["decision"])     # "BUY", "SELL", or "HOLD"
print(result["confidence"])   # 0.0 - 1.0
print(result["risk_level"])   # "low", "medium", or "high"
print(result["summary"])      # Human-readable summary
```

## Disclaimer

This tool is for **educational and research purposes only**. It does not constitute financial advice. Always do your own research and consult a qualified financial advisor before making investment decisions.

## License

MIT
