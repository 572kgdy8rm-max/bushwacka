import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

def advanced_stats(ticker: str):
    try:
        ticker = ticker.upper().strip()
        end = datetime.now()
        start = end - timedelta(days=730)  # 2 years

        stock = yf.Ticker(ticker)
        hist = stock.history(start=start, end=end)

        if len(hist) < 60:
            return None

        # Returns
        closes = hist['Close']
        returns = closes.pct_change().dropna()

        # SPY benchmark
        spy = yf.Ticker("SPY").history(start=start, end=end)['Close'].pct_change().dropna()

        # Align dates
        common = returns.index.intersection(spy.index)
        stock_ret = returns.loc[common]
        spy_ret = spy.loc[common]

        excess = stock_ret - spy_ret

        total_periods = len(excess)
        win_rate = (excess > 0).mean() * 100

        # Wilson Score
        wilson = wilson_lower_bound(win_rate, total_periods)

        # Additional metrics
        sharpe = excess.mean() / excess.std() * np.sqrt(252) if excess.std() > 0 else 0
        volatility = returns.std() * np.sqrt(252) * 100
        max_dd = ((closes / closes.cummax()) - 1).min() * 100
        current_price = closes.iloc[-1]

        # Conviction Score (0-100)
        conviction = (wilson * 0.5) + (sharpe * 12) + (max(0, excess.mean()*100) * 8)
        conviction = max(0, min(100, conviction))

        # Position Sizing + Recommendation
        if conviction >= 85:
            rec = "🔥 STRONG BUY"
            size = 6.0
            risk = "Aggressive"
        elif conviction >= 70:
            rec = "✅ BUY"
            size = 3.5
            risk = "Moderate"
        elif conviction >= 55:
            rec = "⚠️ SMALL POSITION"
            size = 1.5
            risk = "Conservative"
        else:
            rec = "❌ AVOID / WAIT"
            size = 0.0
            risk = "None"

        return {
            "ticker": ticker,
            "conviction": round(conviction, 1),
            "recommendation": rec,
            "position_pct": size,
            "risk_level": risk,
            "wilson_score": round(wilson, 1),
            "win_rate": round(win_rate, 1),
            "sharpe": round(sharpe, 2),
            "annual_vol": round(volatility, 1),
            "max_drawdown": round(max_dd, 1),
            "excess_return": round(excess.mean() * 100, 2),
            "current_price": round(float(current_price), 2),
            "last_updated": datetime.now().isoformat()
        }
    except:
        return None


def wilson_lower_bound(win_rate: float, n: int) -> float:
    if n == 0:
        return 0.0
    p = win_rate / 100
    z = 1.96
    denom = 1 + (z*z)/n
    center = p + (z*z)/(2*n)
    margin = z * np.sqrt((p*(1-p) + (z*z)/(4*n)) / n)
    return max(0.0, (center - margin) / denom * 100)