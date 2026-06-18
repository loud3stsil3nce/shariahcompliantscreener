import sqlite3
import pytest
import pandas as pd
import numpy as np
import json
from unittest.mock import MagicMock, patch

from src.screener import run_screener
from src.optimizer import run_optimizer, get_data
from src.ai_analyst import analyze_company_compliance, SYSTEM_PROMPT
from src.ingestion import run_ingestion
from tests.e2e.conftest import MockGenerativeModel

# Helper to populate stocks table
def insert_stock_data(conn, ticker, total_assets=1000.0, cash_equivalents=100.0, accounts_receivable=50.0, total_debt=100.0, total_revenue=500.0, interest_income=10.0, avg_market_cap_36mo=10000.0, shares_outstanding=100.0, sector="Technology", industry="Software"):
    conn.execute(
        """
        INSERT OR REPLACE INTO stocks (
            ticker, name, sector, industry,
            total_assets, total_debt, cash_equivalents, accounts_receivable,
            total_revenue, interest_income, shares_outstanding, avg_market_cap_36mo,
            raw_info, fetched_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (ticker, f"{ticker} Inc", sector, industry, total_assets, total_debt, cash_equivalents, accounts_receivable, total_revenue, interest_income, shares_outstanding, avg_market_cap_36mo, "{}", "2026-06-13T00:00:00")
    )
    conn.commit()

# --- F1: Tangibility Screen ---

@pytest.mark.tier1
def test_tangibility_pass(isolated_db):
    """F1.1: Non-liquid assets exactly 30% of total assets (passes)."""
    conn = sqlite3.connect(isolated_db)
    # Total assets = 1000. Liquid (Cash 150 + AR 550) = 700. Non-liquid = 300 (30%).
    # Cash screen = 150/1000 = 15% (<30% pass).
    # Tangibility = 300/1000 = 30% (>=30% pass).
    insert_stock_data(conn, "T1_PASS", total_assets=1000.0, cash_equivalents=150.0, accounts_receivable=550.0, total_debt=10.0, total_revenue=100.0, interest_income=1.0, avg_market_cap_36mo=1000.0)
    conn.close()

    run_screener()

    conn = sqlite3.connect(isolated_db)
    df = pd.read_sql_query("SELECT * FROM halal_universe WHERE ticker='T1_PASS'", conn)
    conn.close()
    assert len(df) == 1
@pytest.mark.tier1
def test_tangibility_fail(isolated_db):
    """F1.2: Non-liquid assets less than 30% (e.g. 29.9%, fails)."""
    conn = sqlite3.connect(isolated_db)
    # Total assets = 1000. Liquid (Cash 201 + AR 500) = 701. Non-liquid = 299 (29.9%).
    # Cash screen = 201/1000 = 20.1% (<30% pass).
    # Tangibility = 299/1000 = 29.9% (<30% fail).
    insert_stock_data(conn, "T1_FAIL", total_assets=1000.0, cash_equivalents=201.0, accounts_receivable=500.0, total_debt=10.0, total_revenue=100.0, interest_income=1.0, avg_market_cap_36mo=1000.0)
    conn.close()

    run_screener()

    conn = sqlite3.connect(isolated_db)
    df = pd.read_sql_query("SELECT * FROM halal_rejections WHERE ticker='T1_FAIL'", conn)
    conn.close()
    assert len(df) == 1
    assert "Tangibility" in df.iloc[0]["halal_failure"]
@pytest.mark.tier1
def test_tangibility_liquid_assets_calc(isolated_db):
    """F1.3: Verifies liquid assets = Cash + Accounts Receivable."""
    conn = sqlite3.connect(isolated_db)
    insert_stock_data(conn, "T1_LIQ", total_assets=1000.0, cash_equivalents=100.0, accounts_receivable=200.0, total_debt=10.0, total_revenue=100.0, interest_income=1.0, avg_market_cap_36mo=1000.0)
    conn.close()
    
    run_screener()
    
    # We check the calculated tangibility ratio in the DB.
    # Liquid = 100 + 200 = 300. Tangibility ratio = (1000 - 300)/1000 = 70% (0.7).
    conn = sqlite3.connect(isolated_db)
    df = pd.read_sql_query("SELECT tangibility_ratio FROM halal_universe WHERE ticker='T1_LIQ'", conn)
    conn.close()
    assert len(df) == 1
    assert df.iloc[0]["tangibility_ratio"] == pytest.approx(0.7)

@pytest.mark.tier1
def test_tangibility_non_liquid_assets_calc(isolated_db):
    """F1.4: Verifies non-liquid assets = Total Assets - (Cash + AR)."""
    conn = sqlite3.connect(isolated_db)
    insert_stock_data(conn, "T1_NONLIQ", total_assets=1000.0, cash_equivalents=150.0, accounts_receivable=250.0, total_debt=10.0, total_revenue=100.0, interest_income=1.0, avg_market_cap_36mo=1000.0)
    conn.close()
    
    run_screener()
    
    # Liquid = 150 + 250 = 400. Non-liquid = 1000 - 400 = 600. Ratio = 600/1000 = 60% (0.6).
    conn = sqlite3.connect(isolated_db)
    df = pd.read_sql_query("SELECT tangibility_ratio FROM halal_universe WHERE ticker='T1_NONLIQ'", conn)
    conn.close()
    assert len(df) == 1
    assert df.iloc[0]["tangibility_ratio"] == pytest.approx(0.6)

@pytest.mark.tier1
def test_tangibility_replaces_receivables(isolated_db):
    """F1.5: Verifies no hard 45% AR limit is applied when screening."""
    conn = sqlite3.connect(isolated_db)
    # AR = 500 (50% of assets). Liquid = 50 (Cash) + 500 (AR) = 550. Tangibility = 450/1000 = 45% >= 30%.
    # If 45% limit was applied, this would fail. Under new AAOIFI rules, this passes.
    insert_stock_data(conn, "T1_AR_LIMIT", total_assets=1000.0, cash_equivalents=50.0, accounts_receivable=500.0, total_debt=10.0, total_revenue=100.0, interest_income=1.0, avg_market_cap_36mo=1000.0)
    conn.close()
    
    run_screener()
    
    conn = sqlite3.connect(isolated_db)
    df = pd.read_sql_query("SELECT * FROM halal_universe WHERE ticker='T1_AR_LIMIT'", conn)
    conn.close()
    assert len(df) == 1

# --- F2: Doubtful Database Categorization ---

@pytest.mark.tier1
def test_doubtful_db_insertion(isolated_db):
    """F2.6: Ticker failing only combined haram+doubtful threshold of 5% is written to doubtful_universe."""
    conn = sqlite3.connect(isolated_db)
    # Setup a stock with 1% haram revenue override and 4.1% doubtful revenue override (total 5.1% > 5%).
    insert_stock_data(conn, "DOUBT_CO", total_assets=1000.0, cash_equivalents=100.0, accounts_receivable=50.0, total_debt=10.0, total_revenue=100.0, interest_income=0.0, avg_market_cap_36mo=1000.0)
    conn.execute(
        "INSERT INTO manual_overrides (ticker, haram_revenue_override, doubtful_revenue_override, reasoning, updated_at) VALUES (?, ?, ?, ?, ?)",
        ("DOUBT_CO", 0.01, 0.041, "Doubtful revenue override setup", "2026-06-13T00:00:00")
    )
    conn.commit()
    conn.close()
    
    run_screener()
    
    conn = sqlite3.connect(isolated_db)
    df = pd.read_sql_query("SELECT * FROM doubtful_universe WHERE ticker='DOUBT_CO'", conn)
    conn.close()
    assert len(df) == 1
    assert df.iloc[0]["grade"] == "Doubtful"

@pytest.mark.tier1
def test_doubtful_db_schema(isolated_db):
    """F2.7: Verifies doubtful_universe schema matches halal_universe."""
    conn = sqlite3.connect(isolated_db)
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(halal_universe)")
    halal_cols = {row[1]: row[2] for row in cursor.fetchall()}
    cursor.execute("PRAGMA table_info(doubtful_universe)")
    doubtful_cols = {row[1]: row[2] for row in cursor.fetchall()}
    conn.close()
    
    assert halal_cols == doubtful_cols

@pytest.mark.tier1
def test_doubtful_not_in_halal(isolated_db):
    """F2.8: Verifies doubtful stock is NOT inserted into halal_universe."""
    conn = sqlite3.connect(isolated_db)
    insert_stock_data(conn, "DOUBT_CO", total_assets=1000.0, cash_equivalents=100.0, accounts_receivable=50.0, total_debt=10.0, total_revenue=100.0, interest_income=0.0, avg_market_cap_36mo=1000.0)
    conn.execute("INSERT INTO manual_overrides (ticker, haram_revenue_override, doubtful_revenue_override, updated_at) VALUES (?, ?, ?, ?)", ("DOUBT_CO", 0.01, 0.041, "2026-06-13T00:00:00"))
    conn.commit()
    conn.close()
    
    run_screener()
    
    conn = sqlite3.connect(isolated_db)
    df = pd.read_sql_query("SELECT * FROM halal_universe WHERE ticker='DOUBT_CO'", conn)
    conn.close()
    assert len(df) == 0

@pytest.mark.tier1
def test_doubtful_not_in_rejections(isolated_db):
    """F2.9: Verifies doubtful stock is NOT inserted into halal_rejections as failed/haram."""
    conn = sqlite3.connect(isolated_db)
    insert_stock_data(conn, "DOUBT_CO", total_assets=1000.0, cash_equivalents=100.0, accounts_receivable=50.0, total_debt=10.0, total_revenue=100.0, interest_income=0.0, avg_market_cap_36mo=1000.0)
    conn.execute("INSERT INTO manual_overrides (ticker, haram_revenue_override, doubtful_revenue_override, updated_at) VALUES (?, ?, ?, ?)", ("DOUBT_CO", 0.01, 0.041, "2026-06-13T00:00:00"))
    conn.commit()
    conn.close()
    
    run_screener()
    
    conn = sqlite3.connect(isolated_db)
    df = pd.read_sql_query("SELECT * FROM halal_rejections WHERE ticker='DOUBT_CO'", conn)
    conn.close()
    assert len(df) == 0

@pytest.mark.tier1
def test_doubtful_financial_filters(isolated_db):
    """F2.10: Verifies doubtful stock passes tangibility, debt, and cash screens."""
    conn = sqlite3.connect(isolated_db)
    # Ticker has doubtful revenue but fails tangibility (e.g. liquid = 800, non-liquid = 200/1000 = 20% < 30%).
    # It must fail and be written to halal_rejections, NOT doubtful_universe.
    insert_stock_data(conn, "DOUBT_FAIL_FIN", total_assets=1000.0, cash_equivalents=400.0, accounts_receivable=400.0, total_debt=10.0, total_revenue=100.0, interest_income=0.0, avg_market_cap_36mo=1000.0)
    conn.execute("INSERT INTO manual_overrides (ticker, haram_revenue_override, doubtful_revenue_override, updated_at) VALUES (?, ?, ?, ?)", ("DOUBT_FAIL_FIN", 0.01, 0.041, "2026-06-13T00:00:00"))
    conn.commit()
    conn.close()
    
    run_screener()
    
    conn = sqlite3.connect(isolated_db)
    df_doubt = pd.read_sql_query("SELECT * FROM doubtful_universe WHERE ticker='DOUBT_FAIL_FIN'", conn)
    df_rej = pd.read_sql_query("SELECT * FROM halal_rejections WHERE ticker='DOUBT_FAIL_FIN'", conn)
    conn.close()
    
    assert len(df_doubt) == 0
    assert len(df_rej) == 1

# --- F3: Portfolio Optimizer Doubtful Toggle ---

@pytest.mark.tier1
def test_optimizer_exclude_doubtful_default(isolated_db):
    """F3.11: run_optimizer excludes doubtful stocks by default."""
    conn = sqlite3.connect(isolated_db)
    # Setup H1 in halal_universe and D1 in doubtful_universe
    conn.execute("INSERT INTO halal_universe (ticker, sector, purification_per_share) VALUES (?, ?, ?)", ("H1", "Technology", 0.01))
    conn.execute("INSERT INTO doubtful_universe (ticker, sector, purification_per_share) VALUES (?, ?, ?)", ("D1", "Healthcare", 0.02))
    conn.commit()
    conn.close()
    
    res = run_optimizer(max_weight=1.0, sector_cap=1.0)
    assert res is not None
    assert "H1" in res["allocation"].index
    assert "D1" not in res["allocation"].index

@pytest.mark.tier1
def test_optimizer_include_doubtful_explicit(isolated_db):
    """F3.12: run_optimizer includes doubtful stocks when toggle is True."""
    conn = sqlite3.connect(isolated_db)
    conn.execute("INSERT INTO halal_universe (ticker, sector, purification_per_share) VALUES (?, ?, ?)", ("H1", "Technology", 0.01))
    conn.execute("INSERT INTO doubtful_universe (ticker, sector, purification_per_share) VALUES (?, ?, ?)", ("D1", "Healthcare", 0.02))
    conn.commit()
    conn.close()
    
    res = run_optimizer(max_weight=1.0, sector_cap=1.0, include_doubtful=True)
    assert res is not None
    assert "H1" in res["allocation"].index
    assert "D1" in res["allocation"].index

@pytest.mark.tier1
def test_optimizer_get_data_compliance_filter(isolated_db):
    """F3.13: get_data loads only halal tickers when include_doubtful=False."""
    conn = sqlite3.connect(isolated_db)
    conn.execute("INSERT INTO halal_universe (ticker, sector, purification_per_share) VALUES (?, ?, ?)", ("H1", "Technology", 0.01))
    conn.execute("INSERT INTO doubtful_universe (ticker, sector, purification_per_share) VALUES (?, ?, ?)", ("D1", "Healthcare", 0.02))
    conn.commit()
    conn.close()
    
    prices, sector_map, purification_map = get_data(include_doubtful=False)
    assert "H1" in prices.columns
    assert "D1" not in prices.columns

@pytest.mark.tier1
def test_optimizer_get_data_with_doubtful(isolated_db):
    """F3.14: get_data loads both halal and doubtful tickers when include_doubtful=True."""
    conn = sqlite3.connect(isolated_db)
    conn.execute("INSERT INTO halal_universe (ticker, sector, purification_per_share) VALUES (?, ?, ?)", ("H1", "Technology", 0.01))
    conn.execute("INSERT INTO doubtful_universe (ticker, sector, purification_per_share) VALUES (?, ?, ?)", ("D1", "Healthcare", 0.02))
    conn.commit()
    conn.close()
    
    prices, sector_map, purification_map = get_data(include_doubtful=True)
    assert "H1" in prices.columns
    assert "D1" in prices.columns

@pytest.mark.tier1
def test_optimizer_empty_universe_handling(isolated_db):
    """F3.15: Verifies optimizer behavior when no compliant stocks exist."""
    with pytest.raises(ValueError, match="No halal universe found"):
        get_data()

# --- F4: AI Auditor Interest Priority ---

@pytest.mark.tier1
def test_ai_auditor_extracts_interest_from_notes(isolated_db):
    """F4.16: Verifies AI prompt asks for actual interest income from notes."""
    res = analyze_company_compliance("AAPL", "Apple Inc", "Summary")
    assert res is not None
    assert "interest_income_millions" in res
    assert res["interest_income_millions"] == 3680.0

@pytest.mark.tier1
def test_ai_auditor_fallback_proxy(isolated_db):
    """F4.17: Verifies fallback to 3.0% yield proxy when interest is not disclosed."""
    res = analyze_company_compliance("PROXY_CO", "Proxy Co", "Summary")
    assert res is not None
    assert res["interest_income_millions"] == 150.0  # $10,000M cash * 3% * 6/12 filing period months

@pytest.mark.tier1
def test_ai_auditor_prefer_extracted_to_proxy(isolated_db):
    """F4.18: Verifies AI auditor uses extracted interest instead of proxy if both are present/possible."""
    res = analyze_company_compliance("AAPL", "Apple Inc", "Summary")
    # AAPL has total_cash_and_securities_millions = 143,000. 
    # 3.0% proxy would yield 4290.0 interest. 
    # But actual extracted interest is 3680.0. 
    assert res["interest_income_millions"] == 3680.0
    assert res["interest_income_millions"] != 4290.0

@pytest.mark.tier1
def test_ai_auditor_parser_valid_interest(isolated_db):
    """F4.19: Parser extracts integer/float interest figures in millions."""
    # Let's override MockGenerativeModel response to return raw integer/float
    import google.generativeai as genai
    genai.GenerativeModel.custom_response = json.dumps({
        "haram_revenue": 0.0,
        "doubtful_revenue": 0.0,
        "interest_bearing_debt": 0.0,
        "interest_bearing_securities": 0.0,
        "interest_income": 0.05,
        "total_revenue_millions": 1000.0,
        "haram_revenue_millions": 0.0,
        "doubtful_revenue_millions": 0.0,
        "total_debt_millions": 0.0,
        "interest_bearing_debt_millions": 0.0,
        "short_term_debt_millions": 0.0,
        "long_term_debt_millions": 0.0,
        "total_cash_and_securities_millions": 100.0,
        "interest_bearing_securities_millions": 100.0,
        "short_term_securities_millions": 100.0,
        "long_term_securities_millions": 0.0,
        "interest_income_millions": 50.0, # integer
        "filing_period_months": 12,
        "proposed_rules": [],
        "reasoning": "Standard"
    })
    try:
        res = analyze_company_compliance("ANY", "Any Co", "Summary")
        assert isinstance(res["interest_income_millions"], (int, float))
        assert res["interest_income_millions"] == 50.0
    finally:
        genai.GenerativeModel.custom_response = None
@pytest.mark.tier1
def test_ai_auditor_zero_interest(isolated_db):
    """F4.20: Verifies parser handles explicit zero interest disclosure."""
    import google.generativeai as genai
    genai.GenerativeModel.custom_response = json.dumps({
        "haram_revenue": 0.0,
        "doubtful_revenue": 0.0,
        "interest_bearing_debt": 0.0,
        "interest_bearing_securities": 0.0,
        "interest_income": 0.0,
        "total_revenue_millions": 1000.0,
        "haram_revenue_millions": 0.0,
        "doubtful_revenue_millions": 0.0,
        "total_debt_millions": 0.0,
        "interest_bearing_debt_millions": 0.0,
        "short_term_debt_millions": 0.0,
        "long_term_debt_millions": 0.0,
        "total_cash_and_securities_millions": 100.0,
        "interest_bearing_securities_millions": 100.0,
        "short_term_securities_millions": 100.0,
        "long_term_securities_millions": 0.0,
        "interest_income_millions": 0.0, # Explicit zero
        "filing_period_months": 12,
        "proposed_rules": [],
        "reasoning": "Explicit zero interest"
    })
    try:
        res = analyze_company_compliance("ANY", "Any Co", "Summary")
        assert res["interest_income_millions"] == 0.0
    finally:
        genai.GenerativeModel.custom_response = None

# --- F5: Robust Segment Disaggregation ---

@pytest.mark.tier1
def test_segment_disaggregation_system_prompt(isolated_db):
    """F5.21: Verifies no hardcoded tickers (AAPL, MSFT, ABBV, SPCX) in system prompts."""
    # System prompt must remain general
    for ticker in ["AAPL", "MSFT", "ABBV", "SPCX"]:
        assert f"Ticker: {ticker}" not in SYSTEM_PROMPT
        assert f'"{ticker}"' not in SYSTEM_PROMPT

@pytest.mark.tier1
def test_segment_disaggregation_composite_split(isolated_db):
    """F5.22: Verifies disaggregation on mixed/composite segments based on notes."""
    res = analyze_company_compliance("AAPL", "Apple Inc", "Summary")
    # Services segment is disaggregated into Apple Card ($915M Haram) and streaming/media ($7014M Doubtful).
    assert res["haram_revenue_millions"] == 915.0
    assert res["doubtful_revenue_millions"] == 7014.0

@pytest.mark.tier1
def test_segment_disaggregation_notes_parsing(isolated_db):
    """F5.23: Verifies parsing of tabular sub-disclosures in AI outputs."""
    # Proposed rules contains segment disaggregation rules extracted from tabular notes
    res = analyze_company_compliance("AAPL", "Apple Inc", "Summary")
    assert len(res["proposed_rules"]) > 0
    assert res["proposed_rules"][0]["segment_name"] == "Services"
    assert res["proposed_rules"][0]["compliance_status"] == "doubtful"

@pytest.mark.tier1
def test_segment_disaggregation_doubtful_status(isolated_db):
    """F5.24: Verifies disaggregated haram/doubtful ratio calculations."""
    res = analyze_company_compliance("AAPL", "Apple Inc", "Summary")
    # Ratios computed relative to total revenue of 383,285M
    # haram_revenue = 915.0 / 383285.0 = 0.002387
    # doubtful_revenue = 7014.0 / 383285.0 = 0.018299
    assert res["haram_revenue"] == pytest.approx(915.0 / 383285.0, rel=1e-3)
    assert res["doubtful_revenue"] == pytest.approx(7014.0 / 383285.0, rel=1e-3)

@pytest.mark.tier1
def test_segment_disaggregation_fallback_behavior(isolated_db):
    """F5.25: Verifies behavior when segment details are missing."""
    # If a ticker is unspecified and has no presets, it defaults to the general pattern database
    # Let's test the fallback behavior by calling analyze_company_compliance on an unknown company name
    res = analyze_company_compliance("GENERIC", "Generic Inc", "Summary")
    assert res["haram_revenue_millions"] == 0.0
    assert res["doubtful_revenue_millions"] == 0.0
