import sqlite3
from pathlib import Path

import pytest

from src.analysis.screener import run_screener


def create_stock_db(path: Path):
    conn = sqlite3.connect(path)
    conn.execute(
        """
        CREATE TABLE stocks (
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
            fetched_at TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE manual_overrides (
            ticker TEXT PRIMARY KEY,
            haram_revenue_override REAL,
            debt_ratio_override REAL,
            cash_ratio_override REAL,
            receivables_ratio_override REAL,
            tangibility_ratio_override REAL,
            interest_income_override REAL,
            doubtful_revenue_override REAL,
            reasoning TEXT,
            is_user_override INTEGER DEFAULT 0,
            updated_at TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE curated_benchmarks (
            ticker TEXT PRIMARY KEY,
            haram_revenue_override REAL,
            doubtful_revenue_override REAL,
            interest_income_override REAL,
            cash_ratio_override REAL,
            debt_ratio_override REAL,
            tangibility_ratio_override REAL,
            updated_at TEXT
        )
        """
    )
    conn.executemany(
        """
        INSERT INTO stocks (
            ticker, name, sector, industry,
            total_assets, total_debt, cash_equivalents,
            accounts_receivable, total_revenue, interest_income,
            shares_outstanding, avg_market_cap_36mo, raw_info, fetched_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                "HALAL", "Halal Inc", "Technology", "Software",
                1000, 100, 100, 50, 500, 10,
                100, 10000, "{}", "2026-06-13T00:00:00"
            ),
            (
                "HARAM", "Haram Corp", "Consumer Discretionary", "Casino",
                1000, 500, 100, 300, 500, 50,
                100, 10000, "{}", "2026-06-13T00:00:00"
            ),
        ],
    )
    conn.commit()
    conn.close()


def test_run_screener_creates_halal_universe(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    create_stock_db(db_path)

    def fake_get_db():
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        return conn

    monkeypatch.setattr("src.analysis.screener.get_db", fake_get_db)

    run_screener()

    conn = sqlite3.connect(db_path)
    halal_rows = conn.execute("SELECT ticker FROM halal_universe").fetchall()
    rejected_rows = conn.execute("SELECT ticker, halal_failure FROM halal_rejections").fetchall()
    conn.close()

    assert [row[0] for row in halal_rows] == ["HALAL"]
    assert any("casino" in (row[1] or "").lower() for row in rejected_rows)