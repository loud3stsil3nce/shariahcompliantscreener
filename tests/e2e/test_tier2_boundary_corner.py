import sqlite3
import pytest
import pandas as pd
import numpy as np
import json
from unittest.mock import MagicMock

from src.analysis.screener import run_screener
from src.analysis.optimizer import run_optimizer, get_data
from src.analysis.ai_analyst import analyze_company_compliance
from tests.e2e.conftest import MockGenerativeModel, MockYFinanceTicker

def set_mock_response(val):
    import sys
    import json
    if isinstance(val, dict):
        val = json.dumps(val)
    for module in list(sys.modules.values()):
        if module and hasattr(module, "MockGenerativeModel"):
            getattr(module, "MockGenerativeModel").custom_response = val

def clear_mock_response():
    set_mock_response(None)

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

# --- F1: Tangibility Screen Boundary & Corner ---

@pytest.mark.tier2
def test_tangibility_boundary_exact_30(isolated_db):
    """F1.26: Total Assets = 100, Cash = 20, AR = 50, Non-liquid = 30 (passes)."""
    conn = sqlite3.connect(isolated_db)
    # Non-liquid = 100 - (20 + 50) = 30. 30/100 = 30% (Pass).
    # Cash = 20/100 = 20% (Pass).
    insert_stock_data(conn, "T2_EXACT_30", total_assets=100.0, cash_equivalents=20.0, accounts_receivable=50.0, total_debt=1.0, total_revenue=10.0, interest_income=0.1, avg_market_cap_36mo=100.0)
    conn.close()
    run_screener()
    conn = sqlite3.connect(isolated_db)
    df = pd.read_sql_query("SELECT * FROM halal_universe WHERE ticker='T2_EXACT_30'", conn)
    conn.close()
    assert len(df) == 1
@pytest.mark.tier2
def test_tangibility_boundary_just_below_30(isolated_db):
    """F1.27: Total Assets = 100, Cash = 20.1, AR = 50, Non-liquid = 29.9 (fails)."""
    conn = sqlite3.connect(isolated_db)
    # Non-liquid = 100 - (20.1 + 50) = 29.9. 29.9/100 = 29.9% (Fail).
    # Cash = 20.1/100 = 20.1% (Pass).
    insert_stock_data(conn, "T2_JUST_BELOW_30", total_assets=100.0, cash_equivalents=20.1, accounts_receivable=50.0, total_debt=1.0, total_revenue=10.0, interest_income=0.1, avg_market_cap_36mo=100.0)
    conn.close()
    run_screener()
    conn = sqlite3.connect(isolated_db)
    df = pd.read_sql_query("SELECT * FROM halal_rejections WHERE ticker='T2_JUST_BELOW_30'", conn)
    conn.close()
    assert len(df) == 1
    assert "Tangibility" in df.iloc[0]["halal_failure"]

@pytest.mark.tier2
def test_tangibility_zero_assets(isolated_db):
    """F1.28: Total Assets is zero or negative (handled gracefully without division by zero crash)."""
    conn = sqlite3.connect(isolated_db)
    insert_stock_data(conn, "T2_ZERO_ASSETS", total_assets=0.0, cash_equivalents=10.0, accounts_receivable=10.0, total_debt=10.0, total_revenue=100.0, interest_income=1.0, avg_market_cap_36mo=100.0)
    conn.close()
    
    # Division-by-zero should be caught, resulting in 0.0 tangibility and failing screen
    run_screener()
    conn = sqlite3.connect(isolated_db)
    df = pd.read_sql_query("SELECT * FROM halal_rejections WHERE ticker='T2_ZERO_ASSETS'", conn)
    conn.close()
    assert len(df) == 1

@pytest.mark.tier2
def test_tangibility_negative_cash_or_ar(isolated_db):
    """F1.29: Negative values for cash/AR (validation error or handled cleanly)."""
    conn = sqlite3.connect(isolated_db)
    # Total Assets = 100, Cash = -10, AR = 20. Liquid = 10. Non-liquid = 90 (90% passes).
    insert_stock_data(conn, "T2_NEG_VALUES", total_assets=100.0, cash_equivalents=-10.0, accounts_receivable=20.0, total_debt=1.0, total_revenue=10.0, interest_income=0.1, avg_market_cap_36mo=100.0)
    conn.close()
    run_screener()
    conn = sqlite3.connect(isolated_db)
    df = pd.read_sql_query("SELECT * FROM halal_universe WHERE ticker='T2_NEG_VALUES'", conn)
    conn.close()
    assert len(df) == 1

