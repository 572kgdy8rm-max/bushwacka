"""
core.py — WhaleWatch Pure Quant Engine
All signals derived from price/volume data only. No news, no analyst targets.
Changes: removed Max Drawdown from Risk scoring, threshold position sizing,
         added sector + earnings date, data-as-of date.
v2 additions: OBV fix, short interest, forward P/E vs sector, earnings revision
              direction, sector ETF relative strength.
"""

import numpy as np
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta

# ── CONSTANTS ──────────────────────────────────────────────────────────────
RSI_PERIOD    = 14
SHARPE_DAYS   = 252
ROC_DAYS      = 252
MA_SHORT      = 50
MA_LONG       = 200
MOMENTUM_DAYS = 20
HISTORY_DAYS  = 730

CATEGORY_WEIGHTS = {
    "momentum":          0.28,
    "trend":             0.24,
    "risk":              0.23,
    "relative_strength": 0.20,
    "fundamental":       0.05,   # lightweight sanity check, low weight
}

VERDICT_THRESHOLDS = [
    (80, "Strong Buy"),
    (65, "Buy"),
    (45, "Neutral"),
    (30, "Sell"),
    (0,  "Strong Sell"),
]

# ── SECTOR ETF MAP ─────────────────────────────────────────────────────────
# Maps yfinance sector string → sector ETF ticker
SECTOR_ETF = {
    "Technology":             "XLK",
    "Consumer Cyclical":      "XLY",
    "Consumer Defensive":     "XLP",
    "Communication Services": "XLC",
    "Financial Services":     "XLF",
    "Healthcare":             "XLV",
    "Industrials":            "XLI",
    "Energy":                 "XLE",
    "Basic Materials":        "XLB",
    "Utilities":              "XLU",
    "Real Estate":            "XLRE",
}

# ── SECTOR FORWARD P/E MEDIANS ─────────────────────────────────────────────
# Updated periodically — these are approximate S&P 500 sector medians
SECTOR_PE_MEDIAN = {
    "Technology":             28.0,
    "Consumer Cyclical":      22.0,
    "Consumer Defensive":     20.0,
    "Communication Services": 20.0,
    "Financial Services":     13.0,
    "Healthcare":             17.0,
    "Industrials":            20.0,
    "Energy":                 12.0,
    "Basic Materials":        15.0,
    "Utilities":              16.0,
    "Real Estate":            32.0,
    "Unknown":                20.0,
}

# ── POSITION SIZING ────────────────────────────────────────────────────────
def position_size(conviction: float, entry_flag: str) -> dict:
    if entry_flag == "Wait for Pullback":
        return {"pct": 0.0, "label": "Skip — wait for pullback"}
    if conviction >= 80:
        return {"pct": 100.0, "label": "Full position"}
    elif conviction >= 65:
        return {"pct": 50.0,  "label": "Half position"}
    elif conviction >= 54:
        return {"pct": 25.0,  "label": "Quarter position"}
    else:
        return {"pct": 0.0,   "label": "No position"}

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

def get_metadata(ticker: str) -> dict:
    EMPTY = {
        "sector":        "Unknown",
        "earnings_date": "Unknown",
        "fwd_pe":        None,
        "short_pct":     None,
        "rec_mean":      None,
        "rec_key":       None,
        "num_analysts":  0,
    }
    try:
        t    = yf.Ticker(ticker)
        info = t.fast_info  # faster, more reliable than .info for price data

        # Fall back to full info for fundamental fields
        full = {}
        try:
            full = t.info or {}
        except:
            pass

        # ── Sector ──────────────────────────────────────────────────────
        sector = (
            full.get("sector") or
            full.get("sectorDisp") or
            full.get("sectorKey") or
            "Unknown"
        )

        # ── Earnings date ────────────────────────────────────────────────
        # ── Earnings date ────────────────────────────────────────────────
earnings = "Unknown"
try:
    cal = t.calendar
    if cal is not None:
        # yfinance returns dict in newer versions, DataFrame in older
        if isinstance(cal, dict):
            ed = cal.get("Earnings Date") or cal.get("earningsDate") or cal.get("Earnings Dates")
            if ed:
                # ed is usually a list
                first = ed[0] if hasattr(ed, '__iter__') and not isinstance(ed, str) else ed
                if hasattr(first, 'date'):
                    earnings = str(first.date())
                else:
                    earnings = str(first)[:10]
        elif hasattr(cal, 'empty') and not cal.empty:
            col = cal.columns[0]
            earnings = str(col.date()) if hasattr(col, 'date') else str(col)[:10]
