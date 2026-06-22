import sys
import os
import sqlite3
import pandas as pd
import pytest

# Add src to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.db.helpers import get_db

def test_screener_coalesce():
    print("\n=== Running Screener Coalesce Join Test ===")
    
    # Create an in-memory SQLite DB for testing
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    
    # Create tables
    conn.execute("""
        CREATE TABLE stocks (
            ticker TEXT PRIMARY KEY,
            name TEXT,
            total_revenue REAL,
            total_debt REAL,
            cash_equivalents REAL,
            interest_income REAL
        )
    """)
    conn.execute("""
        CREATE TABLE manual_overrides (
            ticker TEXT PRIMARY KEY,
            haram_revenue_override REAL,
            debt_ratio_override REAL,
            cash_ratio_override REAL,
            receivables_ratio_override REAL,
            tangibility_ratio_override REAL,
            interest_income_override REAL,
            doubtful_revenue_override REAL
        )
    """)
    conn.execute("""
        CREATE TABLE curated_benchmarks (
            ticker TEXT PRIMARY KEY,
            haram_revenue_override REAL,
            debt_ratio_override REAL,
            cash_ratio_override REAL,
            receivables_ratio_override REAL,
            tangibility_ratio_override REAL,
            interest_income_override REAL,
            doubtful_revenue_override REAL
        )
    """)
    
    # Insert test data:
    # 1. Ticker 'MAN' has manual override (takes priority over curated)
    conn.execute("INSERT INTO stocks (ticker, name) VALUES ('MAN', 'Manual Co')")
    conn.execute("INSERT INTO manual_overrides (ticker, haram_revenue_override, debt_ratio_override) VALUES ('MAN', 0.05, 0.10)")
    conn.execute("INSERT INTO curated_benchmarks (ticker, haram_revenue_override, debt_ratio_override) VALUES ('MAN', 0.01, 0.02)")
    
    # 2. Ticker 'CUR' has only curated benchmarks
    conn.execute("INSERT INTO stocks (ticker, name) VALUES ('CUR', 'Curated Co')")
    conn.execute("INSERT INTO curated_benchmarks (ticker, haram_revenue_override, debt_ratio_override) VALUES ('CUR', 0.03, 0.04)")
    
    # 3. Ticker 'NON' has no overrides
    conn.execute("INSERT INTO stocks (ticker, name) VALUES ('NON', 'None Co')")
    
    conn.commit()
    
    # Query with coalesce
    query = """
        SELECT s.*, 
               coalesce(m.haram_revenue_override, cb.haram_revenue_override) as haram_revenue_override,
               coalesce(m.debt_ratio_override, cb.debt_ratio_override) as debt_ratio_override,
               coalesce(m.cash_ratio_override, cb.cash_ratio_override) as cash_ratio_override,
               coalesce(m.receivables_ratio_override, cb.receivables_ratio_override) as receivables_ratio_override,
               coalesce(m.tangibility_ratio_override, cb.tangibility_ratio_override) as tangibility_ratio_override,
               coalesce(m.interest_income_override, cb.interest_income_override) as interest_income_override,
               coalesce(m.doubtful_revenue_override, cb.doubtful_revenue_override) as doubtful_revenue_override
        FROM stocks s
        LEFT JOIN manual_overrides m ON s.ticker = m.ticker
        LEFT JOIN curated_benchmarks cb ON s.ticker = cb.ticker
    """
    df = pd.read_sql_query(query, conn)
    conn.close()
    
    # Verify results
    assert len(df) == 3
    
    # 'MAN' must use manual overrides (0.05, 0.10)
    man_row = df[df["ticker"] == "MAN"].iloc[0]
    assert man_row["haram_revenue_override"] == 0.05
    assert man_row["debt_ratio_override"] == 0.10
    
    # 'CUR' must use curated benchmarks (0.03, 0.04)
    cur_row = df[df["ticker"] == "CUR"].iloc[0]
    assert cur_row["haram_revenue_override"] == 0.03
    assert cur_row["debt_ratio_override"] == 0.04
    
    # 'NON' must have None/NaN
    non_row = df[df["ticker"] == "NON"].iloc[0]
    assert pd.isna(non_row["haram_revenue_override"])
    assert pd.isna(non_row["debt_ratio_override"])
    
    print("✅ Screener coalesce query works correctly with order of priorities!")

if __name__ == "__main__":
    test_screener_coalesce()
