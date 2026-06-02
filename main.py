"""
main.py — WhaleWatch API v4
"""

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from core import analyze
from datetime import datetime
import threading

app = FastAPI(title="WhaleWatch v4")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

BASKET = ["AAPL","MSFT","NVDA","AMZN","TSLA","META","GOOGL","JPM"]

state = {"cache": {}, "refreshing": False, "last": "Never"}
lock = threading.Lock()


def refresh():
    with lock:
        if state["refreshing"]:
            return
        state["refreshing"] = True

    try:
        out = {}
        for t in BASKET:
            out[t] = analyze(t)

        with lock:
            state["cache"] = out
            state["last"] = datetime.utcnow().isoformat()
    finally:
        with lock:
            state["refreshing"] = False


@app.get("/signal/{ticker}")
def signal(ticker: str):
    return analyze(ticker)


@app.get("/options/{ticker}")
def options(ticker: str):
    return analyze(ticker)["options"]


@app.get("/top")
def top():
    with lock:
        items = list(state["cache"].values())

    if not items:
        raise HTTPException(503, "Not ready")

    items.sort(key=lambda x: x["conviction"], reverse=True)

    return {
        "schema_version": "4.0",
        "top": items,
        "last_refresh": state["last"]
    }


@app.post("/refresh")
def manual_refresh(bg: BackgroundTasks):
    bg.add_task(refresh)
    return {"status": "refreshing"}