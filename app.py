"""
TradeGraphAI — Web Application
===============================
Flask server with real-time agent pipeline streaming via SSE.

Usage:
    python app.py
    Open http://localhost:5000
"""

import json, logging, uuid, threading, time, re, csv, io
from datetime import datetime
from queue import Queue

import numpy as np
import yfinance as yf
from flask import Flask, render_template, request, jsonify, Response
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from fpdf import FPDF

from main import run_analysis, run_analysis_raw
from tools.storage import save_job, complete_job, save_result, get_history
from tools.portfolio import analyze_portfolio_risk
from tools.backtester import run_backtest
from tools.scheduler import start_scheduler, stop_scheduler, get_scheduler_status

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
limiter = Limiter(get_remote_address, app=app, default_limits=["60 per minute"])

# In-memory job store: job_id -> {status, results, logs, progress}
_jobs: dict[str, dict] = {}
# SSE event queues per job
_event_queues: dict[str, list[Queue]] = {}

# ── Popular stocks for the selector ──────────────────────────────────────

STOCK_UNIVERSE = [
    {"ticker": "AAPL", "name": "Apple Inc."},
    {"ticker": "MSFT", "name": "Microsoft Corporation"},
    {"ticker": "GOOGL", "name": "Alphabet Inc."},
    {"ticker": "AMZN", "name": "Amazon.com Inc."},
    {"ticker": "NVDA", "name": "NVIDIA Corporation"},
    {"ticker": "TSLA", "name": "Tesla Inc."},
    {"ticker": "META", "name": "Meta Platforms Inc."},
    {"ticker": "JPM", "name": "JPMorgan Chase & Co."},
    {"ticker": "V", "name": "Visa Inc."},
    {"ticker": "JNJ", "name": "Johnson & Johnson"},
    {"ticker": "WMT", "name": "Walmart Inc."},
    {"ticker": "UNH", "name": "UnitedHealth Group"},
    {"ticker": "HD", "name": "Home Depot Inc."},
    {"ticker": "PG", "name": "Procter & Gamble Co."},
    {"ticker": "MA", "name": "Mastercard Inc."},
    {"ticker": "DIS", "name": "Walt Disney Co."},
    {"ticker": "NFLX", "name": "Netflix Inc."},
    {"ticker": "ADBE", "name": "Adobe Inc."},
    {"ticker": "CRM", "name": "Salesforce Inc."},
    {"ticker": "INTC", "name": "Intel Corporation"},
    {"ticker": "AMD", "name": "Advanced Micro Devices"},
    {"ticker": "PYPL", "name": "PayPal Holdings Inc."},
    {"ticker": "BA", "name": "Boeing Co."},
    {"ticker": "NKE", "name": "Nike Inc."},
    {"ticker": "COST", "name": "Costco Wholesale Corp."},
]

# ── Helpers ──────────────────────────────────────────────────────────────

def _send_event(job_id: str, event: str, data: dict):
    """Push an SSE event to all listeners for a job."""
    msg = json.dumps(data, default=str)
    for q in _event_queues.get(job_id, []):
        q.put(f"event: {event}\ndata: {msg}\n\n")


def _run_job(job_id: str, tickers: list[str], portfolio_value: float = 100_000):
    """Background worker — runs analysis for each ticker sequentially."""
    job = _jobs[job_id]
    total = len(tickers)
    raw_states = []  # for portfolio correlation

    for i, ticker in enumerate(tickers, 1):
        job["current"] = ticker
        _send_event(job_id, "progress", {
            "ticker": ticker,
            "step": i,
            "total": total,
            "message": f"Analyzing {ticker} ({i}/{total})..."
        })

        try:
            t_start = time.time()
            result, state = run_analysis_raw(ticker, portfolio_value=portfolio_value)
            elapsed = round(time.time() - t_start, 1)
            if "details" not in result:
                result["details"] = {}

            # Attach chart data (price history as serializable lists)
            hist = state.get("market_data", {}).get("history")
            if hist is not None and not hist.empty:
                result["chart_data"] = {
                    "dates": [d.strftime("%Y-%m-%d") for d in hist.index],
                    "close": [round(float(v), 2) for v in hist["Close"].values],
                    "volume": [int(v) for v in hist["Volume"].values],
                    "sma_20": _sma(hist["Close"].values, 20),
                    "sma_50": _sma(hist["Close"].values, 50),
                }

            # Attach sentiment details
            sent = state.get("sentiment", {})
            if sent.get("details"):
                result["sentiment_details"] = sent["details"]

            result["elapsed_seconds"] = elapsed
            job["results"].append(result)
            raw_states.append({
                "ticker": ticker,
                "_history": state.get("market_data", {}).get("history"),
                "_sector": state.get("market_data", {}).get("sector", "Unknown"),
            })
            save_result(job_id, result)
            _send_event(job_id, "result", result)
        except Exception as e:
            logger.error(f"Analysis failed for {ticker}: {e}")
            err = {"ticker": ticker, "decision": "ERROR", "error": str(e),
                   "confidence": 0, "risk_level": "unknown", "summary": f"Analysis failed: {e}"}
            job["results"].append(err)
            save_result(job_id, err)
            _send_event(job_id, "result", err)

    # Portfolio-level risk analysis
    portfolio_risk = {}
    if len(raw_states) >= 2:
        portfolio_risk = analyze_portfolio_risk(raw_states)

    job["status"] = "completed"
    job["completed_at"] = datetime.now().isoformat()
    job["portfolio_risk"] = portfolio_risk
    complete_job(job_id)
    _send_event(job_id, "done", {
        "message": "All analyses complete", "total": total,
        "portfolio_risk": portfolio_risk,
    })


