"""
core.py — WhaleWatch Pure Quant Engine (Metadata Improved)
PATCHED + METADATA v2
"""

import numpy as np
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta

# ... [All the constants, SECTOR_ETF, SECTOR_PE_MEDIAN, position_size, clamp, etc. remain the same] ...

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
        t = yf.Ticker(ticker)
        info = t.info or {}
        full_info = info.copy()

        # Try fast_info as backup
        try:
            fast = t.fast_info
            full_info.update({k: v for k, v in fast.items() if k not in full_info})
        except:
            pass

        # ── Sector ──────────────────────────────────────────────────────
        sector = (
            full_info.get("sector") or
            full_info.get("sectorDisp") or
            full_info.get("sectorKey") or
            full_info.get("industry") or
            "Unknown"
        )

        # ── Earnings Date (multiple robust attempts) ─────────────────────
        earnings = "Unknown"
        try:
            # Method 1: calendar
            cal = t.calendar
            if isinstance(cal, dict) and cal:
                for key in ["Earnings Date", "earningsDate", "Earnings Dates", "Earnings"]:
                    if key in cal and cal[key]:
                        ed = cal[key]
                        first = ed[0] if isinstance(ed, (list, tuple)) else ed
                        earnings = str(first)[:10]
                        break
        except:
            pass

        if earnings == "Unknown":
            try:
                # Method 2: earnings_dates
                edates = t.get_earnings_dates(limit=5)
                if edates is not None and not edates.empty:
                    future = edates[edates.index > pd.Timestamp.now()]
                    if not future.empty:
                        earnings = str(future.index[0].date())
                    else:
                        earnings = str(edates.index[0].date())
            except:
                pass

        if earnings == "Unknown":
            try:
                # Method 3: info fallback
                ed = full_info.get("earningsDate") or full_info.get("nextEarningsDate")
                if ed:
                    if isinstance(ed, (list, tuple)):
                        first = ed[0]
                    else:
                        first = ed
                    earnings = str(first)[:10]
            except:
                pass

        # ── Forward P/E ─────────────────────────────────────────────────
        fwd_pe = None
        for key in ("forwardPE", "trailingPE", "priceToEarningsTrailing", "forwardEps"):
            raw = full_info.get(key)
            if raw and isinstance(raw, (int, float)) and 0 < raw < 2000:
                fwd_pe = round(float(raw), 1)
                break

        # ── Short Interest ──────────────────────────────────────────────
        short_pct = None
        for key in ("shortPercentOfFloat", "shortRatio"):
            raw = full_info.get(key)
            if raw and isinstance(raw, (int, float)):
                val = float(raw)
                if key == "shortPercentOfFloat" and 0 < val <= 1:
                    short_pct = round(val * 100, 1)
                elif key == "shortRatio":
                    # shortRatio is days-to-cover, not used for % here
                    pass
                break

        # ── Analyst Consensus ───────────────────────────────────────────
        rec_mean = None
        rec_key = full_info.get("recommendationKey")
        num_analysts = int(full_info.get("numberOfAnalystOpinions") or 0)
        raw_rec = full_info.get("recommendationMean")
        if raw_rec and isinstance(raw_rec, (int, float)):
            rec_mean = round(float(raw_rec), 2)

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

# [Rest of the file remains exactly the same as the previous patched version]