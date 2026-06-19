"""
sectors.py — WhaleWatch sector universe

The real GICS 11 sectors, each seeded with liquid, actively-traded US names.
Replaces the old 5 arbitrary batches (Tech / Financials+Healthcare mashed / Wildcards).

Index order is stable — the frontend batch dots/rotation map to these indices,
and cron schedules scan by index. Don't reorder without updating the frontend
BATCH_NAMES array to match.

Ticker lists are intentionally the *liquid* subset, not every listed name in the
sector. Add/trim freely — each is just a python list. Keep them to names with
real options volume and clean daily bars so the engine's signals are meaningful.
"""

SECTORS = [
    {
        "name": "Technology",
        "tickers": [
            "AAPL", "MSFT", "NVDA", "AVGO", "ORCL", "AMD", "ANET", "PLTR", "CRM",
            "INTC", "ADBE", "CSCO", "ACN", "TXN", "QCOM", "IBM", "NOW", "INTU",
            "AMAT", "MU", "LRCX", "KLAC", "ADI", "SNPS", "CDNS", "MRVL", "PANW",
            "CRWD", "FTNT", "DELL",
        ],
    },
    {
        "name": "Financials",
        "tickers": [
            "JPM", "BAC", "WFC", "GS", "MS", "C", "BLK", "SCHW", "AXP", "SPGI",
            "BX", "KKR", "CB", "PGR", "MMC", "USB", "PNC", "TFC", "COF", "AON",
            "ICE", "CME", "MCO", "V", "MA", "PYPL", "FIS", "BK", "AIG", "MET",
        ],
    },
    {
        "name": "Healthcare",
        "tickers": [
            "LLY", "UNH", "JNJ", "ABBV", "MRK", "TMO", "ABT", "DHR", "PFE", "AMGN",
            "ISRG", "BSX", "SYK", "VRTX", "GILD", "MDT", "REGN", "CI", "ELV", "CVS",
            "ZTS", "BDX", "HCA", "MCK", "EW", "DXCM", "IDXX", "BIIB", "HUM", "MRNA",
        ],
    },
    {
        "name": "Energy",
        "tickers": [
            "XOM", "CVX", "COP", "SLB", "EOG", "MPC", "PSX", "WMB", "OKE", "VLO",
            "HES", "OXY", "KMI", "HAL", "DVN", "BKR", "FANG", "TRGP", "CTRA", "MRO",
        ],
    },
    {
        "name": "Industrials",
        "tickers": [
            "CAT", "HON", "GE", "UPS", "RTX", "BA", "UNP", "DE", "LMT", "ETN",
            "ADP", "GD", "NOC", "EMR", "CSX", "ITW", "FDX", "WM", "PH", "TDG",
            "NSC", "GEV", "PCAR", "CARR", "CMI", "JCI", "ROK", "PWR", "URI", "LHX",
        ],
    },
    {
        "name": "Consumer Discretionary",
        "tickers": [
            "AMZN", "TSLA", "HD", "MCD", "NKE", "LOW", "SBUX", "BKNG", "TJX", "ORLY",
            "CMG", "MAR", "GM", "F", "HLT", "AZO", "ROST", "YUM", "LULU", "DHI",
            "LEN", "RCL", "EBAY", "TSCO", "ULTA", "DPZ", "EXPE", "GRMN", "APTV", "BBY",
        ],
    },
    {
        "name": "Consumer Staples",
        "tickers": [
            "PG", "COST", "WMT", "KO", "PEP", "PM", "MO", "MDLZ", "CL", "TGT",
            "KMB", "GIS", "SYY", "KHC", "STZ", "KDP", "MNST", "HSY", "KR", "CHD",
        ],
    },
    {
        "name": "Communication Services",
        "tickers": [
            "GOOGL", "META", "NFLX", "DIS", "T", "VZ", "TMUS", "CMCSA", "CHTR",
            "EA", "TTWO", "WBD", "OMC", "LYV", "PARA", "FOXA", "MTCH", "NWSA",
        ],
    },
    {
        "name": "Utilities",
        "tickers": [
            "NEE", "SO", "DUK", "CEG", "AEP", "SRE", "D", "EXC", "XEL", "PEG",
            "ED", "PCG", "EIX", "WEC", "AWK", "DTE", "ETR", "AEE", "PPL", "FE",
        ],
    },
    {
        "name": "Real Estate",
        "tickers": [
            "PLD", "AMT", "EQIX", "WELL", "SPG", "PSA", "O", "CCI", "DLR", "CBRE",
            "VICI", "EXR", "AVB", "VTR", "EQR", "IRM", "WY", "INVH", "ARE", "MAA",
        ],
    },
    {
        "name": "Materials",
        "tickers": [
            "LIN", "SHW", "FCX", "ECL", "APD", "NEM", "NUE", "DOW", "CTVA", "DD",
            "VMC", "MLM", "PPG", "ALB", "IFF", "STLD", "CF", "BALL", "AMCR", "MOS",
        ],
    },
]

# Convenience: name -> index and index -> name
SECTOR_NAMES = [s["name"] for s in SECTORS]
TOTAL_SECTORS = len(SECTORS)