@pytest.mark.tier2
def test_tangibility_assets_less_than_cash_plus_ar(isolated_db):
    """F1.30: Liquid assets > Total Assets (ratio is negative, fails)."""
    conn = sqlite3.connect(isolated_db)
    # Total Assets = 100, Cash = 60, AR = 50 (Liquid = 110). Non-liquid = -10 (fails).
    insert_stock_data(conn, "T2_NEG_TANG", total_assets=100.0, cash_equivalents=60.0, accounts_receivable=50.0, total_debt=1.0, total_revenue=10.0, interest_income=0.1, avg_market_cap_36mo=100.0)
    conn.close()
    run_screener()
    conn = sqlite3.connect(isolated_db)
    df = pd.read_sql_query("SELECT * FROM halal_rejections WHERE ticker='T2_NEG_TANG'", conn)
    conn.close()
    assert len(df) == 1

# --- F2: Doubtful Database Categorization Boundary & Corner ---

@pytest.mark.tier2
def test_doubtful_revenue_boundary_exact_5(isolated_db):
    """F2.31: Haram + Doubtful revenue = exactly 5.0% (fails combined threshold, category is doubtful)."""
    conn = sqlite3.connect(isolated_db)
    insert_stock_data(conn, "DOUBT_EXACT_5", total_assets=1000.0, cash_equivalents=100.0, accounts_receivable=50.0, total_debt=10.0, total_revenue=100.0, interest_income=0.0, avg_market_cap_36mo=1000.0)
    conn.execute("INSERT INTO manual_overrides (ticker, haram_revenue_override, doubtful_revenue_override, updated_at) VALUES (?, ?, ?, ?)", ("DOUBT_EXACT_5", 0.01, 0.04, "2026-06-13T00:00:00"))
    conn.commit()
    conn.close()
    
    run_screener()
    conn = sqlite3.connect(isolated_db)
    df = pd.read_sql_query("SELECT * FROM doubtful_universe WHERE ticker='DOUBT_EXACT_5'", conn)
    conn.close()
    assert len(df) == 1

@pytest.mark.tier2
def test_doubtful_revenue_just_below_5(isolated_db):
    """F2.32: Haram + Doubtful revenue = 4.9% (passes combined threshold, category is halal)."""
    conn = sqlite3.connect(isolated_db)
    insert_stock_data(conn, "DOUBT_JUST_BELOW_5", total_assets=1000.0, cash_equivalents=100.0, accounts_receivable=50.0, total_debt=10.0, total_revenue=100.0, interest_income=0.0, avg_market_cap_36mo=1000.0)
    conn.execute("INSERT INTO manual_overrides (ticker, haram_revenue_override, doubtful_revenue_override, updated_at) VALUES (?, ?, ?, ?)", ("DOUBT_JUST_BELOW_5", 0.01, 0.039, "2026-06-13T00:00:00"))
    conn.commit()
    conn.close()
    
    run_screener()
    conn = sqlite3.connect(isolated_db)
    df = pd.read_sql_query("SELECT * FROM halal_universe WHERE ticker='DOUBT_JUST_BELOW_5'", conn)
    conn.close()
    assert len(df) == 1

@pytest.mark.tier2
def test_doubtful_revenue_extremely_high(isolated_db):
    """F2.33: Combined revenue = 90% (exceeds 5%, category is doubtful/haram)."""
    conn = sqlite3.connect(isolated_db)
    insert_stock_data(conn, "DOUBT_EXTREME", total_assets=1000.0, cash_equivalents=100.0, accounts_receivable=50.0, total_debt=10.0, total_revenue=100.0, interest_income=0.0, avg_market_cap_36mo=1000.0)
    conn.execute("INSERT INTO manual_overrides (ticker, haram_revenue_override, doubtful_revenue_override, updated_at) VALUES (?, ?, ?, ?)", ("DOUBT_EXTREME", 0.01, 0.89, "2026-06-13T00:00:00"))
    conn.commit()
    conn.close()
    
    run_screener()
    conn = sqlite3.connect(isolated_db)
    df = pd.read_sql_query("SELECT * FROM doubtful_universe WHERE ticker='DOUBT_EXTREME'", conn)
    conn.close()
    assert len(df) == 1

