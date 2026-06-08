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


@app.get("/top")
def top():
    # Broad universe across all sectors — no bias, top 5 by conviction
    universe = [
        # Technology
        "AAPL", "MSFT", "NVDA", "AVGO", "ORCL",
        # Financials
        "JPM", "GS", "V", "MS", "BLK",
        # Healthcare
        "LLY", "UNH", "JNJ", "ABBV", "MRK",
        # Industrials
        "CAT", "HON", "GE", "UPS", "RTX",
        # Energy
        "XOM", "CVX", "COP", "SLB", "EOG",
        # Consumer
        "AMZN", "HD", "MCD", "NKE", "COST",
        # Communication
        "GOOGL", "META", "DIS", "NFLX", "T",
        # Utilities / Real Estate
        "NEE", "DUK", "AMT", "PLD", "SPG",
    ]
    results = []
    for t in universe:
        try:
            result = analyze(t)
            result["options"] = build_options_signal(result)
            results.append(result)
        except:
            continue

    results.sort(key=lambda x: x["conviction"], reverse=True)
    return {"results": results[:5]}