def _sma(data, window):
    """Compute SMA and return as list with None padding."""
    if len(data) < window:
        return [None] * len(data)
    sma = np.convolve(data, np.ones(window) / window, mode="valid")
    pad = [None] * (window - 1)
    return pad + [round(float(v), 2) for v in sma]


# ── Routes ───────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html", stocks=STOCK_UNIVERSE)


@app.route("/api/analyze", methods=["POST"])
@limiter.limit("5 per minute")
def analyze():
    """Start an analysis job. Expects JSON: {"tickers": ["AAPL", "MSFT"]}"""
    data = request.get_json(force=True)
    tickers = data.get("tickers", [])
    portfolio_value = data.get("portfolio_value", 100_000)

    if not tickers:
        return jsonify({"error": "No tickers provided"}), 400
    if len(tickers) > 10:
        return jsonify({"error": "Maximum 10 tickers per request"}), 400

    # Clean input
    tickers = [t.upper().strip() for t in tickers if t.strip()]

    # Validate ticker format
    invalid = [t for t in tickers if not re.match(r'^[A-Z]{1,5}$', t)]
    if invalid:
        return jsonify({"error": f"Invalid ticker(s): {', '.join(invalid)}"}), 400

    # Validate tickers exist on yfinance
    bad = []
    for t in tickers:
        try:
            info = yf.Ticker(t).info
            if not info or info.get("regularMarketPrice") is None:
                bad.append(t)
        except Exception:
            bad.append(t)
    if bad:
        return jsonify({"error": f"Ticker(s) not found: {', '.join(bad)}"}), 400

    job_id = str(uuid.uuid4())[:8]
    _jobs[job_id] = {
        "id": job_id,
        "tickers": tickers,
        "status": "running",
        "results": [],
        "current": None,
        "started_at": datetime.now().isoformat(),
    }
    _event_queues[job_id] = []
    save_job(job_id, tickers)

    thread = threading.Thread(target=_run_job, args=(job_id, tickers, portfolio_value), daemon=True)
    thread.start()

    return jsonify({"job_id": job_id, "tickers": tickers, "status": "running"})


