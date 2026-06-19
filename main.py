"""
main.py — WhaleWatch API
Now backed by the SQLite scan store: /top and /sectors read PRE-COMPUTED scans
(fast, instant) instead of crunching live. Individual /signal still runs live.
"""
import math
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from core import analyze
from options import build_options_signal

import store
from sectors import SECTORS, SECTOR_NAMES, TOTAL_SECTORS


def sanitize(obj):
    """Recursively replace NaN/Inf floats with None so FastAPI can serialize."""
    if isinstance(obj, float):
        return None if (math.isnan(obj) or math.isinf(obj)) else obj
    if isinstance(obj, dict):
        return {k: sanitize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [sanitize(i) for i in obj]
    return obj


app = FastAPI(title="WhaleWatch Quant API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Make sure the store table exists on startup.
store.init_db()


@app.get("/")
def root():
    return FileResponse("index.html")


@app.get("/health")
def health():
    return {"status": "online"}


@app.get("/wake")
def wake():
    """Lightweight ping."""
    return {"awake": True}


@app.get("/signal/{ticker}")
def signal(ticker: str):
    """Live single-ticker analysis — always fresh, computed on demand."""
    try:
        result = sanitize(analyze(ticker))
        result["options"] = build_options_signal(result)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/scan")
def scan(tickers: str):
    """Live bulk scan of an arbitrary ticker list — computed on demand."""
    if not tickers or not tickers.strip():
        raise HTTPException(status_code=400, detail="No tickers provided")

    results = []
    for t in tickers.split(",")[:40]:
        t = t.strip()
        if not t:
            continue
        try:
            result = sanitize(analyze(t))
            result["options"] = build_options_signal(result)
            results.append(result)
        except Exception:
            continue

    results.sort(key=lambda x: x["conviction"], reverse=True)
    return {"results": results}


@app.get("/top")
def top(batch: int = 0):
    """
    Top picks for one sector — reads the PRE-COMPUTED scan from the store.
    Instant. If the sector hasn't been scanned yet, returns an empty result
    with scanned_at=None so the frontend can show 'not yet scanned'.
    """
    key = batch % TOTAL_SECTORS
    stored = store.get_sector(SECTOR_NAMES[key])

    if not stored:
        return {
            "batch": key,
            "batch_name": SECTOR_NAMES[key],
            "next_batch": (key + 1) % TOTAL_SECTORS,
            "total_batches": TOTAL_SECTORS,
            "scanned_at": None,
            "results": [],
        }

    results = sanitize(stored["results"])
    return {
        "batch": key,
        "batch_name": stored["sector"],
        "next_batch": (key + 1) % TOTAL_SECTORS,
        "total_batches": TOTAL_SECTORS,
        "scanned_at": stored["scanned_at"],
        "results": results[:10],
    }


@app.get("/sectors")
def sectors_meta():
    """
    Freshness overview: every sector and when it was last scanned.
    Lets the app show 'Technology · scanned 06:14, Energy · not yet' etc.
    """
    meta = store.get_all_meta()
    by_name = {m["sector"]: m for m in meta}
    out = []
    for i, name in enumerate(SECTOR_NAMES):
        m = by_name.get(name)
        out.append({
            "batch_index": i,
            "sector": name,
            "scanned_at": m["scanned_at"] if m else None,
            "ticker_count": len(SECTORS[i]["tickers"]),
        })
    return {"sectors": out, "total": TOTAL_SECTORS}