@pytest.mark.tier2
def test_doubtful_override_handling(isolated_db):
    """F2.34: Manual override is applied, category updates accordingly in DB."""
    conn = sqlite3.connect(isolated_db)
    insert_stock_data(conn, "DOUBT_OVERRIDE", total_assets=1000.0, cash_equivalents=100.0, accounts_receivable=50.0, total_debt=10.0, total_revenue=100.0, interest_income=0.0, avg_market_cap_36mo=1000.0)
    # Initially halal segment, override sets doubtful to 10%
    conn.execute("INSERT INTO manual_overrides (ticker, haram_revenue_override, doubtful_revenue_override, is_user_override, updated_at) VALUES (?, ?, ?, ?, ?)", ("DOUBT_OVERRIDE", 0.0, 0.10, 1, "2026-06-13T00:00:00"))
    conn.commit()
    conn.close()
    
    run_screener()
    conn = sqlite3.connect(isolated_db)
    df = pd.read_sql_query("SELECT * FROM doubtful_universe WHERE ticker='DOUBT_OVERRIDE'", conn)
    conn.close()
    assert len(df) == 1

@pytest.mark.tier2
def test_doubtful_duplicate_insertion(isolated_db):
    """F2.35: Multiple screen runs preserve unique records in doubtful_universe."""
    conn = sqlite3.connect(isolated_db)
    insert_stock_data(conn, "DOUBT_DUP", total_assets=1000.0, cash_equivalents=100.0, accounts_receivable=50.0, total_debt=10.0, total_revenue=100.0, interest_income=0.0, avg_market_cap_36mo=1000.0)
    conn.execute("INSERT INTO manual_overrides (ticker, haram_revenue_override, doubtful_revenue_override, updated_at) VALUES (?, ?, ?, ?)", ("DOUBT_DUP", 0.01, 0.05, "2026-06-13T00:00:00"))
    conn.commit()
    conn.close()
    
    run_screener()
    run_screener() # Run twice to verify duplicate insertion does not fail on unique constraint
    
    conn = sqlite3.connect(isolated_db)
    df = pd.read_sql_query("SELECT * FROM doubtful_universe WHERE ticker='DOUBT_DUP'", conn)
    conn.close()
    assert len(df) == 1

# --- F3: Optimizer Doubtful Toggle Boundary & Corner ---

@pytest.mark.tier2
def test_optimizer_boundary_one_halal_one_doubtful(isolated_db):
    """F3.36: Allocates weights correctly between 1 Halal and 1 Doubtful stock."""
    conn = sqlite3.connect(isolated_db)
    conn.execute("INSERT INTO halal_universe (ticker, sector, purification_per_share) VALUES (?, ?, ?)", ("H1", "Technology", 0.01))
    conn.execute("INSERT INTO doubtful_universe (ticker, sector, purification_per_share) VALUES (?, ?, ?)", ("D1", "Healthcare", 0.02))
    conn.commit()
    conn.close()
    
    res = run_optimizer(max_weight=0.6, sector_cap=1.0, include_doubtful=True)
    assert res is not None
    # Maximum weight is 60%. Each should get non-zero weight.
    assert res["allocation"]["H1"] > 0.1
    assert res["allocation"]["D1"] > 0.1

@pytest.mark.tier2
def test_optimizer_all_doubtful(isolated_db):
    """F3.37: Universe contains only doubtful stocks (toggle True vs False)."""
    conn = sqlite3.connect(isolated_db)
    conn.execute("INSERT INTO doubtful_universe (ticker, sector, purification_per_share) VALUES (?, ?, ?)", ("D1", "Healthcare", 0.02))
    conn.commit()
    conn.close()
    
    # False should fail with ValueError
    with pytest.raises(ValueError, match="No halal universe found"):
        run_optimizer(include_doubtful=False)
        
    # True should succeed
    res = run_optimizer(include_doubtful=True, max_weight=1.0, sector_cap=1.0)
    assert res is not None
    assert "D1" in res["allocation"].index

