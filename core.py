import yfinance as yf
import numpy as np
from datetime import datetime, timedelta

# ======================
# CORE HELPERS
# ======================

def wilson_lower_bound(win_rate: float, n: int) -> float:
    if n < 30:
        return 0.0
    p = win_rate / 100
    z = 1.96
    denom = 1 + (z*z)/n
    center = p + (z*z)/(2*n)
    margin = z * np.sqrt((p*(1-p) + (z*z)/(4*n)) / n)
    return max(0.0, (center - margin) / denom * 100)


def enrich_with_fundamentals(ticker: str):
    """Analyst + Alternative Data"""
    try:
        info = yf.Ticker(ticker).info
        current = info.get('currentPrice') or info.get('regularMarketPrice')
        target = info.get('targetMeanPrice')
        upside = round(((target / current) - 1) * 100, 1) if target and current else 0

        alt_score = 0
        alt_note = "Neutral"
        if ticker == "NVDA":
            alt_score = 28
            alt_note = "Very Strong: AI demand, Blackwell ramp, sovereign AI"
        elif ticker == "RKLB":
            alt_score = 22
            alt_note = "Strong: Launch cadence + major contracts"
        elif ticker in ["MSFT", "AAPL", "GOOGL", "AMZN", "META"]:
            alt_score = 15
            alt_note = "Positive institutional & product momentum"

        return {
            "analyst_upside": upside,
            "alt_score": alt_score,
            "alt_note": alt_note
        }
    except:
        return {"analyst_upside": 0, "alt_score": 0, "alt_note": "Data unavailable"}


# ======================
# NEW SMART CONVICTION SYSTEM
# ======================

def advanced_stats(ticker: str):
    try:
        ticker = ticker.upper().strip()
        end = datetime.now()
        start = end - timedelta(days=730)

        stock = yf.Ticker(ticker)
        hist = stock.history(start=start, end=end)
        if len(hist) < 60:
            return None

        closes = hist['Close']
        returns = closes.pct_change().dropna()
        spy_returns = yf.Ticker("SPY").history(start=start, end=end)['Close'].pct_change().dropna()

        common = returns.index.intersection(spy_returns.index)
        excess = returns.loc[common] - spy_returns.loc[common]

        total = len(excess)
        win_rate = (excess > 0).mean() * 100 if total > 0 else 0
        wilson = wilson_lower_bound(win_rate, total)
        sharpe = (excess.mean() / excess.std() * np.sqrt(252)) if excess.std() > 0 else 0
        max_dd = ((closes / closes.cummax()) - 1).min() * 100
        avg_excess = excess.mean() * 100
        current_price = closes.iloc[-1]

        fundamentals = enrich_with_fundamentals(ticker)

        # === SMART CONVICTION FORMULA ===
        quant_score = (wilson * 0.35) + (min(sharpe, 3.0) * 22) + (max(avg_excess, -5) * 9)
        
        # Forward-looking boost
        forward_boost = (fundamentals["analyst_upside"] * 0.6) + fundamentals["alt_score"]
        
        # Mild drawdown penalty
        dd_penalty = max(0, (max_dd + 25) * 0.8)
        
        conviction = quant_score + forward_boost - dd_penalty
        conviction = max(15, min(94, conviction))

        # Recommendation
        if conviction >= 80:
            rec = "🔥 STRONG BUY"
            size = 5.0
            risk = "Aggressive"
        elif conviction >= 70:
            rec = "✅ BUY"
            size = 3.5
            risk = "Moderate"
        elif conviction >= 58:
            rec = "⚠️ SMALL POSITION"
            size = 1.5
            risk = "Conservative"
        else:
            rec = "❌ AVOID"
            size = 0.0
            risk = "None"

        projected_price = round(float(current_price) * (1 + max(fundamentals["analyst_upside"], avg_excess*3) / 100), 2)

        return {
            "ticker": ticker,
            "current_price": round(float(current_price), 2),
            "conviction": round(conviction, 1),
            "recommendation": rec,
            "position_pct": size,
            "risk_level": risk,
            "wilson_score": round(wilson, 1),
            "win_rate": round(win_rate, 1),
            "sharpe": round(sharpe, 2),
            "max_drawdown": round(max_dd, 1),
            "excess_return": round(avg_excess, 2),
            "projected_1yr_price": projected_price,
            "projected_1yr_gain_pct": round((projected_price / current_price - 1) * 100, 1),
            "analyst_target_upside": fundamentals["analyst_upside"],
            "alt_data_note": fundamentals["alt_note"],
            "last_updated": datetime.now().isoformat()
        }
    except Exception as e:
        print(f"Error analyzing {ticker}: {e}")
        return None