"""Data ingestion module for Shariah compliant screener."""
import json
import logging
import time
from datetime import datetime

import pandas as pd
import yfinance as yf

from src.db.helpers import get_db
from src.data.ingestion import load_universe

import os
os.makedirs("logs", exist_ok=True)
logging.basicConfig(
    filename="logs/pipeline.log",
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)

TICKERS_CSV = "data/tickers.csv"


def normalize_ticker(ticker: str) -> str:
    return ticker.strip().replace(".", "-").upper()


def load_universe(filepath: str = TICKERS_CSV):
    try:
        df = pd.read_csv(filepath)
        return [normalize_ticker(t) for t in df["Symbol"].dropna().astype(str).unique().tolist()]
    except Exception as e:
        print(f"Error loading CSV: {e}")
        return []




# SCHEMA
CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS stocks (
    ticker TEXT PRIMARY KEY,
    name TEXT,
    sector TEXT,
    industry TEXT,
    total_assets REAL,
    total_debt REAL,
    cash_equivalents REAL,
    accounts_receivable REAL,
    total_revenue REAL,
    interest_income REAL,
    shares_outstanding REAL,
    avg_market_cap_36mo REAL,
    raw_info TEXT,
    sec_filing_url TEXT,
    fetched_at TEXT
);

CREATE TABLE IF NOT EXISTS manual_overrides (
    ticker TEXT PRIMARY KEY,
    haram_revenue_override REAL,
    debt_ratio_override REAL,
    cash_ratio_override REAL,
    receivables_ratio_override REAL,
    interest_income_override REAL,
    reasoning TEXT,
    updated_at TEXT
);
"""

def init_db(conn):
    conn.executescript(CREATE_TABLE)
    # Schema migration: check if sec_filing_url column exists in stocks
    cursor = conn.execute("PRAGMA table_info(stocks)")
    columns = [row[1] for row in cursor.fetchall()]
    if "sec_filing_url" not in columns:
        conn.execute("ALTER TABLE stocks ADD COLUMN sec_filing_url TEXT")
    conn.commit()


def get_36mo_avg_market_cap(t: yf.Ticker, shares_outstanding: float) -> float:
    if not shares_outstanding:
        return 0.0
    try:
        hist = t.history(period="3y", interval="1mo")
        return float(hist["Close"].mean() * shares_outstanding) if not hist.empty else 0.0
    except Exception:
        return 0.0


def get_exchange_rate(from_curr: str, to_curr: str) -> float:
    if not from_curr or not to_curr or from_curr.upper() == to_curr.upper():
        return 1.0
    from_curr = from_curr.upper()
    to_curr = to_curr.upper()
    ticker_sym = f"{from_curr}{to_curr}=X"
    try:
        t = yf.Ticker(ticker_sym)
        rate = t.info.get("regularMarketPrice") or t.info.get("previousClose")
        if rate:
            return float(rate)
        hist = t.history(period="1d")
        if not hist.empty:
            return float(hist["Close"].iloc[-1])
    except Exception:
        pass
        
    ticker_inv = f"{to_curr}{from_curr}=X"
    try:
        t = yf.Ticker(ticker_inv)
        rate = t.info.get("regularMarketPrice") or t.info.get("previousClose")
        if rate:
            return 1.0 / float(rate)
        hist = t.history(period="1d")
        if not hist.empty:
            return 1.0 / float(hist["Close"].iloc[-1])
    except Exception:
        pass
        
    return 1.0


def fetch_stock(ticker: str) -> dict | None:
    t = yf.Ticker(ticker)
    info = t.info
    if not info.get("longName") and not info.get("shortName"):
        return None

    # Construct SEC Filings Search Link
    sec_link = f"https://www.sec.gov/cgi-bin/browse-edgar?CIK={ticker}&action=getcompany&type=10-K"

    bs = t.balance_sheet
    financials = t.financials

    def get_recent_val(df, row_name, fallback):
        try:
            return float(df.loc[row_name].iloc[0]) if not df.empty and row_name in df.index else float(fallback)
        except Exception:
            return float(fallback)

    shares = float(info.get("sharesOutstanding", 0) or 0)
    
    # Currency Conversion Check
    fin_curr = info.get("financialCurrency")
    trading_curr = info.get("currency")
    rate = 1.0
    if fin_curr and trading_curr and fin_curr.upper() != trading_curr.upper():
        rate = get_exchange_rate(fin_curr, trading_curr)
        logging.info(f"Currency mismatch for {ticker}: financials in {fin_curr}, trading in {trading_curr}. Rate: {rate}")
        print(f"💱 Currency mismatch for {ticker}: converting {fin_curr} to {trading_curr} (Rate: {rate:.4f})")

    # 1. Total cash and marketable securities portfolio (securities screen numerator)
    total_cash_st = get_recent_val(bs, "Cash Cash Equivalents And Short Term Investments", 0.0)
    if total_cash_st == 0.0 or pd.isna(total_cash_st):
        cash_equiv = get_recent_val(bs, "Cash And Cash Equivalents", 0.0)
        if cash_equiv == 0.0 or pd.isna(cash_equiv):
            cash_equiv = float(info.get("totalCash", 0.0) or 0.0)
        st_inv = get_recent_val(bs, "Other Short Term Investments", 0.0)
        if pd.isna(st_inv):
            st_inv = 0.0
        total_cash_st = cash_equiv + st_inv
    lt_securities = get_recent_val(bs, "Available For Sale Securities", 0.0)
    if lt_securities == 0.0 or pd.isna(lt_securities):
        lt_securities = get_recent_val(bs, "Investmentin Financial Assets", 0.0)
    if pd.isna(lt_securities):
        lt_securities = 0.0
    cash_and_securities = total_cash_st + lt_securities

    # 2. Interest Income (actual from financials, or deduced using a 3.0% yield proxy if missing/nan/0)
    interest_inc = get_recent_val(financials, "Interest Income", 0.0)
    if interest_inc == 0.0 or pd.isna(interest_inc):
        interest_inc = get_recent_val(financials, "Interest Income Non Operating", 0.0)
    if interest_inc == 0.0 or pd.isna(interest_inc):
        interest_inc = cash_and_securities * 0.03

    # Clean dictionary with only raw data, no compliance logic here
    record = {
        "ticker": ticker.upper(),
        "name": info.get("longName") or info.get("shortName", ""),
        "sector": info.get("sector", ""),
        "industry": info.get("industry", ""),
        "total_assets": get_recent_val(bs, "Total Assets", info.get("totalAssets", 0)) * rate,
        "total_debt": get_recent_val(bs, "Total Debt", info.get("totalDebt", 0)) * rate,
        "cash_equivalents": cash_and_securities * rate,
        "accounts_receivable": get_recent_val(bs, "Accounts Receivable", info.get("netReceivables", 0)) * rate,
        "total_revenue": get_recent_val(financials, "Total Revenue", info.get("totalRevenue", 0)) * rate,
        "interest_income": interest_inc * rate,
        "shares_outstanding": shares,
        "avg_market_cap_36mo": get_36mo_avg_market_cap(t, shares),
        "raw_info": json.dumps({k: v for k, v in info.items() if isinstance(v, (str, int, float, bool))}),
        "sec_filing_url": sec_link,
        "fetched_at": datetime.utcnow().isoformat(),
    }

    return record


def fetch_stock_with_retry(ticker: str, retries: int = 3) -> dict | None:
    for i in range(retries):
        try:
            return fetch_stock(ticker)
        except Exception as e:
            wait = 5 * (i + 1)
            logging.warning(f"Attempt {i+1} failed for {ticker}: {e}. Retrying in {wait}s...")
            time.sleep(wait)
    return None


def process_universe(tickers: list[str], conn, batch_size: int = 50):
    """Process tickers sequentially - fast and stable."""
    total = len(tickers)
    processed = 0
    start_time = time.time()

    for i in range(0, total, batch_size):
        batch = tickers[i : i + batch_size]
        print(f"📦 Processing batch {i // batch_size + 1}: {batch[0]} ...")
        
        for ticker in batch:
            data = fetch_stock_with_retry(ticker)
            if data:
                conn.execute(
                    """INSERT OR REPLACE INTO stocks (
                        ticker, name, sector, industry,
                        total_assets, total_debt, cash_equivalents, accounts_receivable,
                        total_revenue, interest_income,
                        shares_outstanding, avg_market_cap_36mo, raw_info, sec_filing_url, fetched_at
                    ) VALUES (
                        :ticker, :name, :sector, :industry,
                        :total_assets, :total_debt, :cash_equivalents, :accounts_receivable,
                        :total_revenue, :interest_income,
                        :shares_outstanding, :avg_market_cap_36mo, :raw_info, :sec_filing_url, :fetched_at
                    )""",
                    data,
                )
        
        conn.commit()
        processed += len(batch)
        elapsed = time.time() - start_time
        print(f"✅ Progress: {processed}/{total} | Tickers saved. (Elapsed: {int(elapsed)}s)")
        
        if processed < total:
            # Minimal rest to reset session
            time.sleep(2)


def run_ingestion(refresh: bool = False, ticker_file: str | None = None):
    conn = get_db()
    init_db(conn)

    universe = load_universe(ticker_file) if ticker_file else load_universe()
    if not universe:
        print("No tickers loaded. Check your ticker CSV.")
        conn.close()
        return

    to_fetch = universe if refresh else [
        t for t in universe if not conn.execute("SELECT 1 FROM stocks WHERE ticker=?", (t,)).fetchone()
    ]

    if not to_fetch:
        print("Data up to date.")
    else:
        process_universe(to_fetch, conn)

    conn.close()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--ticker-file", default=None)
    args = parser.parse_args()
    run_ingestion(refresh=args.refresh, ticker_file=args.ticker_file)