except:
    pass

# Second attempt via full info dict
if earnings == "Unknown":
    try:
        ed = full.get("earningsDate") or full.get("nextEarningsDate")
        if ed:
            first = list(ed)[0] if hasattr(ed, '__iter__') and not isinstance(ed, str) else ed
            earnings = str(first)[:10]
    except:
        pass

# Third attempt via earnings dates history
if earnings == "Unknown":
    try:
        hist = t.earnings_dates
        if hist is not None and not hist.empty:
            future = hist[hist.index > pd.Timestamp.now()]
            if not future.empty:
                earnings = str(future.index[-1].date())
    except:
        pass


        # ── Forward P/E ──────────────────────────────────────────────────
        fwd_pe = None
        for key in ("forwardPE", "trailingPE"):
            raw = full.get(key)
            if raw and isinstance(raw, (int, float)) and 0 < raw < 2000:
                fwd_pe = round(float(raw), 1)
                break

        # ── Short interest ───────────────────────────────────────────────
        short_pct = None
        raw_short = full.get("shortPercentOfFloat") or full.get("shortRatio")
        if raw_short and isinstance(raw_short, (int, float)):
            # shortPercentOfFloat comes as 0.03 = 3%, shortRatio is different
            val = float(raw_short)
            if full.get("shortPercentOfFloat"):
                short_pct = round(val * 100, 1)
            # shortRatio is days-to-cover, not %, so skip it here

        # ── Analyst consensus ────────────────────────────────────────────
        rec_mean = None
        rec_key  = None
        num_analysts = 0
        raw_rec = full.get("recommendationMean")
        if raw_rec and isinstance(raw_rec, (int, float)):
            rec_mean = round(float(raw_rec), 2)
        rec_key      = full.get("recommendationKey") or None
        num_analysts = int(full.get("numberOfAnalystOpinions") or 0)

        return {
            "sector":        sector,
            "earnings_date": earnings,
            "fwd_pe":        fwd_pe,
            "short_pct":     short_pct,
            "rec_mean":      rec_mean,
            "rec_key":       rec_key,
            "num_analysts":  num_analysts,
        }

    except Exception as e:
        print(f"  [metadata] {ticker} failed: {e}")
        return EMPTY

# ── TECHNICAL CALCULATIONS ─────────────────────────────────────────────────

def rsi(closes, period=RSI_PERIOD):
    d    = closes.diff()
    gain = d.clip(lower=0).rolling(period).mean()
    loss = (-d.clip(upper=0)).rolling(period).mean()
    rs   = gain / loss.replace(0, np.nan)
    return (100 - 100 / (1 + rs)).iloc[-1]

def macd_hist(closes):
    e12 = closes.ewm(span=12).mean()
    e26 = closes.ewm(span=26).mean()
    m   = e12 - e26
    sig = m.ewm(span=9).mean()
    return (m - sig).iloc[-1], m.iloc[-1], sig.iloc[-1]

def adx(df, period=14):
    h      = df["High"].reset_index(drop=True)
    l      = df["Low"].reset_index(drop=True)
    c      = df["Close"].reset_index(drop=True)
    prev_c = c.shift(1)
    prev_h = h.shift(1)
    prev_l = l.shift(1)
    tr     = pd.concat([h - l, (h - prev_c).abs(), (l - prev_c).abs()], axis=1).max(axis=1)
    pdm    = ((h - prev_h) > (prev_l - l)).astype(float) * (h - prev_h).clip(lower=0)
    ndm    = ((prev_l - l) > (h - prev_h)).astype(float) * (prev_l - l).clip(lower=0)
    atr    = tr.ewm(span=period, adjust=False).mean()
    pdi    = 100 * pdm.ewm(span=period, adjust=False).mean() / atr.replace(0, np.nan)
    ndi    = 100 * ndm.ewm(span=period, adjust=False).mean() / atr.replace(0, np.nan)
    dx     = 100 * (pdi - ndi).abs() / (pdi + ndi).replace(0, np.nan)
    return dx.ewm(span=period, adjust=False).mean().iloc[-1]

