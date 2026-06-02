"""
main.py — WhaleWatch API (UNIVERSAL SAFE VERSION)
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from core import analyze

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
        return analyze(ticker)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/scan")
def scan(tickers: str):
    results = []
    for t in tickers.split(",")[:20]:
        try:
            results.append(analyze(t.strip()))
        except:
            continue

    results.sort(key=lambda x: x["conviction"], reverse=True)

    return {"results": results}


@app.get("/top")
def top():
    return {"message": "Basket system removed in universal build"}