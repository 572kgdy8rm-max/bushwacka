"""
options.py — WhaleWatch Options Engine
Reads directly from analyze() output. No redundant data fetches.
"""

from datetime import datetime, timedelta


# ─────────────────────────────────────────────
# IV REGIME — uses vol already computed by core
# ─────────────────────────────────────────────

def iv_regime(vol_pct: float) -> str:
    """
    vol_pct is annualised volatility % from analyze()['raw']['vol_pct']
    """
    if vol_pct is None:
        return "UNKNOWN"
    if vol_pct > 60:
        return "HIGH"
    elif vol_pct > 35:
        return "MED"
    else:
        return "LOW"


# ─────────────────────────────────────────────
# EARNINGS PROXIMITY — within 10 days = risk on
# ─────────────────────────────────────────────

def earnings_proximity(earnings_date: str) -> str:
    """
    Returns 'IMMINENT' if within 10 days, 'NEAR' if within 30, else 'CLEAR'
    """
    if not earnings_date or earnings_date == "Unknown":
        return "UNKNOWN"
    try:
        ed = datetime.strptime(earnings_date[:10], "%Y-%m-%d")
        days = (ed - datetime.now()).days
        if days < 0:
            return "CLEAR"       # already passed
        elif days <= 10:
            return "IMMINENT"
        elif days <= 30:
            return "NEAR"
        else:
            return "CLEAR"
    except:
        return "UNKNOWN"


# ─────────────────────────────────────────────
# STRUCTURE SELECTOR
# ─────────────────────────────────────────────

def select_structure(direction: str, iv: str, earnings: str, conviction: float) -> dict:
    """
    Returns structure name, wing width, and rationale.
    Always defined risk (spreads) unless conviction >= 85 and IV is LOW.
    """
    if earnings == "IMMINENT":
        # Straddle/strangle territory — but we default to no trade
        return {
            "structure": "NO_TRADE",
            "reason":    "Earnings within 10 days — avoid directional options"
        }

    if direction == "LONG":
        if iv == "HIGH":
            # Sell premium into strength — bull put spread
            return {
                "structure": "Bull Put Spread",
                "wing":      0.05,
                "reason":    "High IV favours selling premium; defined risk"
            }
        elif conviction >= 85 and iv == "LOW":
            # High conviction, cheap options — outright call acceptable
            return {
                "structure": "Long Call",
                "wing":      None,
                "reason":    "High conviction + compressed IV — outright call justified"
            }
        else:
            # Default long: bull call spread
            return {
                "structure": "Bull Call Spread",
                "wing":      0.05,
                "reason":    "Defined risk long structure; limits cost in uncertain IV"
            }

    elif direction == "SHORT":
        if iv == "HIGH":
            # Bear call spread — sell into high IV
            return {
                "structure": "Bear Call Spread",
                "wing":      0.05,
                "reason":    "High IV favours selling premium on short side"
            }
        else:
            return {
                "structure": "Bear Put Spread",
                "wing":      0.05,
                "reason":    "Defined risk short structure"
            }

    return {"structure": "NO_TRADE", "reason": "No directional conviction"}


# ─────────────────────────────────────────────
# STRIKE CALCULATOR
# ─────────────────────────────────────────────

def calc_strikes(price: float, direction: str, structure: dict, iv: str) -> dict:
    """
    Returns primary strike and (if spread) short strike.
    ATM for low IV, slight OTM for high IV.
    """
    if not price or structure.get("structure") in ("NO_TRADE", None):
        return {"primary": None, "short": None}

    wing = structure.get("wing") or 0.05

    if direction == "LONG":
        if iv == "HIGH":
            # Bull put spread: sell OTM put, buy further OTM put
            short_strike = round(price * 0.97, 2)
            long_strike  = round(price * (0.97 - wing), 2)
        else:
            # Bull call spread: buy ATM/slight OTM call, sell further OTM
            long_strike  = round(price * 1.00, 2)   # ATM
            short_strike = round(price * (1.00 + wing), 2)
        return {"primary": long_strike, "short": short_strike}

    elif direction == "SHORT":
        if iv == "HIGH":
            # Bear call spread: sell OTM call, buy further OTM call
            short_strike = round(price * 1.03, 2)
            long_strike  = round(price * (1.03 + wing), 2)
        else:
            # Bear put spread: buy ATM put, sell OTM put
            long_strike  = round(price * 1.00, 2)
            short_strike = round(price * (1.00 - wing), 2)
        return {"primary": long_strike, "short": short_strike}

    return {"primary": None, "short": None}


