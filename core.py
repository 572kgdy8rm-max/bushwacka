import yfinance as yf
import pandas as pd
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
    denom = 1 + (z*z)/n
    center = p + (z*z)/(2*n)
    margin = z * np.sqrt((p*(1-p) + (z*z)/(4*n)) / n)
    return max(0.0, (center - margin) / denom * 100)


def calculate_conviction(wilson: float, sharpe: float, excess: float, max_dd: float) -> float:
    base = (wilson * 0.45) + (min(sharpe, 3.0) * 18) + (max(excess, 0) * 12)
    dd_penalty = max(0, (max_dd + 15) * 1.8)
    conviction = base - dd_penalty
    return max(10, min(95, conviction))


# ======================
# CORE BACKTEST
# ======================

def backtest_window(ticker: str, start_date: str, end_date: str):
    try:
        stock = yf.Ticker(ticker)
        hist = stock.history(start=start_date, end=end_date)
        if len(hist) < 30:
            return None

        closes = hist['Close']
        returns = closes.pct_change().dropna()

        spy = yf.Ticker("SPY").history(start=start_date, end=end_date)['Close'].pct_change().dropna()
        common = returns.index.intersection(spy.index)
        
        stock_ret = returns.loc[common]
        spy_ret = spy.loc[common]
        excess = stock_ret - spy_ret

        total = len(excess)
        win_rate = (excess > 0).mean() * 100 if total > 0 else 0
        sharpe = (excess.mean() / excess.std() * np.sqrt(252)) if excess.std() > 0 else 0
        max_dd = ((closes / closes.cummax()) - 1).min() * 100
        avg_excess = excess.mean() * 100

        return {
            "sharpe": round(sharpe, 3),
            "max_drawdown": round(max_dd, 2),
            "win_rate_vs_spy": round(win_rate, 1),
            "excess_return_pct": round(avg_excess, 2),
            "num_days": int(total)
        }
    except:
        return None


# ======================
# WALK-FORWARD BACKTEST
# ======================

def walk_forward_backtest(ticker: str, start_date: str, end_date: str = None, 
                         window_years: int = 1, step_months: int = 3):
    if end_date is None:
        end_date = datetime.now().strftime("%Y-%m-%d")
    
    results = []
    current_start = datetime.strptime(start_date, "%Y-%m-%d")
    final_end = datetime.strptime(end_date, "%Y-%m-%d")
    
    while current_start + timedelta(days=365 * window_years) < final_end:
        train_end = current_start + timedelta(days=365 * window_years)
        test_start = train_end
        test_end = test_start + timedelta(days=30 * step_months)
        
        if test_end > final_end:
            test_end = final_end

        test_result = backtest_window(ticker, test_start.strftime("%Y-%m-%d"), test_end.strftime("%Y-%m-%d"))
        
        if test_result:
            test_result["test_period"] = f"{test_start.strftime('%Y-%m-%d')} to {test_end.strftime('%Y-%m-%d')}"
            results.append(test_result)
        
        current_start += timedelta(days=30 * step_months)
    
    if not results:
        return None
        
    return {
        "ticker": ticker,
        "windows_tested": len(results),
        "avg_sharpe": round(np.mean([r["sharpe"] for r in results]), 3),
        "avg_win_rate": round(np.mean([r["win_rate_vs_spy"] for r in results]), 1),
        "worst_drawdown": round(min([r["max_drawdown"] for r in results]), 2),
        "avg_excess_return": round(np.mean([r["excess_return_pct"] for r in results]), 2),
        "results": results[-6:]  # Last 6 windows for visibility
    }


# ======================
# LIVE SIGNAL + PROJECTION
# ======================

def advanced_stats(ticker: str):
    """Main function used by your app"""
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

        spy = yf.Ticker("SPY").history(start=start, end=end)['Close'].pct_change().dropna()
        common = returns.index.intersection(spy.index)
        stock_ret = returns.loc[common]
        spy_ret = spy.loc[common]

        excess = stock_ret - spy_ret
        total = len(excess)
        win_rate = (excess > 0).mean() * 100 if total > 0 else 0

        wilson = wilson_lower_bound(win_rate, total)
        sharpe = (excess.mean() / excess.std() * np.sqrt(252)) if excess.std() > 0 else 0
        max_dd = ((closes / closes.cummax()) - 1).min() * 100
        avg_excess = excess.mean() * 100
        current_price = closes.iloc[-1]

        conviction = calculate_conviction(wilson, sharpe, avg_excess, max_dd)

        # Run walk-forward for projections
        wf = walk_forward_backtest(ticker, "2020-01-01")

        # Projection logic
        if wf and wf["avg_excess_return"] > 0:
            projected_annual_excess = wf["avg_excess_return"] * 12   # rough annualization from monthly-ish windows
            projected_1yr = round(current_price * (1 + projected_annual_excess/100), 2)
        else:
            projected_annual_excess = avg_excess * 4   # fallback
            projected_1yr = round(current_price * (1 + projected_annual_excess/100 * 0.6), 2)

        # Recommendation
        if conviction >= 82:
            rec = "🔥 STRONG BUY"
            size = 5.0
            risk = "Aggressive"
        elif conviction >= 72:
            rec = "✅ BUY"
            size = 3.0
            risk = "Moderate"
        elif conviction >= 58:
            rec = "⚠️ SMALL POSITION"
            size = 1.5
            risk = "Conservative"
        else:
            rec = "❌ AVOID"
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
            "max_drawdown": round(max_dd, 1),
            "excess_return": round(avg_excess, 2),
            "current_price": round(float(current_price), 2),
            
            # Projections
            "projected_1yr_price": projected_1yr,
            "projected_1yr_gain_pct": round((projected_1yr / current_price - 1) * 100, 1),
            "walkforward_windows": wf["windows_tested"] if wf else 0,
            "wf_avg_sharpe": wf["avg_sharpe"] if wf else None,
            "wf_avg_excess": wf["avg_excess_return"] if wf else None,
            
            "last_updated": datetime.now().isoformat()
        }
    except Exception as e:
        print(f"Error analyzing {ticker}: {e}")
        return None