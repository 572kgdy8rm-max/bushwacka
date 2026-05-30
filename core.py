"""
core.py — WhaleWatch Pure Quant Engine
All signals derived from price/volume data only. No news, no analyst targets.
"""

import numpy as np
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta

# ── CONSTANTS ──────────────────────────────────────────────────────────────
RSI_PERIOD      = 14
SHARPE_DAYS     = 252        # 1 trading year
ROC_DAYS        = 252        # 12-month rate of change
MA_SHORT        = 50
MA_LONG         = 200
MOMENTUM_DAYS   = 20
HISTORY_DAYS    = 730        # 2 years of daily data

CATEGORY_WEIGHTS = {
    "momentum":          0.30,
    "trend":             0.25,
    "risk":              0.25,
    "relative_strength": 0.20,
}

VERDICT_THRESHOLDS = [
    (80, "Strong Buy"),
    (65, "Buy"),
    (45, "Neutral"),
    (30, "Sell"),
    (0,  "Strong Sell"),
]

# ── HELPERS ────────────────────────────────────────────────────────────────

def clamp(x, lo=0.0, hi=10.0):
    return max(lo, min(hi, x))

def fetch(ticker: str):
    end   = datetime.now()
    start = end - timedelta(days=HISTORY_DAYS)
    df    = yf.Ticker(ticker).history(start=start, end=end)
    if len(df) < 60:
        raise ValueError(f"Not enough data for {ticker}")
    return df

def rsi(closes, period=RSI_PERIOD):
    d     = closes.diff()
    gain  = d.clip(lower=0).rolling(period).mean()
    loss  = (-d.clip(upper=0)).rolling(period).mean()
    rs    = gain / loss.replace(0, np.nan)
    return (100 - 100 / (1 + rs)).iloc[-1]

def macd_hist(closes):
    e12  = closes.ewm(span=12).mean()
    e26  = closes.ewm(span=26).mean()
    m    = e12 - e26
    sig  = m.ewm(span=9).mean()
    return (m - sig).iloc[-1], m.iloc[-1], sig.iloc[-1]

def adx(df, period=14):
    import pandas as pd
    h = df["High"].reset_index(drop=True)
    l = df["Low"].reset_index(drop=True)
    c = df["Close"].reset_index(drop=True)

    prev_c  = c.shift(1)
    prev_h  = h.shift(1)
    prev_l  = l.shift(1)

    tr  = pd.concat([h - l, (h - prev_c).abs(), (l - prev_c).abs()], axis=1).max(axis=1)
    pdm = ((h - prev_h) > (prev_l - l)).astype(float) * (h - prev_h).clip(lower=0)
    ndm = ((prev_l - l) > (h - prev_h)).astype(float) * (prev_l - l).clip(lower=0)

    atr = tr.ewm(span=period, adjust=False).mean()
    pdi = 100 * pdm.ewm(span=period, adjust=False).mean() / atr.replace(0, np.nan)
    ndi = 100 * ndm.ewm(span=period, adjust=False).mean() / atr.replace(0, np.nan)
    dx  = 100 * (pdi - ndi).abs() / (pdi + ndi).replace(0, np.nan)
    return dx.ewm(span=period, adjust=False).mean().iloc[-1]

def obv_slope(df, window=20):
    direction = np.sign(df["Close"].diff())
    obv       = (direction * df["Volume"]).cumsum()
    x         = np.arange(window)
    y         = obv.iloc[-window:].values
    if len(y) < window:
        return 0.0
    slope     = np.polyfit(x, y, 1)[0]
    norm      = df["Volume"].mean()
    return slope / norm if norm else 0.0

def sharpe(returns, rf=0.0):
    ann = returns.mean() * SHARPE_DAYS
    std = returns.std() * np.sqrt(SHARPE_DAYS)
    return (ann - rf) / std if std > 0 else 0.0

def sortino(returns, rf=0.0):
    ann     = returns.mean() * SHARPE_DAYS
    down    = returns[returns < 0]
    d_std   = down.std() * np.sqrt(SHARPE_DAYS) if len(down) > 1 else 1e-9
    return (ann - rf) / d_std