# ─────────────────────────────────────────────
# EXPIRY SELECTOR
# ─────────────────────────────────────────────

def select_expiry(iv: str, earnings: str) -> str:
    if earnings == "NEAR":
        return "7–14 DTE (avoid earnings overlap)"
    if iv == "HIGH":
        return "14–21 DTE (harvest elevated premium faster)"
    if iv == "LOW":
        return "45–60 DTE (give long options time to work)"
    return "30–45 DTE"


# ─────────────────────────────────────────────
# MAIN ENGINE
# ─────────────────────────────────────────────

def build_options_signal(signal: dict) -> dict:
    """
    Takes the full analyze() output dict and returns an options recommendation.
    """
    if not isinstance(signal, dict):
        return {"trade": "NO_TRADE", "reason": "invalid input"}

    ticker     = signal.get("ticker")
    price      = signal.get("price")
    conviction = signal.get("conviction")
    entry      = signal.get("entry_flag", "")
    verdict    = signal.get("verdict", "")
    earnings   = signal.get("earnings_date", "Unknown")
    raw        = signal.get("raw", {})
    vol_pct    = raw.get("vol_pct")
    beta_val   = raw.get("beta")

    if not ticker or conviction is None:
        return {"trade": "NO_TRADE", "reason": "missing required fields"}

    try:
        conviction = float(conviction)
        price      = float(price)
    except:
        return {"trade": "NO_TRADE", "reason": "invalid conviction or price"}

    # ── Direction ──────────────────────────────────────────────────────────
    if verdict in ("Strong Buy", "Buy") and conviction >= 65:
        direction = "LONG"
    elif verdict in ("Strong Sell", "Sell") and conviction <= 40:
        direction = "SHORT"
    else:
        return {
            "trade":     "NO_TRADE",
            "reason":    f"Conviction {conviction} + verdict '{verdict}' — no options edge",
            "iv_regime": iv_regime(vol_pct),
        }

    # ── Entry flag override ────────────────────────────────────────────────
    if entry == "Wait for Pullback" and direction == "LONG":
        return {
            "trade":     "NO_TRADE",
            "reason":    "Entry flag: Wait for Pullback — hold off on long options",
            "iv_regime": iv_regime(vol_pct),
        }

    # ── Build components ───────────────────────────────────────────────────
    iv       = iv_regime(vol_pct)
    earn_prx = earnings_proximity(earnings)
    struct   = select_structure(direction, iv, earn_prx, conviction)

    if struct["structure"] == "NO_TRADE":
        return {
            "trade":          "NO_TRADE",
            "reason":         struct["reason"],
            "iv_regime":      iv,
            "earnings_risk":  earn_prx,
        }

    strikes = calc_strikes(price, direction, struct, iv)
    exp     = select_expiry(iv, earn_prx)

    # ── Format strike display ──────────────────────────────────────────────
    if strikes["short"]:
        strike_display = f"${strikes['primary']} / ${strikes['short']}"
    else:
        strike_display = f"${strikes['primary']}"

    return {
        "trade":          "OPTIONS",
        "ticker":         ticker,
        "direction":      direction,
        "structure":      struct["structure"],
        "strike":         strike_display,
        "expiry":         exp,
        "iv_regime":      iv,
        "earnings_risk":  earn_prx,
        "confidence":     conviction,
        "rationale":      struct["reason"],
    }
 