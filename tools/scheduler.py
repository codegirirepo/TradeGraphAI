"""Real-time trading bot scheduler — runs analysis on a configurable interval.

Only runs during US market hours (9:30 AM - 4:00 PM ET, Mon-Fri).
Detects signal changes and logs alerts.
"""

import logging
from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
import pytz

from main import run_analysis
from tools.storage import save_job, save_result, complete_job
from tools.memory import store_analysis

logger = logging.getLogger(__name__)

_scheduler = None
_watchlist: list[str] = []
_last_signals: dict[str, str] = {}  # ticker -> last decision
_signal_log: list[dict] = []  # recent signal changes

ET = pytz.timezone("US/Eastern")


def _is_market_hours() -> bool:
    """Check if current time is within US market hours."""
    now = datetime.now(ET)
    if now.weekday() >= 5:  # Saturday/Sunday
        return False
    market_open = now.replace(hour=9, minute=30, second=0, microsecond=0)
    market_close = now.replace(hour=16, minute=0, second=0, microsecond=0)
    return market_open <= now <= market_close


def _run_scheduled_scan():
    """Run analysis on all watchlist tickers."""
    if not _watchlist:
        return
    if not _is_market_hours():
        logger.info("[Scheduler] Outside market hours — skipping scan")
        return

    logger.info(f"[Scheduler] Running scan for {len(_watchlist)} tickers: {_watchlist}")

    for ticker in _watchlist:
        try:
            result = run_analysis(ticker)
            decision = result.get("decision", "HOLD")

            # Detect signal change
            prev = _last_signals.get(ticker)
            if prev and prev != decision:
                alert = {
                    "ticker": ticker,
                    "prev": prev,
                    "new": decision,
                    "confidence": result.get("confidence", 0),
                    "time": datetime.now().isoformat(),
                }
                _signal_log.append(alert)
                logger.warning(f"[Scheduler] SIGNAL CHANGE: {ticker} {prev} -> {decision}")

            _last_signals[ticker] = decision
        except Exception as e:
            logger.error(f"[Scheduler] Failed for {ticker}: {e}")


def start_scheduler(tickers: list[str], interval_minutes: int = 15):
    """Start the background scheduler."""
    global _scheduler, _watchlist
    _watchlist = [t.upper() for t in tickers]

    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)

    _scheduler = BackgroundScheduler()
    _scheduler.add_job(
        _run_scheduled_scan,
        trigger=IntervalTrigger(minutes=interval_minutes),
        id="market_scan",
        replace_existing=True,
    )
    _scheduler.start()
    logger.info(f"[Scheduler] Started — scanning {_watchlist} every {interval_minutes}min")


def stop_scheduler():
    """Stop the background scheduler."""
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("[Scheduler] Stopped")
    _scheduler = None


def get_scheduler_status() -> dict:
    """Return current scheduler state."""
    return {
        "running": _scheduler is not None and _scheduler.running if _scheduler else False,
        "watchlist": _watchlist,
        "last_signals": _last_signals,
        "signal_changes": _signal_log[-20:],
        "market_hours": _is_market_hours(),
    }