def max_drawdown(closes):
    peak = closes.cummax()
    dd   = (closes / peak - 1)
    return dd.min() * 100

def annualised_vol(returns):
    return returns.std() * np.sqrt(SHARPE_DAYS) * 100

def beta(stock_ret, spy_ret):
    common = stock_ret.index.intersection(spy_ret.index)
    s, m   = stock_ret.loc[common], spy_ret.loc[common]
    cov    = np.cov(s, m)
    return cov[0, 1] / cov[1, 1] if cov[1, 1] > 0 else 1.0

# ── SCORE FUNCTIONS (each returns 0–10) ───────────────────────────────────

def score_rsi(val):
    # Sweet spot 40–60; penalise extremes
    if   val < 20:  return clamp(4 + (val - 20) * 0.1)
    elif val < 30:  return clamp(6 - (30 - val) * 0.2)
    elif val < 40:  return clamp(7 + (val - 30) * 0.1)
    elif val <= 60: return 10.0
    elif val <= 70: return clamp(10 - (val - 60) * 0.3)
    elif val <= 80: return clamp(7  - (val - 70) * 0.3)
    else:           return clamp(4  - (val - 80) * 0.1)

def score_macd(hist_val, m_val):
    # Positive histogram = bullish; crossover bonus
    base = clamp(5 + hist_val * 500)
    return clamp(base)

def score_roc(roc_pct):
    # 0–30% gains score well; negative and >60% penalised
    if   roc_pct < -30: return 0.0
    elif roc_pct < 0:   return clamp(5 + roc_pct / 6)
    elif roc_pct < 30:  return clamp(5 + roc_pct / 6)
    elif roc_pct < 60:  return clamp(10 - (roc_pct - 30) / 10)
    else:               return clamp(7  - (roc_pct - 60) / 20)

def score_obv(slope_norm):
    return clamp(5 + slope_norm * 5)

def score_momentum_20d(ret_20):
    # 20-day return; sweet spot +2% to +10%
    pct = ret_20 * 100
    if   pct < -15: return 0.0
    elif pct < 0:   return clamp(5 + pct / 3)
    elif pct < 10:  return clamp(5 + pct / 2)
    elif pct < 20:  return clamp(10 - (pct - 10) / 5)
    else:           return clamp(8  - (pct - 20) / 10)

def score_vs_ma(price, ma):
    pct = (price / ma - 1) * 100
    if   pct >  15: return clamp(10 - (pct - 15) / 5)
    elif pct >   0: return clamp(7  + pct / 5)
    elif pct > -10: return clamp(7  + pct / 3)
    else:           return clamp(4  + pct / 5)

def score_ma_cross(ma50, ma200):
    spread = (ma50 / ma200 - 1) * 100
    if   spread >  5: return 10.0
    elif spread >  0: return clamp(7 + spread * 0.6)
    elif spread > -5: return clamp(7 + spread * 0.6)
    else:             return 0.0

def score_adx(adx_val):
    if   adx_val >= 40: return 10.0
    elif adx_val >= 25: return clamp(7 + (adx_val - 25) / 5)
    elif adx_val >= 15: return clamp(4 + (adx_val - 15) / 3.3)
    else:               return clamp(adx_val / 3)

def score_52w(price, low52, high52):
    rng = high52 - low52
    if rng == 0: return 5.0
    pos = (price - low52) / rng * 100
    # Upper third scores best for trend; very top slightly penalised
    if   pos > 90: return 8.0
    elif pos > 60: return clamp(6 + (pos - 60) / 15)
    elif pos > 30: return clamp(4 + (pos - 30) / 15)
    else:          return clamp(pos / 7.5)

def score_sharpe(sh):
    if   sh >= 2.0: return 10.0
    elif sh >= 1.0: return clamp(7 + (sh - 1.0) * 3)
    elif sh >= 0.0: return clamp(5 + sh * 2)
    elif sh >= -1:  return clamp(5 + sh * 3)
    else:           return 0.0

