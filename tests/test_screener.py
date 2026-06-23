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


def test_pre_ipo_fallback_denominator(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    create_stock_db(db_path)

    # Insert a pre-IPO company (market cap = 0) with liabilities in raw_info
    # Total Assets = 1000, Total Debt = 150, Cash = 100
    # Liabilities = 400 => Book Value = 1000 - 400 = 600
    # Debt ratio = 150 / 600 = 25% (<33%, passes)
    # Cash ratio = 100 / 600 = 16.6% (<33%, passes)
    # Tangibility ratio = (1000 - (100 + 0)) / 1000 = 90% (>=30%, passes)
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        INSERT INTO stocks (
            ticker, name, sector, industry,
            total_assets, total_debt, cash_equivalents,
            accounts_receivable, total_revenue, interest_income,
            shares_outstanding, avg_market_cap_36mo, raw_info, fetched_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "LIME", "Lime Pre IPO", "Technology", "Software",
            1000.0, 150.0, 100.0, 0.0, 500.0, 0.0,
            100.0, 0.0, '{"total_liabilities": 400.0}', "2026-06-13T00:00:00"
        )
    )
    conn.commit()
    conn.close()

    def fake_get_db():
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        return conn

    monkeypatch.setattr("src.analysis.screener.get_db", fake_get_db)

    run_screener()

    conn = sqlite3.connect(db_path)
    halal_rows = conn.execute("SELECT ticker FROM halal_universe").fetchall()
    conn.close()

    # Verify LIME passed the screening because the denominator fell back to book value
    assert "LIME" in [row[0] for row in halal_rows]


def test_multi_source_custom_sec_url(tmp_path, monkeypatch):
    import asyncio
    from unittest.mock import MagicMock, AsyncMock
    from src.data.sec_extractor import SECParser
    import src.data.harvester as harvester
    from src.api import run_ai_audit, AuditInput
    
    # 1. Setup temporary database with a custom stock having sec_filing_url
    db_path = tmp_path / "test_audit.db"
    create_stock_db(db_path)
    
    conn = sqlite3.connect(db_path)
    conn.execute("ALTER TABLE stocks ADD COLUMN sec_filing_url TEXT")
    conn.execute(
        """
        INSERT INTO stocks (
            ticker, name, sector, industry,
            total_assets, total_debt, cash_equivalents,
            accounts_receivable, total_revenue, interest_income,
            shares_outstanding, avg_market_cap_36mo, raw_info, sec_filing_url, fetched_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "LIME", "Neutron Holdings", "Technology", "Software",
            1000.0, 150.0, 100.0, 0.0, 500.0, 0.0,
            100.0, 0.0, '{"total_liabilities": 400.0}', "https://www.sec.gov/S-1/lime-prospectus.htm", "2026-06-13T00:00:00"
        )
    )
    conn.commit()
    conn.close()
    
    class FakeDbConn:
        def __init__(self, db_path):
            self.conn = sqlite3.connect(db_path)
            self.conn.row_factory = sqlite3.Row
        def execute(self, query, params=None):
            if params:
                return self.conn.execute(query, params)
            return self.conn.execute(query)
        def commit(self):
            self.conn.commit()
        def close(self):
            self.conn.close()
            
    def fake_get_db():
        return FakeDbConn(db_path)
        
    monkeypatch.setattr("src.api.get_db", fake_get_db)
    monkeypatch.setattr("src.db.helpers.get_db", fake_get_db)
    
    # Mock SECParser get_text_from_url
    mock_get_text = MagicMock(return_value="Cleaned prospectus text with balance sheets")
    monkeypatch.setattr(SECParser, "get_text_from_url", mock_get_text)
    
    # Mock harvester web search and other calls
    mock_web_search = AsyncMock(return_value="Web search evidence text")
    monkeypatch.setattr(harvester, "search_web_evidence", mock_web_search)
    
    mock_transcript = AsyncMock(return_value="Earnings transcript text")
    monkeypatch.setattr(harvester, "fetch_transcript", mock_transcript)
    
    mock_pdf = AsyncMock(return_value="https://test.com/presentation.pdf")
    monkeypatch.setattr(harvester, "search_ir_presentation_pdf", mock_pdf)
    
    mock_download_pdf = AsyncMock(return_value="Investor presentation text")
    monkeypatch.setattr(harvester, "download_pdf_text", mock_download_pdf)
    
    # Mock pandas read_sql_query for the api
    import pandas as pd
    orig_read_sql = pd.read_sql_query
    def fake_read_sql_query(query, conn):
        actual_conn = conn.conn if hasattr(conn, "conn") else conn
        return orig_read_sql(query, actual_conn)
        
    monkeypatch.setattr("pandas.read_sql_query", fake_read_sql_query)
    
    # Mock AI Analyst compliance check
    mock_analyze = MagicMock(return_value={
        "filing_period_months": 12,
        "total_revenue_millions": 500.0,
        "haram_revenue_millions": 0.0,
        "doubtful_revenue_millions": 0.0,
        "interest_income_millions": 0.0,
        "interest_bearing_debt_millions": 150.0,
        "total_cash_and_securities_millions": 100.0,
        "verdict": "Pass",
        "detailed_reasoning": "Permissible business activities"
    })
    monkeypatch.setattr("src.analysis.ai_analyst.analyze_multi_source_compliance", mock_analyze)
    
    # Test harvest_all_sources directly
    harvested = asyncio.run(harvester.harvest_all_sources("LIME", year=2025, quarter=4))
    
    # Verify company name was retrieved from database and used in queries instead of placeholder "LIME"
    called_queries = [call.args[0] for call in mock_web_search.call_args_list]
    assert any("Neutron Holdings segment revenue" in q for q in called_queries)
    
    # Test the API endpoint run_ai_audit itself
    audit_input = AuditInput(audit_type="multi_source")
    response = asyncio.run(run_ai_audit("LIME", audit_input))
    
    # Verify that SECParser.get_text_from_url was called with the database's sec_filing_url
    mock_get_text.assert_called_with("https://www.sec.gov/S-1/lime-prospectus.htm")
    assert response is not None


def test_fallback_on_rate_limit(monkeypatch):
    import os
    from src.ai.gemini_client import call_gemini
    
    # Force API Key to be configured for testing
    monkeypatch.setenv("GEMINI_API_KEY", "dummy_key")
    monkeypatch.setenv("FALLBACK_ON_RATE_LIMIT", "true")
    
    class DummyClient:
        class GenerativeModel:
            def __init__(self, *args, **kwargs):
                pass
            def generate_content(self, *args, **kwargs):
                raise Exception("Resource has been exhausted (e.g. check quotas/limit). 429 error.")
                
    result = call_gemini("dummy prompt", "dummy system instruction", client=DummyClient)
    
    # Verify it returned a rate limit error dictionary immediately instead of retrying/sleeping
    assert isinstance(result, dict)
    assert "error" in result
    assert "rate limit hit" in result["error"].lower()