def obv_slope(df, window=20):
    """
    Returns (normalised_slope, direction_string).
    Normalised slope: slope of OBV line divided by mean volume,
    so the value is dimensionless and comparable across tickers.
    """
    direction = np.sign(df["Close"].diff())
    obv       = (direction * df["Volume"]).cumsum()
    if len(obv) < window:
        return 0.0, "Flat"
    x     = np.arange(window)
    y     = obv.iloc[-window:].values
    slope = np.polyfit(x, y, 1)[0]
    norm  = df["Volume"].mean()
    norm_slope = slope / norm if norm else 0.0

    if   norm_slope >  0.05: direction_str = "↑ Strong"
    elif norm_slope >  0.01: direction_str = "↑ Positive"
    elif norm_slope > -0.01: direction_str = "→ Flat"
    elif norm_slope > -0.05: direction_str = "↓ Negative"
    else:                    direction_str = "↓ Weak"

    return norm_slope, direction_str

def sharpe(returns, rf=0.0):
    ann = returns.mean() * SHARPE_DAYS
    std = returns.std() * np.sqrt(SHARPE_DAYS)
    return (ann - rf) / std if std > 0 else 0.0

def sortino(returns, rf=0.0):
    ann   = returns.mean() * SHARPE_DAYS
    down  = returns[returns < 0]
    d_std = down.std() * np.sqrt(SHARPE_DAYS) if len(down) > 1 else 1e-9
    return (ann - rf) / d_std

def max_drawdown(closes):
    peak = closes.cummax()
    return ((closes / peak) - 1).min() * 100

def annualised_vol(returns):
    return returns.std() * np.sqrt(SHARPE_DAYS) * 100

def beta(stock_ret, spy_ret):
    common = stock_ret.index.intersection(spy_ret.index)
    s, m   = stock_ret.loc[common], spy_ret.loc[common]
    cov    = np.cov(s, m)
    return cov[0, 1] / cov[1, 1] if cov[1, 1] > 0 else 1.0

# ── SCORE FUNCTIONS (0–10) ─────────────────────────────────────────────────

def score_rsi(val):
    if   val < 20:  return clamp(4 + (val - 20) * 0.1)
    elif val < 30:  return clamp(6 - (30 - val) * 0.2)
    elif val < 40:  return clamp(7 + (val - 30) * 0.1)
    elif val <= 60: return 10.0
    elif val <= 70: return clamp(10 - (val - 60) * 0.3)
    elif val <= 80: return clamp(7  - (val - 70) * 0.3)
    else:           return clamp(4  - (val - 80) * 0.1)

def score_macd(hist_val, m_val):
    return clamp(5 + hist_val * 500)

def score_roc(roc_pct):
    if   roc_pct < -30: return 0.0
    elif roc_pct < 0:   return clamp(5 + roc_pct / 6)
    elif roc_pct < 30:  return clamp(5 + roc_pct / 6)
    elif roc_pct < 60:  return clamp(10 - (roc_pct - 30) / 10)
    else:               return clamp(7  - (roc_pct - 60) / 20)

def score_obv(slope_norm):
    """Score OBV normalised slope. Positive = accumulation, negative = distribution."""
    return clamp(5 + slope_norm * 50)   # wider multiplier for normalised values

def score_momentum_20d(ret_20):
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

def score_short_interest(short_pct):
    """
    Score short interest % of float.
    Low short = bullish (low headwind). High short = bearish (crowded short or squeeze risk).
    We score it as a risk metric: lower short = better score.
    """
    if short_pct is None:
        return 5.0   # neutral if unavailable
    if   short_pct < 2:  return 10.0
    elif short_pct < 5:  return clamp(8 - (short_pct - 2) * 0.5)
    elif short_pct < 10: return clamp(6 - (short_pct - 5) * 0.4)
    elif short_pct < 20: return clamp(4 - (short_pct - 10) * 0.2)
    else:                return clamp(2 - (short_pct - 20) * 0.1)

def score_fwd_pe_vs_sector(fwd_pe, sector):
    """
    Score forward P/E relative to sector median.
    At or below median = good. Stretched premium = penalty.
    """
    if fwd_pe is None:
        return 5.0   # neutral if unavailable
    median = SECTOR_PE_MEDIAN.get(sector, SECTOR_PE_MEDIAN["Unknown"])
    ratio  = fwd_pe / median   # 1.0 = exactly at median
    if   ratio < 0.7:  return 10.0              # deeply undervalued vs sector
    elif ratio < 1.0:  return clamp(7 + (1.0 - ratio) * 10)
    elif ratio < 1.2:  return clamp(7 - (ratio - 1.0) * 15)
    elif ratio < 1.5:  return clamp(4 - (ratio - 1.2) * 6.7)
    else:              return clamp(2 - (ratio - 1.5) * 4)