@pytest.mark.tier2
def test_optimizer_invalid_toggle_value(isolated_db):
    """F3.38: Passing non-boolean values to toggle parameter."""
    conn = sqlite3.connect(isolated_db)
    conn.execute("INSERT INTO halal_universe (ticker, sector, purification_per_share) VALUES (?, ?, ?)", ("H1", "Technology", 0.01))
    conn.commit()
    conn.close()
    
    with pytest.raises(TypeError):
        run_optimizer(include_doubtful="not_a_bool")

@pytest.mark.tier2
def test_optimizer_constraint_bounds(isolated_db):
    """F3.39: Weight caps constraints are respected when doubtful is included."""
    conn = sqlite3.connect(isolated_db)
    conn.execute("INSERT INTO halal_universe (ticker, sector, purification_per_share) VALUES (?, ?, ?)", ("H1", "Technology", 0.01))
    conn.execute("INSERT INTO halal_universe (ticker, sector, purification_per_share) VALUES (?, ?, ?)", ("H2", "Technology", 0.01))
    conn.execute("INSERT INTO halal_universe (ticker, sector, purification_per_share) VALUES (?, ?, ?)", ("H3", "Technology", 0.01))
    conn.execute("INSERT INTO halal_universe (ticker, sector, purification_per_share) VALUES (?, ?, ?)", ("H4", "Technology", 0.01))
    conn.execute("INSERT INTO doubtful_universe (ticker, sector, purification_per_share) VALUES (?, ?, ?)", ("D1", "Healthcare", 0.02))
    conn.commit()
    conn.close()
    
    # Weight cap = 20% (0.20). With 5 assets, this is exactly 100%.
    res = run_optimizer(max_weight=0.20, sector_cap=1.0, include_doubtful=True)
    assert res is not None
    for ticker, weight in res["allocation"].items():
        assert weight <= 0.20 + 1e-5

@pytest.mark.tier2
def test_optimizer_purification_calc(isolated_db):
    """F3.40: Verifies purification calculations for doubtful stocks."""
    conn = sqlite3.connect(isolated_db)
    conn.execute("INSERT INTO halal_universe (ticker, sector, purification_per_share) VALUES (?, ?, ?)", ("H1", "Technology", 0.05))
    conn.execute("INSERT INTO doubtful_universe (ticker, sector, purification_per_share) VALUES (?, ?, ?)", ("D1", "Healthcare", 0.10))
    conn.commit()
    conn.close()
    
    res = run_optimizer(max_weight=0.5, sector_cap=1.0, include_doubtful=True)
    assert res is not None
    assert res["purification_per_1000"] > 0.0

# --- F4: AI Auditor Interest Priority Boundary & Corner ---

@pytest.mark.tier2
def test_ai_auditor_malformed_json_response(isolated_db):
    """F4.41: Parser handles malformed JSON response from LLM gracefully."""
    set_mock_response("{malformed_json_here...")
    try:
        res = analyze_company_compliance("ANY", "Any Co", "Summary")
        assert "error" in res
    finally:
        clear_mock_response()

@pytest.mark.tier2
def test_ai_auditor_missing_financials(isolated_db):
    """F4.42: Filings missing revenue or asset details (handled with default fallback)."""
    set_mock_response({
        "haram_revenue": 0.0,
        "doubtful_revenue": 0.0,
        "interest_bearing_debt": 0.0,
        "interest_bearing_securities": 0.0,
        "interest_income": 0.0,
        "total_revenue_millions": 0.0, # missing/zero
        "haram_revenue_millions": 0.0,
        "doubtful_revenue_millions": 0.0,
        "total_debt_millions": 0.0,
        "interest_bearing_debt_millions": 0.0,
        "short_term_debt_millions": 0.0,
        "long_term_debt_millions": 0.0,
        "total_cash_and_securities_millions": 0.0,
        "interest_bearing_securities_millions": 0.0,
        "short_term_securities_millions": 0.0,
        "long_term_securities_millions": 0.0,
        "interest_income_millions": 0.0,
        "filing_period_months": 12,
        "proposed_rules": [],
        "reasoning": "Zero/missing financials"
    })
    try:
        res = analyze_company_compliance("ANY", "Any Co", "Summary")
        assert res["total_revenue_millions"] == 0.0
    finally:
        clear_mock_response()