def score_sortino(so):
    if   so >= 3.0: return 10.0
    elif so >= 1.5: return clamp(7 + (so - 1.5) * 2)
    elif so >= 0.0: return clamp(5 + so * 1.3)
    elif so >= -1:  return clamp(5 + so * 3)
    else:           return 0.0

def score_drawdown(dd_pct):
    # dd_pct is negative
    if   dd_pct > -10: return 10.0
    elif dd_pct > -20: return clamp(10 + (dd_pct + 10) / 2)
    elif dd_pct > -35: return clamp(5  + (dd_pct + 20) / 3)
    elif dd_pct > -50: return clamp(5  + (dd_pct + 35) / 5)
    else:              return 0.0

def score_volatility(vol_pct):
    if   vol_pct < 15: return 10.0
    elif vol_pct < 25: return clamp(10 - (vol_pct - 15) / 2)
    elif vol_pct < 40: return clamp(5  - (vol_pct - 25) / 5)
    elif vol_pct < 60: return clamp(2  - (vol_pct - 40) / 20)
    else:              return 0.0

def score_beta(b):
    if   b < 0:   return 3.0
    elif b < 0.5: return clamp(5 + b * 4)
    elif b < 1.0: return 10.0
    elif b < 1.5: return clamp(10 - (b - 1.0) * 4)
    elif b < 2.0: return clamp(8  - (b - 1.5) * 6)
    else:         return clamp(5  - (b - 2.0) * 2)

def score_alpha(alpha_pct):
    if   alpha_pct >  15: return 10.0
    elif alpha_pct >   5: return clamp(7 + (alpha_pct - 5) / 3.3)
    elif alpha_pct >   0: return clamp(5 + alpha_pct * 0.4)
    elif alpha_pct >  -5: return clamp(5 + alpha_pct * 0.6)
    elif alpha_pct > -15: return clamp(2 + (alpha_pct + 5) / 5)
    else:                 return 0.0

def score_win_rate(wr_pct):
    if   wr_pct >= 60: return 10.0
    elif wr_pct >= 52: return clamp(6 + (wr_pct - 52) / 2)
    elif wr_pct >= 48: return clamp(5 + (wr_pct - 48) / 0.8)
    elif wr_pct >= 40: return clamp(5 - (48 - wr_pct) / 2.7)
    else:              return 0.0

def score_excess_consistency(excess_returns):
    """Fraction of rolling 20-day windows where stock beat SPY."""
    windows = [excess_returns.iloc[i:i+20].sum() for i in range(0, len(excess_returns)-20, 5)]
    if not windows: return 5.0
    frac = sum(1 for w in windows if w > 0) / len(windows) * 100
    return score_win_rate(frac)

# ── WARNINGS ───────────────────────────────────────────────────────────────

def compute_warnings(rsi_val, ma50, ma200, dd_pct, vol_pct, b, adx_val, sharpe_val):
    flags = []
    if ma50 < ma200:
        flags.append("⚠️ Death cross active (MA50 < MA200)")
    if rsi_val > 75:
        flags.append(f"⚠️ RSI overbought ({rsi_val:.0f}) — pullback risk")
    elif rsi_val < 25:
        flags.append(f"⚠️ RSI oversold ({rsi_val:.0f}) — high selling pressure")
    if dd_pct < -40:
        flags.append(f"⚠️ Deep drawdown ({dd_pct:.0f}%) — significant historical loss")
    if vol_pct > 60:
        flags.append(f"⚠️ Extreme volatility ({vol_pct:.0f}% ann.) — unpredictable")
    if sharpe_val < 0:
        flags.append(f"⚠️ Negative Sharpe ({sharpe_val:.2f}) — poor risk-adjusted return")
    if b > 2.0:
        flags.append(f"⚠️ Beta {b:.1f} — moves 2× the market, very high sensitivity")
    if adx_val < 15:
        flags.append(f"⚠️ ADX {adx_val:.0f} — no clear trend, directionless")
    return flags[:3]

# ── ENTRY FLAG ─────────────────────────────────────────────────────────────