@app.route("/api/stream/<job_id>")
def stream(job_id):
    """SSE endpoint — streams real-time progress and results."""
    if job_id not in _jobs:
        return jsonify({"error": "Job not found"}), 404

    q = Queue()
    _event_queues.setdefault(job_id, []).append(q)

    def generate():
        try:
            while True:
                msg = q.get(timeout=120)
                yield msg
                if '"All analyses complete"' in msg:
                    break
        except Exception:
            pass
        finally:
            _event_queues.get(job_id, []).remove(q) if q in _event_queues.get(job_id, []) else None

    return Response(generate(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.route("/api/job/<job_id>")
def get_job(job_id):
    """Poll endpoint — returns current job state."""
    job = _jobs.get(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    return jsonify(job)


@app.route("/api/history")
def history_api():
    """Return recent analysis history from SQLite."""
    limit = request.args.get("limit", 50, type=int)
    return jsonify(get_history(limit))


@app.route("/api/export/csv")
def export_csv():
    """Export analysis history as CSV download."""
    rows = get_history(500)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Date", "Ticker", "Decision", "Confidence", "Risk Level", "Summary"])
    for r in rows:
        writer.writerow([
            r.get("created_at", ""), r.get("ticker", ""), r.get("decision", ""),
            r.get("confidence", ""), r.get("risk_level", ""), r.get("summary", ""),
        ])
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=tradegraph_history.csv"},
    )


@app.route("/api/export/pdf/<job_id>")
def export_pdf(job_id):
    """Generate a professional PDF report for a completed job."""
    job = _jobs.get(job_id)
    if not job or job["status"] != "completed":
        return jsonify({"error": "Job not found or not completed"}), 404

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    # Title
    pdf.set_font("Helvetica", "B", 20)
    pdf.cell(0, 12, "TradeGraphAI Analysis Report", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(120, 120, 120)
    pdf.cell(0, 6, f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}  |  Tickers: {', '.join(job['tickers'])}",
             new_x="LMARGIN", new_y="NEXT")
    pdf.ln(8)

    # Summary table
    pdf.set_text_color(0, 0, 0)
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 8, "Portfolio Summary", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "B", 9)
    col_w = [25, 25, 25, 25, 85]
    headers = ["Ticker", "Decision", "Confidence", "Risk", "Summary"]
    for i, h in enumerate(headers):
        pdf.cell(col_w[i], 7, h, border=1)
    pdf.ln()

    pdf.set_font("Helvetica", "", 8)
    for r in job["results"]:
        conf = f"{round(r.get('confidence', 0) * 100)}%"
        summary = (r.get("summary", "") or "")[:80]
        pdf.cell(col_w[0], 6, r.get("ticker", ""), border=1)
        pdf.cell(col_w[1], 6, r.get("decision", ""), border=1)
        pdf.cell(col_w[2], 6, conf, border=1)
        pdf.cell(col_w[3], 6, r.get("risk_level", ""), border=1)
        pdf.cell(col_w[4], 6, summary, border=1)
        pdf.ln()

    # Detail sections
    for r in job["results"]:
        pdf.add_page()
        pdf.set_font("Helvetica", "B", 14)
        pdf.cell(0, 10, f"{r.get('ticker', '?')} - {r.get('name', '')}", new_x="LMARGIN", new_y="NEXT")

        d = r.get("details", {})
        pdf.set_font("Helvetica", "", 9)
        metrics = [
            ("Decision", r.get("decision")), ("Confidence", f"{round(r.get('confidence', 0) * 100)}%"),
            ("Price", f"${d.get('price', 0):.2f}" if d.get('price') else "N/A"),
            ("Trend", d.get("trend")), ("RSI", d.get("rsi")),
            ("MACD", d.get("macd_direction")), ("Technical", d.get("technical_signal")),
            ("Fundamental", d.get("fundamental_rating")), ("P/E", d.get("pe_ratio")),
            ("Sentiment", d.get("sentiment_label")), ("Volatility", d.get("volatility")),
            ("Risk", r.get("risk_level")), ("Stop-Loss", f"${d.get('stop_loss')}" if d.get('stop_loss') else "N/A"),
            ("Position Size", f"{d.get('position_size')} shares" if d.get('position_size') else "N/A"),
        ]
        for label, val in metrics:
            pdf.cell(45, 6, f"{label}:", border=0)
            pdf.cell(0, 6, str(val or "N/A"), new_x="LMARGIN", new_y="NEXT")

        pdf.ln(4)
        pdf.set_font("Helvetica", "I", 8)
        pdf.multi_cell(0, 5, r.get("summary", ""))

    # Footer
    pdf.set_font("Helvetica", "I", 7)
    pdf.set_text_color(150, 150, 150)
    pdf.cell(0, 10, "Disclaimer: For educational purposes only. Not financial advice.",
             new_x="LMARGIN", new_y="NEXT")

    buf = io.BytesIO()
    pdf.output(buf)
    buf.seek(0)
    return Response(
        buf.getvalue(),
        mimetype="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=TradeGraphAI_Report_{job_id}.pdf"},
    )


@app.route("/api/backtest", methods=["POST"])
@limiter.limit("3 per minute")
def backtest_api():
    """Run a backtest. Expects JSON: {ticker, days_back, hold_days}"""
    data = request.get_json(force=True)
    ticker = data.get("ticker", "").upper().strip()
    days_back = data.get("days_back", 120)
    hold_days = data.get("hold_days", 5)
    if not ticker:
        return jsonify({"error": "No ticker provided"}), 400
    try:
        result = run_backtest(ticker, days_back=days_back, hold_days=hold_days)
        return jsonify(result)
    except Exception as e:
        logger.error(f"Backtest failed: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/backtest")
def backtest_page():
    return render_template("backtest.html", stocks=STOCK_UNIVERSE)


@app.route("/api/bot/start", methods=["POST"])
def bot_start():
    """Start the real-time bot. Expects JSON: {tickers, interval_minutes}"""
    data = request.get_json(force=True)
    tickers = [t.upper().strip() for t in data.get("tickers", []) if t.strip()]
    interval = data.get("interval_minutes", 15)
    if not tickers:
        return jsonify({"error": "No tickers provided"}), 400
    start_scheduler(tickers, interval_minutes=interval)
    return jsonify({"status": "started", "tickers": tickers, "interval": interval})


@app.route("/api/bot/stop", methods=["POST"])
def bot_stop():
    """Stop the real-time bot."""
    stop_scheduler()
    return jsonify({"status": "stopped"})


@app.route("/api/bot/status")
def bot_status():
    """Return current bot status and signal history."""
    return jsonify(get_scheduler_status())


@app.route("/history")
def history_page():
    return render_template("history.html")


if __name__ == "__main__":
    app.run(debug=False, port=5000, threaded=True)