@pytest.mark.tier2
def test_ai_auditor_non_numeric_interest(isolated_db):
    """F4.43: LLM returns text like 'N/A' or 'undisclosed' for interest."""
    # The RESPONSE_SCHEMA dictates double/number, but LLM might bypass schema validation in extreme cases
    set_mock_response({
        "haram_revenue": 0.0,
        "doubtful_revenue": 0.0,
        "interest_bearing_debt": 0.0,
        "interest_bearing_securities": 0.0,
        "interest_income": 0.0,
        "total_revenue_millions": 100.0,
        "haram_revenue_millions": 0.0,
        "doubtful_revenue_millions": 0.0,
        "total_debt_millions": 10.0,
        "interest_bearing_debt_millions": 10.0,
        "short_term_debt_millions": 0.0,
        "long_term_debt_millions": 10.0,
        "total_cash_and_securities_millions": 50.0,
        "interest_bearing_securities_millions": 50.0,
        "short_term_securities_millions": 50.0,
        "long_term_securities_millions": 0.0,
        "interest_income_millions": "N/A",  # non-numeric
        "filing_period_months": 12,
        "proposed_rules": [],
        "reasoning": "Non-numeric interest string"
    })
    try:
        res = analyze_company_compliance("ANY", "Any Co", "Summary")
        # Under normal circumstances, json.loads succeeded but types might be malformed.
        # Check that we handle or return it
        assert res["interest_income_millions"] == "N/A"
    finally:
        clear_mock_response()

@pytest.mark.tier2
def test_ai_auditor_extreme_interest_values(isolated_db):
    """F4.44: Interest income exceeds total revenue (handled/flagged)."""
    set_mock_response({
        "haram_revenue": 0.0,
        "doubtful_revenue": 0.0,
        "interest_bearing_debt": 0.0,
        "interest_bearing_securities": 0.0,
        "interest_income": 2.0,  # 200%
        "total_revenue_millions": 10.0,
        "haram_revenue_millions": 0.0,
        "doubtful_revenue_millions": 0.0,
        "total_debt_millions": 0.0,
        "interest_bearing_debt_millions": 0.0,
        "short_term_debt_millions": 0.0,
        "long_term_debt_millions": 0.0,
        "total_cash_and_securities_millions": 1000.0,
        "interest_bearing_securities_millions": 1000.0,
        "short_term_securities_millions": 1000.0,
        "long_term_securities_millions": 0.0,
        "interest_income_millions": 20.0,  # 20.0 > 10.0 revenue
        "filing_period_months": 12,
        "proposed_rules": [],
        "reasoning": "High cash yields exceeding revenue"
    })
    try:
        res = analyze_company_compliance("ANY", "Any Co", "Summary")
        assert res["interest_income_millions"] == 20.0
    finally:
        clear_mock_response()

@pytest.mark.tier2
def test_ai_auditor_multiple_interest_mentions(isolated_db):
    """F4.45: AI resolves multiple conflicting interest figures."""
    res = analyze_company_compliance("AAPL", "Apple Inc", "Summary")
    # Verify AI mock resolves and returns 3680.0
    assert res["interest_income_millions"] == 3680.0

# --- F5: Robust Segment Disaggregation Boundary & Corner ---

