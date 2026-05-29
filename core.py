import yfinance as yf
import numpy as np
from datetime import datetime, timedelta

# ======================
# HELPERS
# ======================

def wilson_lower_bound(win_rate: float, n: int) -> float:
    if n < 30:
        return 0.0
    p = win_rate / 100
    z = 1.96
    denom = 1 + (z * z) / n
    center = p + (z * z) / (2 * n)
    margin = z * np.sqrt((p * (1 - p) + (z * z) / (4 * n)) / n)
    return max(0.0, (center - margin) / denom * 100)


def get_fundamentals(ticker: str) -> dict:
    try:
        info = yf.Ticker(ticker).info
        current = info.get("currentPrice") or info.get("regularMarketPrice")
        target = info.get("targetMeanPrice")
        upside = round(((target / current) - 1) * 100, 1) if target and current else 0
        pe = info.get("trailingPE")
        fwd_pe = info.get("forwardPE")
        revenue_growth = info.get("revenueGrowth")
        profit_margins = info.get("profitMargins")
        return {
            "analyst_upside": upside,
            "pe": round(pe, 1) if pe else None,
            "fwd_pe": round(fwd_pe, 1) if fwd_pe else None,
            "revenue_growth": round(revenue_growth * 100, 1) if revenue_growth else None,
            "profit_margin": round(profit_margins * 100, 1) if profit_margins else None,
        }
    except:
        return {"analyst_upside": 0, "pe": None, "fwd_pe": None, "revenue_growth": None, "profit_margin": None}


def compute_technicals(closes) -> dict:
    """RSI, MACD, Bollinger, MA signals."""
    signals = []
    reasons = []

    # --- RSI (14) ---
    delta = closes.diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rs = gain / loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    rsi_val = rsi.iloc[-1]

    if rsi_val < 35:
        signals.append(+2)
        reasons.append(f"RSI oversold ({rsi_val:.0f}) â potential bounce")
    elif rsi_val < 50:
        signals.append(+1)
        reasons.append(f"RSI below midline ({rsi_val:.0f}) â building momentum")
    elif rsi_val > 75:
        signals.append(-2)
        reasons.append(f"RSI overbought ({rsi_val:.0f}) â elevated pullback risk")
    elif rsi_val > 60:
        signals.append(+1)
        reasons.append(f"RSI strong ({rsi_val:.0f}) â bullish momentum")

    # --- MACD ---
    ema12 = closes.ewm(span=12).mean()
    ema26 = closes.ewm(span=26).mean()
    macd = ema12 - ema26
    signal_line = macd.ewm(span=9).mean()
    hist = macd - signal_line
    if hist.iloc[-1] > 0 and hist.iloc[-2] <= 0:
        signals.append(+2)
        reasons.append("MACD bullish crossover â fresh buy signal")
    elif hist.iloc[-1] > 0:
        signals.append(+1)
        reasons.append("MACD histogram positive â upward trend")
    elif hist.iloc[-1] < 0 and hist.iloc[-2] >= 0:
        signals.append(-2)
        reasons.append("MACD bearish crossover â fresh sell signal")
    elif hist.iloc[-1] < 0:
        signals.append(-1)
        reasons.append("MACD histogram negative â downward pressure")

    # --- Moving Averages ---
    ma50 = closes.rolling(50).mean().iloc[-1]
    ma200 = closes.rolling(200).mean().iloc[-1]
    price = closes.iloc[-1]

    if price > ma50 and price > ma200:
        signals.append(+2)
        reasons.append("Price above 50 & 200 MA â strong uptrend")
    elif price > ma50:
        signals.append(+1)
        reasons.append("Price above 50 MA â short-term bullish")
    elif price < ma50 and price < ma200:
        signals.append(-2)
        reasons.append("Price below 50 & 200 MA â confirmed downtrend")
    elif price < ma50:
        signals.append(-1)
        reasons.append("Price below 50 MA â short-term bearish")

    # --- Bollinger Bands ---
    bb_mid = closes.rolling(20).mean()
    bb_std = closes.rolling(20).std()
    bb_upper = bb_mid + 2 * bb_std
    bb_lower = bb_mid - 2 * bb_std
    bb_pos = (price - bb_lower.iloc[-1]) / (bb_upper.iloc[-1] - bb_lower.iloc[-1])

    if bb_pos < 0.1:
        signals.append(+2)
        reasons.append("Near lower Bollinger Band â mean reversion setup")
    elif bb_pos > 0.9:
        signals.append(-1)
        reasons.append("Near upper Bollinger Band â stretched, caution")

    return {
        "rsi": round(rsi_val, 1),
        "macd_hist": round(hist.iloc[-1], 4),
        "ma50": round(ma50, 2),
        "ma200": round(ma200, 2),
        "tech_signal_sum": sum(signals),
        "tech_reasons": reasons,
    }


def compute_timeframe_score(returns, spy_returns, label: str) -> dict:
    common = returns.index.intersection(spy_returns.index)
    excess = returns.loc[common] - spy_returns.loc[common]
    n = len(excess)
    win_rate = (excess > 0).mean() * 100 if n > 0 else 0
    wilson = wilson_lower_bound(win_rate, n)
    sharpe = (excess.mean() / excess.std() * np.sqrt(252)) if excess.std() > 0 else 0
    avg_excess = excess.mean() * 100
    return {
        "label": label,
        "win_rate": round(win_rate, 1),
        "wilson": round(wilson, 1),
        "sharpe": round(sharpe, 2),
        "avg_excess_pct": round(avg_excess, 3),
        "n": n,
    }


# ======================
# POSITION SIZING (Kelly-inspired)
# ======================

