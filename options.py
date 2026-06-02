"""
options.py — WhaleWatch Options Engine (UNIVERSAL SAFE v2)
"""

import numpy as np
import yfinance as yf


# ─────────────────────────────────────────────
# VOLATILITY REGIME (ROBUST)
# ─────────────────────────────────────────────

def iv_regime(ticker):
    try:
        hist = yf.Ticker(ticker).history(period="3mo")

        if hist is None or hist.empty or "Close" not in hist:
            return "UNKNOWN"

        close = hist["Close"].dropna()
        if len(close) < 20:
            return "UNKNOWN"

        rets = close.pct_change().dropna()

        if len(rets) == 0:
            return "UNKNOWN"

        vol = float(rets.std() * np.sqrt(252))

        if np.isnan(vol):
            return "UNKNOWN"

        if vol > 0.6:
            return "HIGH"
        elif vol > 0.35:
            return "MED"
        else:
            return "LOW"

    except:
        return "UNKNOWN"


# ─────────────────────────────────────────────
# EARNINGS RISK (SAFE EXTRACTION)
# ─────────────────────────────────────────────

def earnings_risk(meta):
    try:
        ed = meta.get("earnings_date")
        if not ed or ed == "Unknown":
            return "UNKNOWN"
        return "HIGH"
    except:
        return "UNKNOWN"


# ─────────────────────────────────────────────
# STRIKE MODEL (SAFE + LOGICAL)
# ─────────────────────────────────────────────

def strike(price, direction, iv):
    if price is None:
        return None

    try:
        price = float(price)
    except:
        return None

    if direction == "LONG":
        if iv == "HIGH":
            return round(price * 0.95, 2)
        return round(price * 0.98, 2)

    if direction == "SHORT":
        if iv == "HIGH":
            return round(price * 1.05, 2)
        return round(price * 1.02, 2)

    return price


# ─────────────────────────────────────────────
# EXPIRY MODEL (EVENT-AWARE)
# ─────────────────────────────────────────────

def expiry(iv, earnings):
    if earnings == "HIGH":
        return "7–14DTE"
    if iv == "HIGH":
        return "14–30DTE"
    return "30–60DTE"


# ─────────────────────────────────────────────
# MAIN ENGINE
# ─────────────────────────────────────────────

def build_options_signal(signal: dict):
    if not isinstance(signal, dict):
        return {"trade": "NO_TRADE", "reason": "invalid input"}

    ticker = signal.get("ticker")
    price = signal.get("price")
    conv = signal.get("conviction")

    if not ticker:
        return {"trade": "NO_TRADE", "reason": "missing ticker"}

    try:
        conv = float(conv)
    except:
        return {"trade": "NO_TRADE", "reason": "invalid conviction"}

    # ── Direction logic (clean threshold system)
    if conv >= 70:
        direction = "LONG"
    elif conv <= 40:
        direction = "SHORT"
    else:
        return {"trade": "NO_TRADE", "reason": "neutral regime"}

    meta = signal.get("raw") or {}

    iv = iv_regime(ticker)
    earn = earnings_risk(meta)

    return {
        "trade": "OPTIONS",
        "ticker": ticker,
        "direction": direction,
        "structure": "CALL" if direction == "LONG" else "PUT",

        "strike": strike(price, direction, iv),
        "expiry": expiry(iv, earn),

        "iv_regime": iv,
        "earnings_risk": earn,

        "confidence": conv,
        "rationale": f"conv={conv} | iv={iv} | earnings={earn}"
    }