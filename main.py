"""
main.py — WhaleWatch API
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from core import analyze
from options import build_options_signal

app = FastAPI(title="WhaleWatch Quant API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root():
    return {"status": "online"}


@app.get("/wake")
def wake():
    """Lightweight ping to wake Render from sleep before heavy requests."""
    return {"awake": True}


@app.get("/signal/{ticker}")
def signal(ticker: str):
    try:
        result = analyze(ticker)
        result["options"] = build_options_signal(result)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/scan")
def scan(tickers: str):
    if not tickers or not tickers.strip():
        raise HTTPException(status_code=400, detail="No tickers provided")

    results = []
    for t in tickers.split(",")[:20]:
        t = t.strip()
        if not t:
            continue
        try:
            result = analyze(t)
            result["options"] = build_options_signal(result)
            results.append(result)
        except:
            continue

    results.sort(key=lambda x: x["conviction"], reverse=True)
    return {"results": results}


BATCHES = {
    "0": {
        "name": "Technology",
        "tickers": ["AAPL", "MSFT", "NVDA", "AVGO", "ORCL", "AMD", "ANET", "PLTR", "CRM", "INTC"]
    },
    "1": {
        "name": "Financials & Healthcare",
        "tickers": ["JPM", "GS", "V", "MS", "BLK", "LLY", "UNH", "JNJ", "ABBV", "MRK"]
    },
    "2": {
        "name": "Energy & Industrials",
        "tickers": ["XOM", "CVX", "COP", "SLB", "EOG", "CAT", "HON", "GE", "UPS", "RTX"]
    },
    "3": {
        "name": "Consumer & Communication",
        "tickers": ["AMZN", "HD", "MCD", "NKE", "COST", "GOOGL", "META", "DIS", "NFLX", "T"]
    },
    "4": {
        "name": "Wildcards",
        "tickers": ["TSLA", "MSTR", "CEG", "TEM", "ALAB", "RKLB", "IONQ", "HOOD", "COIN", "SOFI"]
    },
}


@app.get("/top")
def top(batch: int = 0):
    key     = str(batch % len(BATCHES))
    group   = BATCHES[key]
    results = []

    for t in group["tickers"]:
        try:
            result = analyze(t)
            result["options"] = build_options_signal(result)
            results.append(result)
        except:
            continue

    results.sort(key=lambda x: x["conviction"], reverse=True)

    return {
        "batch":       int(key),
        "batch_name":  group["name"],
        "next_batch":  (int(key) + 1) % len(BATCHES),
        "total_batches": len(BATCHES),
        "results":     results[:5],
    }