def kelly_position(win_rate: float, avg_win: float, avg_loss: float, max_pct: float = 8.0) -> float:
    """Fractional Kelly criterion for position sizing."""
    if avg_loss == 0 or win_rate <= 0:
        return 0.0
    p = win_rate / 100
    b = abs(avg_win / avg_loss) if avg_loss != 0 else 1
    kelly = (p * b - (1 - p)) / b
    fractional = kelly * 0.25  # Quarter Kelly for safety
    return round(max(0.0, min(max_pct, fractional * 100)), 1)


# ======================
# MAIN ANALYSIS
# ======================

def advanced_stats(ticker: str) -> dict | None:
    try:
        ticker = ticker.upper().strip()
        end = datetime.now()
        spy_hist = yf.Ticker("SPY").history(start=end - timedelta(days=730), end=end)["Close"]
        spy_returns = spy_hist.pct_change().dropna()

        stock = yf.Ticker(ticker)
        hist = stock.history(start=end - timedelta(days=730), end=end)
        if len(hist) < 60:
            return None

        closes = hist["Close"]
        returns = closes.pct_change().dropna()

        # Multi-timeframe analysis
        tf_short = compute_timeframe_score(
            returns.last("63D"), spy_returns.last("63D"), "3-month"
        )
        tf_mid = compute_timeframe_score(
            returns.last("126D"), spy_returns.last("126D"), "6-month"
        )
        tf_long = compute_timeframe_score(returns, spy_returns, "2-year")

        # Technical signals
        tech = compute_technicals(closes)

        # Fundamentals
        fund = get_fundamentals(ticker)

        # Max drawdown
        max_dd = ((closes / closes.cummax()) - 1).min() * 100

        # Volatility (annualised)
        vol = returns.std() * np.sqrt(252) * 100

        # Weighted conviction score
        quant = (
            tf_long["wilson"] * 0.20
            + tf_mid["wilson"] * 0.25
            + tf_short["wilson"] * 0.15
            + min(tf_long["sharpe"], 3.0) * 10
            + min(tf_mid["sharpe"], 3.0) * 8
            + max(tf_long["avg_excess_pct"], -5) * 6
        )

        # Technical score contribution (scaled)
        tech_contrib = tech["tech_signal_sum"] * 2.5

        # Forward-looking
        forward = fund["analyst_upside"] * 0.5

        # Penalties
        dd_penalty = max(0, (max_dd + 30) * 0.5)
        vol_penalty = max(0, (vol - 40) * 0.2)

        conviction = quant + tech_contrib + forward - dd_penalty - vol_penalty
        conviction = round(max(10, min(96, conviction)), 1)

        # Signal reasons â top 3 most impactful
        all_reasons = tech["tech_reasons"].copy()

        if tf_short["wilson"] > tf_long["wilson"] + 5:
            all_reasons.insert(0, f"Improving recent performance vs SPY ({tf_short['label']})")
        if tf_short["wilson"] < tf_long["wilson"] - 5:
            all_reasons.insert(0, f"Recent underperformance vs SPY ({tf_short['label']})")
        if fund["analyst_upside"] > 20:
            all_reasons.insert(0, f"Analysts see {fund['analyst_upside']}% upside to price target")
        if max_dd < -40:
            all_reasons.append(f"Deep historical drawdown ({max_dd:.0f}%) â high risk")

        top_reasons = all_reasons[:3]

        # Recommendation + sizing
        if conviction >= 80:
            rec = "ð¥ STRONG BUY"
            risk = "Aggressive"
        elif conviction >= 68:
            rec = "â BUY"
            risk = "Moderate"
        elif conviction >= 54:
            rec = "â ï¸ SMALL POSITION"
            risk = "Conservative"
        else:
            rec = "â AVOID"
            risk = "None"

        # Kelly-based sizing using long-term stats
        common = returns.index.intersection(spy_returns.index)
        excess = returns.loc[common] - spy_returns.loc[common]
        avg_win = excess[excess > 0].mean() * 100 if (excess > 0).any() else 0
        avg_loss = excess[excess < 0].mean() * 100 if (excess < 0).any() else -1
        position_pct = kelly_position(tf_long["win_rate"], avg_win, avg_loss)
        if conviction < 54:
            position_pct = 0.0

        current_price = closes.iloc[-1]
        proj_gain = max(fund["analyst_upside"], tf_long["avg_excess_pct"] * 252)
        projected_price = round(float(current_price) * (1 + proj_gain / 100), 2)

        return {
            "ticker": ticker,
            "current_price": round(float(current_price), 2),
            "conviction": conviction,
            "recommendation": rec,
            "position_pct": position_pct,
            "risk_level": risk,
            "signal_reasons": top_reasons,
            # Technical
            "rsi": tech["rsi"],
            "macd_trend": "bullish" if tech["macd_hist"] > 0 else "bearish",
            "above_ma50": bool(current_price > tech["ma50"]),
            "above_ma200": bool(current_price > tech["ma200"]),
            # Quant stats
            "wilson_score": tf_long["wilson"],
            "win_rate": tf_long["win_rate"],
            "sharpe": tf_long["sharpe"],
            "max_drawdown": round(max_dd, 1),
            "volatility_annualised": round(vol, 1),
            # Timeframes
            "tf_short": tf_short,
            "tf_mid": tf_mid,
            "tf_long": tf_long,
            # Fundamentals
            "analyst_target_upside": fund["analyst_upside"],
            "pe": fund["pe"],
            "fwd_pe": fund["fwd_pe"],
            "revenue_growth": fund["revenue_growth"],
            "profit_margin": fund["profit_margin"],
            # Projection
            "projected_1yr_price": projected_price,
            "projected_1yr_gain_pct": round(proj_gain, 1),
            "last_updated": datetime.now().isoformat(),
        }

    except Exception as e:
        print(f"Error analyzing {ticker}: {e}")
        return None
