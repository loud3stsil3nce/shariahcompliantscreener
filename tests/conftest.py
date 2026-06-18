"""Pytest configuration file containing E2E test fixtures, database isolation, and yfinance mocks."""

import sqlite3
from pathlib import Path
import pandas as pd
import pytest
import yfinance as yf

from src.ingestion import init_db

# Presets for mock yfinance Ticker data
TICKER_PRESETS = {
    "HALAL": {
        "info": {
            "longName": "Halal Inc",
            "shortName": "HALAL",
            "sector": "Technology",
            "industry": "Software",
            "sharesOutstanding": 100.0,
            "totalCash": 100.0,
            "totalAssets": 1000.0,
            "totalDebt": 100.0,
            "totalRevenue": 500.0,
            "marketCap": 10000.0,
            "financialCurrency": "USD",
            "currency": "USD"
        },
        "balance_sheet": {
            "Cash Cash Equivalents And Short Term Investments": [100.0],
            "Cash And Cash Equivalents": [100.0],
            "Other Short Term Investments": [0.0],
            "Available For Sale Securities": [0.0],
            "Investmentin Financial Assets": [0.0],
            "Total Assets": [1000.0],
            "Total Debt": [100.0],
            "Accounts Receivable": [50.0]
        },
        "financials": {
            "Interest Income": [10.0],
            "Interest Income Non Operating": [0.0],
            "Total Revenue": [500.0]
        }
    },
    "HARAM": {
        "info": {
            "longName": "Haram Corp",
            "shortName": "HARAM",
            "sector": "Consumer Discretionary",
            "industry": "Casino",
            "sharesOutstanding": 100.0,
            "totalCash": 100.0,
            "totalAssets": 1000.0,
            "totalDebt": 500.0,
            "totalRevenue": 500.0,
            "marketCap": 10000.0,
            "financialCurrency": "USD",
            "currency": "USD"
        },
        "balance_sheet": {
            "Cash Cash Equivalents And Short Term Investments": [100.0],
            "Total Assets": [1000.0],
            "Total Debt": [500.0],
            "Accounts Receivable": [300.0]
        },
        "financials": {
            "Interest Income": [50.0],
            "Total Revenue": [500.0]
        }
    }
}

class MockTicker:
    def __init__(self, ticker):
        self.ticker = ticker
        self.info = TICKER_PRESETS.get(ticker, TICKER_PRESETS["HALAL"])["info"]
        self.balance_sheet = pd.DataFrame(TICKER_PRESETS.get(ticker, TICKER_PRESETS["HALAL"])["balance_sheet"])
        self.financials = pd.DataFrame(TICKER_PRESETS.get(ticker, TICKER_PRESETS["HALAL"])["financials"])
        self.fast_info = self.info # Simplified

    def history(self, *args, **kwargs):
        return pd.DataFrame({"Close": [100.0, 105.0, 110.0]})

def mock_download(*args, **kwargs):
    # Return mock price data for optimizer
    tickers = args[0] if args else kwargs.get("tickers", ["AAPL"])
    if isinstance(tickers, str):
        tickers = [tickers]
    
    dates = pd.date_range(start="2024-01-01", periods=10, freq="D")
    data = pd.DataFrame(index=dates)
    for t in tickers:
        data[t] = [100.0 + i for i in range(10)]
    return data

@pytest.fixture
def db_path(tmp_path) -> Path:
    """Returns the Path to a temporary SQLite database file using pytest's tmp_path."""
    return tmp_path / "test_halal_screener.db"


