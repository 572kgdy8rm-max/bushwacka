from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from core import advanced_stats
from datetime import datetime

app = FastAPI(title="Ben's WhaleWatch Supercomputer")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def root():
    return {"message": "WhaleWatch Supercomputer Online", "time": datetime.now().isoformat()}

@app.get("/signal/{ticker}")
def get_signal(ticker: str):
    result = advanced_stats(ticker)
    if not result:
        raise HTTPException(404, f"Could not analyze {ticker}")
    return result

@app.get("/top")
def get_top():
    watchlist = ["NVDA", "RKLB", "TSLA", "AAPL", "MSFT", "GOOGL", "AMZN", "META", "AVGO", "PLTR"]
    results = []
    for t in watchlist:
        data = advanced_stats(t)
        if data:
            results.append(data)
    results.sort(key=lambda x: x["conviction"], reverse=True)
    return {"top": results[:10], "updated": datetime.now().isoformat()}