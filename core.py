import yfinance as yf
import numpy as np
from datetime import datetime, timedelta

def wilson_lower_bound(win_rate: float, n: int) -> float:
    if n < 30:
        return 0.0
    p = win_rate / 100
    z = 1.96
    denom = 1 + (z*z)/n
    center = p + (z*z)/(2*n)
    margin = z * np.sqrt((p*(1-p) + (z*z)/(4*n)) / n)
    return max(0.0, (center - margin) / denom * 100)


def calculate_conviction(wilson: float, sharpe: float, excess: float, max_dd: float) -> float:
    base = (wilson * 0.45) + (min(sharpe, 3.0) * 18) + (max(excess, 0) * 12)
    dd_penalty = max(0, (max_dd + 15) * 1.8)
    conviction = base - dd_penalty
    return max(10, min(95, conviction))


def enrich_with_fundamentals(ticker: str):
    try:
        info = yf.Ticker(ticker).info
        current = info.get('currentPrice') or info.get('regularMarketPrice')
        target = info.get('targetMeanPrice')
        upside = round(((target / current) - 1) * 100, 1) if target and current else None

        alt_note = "No strong alt data"
        if ticker == "NVDA":
            alt_note = "Very Strong AI demand (Blackwell, sovereign AI, earnings calls)"
        elif ticker == "RKLB":
            alt_note = "Strong launch cadence + government contracts"

        return {
            "analyst_target_upside": upside,
            "alt_data_note": alt_note,
            "boost": 1.15 if upside and upside > 20 else 1.05
        }
    except:
        return {"analyst_target_upside": None, "alt_data_note": "Data unavailable", "boost": 1.0}


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

        conviction = calculate_conviction(wilson, sharpe, avg_excess, max_dd)

        fundamentals = enrich_with_fundamentals(ticker)
        conviction = min(95, conviction * fundamentals["boost"])

        # Simple projection
        projected_1yr_price = round(float(current_price) * (1 + max(avg_excess * 4, 8) / 100), 2)

        if conviction >= 82:
            rec = "🔥 STRONG BUY"; size = 5.0; risk = "Aggressive"
        elif conviction >= 72:
            rec = "✅ BUY"; size = 3.0; risk = "Moderate"
        elif conviction >= 58:
            rec = "⚠️ SMALL POSITION"; size = 1.5; risk = "Conservative"
        else:
            rec = "❌ AVOID"; size = 0.0; risk = "None"

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
            "projected_1yr_price": projected_1yr_price,
            "projected_1yr_gain_pct": round((projected_1yr_price / current_price - 1) * 100, 1),
            "analyst_target_upside": fundamentals["analyst_target_upside"],
            "alt_data_note": fundamentals["alt_data_note"],
            "last_updated": datetime.now().isoformat()
        }
    except Exception as e:
        print(f"Error: {e}")
        return None