def score_analyst_revision(rec_mean):
    """
    Score analyst consensus mean (1=Strong Buy, 5=Strong Sell).
    Lower rec_mean = more bullish consensus.
    """
    if rec_mean is None:
        return 5.0
    if   rec_mean <= 1.5: return 10.0
    elif rec_mean <= 2.0: return clamp(8  + (2.0 - rec_mean) * 4)
    elif rec_mean <= 2.5: return clamp(6  + (2.5 - rec_mean) * 4)
    elif rec_mean <= 3.0: return clamp(4  + (3.0 - rec_mean) * 4)
    elif rec_mean <= 3.5: return clamp(2  + (3.5 - rec_mean) * 4)
    else:                 return clamp(2  - (rec_mean - 3.5) * 2)

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
    windows = [excess_returns.iloc[i:i + 20].sum() for i in range(0, len(excess_returns) - 20, 5)]
    if not windows: return 5.0
    frac = sum(1 for w in windows if w > 0) / len(windows) * 100
    return score_win_rate(frac)

# ── WARNINGS ───────────────────────────────────────────────────────────────

def compute_warnings(rsi_val, ma50, ma200, dd_pct, vol_pct, b, adx_val,
                     sharpe_val, short_pct, fwd_pe, sector):
    flags = []
    if ma50 < ma200:
        flags.append("Death cross active (MA50 < MA200)")
    if rsi_val > 75:
        flags.append(f"RSI overbought ({rsi_val:.0f}) — momentum may be extended, not a hard filter")
    elif rsi_val < 25:
        flags.append(f"RSI oversold ({rsi_val:.0f}) — heavy selling pressure")
    if dd_pct < -40:
        flags.append(f"Deep historical drawdown ({dd_pct:.0f}%) — note: not scored, for context only")
    if vol_pct > 60:
        flags.append(f"Extreme volatility ({vol_pct:.0f}% ann.)")
    if sharpe_val < 0:
        flags.append(f"Negative Sharpe ({sharpe_val:.2f}) — poor risk-adjusted return")
    if b > 2.0:
        flags.append(f"Beta {b:.1f} — moves 2x the market")
    if adx_val < 15:
        flags.append(f"ADX {adx_val:.0f} — no clear trend, directionless")
    if short_pct and short_pct > 15:
        flags.append(f"High short interest ({short_pct:.1f}% of float) — elevated bearish positioning")
    if fwd_pe:
        median = SECTOR_PE_MEDIAN.get(sector, 20.0)
        if fwd_pe > median * 1.5:
            flags.append(f"Forward P/E {fwd_pe:.1f}x — {((fwd_pe/median-1)*100):.0f}% premium to sector median")
    return flags[:4]   # allow one extra flag now that we have more signals

# ── ENTRY FLAG ─────────────────────────────────────────────────────────────

def entry_flag(rsi_val, price, ma50, bb_upper, bb_lower, mom_20):
    extended = (price > bb_upper) or (rsi_val > 68) or (mom_20 > 0.12)
    oversold = (price < bb_lower) or (rsi_val < 32)
    if oversold:    return "Oversold Bounce"
    elif extended:  return "Wait for Pullback"
    else:           return "Good Entry"

# ── RISK DOWNGRADE ─────────────────────────────────────────────────────────

def apply_risk_downgrade(verdict, vol_pct):
    order = ["Strong Sell", "Sell", "Neutral", "Buy", "Strong Buy"]
    if vol_pct > 60:
        idx = order.index(verdict)
        return order[max(0, idx - 1)]
    return verdict

# ── MAIN ANALYSIS ──────────────────────────────────────────────────────────

