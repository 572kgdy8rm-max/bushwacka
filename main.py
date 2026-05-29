from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from core import advanced_stats
from datetime import datetime
import asyncio
from functools import lru_cache
import time

app = FastAPI(title="WhaleWatch Supercomputer")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Simple in-memory cache: ticker -> (result, timestamp)
_cache: dict = {}
CACHE_TTL = 300  # 5 minutes

DEFAULT_WATCHLIST = [
    "NVDA", "RKLB", "TSLA", "AAPL", "MSFT",
    "GOOGL", "AMZN", "META", "AVGO", "PLTR",
    "AMD", "CRM", "SHOP", "COIN", "MSTR",
]


def get_cached(ticker: str):
    entry = _cache.get(ticker)
    if entry:
        result, ts = entry
        if time.time() - ts < CACHE_TTL:
            return result
    result = advanced_stats(ticker)
    if result:
        _cache[ticker] = (result, time.time())
    return result


@app.get("/")
def root():
    return {
        "message": "WhaleWatch Supercomputer Online",
        "time": datetime.now().isoformat(),
        "endpoints": ["/signal/{ticker}", "/top", "/scan"],
    }


@app.get("/signal/{ticker}")
def get_signal(ticker: str):
    result = get_cached(ticker.upper().strip())
    if not result:
        raise HTTPException(404, f"Could not analyze {ticker}. Check the ticker and try again.")
    return result


@app.get("/top")
def get_top(limit: int = Query(default=10, le=20)):
    """Return top conviction picks from the default watchlist."""
    results = []
    for t in DEFAULT_WATCHLIST:
        data = get_cached(t)
        if data:
            results.append(data)
    results.sort(key=lambda x: x["conviction"], reverse=True)
    return {
        "top": results[:limit],
        "updated": datetime.now().isoformat(),
        "count": len(results),
    }


@app.get("/scan")
def scan_tickers(tickers: str = Query(..., description="Comma-separated list of tickers")):
    """Bulk scan custom tickers. E.g. /scan?tickers=NVDA,TSLA,AAPL"""
    ticker_list = [t.strip().upper() for t in tickers.split(",") if t.strip()][:20]
    results = []
    for t in ticker_list:
        data = get_cached(t)
        if data:
            results.append(data)
    results.sort(key=lambda x: x["conviction"], reverse=True)
    return {"results": results, "updated": datetime.now().isoformat()}
