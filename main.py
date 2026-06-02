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
    watchlist = [
        "AAPL","MSFT","NVDA","GOOGL","AMZN",
        "META","TSLA","AVGO","JPM","V"
    ]
    results = []
    for t in watchlist:
        try:
            result = analyze(t)
            result["options"] = build_options_signal(result)
            results.append(result)
        except:
            continue

    results.sort(key=lambda x: x["conviction"], reverse=True)
    return {"results": results[:5]}