@pytest.fixture
def setup_db(db_path, monkeypatch):
    """Initializes the database with schema and seed data, and monkeypatches get_db across modules."""
    
    # Define connection generator returning isolated connection
    def fake_get_db():
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        return conn

    # Import modules to patch
    import src.utils
    import src.screener
    import src.optimizer
    import src.ai_analyst
    import src.ingestion
    import src.backtester
    import src.db_setup
    
    # Apply monkeypatching BEFORE initializing schema
    monkeypatch.setattr(src.utils, "get_db", fake_get_db)
    monkeypatch.setattr(src.screener, "get_db", fake_get_db)
    monkeypatch.setattr(src.optimizer, "get_db", fake_get_db)
    monkeypatch.setattr(src.ingestion, "get_db", fake_get_db)
    monkeypatch.setattr(src.ai_analyst, "get_db", fake_get_db, raising=False)
    monkeypatch.setattr(src.backtester, "get_db", fake_get_db, raising=False)
    monkeypatch.setattr(src.db_setup, "get_db", fake_get_db)
    
    # We may also need to patch UI modules if they are imported by tests
    try:
        import ui.database_tab
        monkeypatch.setattr(ui.database_tab, "get_db", fake_get_db)
        import ui.explorer_tab
        monkeypatch.setattr(ui.explorer_tab, "get_db", fake_get_db)
        import ui.rules_tab
        monkeypatch.setattr(ui.rules_tab, "get_db", fake_get_db)
    except ImportError:
        pass

    conn = sqlite3.connect(db_path)

    # Initialize basic schema via src.ingestion.init_db
    init_db(conn)

    # Ensure all required tables are created
    tables_sql = {
        "curated_benchmarks": """
            CREATE TABLE IF NOT EXISTS curated_benchmarks (
                ticker TEXT PRIMARY KEY,
                haram_revenue_override REAL,
                doubtful_revenue_override REAL,
                interest_income_override REAL,
                cash_ratio_override REAL,
                debt_ratio_override REAL,
                tangibility_ratio_override REAL,
                updated_at TEXT
            );
        """,
        "shariah_segment_map": """
            CREATE TABLE IF NOT EXISTS shariah_segment_map (
                ticker TEXT,
                segment_name TEXT,
                compliance_status TEXT CHECK(compliance_status IN ('halal', 'haram', 'doubtful')),
                notes TEXT,
                PRIMARY KEY (ticker, segment_name)
            );
        """,
        "global_segment_patterns": """
            CREATE TABLE IF NOT EXISTS global_segment_patterns (
                pattern TEXT PRIMARY KEY,
                compliance_status TEXT CHECK(compliance_status IN ('halal', 'haram', 'doubtful')),
                notes TEXT
            );
        """,
        "proposed_segment_rules": """
            CREATE TABLE IF NOT EXISTS proposed_segment_rules (
                ticker TEXT,
                segment_name TEXT,
                compliance_status TEXT CHECK(compliance_status IN ('halal', 'haram', 'doubtful')),
                suggested_notes TEXT,
                status TEXT DEFAULT 'pending' CHECK(status IN ('pending', 'approved', 'rejected')),
                created_at TEXT,
                PRIMARY KEY (ticker, segment_name)
            );
        """
    }

    for table_name, create_sql in tables_sql.items():
        conn.execute(create_sql)
        
    # Insert seed data if tables are empty
    # Seed data for stocks
    stocks_count = conn.execute("SELECT COUNT(*) FROM stocks").fetchone()[0]
    if stocks_count == 0:
        conn.executemany(
            """
            INSERT OR REPLACE INTO stocks (
                ticker, name, sector, industry,
                total_assets, total_debt, cash_equivalents, accounts_receivable,
                total_revenue, interest_income, shares_outstanding, avg_market_cap_36mo,
                raw_info, fetched_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    "HALAL", "Halal Inc", "Technology", "Software",
                    1000.0, 100.0, 100.0, 50.0, 500.0, 10.0, 100.0, 10000.0,
                    "{}", "2026-06-13T00:00:00"
                ),
                (
                    "HARAM", "Haram Corp", "Consumer Discretionary", "Casino",
                    1000.0, 500.0, 100.0, 300.0, 500.0, 50.0, 100.0, 10000.0,
                    "{}", "2026-06-13T00:00:00"
                ),
                (
                    "AAPL", "Apple Inc", "Technology", "Consumer Electronics",
                    350000.0, 100000.0, 30000.0, 20000.0, 380000.0, 30000.0, 15000.0, 3000000.0,
                    "{}", "2026-06-13T00:00:00"
                ),
                (
                    "MSFT", "Microsoft Corp", "Technology", "Software",
                    410000.0, 80000.0, 80000.0, 25000.0, 210000.0, 20000.0, 7400.0, 3200000.0,
                    "{}", "2026-06-13T00:00:00"
                )
            ]
        )
        
    # Seed data for manual_overrides
    mo_count = conn.execute("SELECT COUNT(*) FROM manual_overrides").fetchone()[0]
    if mo_count == 0:
        conn.executemany(
            """
            INSERT OR REPLACE INTO manual_overrides (
                ticker, haram_revenue_override, debt_ratio_override, cash_ratio_override,
                receivables_ratio_override, interest_income_override, doubtful_revenue_override,
                reasoning, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                ("AAPL", None, 0.0262, 0.0447, None, 0.0096, 0.0312, "Curated Apple metrics", "2026-06-13T00:00:00"),
                ("MSFT", 0.076, 0.0197, 0.0315, None, 0.0094, None, "Curated MSFT metrics", "2026-06-13T00:00:00")
            ]
        )
        
    # Seed data for curated_benchmarks
    cb_count = conn.execute("SELECT COUNT(*) FROM curated_benchmarks").fetchone()[0]
    if cb_count == 0:
        conn.executemany(
            """
            INSERT OR REPLACE INTO curated_benchmarks (
                ticker, doubtful_revenue_override, interest_income_override, cash_ratio_override,
                debt_ratio_override, haram_revenue_override, reasoning
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                ("AAPL", 0.0312, 0.0096, 0.0447, 0.0262, None, "Curated Apple metrics"),
                ("MSFT", None, 0.0094, 0.0315, 0.0197, 0.076, "Curated MSFT metrics"),
                ("GOOG", 0.7200, 0.0108, None, None, None, "Curated Google metrics"),
                ("GOOGL", 0.7200, 0.0108, None, None, None, "Curated Google metrics"),
                ("META", 0.9800, 0.0120, None, None, None, "Curated Meta metrics")
            ]
        )
        
    conn.commit()
    conn.close()

    return db_path


@pytest.fixture(autouse=True)
def mock_yfinance(monkeypatch):
    """Automatically mock yfinance to prevent live internet calls during tests."""
    monkeypatch.setattr("yfinance.Ticker", MockTicker)
    monkeypatch.setattr("yfinance.download", mock_download)
