"""
TradeGraphAI — Web Application
===============================
Flask server with real-time agent pipeline streaming via SSE.

Usage:
    python app.py
    Open http://localhost:5000
"""

import json, logging, uuid, threading, time, re
from datetime import datetime
from queue import Queue

import yfinance as yf
from flask import Flask, render_template, request, jsonify, Response
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from main import run_analysis
from tools.storage import save_job, complete_job, save_result, get_history

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


def _run_job(job_id: str, tickers: list[str]):
    """Background worker — runs analysis for each ticker sequentially."""
    job = _jobs[job_id]
    total = len(tickers)

    for i, ticker in enumerate(tickers, 1):
        job["current"] = ticker
        _send_event(job_id, "progress", {
            "ticker": ticker,
            "step": i,
            "total": total,
            "message": f"Analyzing {ticker} ({i}/{total})..."
        })

        try:
            result = run_analysis(ticker)
            if "details" not in result:
                result["details"] = {}
            job["results"].append(result)
            save_result(job_id, result)
            _send_event(job_id, "result", result)
        except Exception as e:
            logger.error(f"Analysis failed for {ticker}: {e}")
            err = {"ticker": ticker, "decision": "ERROR", "error": str(e),
                   "confidence": 0, "risk_level": "unknown", "summary": f"Analysis failed: {e}"}
            job["results"].append(err)
            save_result(job_id, err)
            _send_event(job_id, "result", err)

    job["status"] = "completed"
    job["completed_at"] = datetime.now().isoformat()
    complete_job(job_id)
    _send_event(job_id, "done", {"message": "All analyses complete", "total": total})


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

    thread = threading.Thread(target=_run_job, args=(job_id, tickers), daemon=True)
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
def history():
    """Return recent analysis history from SQLite."""
    limit = request.args.get("limit", 50, type=int)
    return jsonify(get_history(limit))


if __name__ == "__main__":
    app.run(debug=False, port=5000, threaded=True)
