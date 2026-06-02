"""
core.py — WhaleWatch Quant Engine v4 (Signal + Options Ready)
"""

import numpy as np
import yfinance as yf
from datetime import datetime
from options import build_options_signal


# ─────────────────────────────────────────────
# SAFE HELPERS
# ─────────────────────────────────────────────

def safe(x):
    try:
        if x is None:
            return None
        return float(x)
    except:
        return None


def clamp(x):
    if x is None:
        return 0
    return max(0, min(100, x))


# ─────────────────────────────────────────────
# METADATA
# ─────────────────────────────────────────────

def get_metadata(ticker):
    t = yf.Ticker(ticker)

    info = {}
    try:
        info = t.info or {}
    except:
        pass

    return {
        "sector": info.get("sector", "Unknown"),
        "fwd_pe": safe(info.get("forwardPE")),
        "rec_mean": safe(info.get("recommendationMean")),
        "rec_key": info.get("recommendationKey"),
        "num_analysts": int(info.get("numberOfAnalystOpinions") or 0),
        "short_pct": safe(info.get("shortPercentOfFloat")),
        "earnings_date": str(info.get("earningsDate") or "Unknown")[:10]
    }


# ─────────────────────────────────────────────
# CORE ANALYSIS ENGINE
# ─────────────────────────────────────────────

def analyze(ticker, spy_df=None):
    t = yf.Ticker(ticker)

    price = None
    try:
        price = t.fast_info.get("lastPrice")
    except:
        pass

    meta = get_metadata(ticker)

    # ── Synthetic but stable factors (replace later with real TA engine)
    momentum = np.random.randint(35, 95)
    trend = np.random.randint(35, 95)
    risk = np.random.randint(20, 80)
    rel_strength = np.random.randint(40, 90)

    conviction = clamp(
        0.3 * momentum +
        0.3 * trend +
        0.2 * rel_strength +
        0.2 * (100 - risk)
    )

    if conviction >= 80:
        verdict = "Strong Buy"
    elif conviction >= 65:
        verdict = "Buy"
    elif conviction >= 45:
        verdict = "Neutral"
    else:
        verdict = "Sell"

    entry_flag = "Good Entry" if conviction >= 70 else "Wait for Pullback"

    base_signal = {
        "schema_version": "4.0",
        "ticker": ticker,
        "price": price,
        "sector": meta["sector"],
        "earnings_date": meta["earnings_date"],

        "conviction": round(conviction, 1),
        "verdict": verdict,
        "entry_flag": entry_flag,

        "momentum": momentum,
        "trend": trend,
        "risk": risk,
        "relative_strength": rel_strength,

        "fundamentals": meta,
        "data_as_of": datetime.utcnow().isoformat()
    }

    # ── OPTIONS LAYER (FULL INTEGRATION)
    base_signal["options"] = build_options_signal(base_signal)

    return base_signal