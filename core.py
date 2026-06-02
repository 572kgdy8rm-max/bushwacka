"""
core.py — WhaleWatch Quant Engine (HARDENED UNIVERSAL)
"""

import numpy as np
import pandas as pd
import yfinance as yf
from datetime import datetime


# ─────────────────────────────────────────────
# SAFE DATA FETCH
# ─────────────────────────────────────────────

def fetch_price_data(ticker: str):
    try:
        df = yf.Ticker(ticker).history(period="6mo")
        if df is None or df.empty:
            return None
        return df
    except:
        return None


# ─────────────────────────────────────────────
# METADATA (SAFE)
# ─────────────────────────────────────────────

def get_metadata(ticker: str):
    try:
        t = yf.Ticker(ticker)
        info = getattr(t, "info", {}) or {}

        return {
            "sector": info.get("sector", "Unknown"),
            "fwd_pe": info.get("forwardPE"),
            "short_pct": info.get("shortPercentOfFloat"),
            "rec_mean": info.get("recommendationMean"),
            "rec_key": info.get("recommendationKey"),
            "num_analysts": info.get("numberOfAnalystOpinions", 0),
        }
    except:
        return {
            "sector": "Unknown",
            "fwd_pe": None,
            "short_pct": None,
            "rec_mean": None,
            "rec_key": None,
            "num_analysts": 0,
        }


# ─────────────────────────────────────────────
# SAFE INDICATORS
# ─────────────────────────────────────────────

def safe_indicators(df):
    if df is None or len(df) < 20:
        return {}

    close = df["Close"].dropna()

    if len(close) < 20:
        return {}

    returns = close.pct_change().dropna()

    return {
        "vol": float(returns.std() * np.sqrt(252)) if len(returns) else 0,
        "mom_20d": float((close.iloc[-1] / close.iloc[-20] - 1) * 100),
        "ma50": float(close.rolling(50).mean().iloc[-1]),
        "ma200": float(close.rolling(200).mean().iloc[-1]),
    }


# ─────────────────────────────────────────────
# MAIN ANALYSIS (NO CRASH GUARANTEE)
# ─────────────────────────────────────────────

def analyze(ticker: str, spy_df=None):
    ticker = ticker.upper().strip()

    price_df = fetch_price_data(ticker)
    meta = get_metadata(ticker)
    ind = safe_indicators(price_df)

    price = None
    if price_df is not None and not price_df.empty:
        price = float(price_df["Close"].iloc[-1])

    momentum = min(max(ind.get("mom_20d", 0), -100), 100)
    vol = ind.get("vol", 0)

    # ── CORE SCORE ENGINE (SIMPLIFIED BUT STABLE)
    trend_score = 50
    if ind.get("ma50") and ind.get("ma200"):
        trend_score += 20 if ind["ma50"] > ind["ma200"] else -20

    risk_score = max(0, 100 - (vol * 100))
    momentum_score = max(0, min(100, 50 + momentum))
    rs_score = 50  # placeholder safe baseline

    conviction = int(
        0.35 * momentum_score +
        0.25 * trend_score +
        0.25 * rs_score +
        0.15 * risk_score
    )

    verdict = (
        "Strong Buy" if conviction >= 80 else
        "Buy" if conviction >= 65 else
        "Neutral" if conviction >= 45 else
        "Sell"
    )

    return {
        "ticker": ticker,
        "price": price or 0,
        "sector": meta["sector"],
        "earnings_date": "Unknown",
        "data_as_of": datetime.utcnow().isoformat(),

        "conviction": conviction,
        "verdict": verdict,
        "entry_flag": "Good Entry" if conviction > 65 else "Wait",

        "momentum_score": int(momentum_score),
        "trend_score": int(trend_score),
        "risk_score": int(risk_score),
        "rs_score": int(rs_score),
        "fundamental_score": 50,

        "metrics": {
            "Momentum": {
                "20d Momentum": int(momentum),
            },
            "Trend": {
                "MA Cross": 8 if ind.get("ma50",0) > ind.get("ma200",0) else 3,
            },
            "Risk": {
                "Volatility": int(max(0, 100 - vol * 100))
            },
            "Relative Strength": {
                "Baseline": 5
            },
            "Fundamental": {
                "Analyst Consensus": 5
            }
        },

        "raw": {
            "fwd_pe": meta["fwd_pe"],
            "short_pct": meta["short_pct"],
            "rec_mean": meta["rec_mean"],
            "rec_key": meta["rec_key"],
            "num_analysts": meta["num_analysts"],
            "sector_pe_median": 20,
            "alpha_vs_sector": None,
            "sector_etf": meta["sector"]
        }
    }