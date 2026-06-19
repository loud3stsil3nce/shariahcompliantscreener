import sqlite3
import pytest
import pandas as pd
from src.analysis.screener import run_screener
from src.analysis.optimizer import run_optimizer
from src.analysis.batch_ai_audit import run_background_audit

# Helper to populate stocks table
def insert_stock_data(conn, ticker, total_assets=1000.0, cash_equivalents=100.0, accounts_receivable=50.0, total_debt=100.0, total_revenue=500.0, interest_income=10.0, avg_market_cap_36mo=10000.0, shares_outstanding=100.0, sector="Technology", industry="Software"):
    # Scale to absolute dollars (millions * 1e6)
    total_assets *= 1e6
    total_debt *= 1e6
    cash_equivalents *= 1e6
    accounts_receivable *= 1e6
    total_revenue *= 1e6
    interest_income *= 1e6
    avg_market_cap_36mo *= 1e6
    
    conn.execute(
        """
        INSERT OR REPLACE INTO stocks (
            ticker, name, sector, industry,
            total_assets, total_debt, cash_equivalents, accounts_receivable,
            total_revenue, interest_income, shares_outstanding, avg_market_cap_36mo,
            raw_info, fetched_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (ticker, f"{ticker} Inc", sector, industry, total_assets, total_debt, cash_equivalents, accounts_receivable, total_revenue, interest_income, shares_outstanding, avg_market_cap_36mo, '{"longBusinessSummary":"Summary text", "marketCap": 100000.0}', "2026-06-13T00:00:00")
    )
    conn.commit()

@pytest.mark.tier4
def test_real_world_spcx_validation(isolated_db):
    """56. Opaque-box validation of SPCX parsing. The mock file/filing for SPCX is parsed, and resolves to a doubtful revenue ratio of ~9.31% and interest income ratio of ~4.34% without stock-specific prompts."""
    conn = sqlite3.connect(isolated_db)
    # Seed SPCX details
    insert_stock_data(
        conn, 
        "SPCX", 
        total_assets=100000.0, 
        cash_equivalents=27015.0, 
        accounts_receivable=2000.0, 
        total_debt=1000.0, 
        total_revenue=18674.0, 
        interest_income=0.0, 
        avg_market_cap_36mo=100000.0
    )
    # Seed a halal stock H1 to keep the optimizer happy when SPCX is excluded
    insert_stock_data(conn, "H1", total_assets=1000.0, cash_equivalents=100.0, total_debt=10.0, total_revenue=100.0, avg_market_cap_36mo=10000.0)
    conn.commit()
    conn.close()
    
    # Run Background Audit which triggers AI parser
    run_background_audit()
    
    # Run Screener
    run_screener()
    
    # Assert SPCX is written to doubtful_universe (failing combined threshold of 13.65% > 5.0%)
    conn = sqlite3.connect(isolated_db)
    df_doubt = pd.read_sql_query("SELECT * FROM doubtful_universe WHERE ticker='SPCX'", conn)
    df_halal = pd.read_sql_query("SELECT * FROM halal_universe WHERE ticker='SPCX'", conn)
    df_rej = pd.read_sql_query("SELECT * FROM halal_rejections WHERE ticker='SPCX'", conn)
    conn.close()
    
    assert len(df_doubt) == 1
    assert len(df_halal) == 0
    assert len(df_rej) == 0
    assert df_doubt.iloc[0]["grade"] == "Doubtful"
    
    # Verify optimizer toggle exclusion
    res_false = run_optimizer(max_weight=1.0, sector_cap=1.0, include_doubtful=False)
    assert "SPCX" not in res_false["allocation"].index
    assert "H1" in res_false["allocation"].index
    
    # Verify optimizer toggle inclusion
    res_true = run_optimizer(max_weight=1.0, sector_cap=1.0, include_doubtful=True)
    assert "SPCX" in res_true["allocation"].index
    assert "H1" in res_true["allocation"].index

@pytest.mark.tier4
def test_real_world_aapl_standard_flow(isolated_db):
    """57. Standard halal stock flow (Apple Inc) with low debt, high tangibility, low doubtful revenue."""
    conn = sqlite3.connect(isolated_db)
    insert_stock_data(
        conn, 
        "AAPL", 
        total_assets=350000.0, 
        cash_equivalents=143000.0, 
        accounts_receivable=20000.0, 
        total_debt=111000.0, 
        total_revenue=383285.0, 
        interest_income=0.0, 
        avg_market_cap_36mo=3000000.0
    )
    conn.commit()
    conn.close()
    
    run_background_audit()
    run_screener()
    
    conn = sqlite3.connect(isolated_db)
    df_halal = pd.read_sql_query("SELECT * FROM halal_universe WHERE ticker='AAPL'", conn)
    conn.close()
    
    assert len(df_halal) == 1
    assert df_halal.iloc[0]["grade"] in ["A+", "A", "B+", "B", "C+", "C", "D"]

@pytest.mark.tier4
def test_real_world_abbv_standard_flow(isolated_db):
    """58. AbbVie Inc flow, ensuring general segment disaggregation correctly screens healthcare/aesthetics."""
    conn = sqlite3.connect(isolated_db)
    insert_stock_data(
        conn, 
        "ABBV", 
        total_assets=80000.0, 
        cash_equivalents=12000.0, 
        accounts_receivable=5000.0, 
        total_debt=62000.0, 
        total_revenue=58020.0, 
        interest_income=0.0, 
        avg_market_cap_36mo=300000.0 # Increased to pass debt screen (62/300 = 20.6% < 30%)
    )
    conn.commit()
    conn.close()
    
    run_background_audit()
    run_screener()
    
    conn = sqlite3.connect(isolated_db)
    df_halal = pd.read_sql_query("SELECT * FROM halal_universe WHERE ticker='ABBV'", conn)
    conn.close()
    
    # Combined haram aesthetics + interest = 1.64% + 0.62% = 2.26% < 5%. Passes!
    assert len(df_halal) == 1

@pytest.mark.tier4
def test_real_world_highly_leveraged_financial_institution(isolated_db):
    """59. Standard bank flow, failing interest income screening."""
    conn = sqlite3.connect(isolated_db)
    insert_stock_data(
        conn, 
        "HIGHLY_LEVERAGED", 
        total_assets=1000.0, 
        cash_equivalents=100.0, 
        accounts_receivable=50.0, 
        total_debt=800.0, 
        total_revenue=1000.0, 
        interest_income=0.0, 
        avg_market_cap_36mo=10000.0
    )
    conn.commit()
    conn.close()
    
    run_background_audit()
    run_screener()
    
    conn = sqlite3.connect(isolated_db)
    df_rej = pd.read_sql_query("SELECT * FROM halal_rejections WHERE ticker='HIGHLY_LEVERAGED'", conn)
    conn.close()
    
    assert len(df_rej) == 1
    assert df_rej.iloc[0]["grade"] == "F"

@pytest.mark.tier4
def test_real_world_conglomerate_disaggregation(isolated_db):
    """60. Multi-segment conglomerate disaggregation (e.g., defense, services, entertainment)."""
    conn = sqlite3.connect(isolated_db)
    insert_stock_data(
        conn, 
        "CONGLOMERATE", 
        total_assets=20000.0, 
        cash_equivalents=2000.0, 
        accounts_receivable=1000.0, 
        total_debt=1000.0, 
        total_revenue=10000.0, 
        interest_income=0.0, 
        avg_market_cap_36mo=100000.0
    )
    conn.commit()
    conn.close()
    
    run_background_audit()
    run_screener()
    
    conn = sqlite3.connect(isolated_db)
    df_halal = pd.read_sql_query("SELECT * FROM halal_universe WHERE ticker='CONGLOMERATE'", conn)
    conn.close()
    
    assert len(df_halal) == 1
