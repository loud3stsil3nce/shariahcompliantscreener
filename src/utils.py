import sqlite3
import pandas as pd

DB_PATH = "data/halal_screener.db"
TICKERS_CSV = "data/tickers.csv"


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def normalize_ticker(ticker: str) -> str:
    return ticker.strip().replace(".", "-").upper()


def load_universe(filepath: str = TICKERS_CSV):
    try:
        df = pd.read_csv(filepath)
        return [normalize_ticker(t) for t in df["Symbol"].dropna().astype(str).unique().tolist()]
    except Exception as e:
        print(f"Error loading CSV: {e}")
        return []