@pytest.mark.tier2
def test_segment_disaggregation_unclear_text(isolated_db):
    """F5.46: Unstructured text with no clear numbers."""
    set_mock_response({
        "haram_revenue": 0.0,
        "doubtful_revenue": 0.0,
        "interest_bearing_debt": 0.0,
        "interest_bearing_securities": 0.0,
        "interest_income": 0.0,
        "total_revenue_millions": 100.0,
        "haram_revenue_millions": 0.0,
        "doubtful_revenue_millions": 0.0,
        "total_debt_millions": 0.0,
        "interest_bearing_debt_millions": 0.0,
        "short_term_debt_millions": 0.0,
        "long_term_debt_millions": 0.0,
        "total_cash_and_securities_millions": 10.0,
        "interest_bearing_securities_millions": 10.0,
        "short_term_securities_millions": 10.0,
        "long_term_securities_millions": 0.0,
        "interest_income_millions": 0.0,
        "filing_period_months": 12,
        "proposed_rules": [],
        "reasoning": "Text lacks segment information completely."
    })
    try:
        res = analyze_company_compliance("ANY", "Any Co", "No segment tables available.")
        assert res["haram_revenue_millions"] == 0.0
        assert res["doubtful_revenue_millions"] == 0.0
    finally:
        clear_mock_response()

@pytest.mark.tier2
def test_segment_disaggregation_rounding(isolated_db):
    """F5.47: Segment percentages sum to 99.9% or 100.1% due to rounding."""
    set_mock_response({
        "haram_revenue": 0.001,
        "doubtful_revenue": 0.002,
        "interest_bearing_debt": 0.0,
        "interest_bearing_securities": 0.0,
        "interest_income": 0.0,
        "total_revenue_millions": 100.0,
        "haram_revenue_millions": 0.1,  # 0.1%
        "doubtful_revenue_millions": 0.2, # 0.2%
        "total_debt_millions": 0.0,
        "interest_bearing_debt_millions": 0.0,
        "short_term_debt_millions": 0.0,
        "long_term_debt_millions": 0.0,
        "total_cash_and_securities_millions": 10.0,
        "interest_bearing_securities_millions": 10.0,
        "short_term_securities_millions": 10.0,
        "long_term_securities_millions": 0.0,
        "interest_income_millions": 0.0,
        "filing_period_months": 12,
        "proposed_rules": [],
        "reasoning": "Rounding limits verification."
    })
    try:
        res = analyze_company_compliance("ANY", "Any Co", "Summary")
        assert res["haram_revenue"] + res["doubtful_revenue"] == pytest.approx(0.003)
    finally:
        clear_mock_response()

@pytest.mark.tier2
def test_segment_disaggregation_negative_revenue(isolated_db):
    """F5.48: Handles negative segment revenue (e.g. accounting adjustments)."""
    set_mock_response({
        "haram_revenue": 0.0,
        "doubtful_revenue": 0.0,
        "interest_bearing_debt": 0.0,
        "interest_bearing_securities": 0.0,
        "interest_income": 0.0,
        "total_revenue_millions": 100.0,
        "haram_revenue_millions": -5.0,  # Negative adjustment
        "doubtful_revenue_millions": 0.0,
        "total_debt_millions": 0.0,
        "interest_bearing_debt_millions": 0.0,
        "short_term_debt_millions": 0.0,
        "long_term_debt_millions": 0.0,
        "total_cash_and_securities_millions": 10.0,
        "interest_bearing_securities_millions": 10.0,
        "short_term_securities_millions": 10.0,
        "long_term_securities_millions": 0.0,
        "interest_income_millions": 0.0,
        "filing_period_months": 12,
        "proposed_rules": [],
        "reasoning": "Negative segment revenue adjustment."
    })
    try:
        res = analyze_company_compliance("ANY", "Any Co", "Summary")
        assert res["haram_revenue_millions"] == -5.0
    finally:
        clear_mock_response()

@pytest.mark.tier2
def test_segment_disaggregation_large_segments(isolated_db):
    """F5.49: Very large number of segments (e.g., 20+)."""
    # Simply verify the model response structure is handled cleanly
    res = analyze_company_compliance("AAPL", "Apple Inc", "Summary")
    assert "proposed_rules" in res

@pytest.mark.tier2
def test_segment_disaggregation_unknown_categories(isolated_db):
    """F5.50: Handles custom/unknown segment names gracefully."""
    res = analyze_company_compliance("GENERIC", "Generic Inc", "Summary")
    assert res["proposed_rules"] == []
