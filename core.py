import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# ======================
# HELPER FUNCTIONS
# ======================

def wilson_lower_bound(win_rate: float, n: int) -> float:
    """Wilson score 95% confidence interval"""
    if n == 0:
        return 0.0
    p = win_rate / 100
    z = 1.96
    denom = 1 + (z*z)/n
    center = p + (z*z)/(2*n)
    margin = z * np.sqrt((p*(1-p) + (z*z)/(4*n)) / n)
    return max(0.0, (center - margin) / denom * 100)


# ======================
# CORE BACKTEST FUNCTION
# ======================

def backtest_window(ticker: str, start_date: str, end_date: str):
    """
    Core backtest function.
    Inputs: ticker, start_date (YYYY-MM-DD), end_date (YYYY-MM-DD)
    Outputs: Sharpe, Max Drawdown, Win Rate vs SPY
    """
    try:
        ticker = ticker.upper().strip()
        
        stock = yf.Ticker(ticker)
        hist = stock.history(start=start_date, end=end_date)
        
        if len(hist) < 30:
            return None

        closes = hist['Close']
        returns = closes.pct_change().dropna()

        # SPY benchmark
        spy = yf.Ticker("SPY").history(start=start_date, end=end_date)['Close'].pct_change().dropna()

        # Align dates
        common_idx = returns.index.intersection(spy.index)
        stock_ret = returns.loc[common_idx]
        spy_ret = spy.loc[common_idx]

        excess = stock_ret - spy_ret

        total_periods = len(excess)
        win_rate = (excess > 0).mean() * 100 if total_periods > 0 else 0
        
        sharpe = (excess.mean() / excess.std() * np.sqrt(252)) if excess.std() > 0 else 0
        max_dd = ((closes / closes.cummax()) - 1).min() * 100
        avg_excess = excess.mean() * 100

        return {
            "ticker": ticker,
            "period": f"{start_date} to {end_date}",
            "sharpe": round(sharpe, 3),
            "max_drawdown": round(max_dd, 2),
            "win_rate_vs_spy": round(win_rate, 1),
            "excess_return_pct": round(avg_excess, 2),
            "num_days": int(total_periods)
        }
    except Exception as e:
        print(f"Backtest error for {ticker} {start_date}-{end_date}: {e}")
        return None


# ======================
# WALK-FORWARD WRAPPER
# ======================

def walk_forward_backtest(ticker: str, 
                         start_date: str, 
                         end_date: str = None, 
                         window_years: int = 1, 
                         step_months: int = 3):
    """
    Walk-forward backtest.
    Test periods never overlap with training periods.
    """
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
        
        train_start_str = current_start.strftime("%Y-%m-%d")
        train_end_str = train_end.strftime("%Y-%m-%d")
        test_start_str = test_start.strftime("%Y-%m-%d")
        test_end_str = test_end.strftime("%Y-%m-%d")
        
        # Only testing on out-of-sample period
        test_result = backtest_window(ticker, test_start_str, test_end_str)
        
        if test_result:
            test_result["train_period"] = f"{train_start_str} to {train_end_str}"
            results.append(test_result)
        
        # Step forward
        current_start = current_start + timedelta(days=30 * step_months)
    
    # Summary
    if results:
        avg_sharpe = np.mean([r["sharpe"] for r in results])
        avg_winrate = np.mean([r["win_rate_vs_spy"] for r in results])
        worst_dd = min([r["max_drawdown"] for r in results])
        
        return {
            "ticker": ticker,
            "windows_tested": len(results),
            "avg_sharpe": round(avg_sharpe, 3),
            "avg_win_rate": round(avg_winrate, 1),
            "worst_drawdown": round(worst_dd, 2),
            "results": results
        }
    return None


# ======================
# LIVE SIGNAL FUNCTION (for your web app)
# ======================

def advanced_stats(ticker: str):
    """Live signal used by the frontend"""
    try:
        ticker = ticker.upper().strip()
        end = datetime.now()
        start = end - timedelta(days=730)  # 2 years

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

        total_periods = len(excess)
        win_rate = (excess > 0).mean() * 100

        wilson = wilson_lower_bound(win_rate, total_periods)

        sharpe = excess.mean() / excess.std() * np.sqrt(252) if excess.std() > 0 else 0
        volatility = returns.std() * np.sqrt(252) * 100
        max_dd = ((closes / closes.cummax()) - 1).min() * 100
        current_price = closes.iloc[-1]

        conviction = (wilson * 0.5) + (sharpe * 12) + (max(0, excess.mean()*100) * 8)
        conviction = max(0, min(100, conviction))

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