def entry_flag(rsi_val, price, ma50, bb_upper, bb_lower, mom_20):
    above_bb  = price > bb_upper
    below_bb  = price < bb_lower
    extended  = above_bb or (rsi_val > 68) or (mom_20 > 0.12)
    oversold  = below_bb or rsi_val < 32
    if oversold:
        return "Oversold Bounce"
    elif extended:
        return "Wait for Pullback"
    else:
        return "Good Entry"

# ── RISK DOWNGRADE ─────────────────────────────────────────────────────────

def apply_risk_downgrade(verdict, vol_pct, dd_pct):
    order = ["Strong Sell", "Sell", "Neutral", "Buy", "Strong Buy"]
    if vol_pct > 60 or dd_pct < -50:
        idx = order.index(verdict)
        return order[max(0, idx - 1)]
    return verdict

# ── MAIN ANALYSIS ──────────────────────────────────────────────────────────

def analyze(ticker: str, spy_df=None) -> dict:
    ticker = ticker.upper().strip()
    df     = fetch(ticker)
    closes = df["Close"]
    ret    = closes.pct_change().dropna()

    # SPY for relative strength
    if spy_df is None:
        spy_df = fetch("SPY")
    spy_ret = spy_df["Close"].pct_change().dropna()

    # ── RAW VALUES ──
    rsi_val     = rsi(closes)
    hist_val, m_val, sig_val = macd_hist(closes)
    roc_val     = (closes.iloc[-1] / closes.iloc[-ROC_DAYS] - 1) * 100 if len(closes) >= ROC_DAYS else 0.0
    obv_s       = obv_slope(df)
    mom_20      = (closes.iloc[-1] / closes.iloc[-MOMENTUM_DAYS] - 1) if len(closes) >= MOMENTUM_DAYS else 0.0
    ma50_val    = closes.rolling(MA_SHORT).mean().iloc[-1]
    ma200_val   = closes.rolling(MA_LONG).mean().iloc[-1]
    adx_val     = adx(df)
    low52       = closes.iloc[-252:].min() if len(closes) >= 252 else closes.min()
    high52      = closes.iloc[-252:].max() if len(closes) >= 252 else closes.max()
    price       = closes.iloc[-1]
    sh          = sharpe(ret)
    so          = sortino(ret)
    dd          = max_drawdown(closes)
    vol         = annualised_vol(ret)
    b           = beta(ret, spy_ret)

    # Bollinger (20, 2σ)
    bb_mid   = closes.rolling(20).mean()
    bb_std   = closes.rolling(20).std()
    bb_upper = (bb_mid + 2 * bb_std).iloc[-1]
    bb_lower = (bb_mid - 2 * bb_std).iloc[-1]

    # Relative strength alphas
    def alpha_n(days):
        common = ret.index.intersection(spy_ret.index)
        s_r = ret.loc[common].iloc[-days:]
        m_r = spy_ret.loc[common].iloc[-days:]
        return ((1 + s_r).prod() - (1 + m_r).prod()) * 100

    alpha_3m  = alpha_n(63)
    alpha_6m  = alpha_n(126)
    alpha_1y  = alpha_n(252)

    common    = ret.index.intersection(spy_ret.index)
    excess    = ret.loc[common] - spy_ret.loc[common]
    wr        = (excess > 0).mean() * 100

    # ── PER-METRIC SCORES (0–10) ──
    scores = {
        # Momentum
        "RSI":              score_rsi(rsi_val),
        "MACD":             score_macd(hist_val, m_val),
        "Rate of Change":   score_roc(roc_val),
        "OBV Trend":        score_obv(obv_s),
        "20d Momentum":     score_momentum_20d(mom_20),
        # Trend
        "vs MA50":          score_vs_ma(price, ma50_val),
        "vs MA200":         score_vs_ma(price, ma200_val),
        "MA Cross":         score_ma_cross(ma50_val, ma200_val),
        "ADX Strength":     score_adx(adx_val),
        "52w Range":        score_52w(price, low52, high52),
        # Risk
        "Sharpe (1yr)":     score_sharpe(sh),
        "Sortino (1yr)":    score_sortino(so),
        "Max Drawdown":     score_drawdown(dd),
        "Volatility":       score_volatility(vol),
        "Beta vs SPY":      score_beta(b),
        # Relative Strength
        "Alpha 3m":         score_alpha(alpha_3m),
        "Alpha 6m":         score_alpha(alpha_6m),
        "Alpha 1yr":        score_alpha(alpha_1y),
        "Excess Consistency": score_excess_consistency(excess),
        "Win Rate vs SPY":  score_win_rate(wr),
    }

    # Round all scores
    scores = {k: round(v, 1) for k, v in scores.items()}

    # ── CATEGORY SCORES (0–100) ──
    def cat(keys):
        vals = [scores[k] for k in keys]
        return round(np.mean(vals) * 10, 1)

    momentum_score  = cat(["RSI", "MACD", "Rate of Change", "OBV Trend", "20d Momentum"])
    trend_score     = cat(["vs MA50", "vs MA200", "MA Cross", "ADX Strength", "52w Range"])
    risk_score      = cat(["Sharpe (1yr)", "Sortino (1yr)", "Max Drawdown", "Volatility", "Beta vs SPY"])
    rs_score        = cat(["Alpha 3m", "Alpha 6m", "Alpha 1yr", "Excess Consistency", "Win Rate vs SPY"])

    conviction = round(
        momentum_score  * CATEGORY_WEIGHTS["momentum"] +
        trend_score     * CATEGORY_WEIGHTS["trend"] +
        risk_score      * CATEGORY_WEIGHTS["risk"] +
        rs_score        * CATEGORY_WEIGHTS["relative_strength"],
        1
    )

    # ── VERDICT ──
    verdict = next(v for threshold, v in VERDICT_THRESHOLDS if conviction >= threshold)
    verdict = apply_risk_downgrade(verdict, vol, dd)

    # ── WARNINGS ──
    warnings = compute_warnings(rsi_val, ma50_val, ma200_val, dd, vol, b, adx_val, sh)

    # ── ENTRY FLAG ──
    entry = entry_flag(rsi_val, price, ma50_val, bb_upper, bb_lower, mom_20)

    return {
        "ticker":           ticker,
        "price":            round(float(price), 2),
        "conviction":       conviction,
        "verdict":          verdict,
        "entry_flag":       entry,
        "warnings":         warnings,
        # Category scores
        "momentum_score":   momentum_score,
        "trend_score":      trend_score,
        "risk_score":       risk_score,
        "rs_score":         rs_score,
        # Per-metric scores
        "metrics": {
            "Momentum":          {k: scores[k] for k in ["RSI", "MACD", "Rate of Change", "OBV Trend", "20d Momentum"]},
            "Trend":             {k: scores[k] for k in ["vs MA50", "vs MA200", "MA Cross", "ADX Strength", "52w Range"]},
            "Risk":              {k: scores[k] for k in ["Sharpe (1yr)", "Sortino (1yr)", "Max Drawdown", "Volatility", "Beta vs SPY"]},
            "Relative Strength": {k: scores[k] for k in ["Alpha 3m", "Alpha 6m", "Alpha 1yr", "Excess Consistency", "Win Rate vs SPY"]},
        },
        # Raw values for display
        "raw": {
            "rsi":        round(rsi_val, 1),
            "macd_hist":  round(float(hist_val), 4),
            "roc_pct":    round(roc_val, 1),
            "mom_20d_pct":round(mom_20 * 100, 1),
            "ma50":       round(float(ma50_val), 2),
            "ma200":      round(float(ma200_val), 2),
            "adx":        round(adx_val, 1),
            "52w_low":    round(float(low52), 2),
            "52w_high":   round(float(high52), 2),
            "sharpe":     round(sh, 2),
            "sortino":    round(so, 2),
            "max_dd_pct": round(dd, 1),
            "vol_pct":    round(vol, 1),
            "beta":       round(b, 2),
            "alpha_3m":   round(alpha_3m, 1),
            "alpha_6m":   round(alpha_6m, 1),
            "alpha_1y":   round(alpha_1y, 1),
            "win_rate":   round(wr, 1),
        },
        "analysed_at": datetime.now().isoformat(),
    }
