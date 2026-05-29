from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from core import advanced_stats
from datetime import datetime

app = FastAPI(title="Ben's Trading Supercomputer")

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

@app.get("/")
def root():
    return {"message": "Ben's Super Quant Assistant Online", "time": datetime.now().isoformat()}

@app.get("/signal/{ticker}")
def get_signal(ticker: str):
    result = advanced_stats(ticker)
    if not result:
        raise HTTPException(404, f"Could not analyze {ticker}")
    return result

@app.get("/top")
def get_top():
    watchlist = ["NVDA","AAPL","MSFT","GOOGL","AMZN","META","TSLA","AVGO","AMD","LMT","TSM","COIN","PLTR","RKLB"]
    results = [advanced_stats(t) for t in watchlist]
    results = [r for r in results if r]
    results.sort(key=lambda x: x['conviction'], reverse=True)
    return {"top": results[:12], "updated": datetime.now().isoformat()}