def analyze(ticker: str, spy_df=None) -> dict:
    ticker = ticker.upper().strip()
    df     = fetch(ticker)
    closes = df["Close"]
    ret    = closes.pct_change().dropna()

    if spy_df is None:
        spy_df = fetch("SPY")
    spy_ret = spy_df["Close"].pct_change().dropna()

    # ── Raw technical values ───────────────────────────────────────────────
    rsi_val              = rsi(closes)
    hist_val, m_val, _   = macd_hist(closes)
    roc_val              = (closes.iloc[-1] / closes.iloc[-ROC_DAYS] - 1) * 100 if len(closes) >= ROC_DAYS else 0.0
    obv_norm, obv_dir    = obv_slope(df)
    mom_20               = (closes.iloc[-1] / closes.iloc[-MOMENTUM_DAYS] - 1) if len(closes) >= MOMENTUM_DAYS else 0.0
    ma50_val             = closes.rolling(MA_SHORT).mean().iloc[-1]
    ma200_val            = closes.rolling(MA_LONG).mean().iloc[-1]
    adx_val              = adx(df)
    low52                = closes.iloc[-252:].min() if len(closes) >= 252 else closes.min()
    high52               = closes.iloc[-252:].max() if len(closes) >= 252 else closes.max()
    price                = closes.iloc[-1]
    sh                   = sharpe(ret)
    so                   = sortino(ret)
    dd                   = max_drawdown(closes)
    vol                  = annualised_vol(ret)
    b                    = beta(ret, spy_ret)
    data_as_of           = str(df.index[-1].date()) if hasattr(df.index[-1], 'date') else str(df.index[-1])[:10]

    # Bollinger Bands
    bb_mid   = closes.rolling(20).mean()
    bb_std   = closes.rolling(20).std()
    bb_upper = (bb_mid + 2 * bb_std).iloc[-1]
    bb_lower = (bb_mid - 2 * bb_std).iloc[-1]

    # ── Alpha calculations ────────────────────────────────────────────────
    def alpha_n(days):
        common = ret.index.intersection(spy_ret.index)
        s_r    = ret.loc[common].iloc[-days:]
        m_r    = spy_ret.loc[common].iloc[-days:]
        return ((1 + s_r).prod() - (1 + m_r).prod()) * 100

    alpha_3m = alpha_n(63)
    alpha_6m = alpha_n(126)
    alpha_1y = alpha_n(252)
    common   = ret.index.intersection(spy_ret.index)
    excess   = ret.loc[common] - spy_ret.loc[common]
    wr       = (excess > 0).mean() * 100

    # ── Metadata + fundamental overlays ───────────────────────────────────
    meta      = get_metadata(ticker)
    sector    = meta["sector"]
    fwd_pe    = meta["fwd_pe"]
    short_pct = meta["short_pct"]
    rec_mean  = meta["rec_mean"]
    rec_key   = meta["rec_key"]

    # ── Sector ETF alpha ───────────────────────────────────────────────────
    sector_etf_ticker = SECTOR_ETF.get(sector)
    alpha_vs_sector   = None
    try:
        if sector_etf_ticker:
            etf_df  = fetch(sector_etf_ticker)
            etf_ret = etf_df["Close"].pct_change().dropna()
            common_s = ret.index.intersection(etf_ret.index)
            s_r      = ret.loc[common_s].iloc[-63:]    # 3-month vs sector
            e_r      = etf_ret.loc[common_s].iloc[-63:]
            alpha_vs_sector = round(((1 + s_r).prod() - (1 + e_r).prod()) * 100, 1)
    except:
        alpha_vs_sector = None

    # ── Per-metric scores ──────────────────────────────────────────────────
    scores = {
        # Momentum
        "RSI":                score_rsi(rsi_val),
        "MACD":               score_macd(hist_val, m_val),
        "Rate of Change":     score_roc(roc_val),
        "OBV Trend":          score_obv(obv_norm),
        "20d Momentum":       score_momentum_20d(mom_20),
        # Trend
        "vs MA50":            score_vs_ma(price, ma50_val),
        "vs MA200":           score_vs_ma(price, ma200_val),
        "MA Cross":           score_ma_cross(ma50_val, ma200_val),
        "ADX Strength":       score_adx(adx_val),
        "52w Range":          score_52w(price, low52, high52),
        # Risk
        "Sharpe (1yr)":       score_sharpe(sh),
        "Sortino (1yr)":      score_sortino(so),
        "Volatility":         score_volatility(vol),
        "Beta vs SPY":        score_beta(b),
        "Short Interest":     score_short_interest(short_pct),
        # Relative Strength
        "Alpha 3m":           score_alpha(alpha_3m),
        "Alpha 6m":           score_alpha(alpha_6m),
        "Alpha 1yr":          score_alpha(alpha_1y),
        "Excess Consistency": score_excess_consistency(excess),
        "Win Rate vs SPY":    score_win_rate(wr),
        # Fundamental (lightweight sanity check)
        "Fwd P/E vs Sector":  score_fwd_pe_vs_sector(fwd_pe, sector),
        "Analyst Consensus":  score_analyst_revision(rec_mean),
        "Sector Alpha 3m":    score_alpha(alpha_vs_sector) if alpha_vs_sector is not None else 5.0,
    }
    scores = {k: round(v, 1) for k, v in scores.items()}

    # ── Category scores ────────────────────────────────────────────────────
    def cat(keys):
        return round(np.mean([scores[k] for k in keys]) * 10, 1)

    momentum_score    = cat(["RSI", "MACD", "Rate of Change", "OBV Trend", "20d Momentum"])
    trend_score       = cat(["vs MA50", "vs MA200", "MA Cross", "ADX Strength", "52w Range"])
    risk_score        = cat(["Sharpe (1yr)", "Sortino (1yr)", "Volatility", "Beta vs SPY", "Short Interest"])
    rs_score          = cat(["Alpha 3m", "Alpha 6m", "Alpha 1yr", "Excess Consistency", "Win Rate vs SPY"])
    fundamental_score = cat(["Fwd P/E vs Sector", "Analyst Consensus", "Sector Alpha 3m"])

    conviction = round(
        momentum_score    * CATEGORY_WEIGHTS["momentum"] +
        trend_score       * CATEGORY_WEIGHTS["trend"] +
        risk_score        * CATEGORY_WEIGHTS["risk"] +
        rs_score          * CATEGORY_WEIGHTS["relative_strength"] +
        fundamental_score * CATEGORY_WEIGHTS["fundamental"],
        1
    )

    verdict = next(v for threshold, v in VERDICT_THRESHOLDS if conviction >= threshold)
    verdict = apply_risk_downgrade(verdict, vol)

    entry   = entry_flag(rsi_val, price, ma50_val, bb_upper, bb_lower, mom_20)
    sizing  = position_size(conviction, entry)
    warnings = compute_warnings(
        rsi_val, ma50_val, ma200_val, dd, vol, b, adx_val,
        sh, short_pct, fwd_pe, sector
    )

    return {
        "ticker":          ticker,
        "price":           round(float(price), 2),
        "data_as_of":      data_as_of,
        "sector":          sector,
        "earnings_date":   meta["earnings_date"],
        "conviction":      conviction,
        "verdict":         verdict,
        "entry_flag":      entry,
        "position_size":   sizing,
        "warnings":        warnings,
        "momentum_score":  momentum_score,
        "trend_score":     trend_score,
        "risk_score":      risk_score,
        "rs_score":        rs_score,
        "fundamental_score": fundamental_score,
        "metrics": {
            "Momentum":          {k: scores[k] for k in ["RSI", "MACD", "Rate of Change", "OBV Trend", "20d Momentum"]},
            "Trend":             {k: scores[k] for k in ["vs MA50", "vs MA200", "MA Cross", "ADX Strength", "52w Range"]},
            "Risk":              {k: scores[k] for k in ["Sharpe (1yr)", "Sortino (1yr)", "Volatility", "Beta vs SPY", "Short Interest"]},
            "Relative Strength": {k: scores[k] for k in ["Alpha 3m", "Alpha 6m", "Alpha 1yr", "Excess Consistency", "Win Rate vs SPY"]},
            "Fundamental":       {k: scores[k] for k in ["Fwd P/E vs Sector", "Analyst Consensus", "Sector Alpha 3m"]},
        },
        "raw": {
            "rsi":              round(rsi_val, 1),
            "macd_hist":        round(float(hist_val), 4),
            "roc_pct":          round(roc_val, 1),
            "obv_norm":         round(float(obv_norm), 4),
            "obv_dir":          obv_dir,
            "mom_20d_pct":      round(mom_20 * 100, 1),
            "ma50":             round(float(ma50_val), 2),
            "ma200":            round(float(ma200_val), 2),
            "adx":              round(adx_val, 1),
            "52w_low":          round(float(low52), 2),
            "52w_high":         round(float(high52), 2),
            "sharpe":           round(sh, 2),
            "sortino":          round(so, 2),
            "max_dd_pct":       round(dd, 1),
            "vol_pct":          round(vol, 1),
            "beta":             round(b, 2),
            "short_pct":        short_pct,
            "alpha_3m":         round(alpha_3m, 1),
            "alpha_6m":         round(alpha_6m, 1),
            "alpha_1y":         round(alpha_1y, 1),
            "alpha_vs_sector":  alpha_vs_sector,
            "sector_etf":       sector_etf_ticker,
            "win_rate":         round(wr, 1),
            "fwd_pe":           fwd_pe,
            "sector_pe_median": SECTOR_PE_MEDIAN.get(sector, 20.0),
            "rec_mean":         rec_mean,
            "rec_key":          rec_key,
            "num_analysts":     meta["num_analysts"],
        },
        "analysed_at": datetime.now().isoformat(),
    }
