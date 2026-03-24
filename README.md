# TradeGraphAI

A production-ready multi-agent stock market analysis system built with **LangGraph** and **LangChain**. Uses a hedge-fund-style pipeline of specialized AI agents to generate BUY / SELL / HOLD recommendations — entirely with open-source tools and free APIs.

![Python](https://img.shields.io/badge/Python-3.10%2B-blue)
![LangGraph](https://img.shields.io/badge/LangGraph-Stateful%20Orchestration-green)
![Flask](https://img.shields.io/badge/Flask-Web%20Dashboard-orange)
![License](https://img.shields.io/badge/License-MIT-yellow)

## Features

- **7 specialized AI agents** orchestrated via LangGraph StateGraph
- **Web dashboard** with real-time SSE streaming of agent progress
- **Interactive price charts** with SMA-20/50 overlays (Chart.js)
- **FinBERT sentiment analysis** on financial news headlines with per-headline breakdown
- **Sector-aware decision weights** (10 sector profiles)
- **Portfolio-level risk analysis** with correlation matrix and concentration warnings
- **Side-by-side stock comparison** table across all metrics
- **Watchlist** with localStorage persistence
- **Dark / Light theme** toggle
- **PDF report generation** with professional formatting
- **CSV export** of analysis history
- **Configurable via config.yaml** — all thresholds, weights, and parameters in one place
- **TTL-based caching** (diskcache) to avoid redundant API calls
- **SQLite persistence** for analysis history
- **Rate limiting** to prevent abuse
- **Ticker validation** before analysis
- **Per-agent pipeline visualization** with timing

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
| **Decision** | Combines all signals with sector-aware weighted scoring | All agent outputs |

### Decision Weights (Default)

| Signal | Weight |
|--------|--------|
| Technical | 30% |
| Fundamental | 25% |
| Sentiment | 20% |
| Trend | 15% |
| Risk | 10% |

Weights are automatically adjusted per sector (e.g. Technology weights technicals higher, Utilities weights fundamentals higher). See `config.yaml` and `agents/decision_agent.py` for all 10 sector profiles.

## Project Structure

```
TradeGraphAI/
├── agents/
│   ├── market_agent.py         # Price data + trend detection
│   ├── technical_agent.py      # RSI, MACD, SMA signals
│   ├── fundamental_agent.py    # Valuation & profitability scoring
│   ├── sentiment_agent.py      # News sentiment via FinBERT
│   ├── risk_agent.py           # Volatility, stop-loss, position sizing
│   └── decision_agent.py       # Sector-aware weighted signal -> BUY/SELL/HOLD
├── tools/
│   ├── data_fetcher.py         # yfinance + API integrations with retry + caching
│   ├── indicators.py           # Technical indicator computation (ta library)
│   ├── sentiment_scorer.py     # FinBERT pipeline (ProsusAI/finbert)
│   ├── storage.py              # SQLite persistence for jobs & results
│   └── portfolio.py            # Portfolio correlation & concentration analysis
├── graph/
│   ├── state.py                # GraphState TypedDict
│   └── builder.py              # LangGraph StateGraph with conditional edges
├── templates/
│   ├── index.html              # Main dashboard
│   └── history.html            # Analysis history page
├── static/
│   ├── css/style.css           # Dark-themed responsive styles
│   └── js/app.js               # Frontend logic + SSE streaming
├── app.py                      # Flask web server
├── main.py                     # CLI entry point + run_analysis()
├── config.py                   # Config loader
├── config.yaml                 # All tunable parameters
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

### 3. Run (CLI)

```bash
# Single stock
python main.py AAPL

# Multiple stocks (portfolio scan)
python main.py AAPL MSFT TSLA NVDA GOOGL
```

### 4. Run (Web Dashboard)

```bash
python app.py
# Open http://localhost:5000
```

## Web Dashboard

The web UI provides:
- **Glassmorphism sidebar layout** with tab-based navigation
- **Stock selector** with 25 popular tickers + custom input
- **Portfolio value input** for personalized position sizing
- **Real-time pipeline visualization** showing which agent is running with timing
- **Interactive price charts** with SMA-20/50 overlays per stock (Chart.js)
- **Result cards** with metrics, confidence bars, sentiment breakdown, and summaries
- **Side-by-side comparison table** across all analyzed stocks
- **Watchlist** — save favorite tickers (persisted in browser localStorage)
- **Portfolio risk warnings** (correlation, sector concentration)
- **Dark / Light theme toggle** (persisted in localStorage)
- **PDF report export** — professional multi-page report per job
- **CSV export** at `/api/export/csv`
- **Analysis history** page at `/history`

## Configuration

All tunable parameters are in `config.yaml`:

```yaml
portfolio:
  default_value: 100000
  risk_per_trade_pct: 0.01

decision:
  buy_threshold: 0.15
  sell_threshold: -0.15

risk:
  high_volatility: 0.50
  medium_volatility: 0.30
  stop_loss_multiplier: 2

sentiment:
  bullish_threshold: 0.15
  max_retries: 2

cache:
  ttl_seconds: 900
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
| Web Server | Flask + SSE |
| Stock Data | yfinance |
| Technical Indicators | ta (Technical Analysis library) |
| Sentiment Model | FinBERT (ProsusAI/finbert) via HuggingFace Transformers |
| Data Processing | pandas, numpy |
| Charts | Chart.js |
| PDF Reports | fpdf2 |
| Caching | diskcache (TTL-based) |
| Storage | SQLite |
| Rate Limiting | Flask-Limiter |
| API Calls | requests with retry decorator |

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Main dashboard |
| `/history` | GET | Analysis history page |
| `/api/analyze` | POST | Start analysis job (rate limited: 5/min) |
| `/api/stream/<job_id>` | GET | SSE stream for real-time progress |
| `/api/job/<job_id>` | GET | Poll job status |
| `/api/history` | GET | JSON history data |
| `/api/export/csv` | GET | Download history as CSV |
| `/api/export/pdf/<job_id>` | GET | Download PDF report for a job |

## Programmatic Usage

```python
from main import run_analysis

result = run_analysis("AAPL", portfolio_value=50_000)
print(result["decision"])     # "BUY", "SELL", or "HOLD"
print(result["confidence"])   # 0.0 - 1.0
print(result["risk_level"])   # "low", "medium", or "high"
print(result["summary"])      # Human-readable summary
```

## Disclaimer

This tool is for **educational and research purposes only**. It does not constitute financial advice. Always do your own research and consult a qualified financial advisor before making investment decisions.

## License

MIT
