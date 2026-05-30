"""
main.py — WhaleWatch API
Daily basket refresh at 4pm EST, manual override, live individual ticker analysis.
"""

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
import yfinance as yf
import time
import threading
from datetime import datetime
from core import analyze, fetch

app = FastAPI(title="WhaleWatch Quant API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── BASKET ────────────────────────────────────────────────────────────────
# ~50 stocks across S&P 500 sectors
BASKET = [
    # Technology
    "AAPL", "MSFT", "NVDA", "AVGO", "AMD", "ORCL", "CRM", "ADBE", "QCOM", "TXN",
    # Consumer Discretionary
    "AMZN", "TSLA", "MCD", "NKE", "SBUX", "HD", "LOW",
    # Communication
    "META", "GOOGL", "NFLX", "DIS", "VZ",
    # Financials
    "JPM", "BAC", "GS", "MS", "V", "MA", "BLK",
    # Healthcare
    "JNJ", "UNH", "LLY", "PFE", "ABBV", "MRK",
    # Industrials
    "CAT", "DE", "BA", "HON", "UPS",
    # Energy
    "XOM", "CVX", "COP",
    # Materials / Utilities / Real Estate
    "LIN", "NEE", "AMT",
    # High-conviction speculative
    "PLTR", "COIN", "RKLB", "MSTR",
]

# ── STATE ─────────────────────────────────────────────────────────────────
basket_cache: dict = {}          # ticker -> result
basket_lock  = threading.Lock()
last_refresh: str  = "Never"
refresh_running    = False

# Individual ticker cache (5 min TTL)
ticker_cache: dict = {}
TICKER_TTL = 300

# ── BASKET REFRESH ────────────────────────────────────────────────────────

def refresh_basket():
    global last_refresh, refresh_running
    if refresh_running:
        return
    refresh_running = True
    print(f"[{datetime.now().isoformat()}] Refreshing basket ({len(BASKET)} tickers)…")
    try:
        spy_df = fetch("SPY")
        results = {}
        for t in BASKET:
            try:
                results[t] = analyze(t, spy_df=spy_df)
                time.sleep(0.3)   # gentle on yfinance
            except Exception as e:
                print(f"  Skipped {t}: {e}")
        with basket_lock:
            basket_cache.clear()
            basket_cache.update(results)
            last_refresh = datetime.now().isoformat()
        print(f"  Done. {len(results)}/{len(BASKET)} analysed.")
    finally:
        refresh_running = False


# ── SCHEDULER (4pm EST = 21:00 UTC) ──────────────────────────────────────
scheduler = BackgroundScheduler(timezone="UTC")
scheduler.add_job(refresh_basket, CronTrigger(hour=21, minute=0))
scheduler.start()

# Warm the cache on startup in background
threading.Thread(target=refresh_basket, daemon=True).start()

# ── ROUTES ────────────────────────────────────────────────────────────────

@app.get("/")
def root():
    return {
        "status":        "online",
        "last_refresh":  last_refresh,
        "refresh_running": refresh_running,
        "basket_size":   len(basket_cache),
        "time":          datetime.now().isoformat(),
    }


@app.get("/signal/{ticker}")
def get_signal(ticker: str):
    """Live analysis of any ticker."""
    t = ticker.upper().strip()
    # Check short-lived ticker cache
    entry = ticker_cache.get(t)
    if entry:
        result, ts = entry
        if time.time() - ts < TICKER_TTL:
            return result
    try:
        result = analyze(t)
    except Exception as e:
        raise HTTPException(404, str(e))
    ticker_cache[t] = (result, time.time())
    return result


@app.get("/top")
def get_top(limit: int = 15):
    """Ranked basket leaderboard from daily cache."""
    with basket_lock:
        items = list(basket_cache.values())
    if not items:
        raise HTTPException(503, "Basket not yet loaded — try again in a moment.")
    items.sort(key=lambda x: x["conviction"], reverse=True)

    # Attach percentile ranks
    convictions = [x["conviction"] for x in items]
    for item in items:
        below = sum(1 for c in convictions if c < item["conviction"])
        item["percentile"] = round(below / len(convictions) * 100)

    return {
        "top":          items[:limit],
        "total":        len(items),
        "last_refresh": last_refresh,
        "refresh_running": refresh_running,
    }


@app.get("/scan")
def scan(tickers: str):
    """Live scan of comma-separated tickers with percentile vs basket."""
    ticker_list = [t.strip().upper() for t in tickers.split(",") if t.strip()][:20]
    try:
        spy_df = fetch("SPY")
    except:
        spy_df = None

    results = []
    for t in ticker_list:
        try:
            r = analyze(t, spy_df=spy_df)
            results.append(r)
        except Exception as e:
            print(f"Scan skipped {t}: {e}")

    # Percentile vs basket
    with basket_lock:
        basket_convictions = [v["conviction"] for v in basket_cache.values()]

    for r in results:
        if basket_convictions:
            below = sum(1 for c in basket_convictions if c < r["conviction"])
            r["percentile"] = round(below / len(basket_convictions) * 100)
        else:
            r["percentile"] = None

    results.sort(key=lambda x: x["conviction"], reverse=True)
    return {"results": results, "scanned_at": datetime.now().isoformat()}


@app.post("/refresh")
def manual_refresh(background_tasks: BackgroundTasks):
    """Manual override — clears basket cache and reruns all tickers."""
    if refresh_running:
        return {"message": "Refresh already in progress.", "last_refresh": last_refresh}
    background_tasks.add_task(refresh_basket)
    return {"message": "Basket refresh started.", "last_refresh": last_refresh}
