import sqlite3
import pytest
import pandas as pd
from src.analysis.screener import run_screener
from src.analysis.optimizer import run_optimizer
from src.analysis.batch_ai_audit import run_background_audit
from src.analysis.ai_analyst import analyze_company_compliance
from tests.e2e.conftest import MockGenerativeModel

# Helper to populate stocks table
def insert_stock_data(conn, ticker, total_assets=1000.0, cash_equivalents=100.0, accounts_receivable=50.0, total_debt=100.0, total_revenue=500.0, interest_income=10.0, avg_market_cap_36mo=10000.0, shares_outstanding=100.0, sector="Technology", industry="Software"):
    # Scale to absolute dollars (millions * 1e6) to match run_background_audit expectations
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
        (ticker, f"{ticker} Inc", sector, industry, total_assets, total_debt, cash_equivalents, accounts_receivable, total_revenue, interest_income, shares_outstanding, avg_market_cap_36mo, '{"longBusinessSummary":"Summary text"}', "2026-06-13T00:00:00")
    )
    conn.commit()

@pytest.mark.tier3
def test_tangibility_and_doubtful_interaction(isolated_db):
    """51. Stock fails tangibility screen and has 6% haram/doubtful revenue (should fail outright due to tangibility, not categorized as doubtful)."""
    conn = sqlite3.connect(isolated_db)
    # Liquid = 400 + 400 = 800. Tangibility = 200/1000 = 20% < 30%. Fails tangibility.
    insert_stock_data(conn, "CROSS_TANG", total_assets=1000.0, cash_equivalents=400.0, accounts_receivable=400.0, total_debt=10.0, total_revenue=100.0, interest_income=0.0, avg_market_cap_36mo=1000.0)
    # Add override for 6% doubtful revenue
    conn.execute("INSERT INTO manual_overrides (ticker, haram_revenue_override, doubtful_revenue_override, updated_at) VALUES (?, ?, ?, ?)", ("CROSS_TANG", 0.0, 0.06, "2026-06-13T00:00:00"))
    conn.commit()
    conn.close()
    
    run_screener()
    
    conn = sqlite3.connect(isolated_db)
    df_doubt = pd.read_sql_query("SELECT * FROM doubtful_universe WHERE ticker='CROSS_TANG'", conn)
    df_rej = pd.read_sql_query("SELECT * FROM halal_rejections WHERE ticker='CROSS_TANG'", conn)
    conn.close()
    
    # Should fail outright on Tangibility (grade F) and not go to doubtful_universe
    assert len(df_doubt) == 0
    assert len(df_rej) == 1
    assert "Tangibility" in df_rej.iloc[0]["halal_failure"]
    assert df_rej.iloc[0]["grade"] == "F"

@pytest.mark.tier3
def test_doubtful_optimizer_and_db_flow(isolated_db):
    """52. Audit inserts doubtful stock -> DB stores it -> Optimizer fetches it with toggle True and allocates weights."""
    conn = sqlite3.connect(isolated_db)
    insert_stock_data(conn, "D1", total_assets=1000.0, cash_equivalents=100.0, accounts_receivable=50.0, total_debt=10.0, total_revenue=100.0, interest_income=0.0, avg_market_cap_36mo=1000.0)
    conn.execute("INSERT INTO manual_overrides (ticker, haram_revenue_override, doubtful_revenue_override, updated_at) VALUES (?, ?, ?, ?)", ("D1", 0.0, 0.06, "2026-06-13T00:00:00"))
    conn.commit()
    conn.close()
    
    run_screener()
    
    # Verify D1 is in doubtful_universe
    conn = sqlite3.connect(isolated_db)
    df_doubt = pd.read_sql_query("SELECT * FROM doubtful_universe WHERE ticker='D1'", conn)
    conn.close()
    assert len(df_doubt) == 1
    
    # Run optimizer with include_doubtful=True
    res = run_optimizer(max_weight=1.0, sector_cap=1.0, include_doubtful=True)
    assert res is not None
    assert "D1" in res["allocation"].index

@pytest.mark.tier3
def test_ai_auditor_interest_and_revenue_screener(isolated_db):
    """53. AI extracts interest income & segments -> Ingestion stores them -> Screener uses them for tangibility and revenue tests."""
    conn = sqlite3.connect(isolated_db)
    insert_stock_data(conn, "AI_DOUBTFUL_TEST", total_assets=1000.0, cash_equivalents=100.0, accounts_receivable=50.0, total_debt=10.0, total_revenue=100.0, interest_income=0.0, avg_market_cap_36mo=1000.0)
    conn.commit()
    conn.close()
    
    # Trigger background audit which calls AI analyst.
    # For ticker containing DOUBTFUL, get_mock_ai_response returns:
    # haram_m = 10.0, doubtful_m = 41.0, combined = 51.0 (5.1%), interest_income_millions = 10.0
    run_background_audit()
    
    # Run screener
    run_screener()
    
    conn = sqlite3.connect(isolated_db)
    df_doubt = pd.read_sql_query("SELECT * FROM doubtful_universe WHERE ticker='AI_DOUBTFUL_TEST'", conn)
    conn.close()
    
    assert len(df_doubt) == 1
    assert df_doubt.iloc[0]["grade"] == "Doubtful"

@pytest.mark.tier3
def test_override_and_optimizer_flow(isolated_db):
    """54. AI extracts halal segment -> Manual override changes it to doubtful -> Optimizer includes/excludes based on override."""
    conn = sqlite3.connect(isolated_db)
    # Seed multiple halal stocks
    insert_stock_data(conn, "H_TEST", total_assets=1000.0, sector="Technology")
    insert_stock_data(conn, "H_KEEP", total_assets=1000.0, sector="Technology")
    insert_stock_data(conn, "H3", total_assets=1000.0, sector="Healthcare")
    insert_stock_data(conn, "H4", total_assets=1000.0, sector="Healthcare")
    insert_stock_data(conn, "H5", total_assets=1000.0, sector="Energy")
    conn.commit()
    conn.close()
    
    run_screener()
    
    # Initially H_TEST should be in halal_universe
    conn = sqlite3.connect(isolated_db)
    assert len(pd.read_sql_query("SELECT * FROM halal_universe WHERE ticker='H_TEST'", conn)) == 1
    conn.close()
    
    # Add override to make H_TEST doubtful: doubtful_revenue_override = 0.06 (6%), is_user_override = 1
    conn = sqlite3.connect(isolated_db)
    conn.execute("INSERT OR REPLACE INTO manual_overrides (ticker, haram_revenue_override, doubtful_revenue_override, is_user_override, updated_at) VALUES (?, ?, ?, ?, ?)", ("H_TEST", 0.0, 0.06, 1, "2026-06-13T00:00:00"))
    conn.commit()
    conn.close()
    
    run_screener()
    
    # Now H_TEST should be in doubtful_universe and NOT in halal_universe
    conn = sqlite3.connect(isolated_db)
    assert len(pd.read_sql_query("SELECT * FROM halal_universe WHERE ticker='H_KEEP'", conn)) == 1
    assert len(pd.read_sql_query("SELECT * FROM halal_universe WHERE ticker='H_TEST'", conn)) == 0
    assert len(pd.read_sql_query("SELECT * FROM doubtful_universe WHERE ticker='H_TEST'", conn)) == 1
    conn.close()
    
    # Run optimizer with include_doubtful=False
    res_false = run_optimizer(max_weight=0.5, sector_cap=1.0, include_doubtful=False)
    assert res_false is not None
    assert "H_TEST" not in res_false["allocation"].index
    
    # Run optimizer with include_doubtful=True
    res_true = run_optimizer(max_weight=0.5, sector_cap=1.0, include_doubtful=True)
    assert res_true is not None
    assert "H_TEST" in res_true["allocation"].index

@pytest.mark.tier3
def test_extreme_all_features(isolated_db):
    """55. Stock with 29.9% tangibility, 5.0% doubtful revenue, and extracted interest income (verifies correct end-to-end routing)."""
    conn = sqlite3.connect(isolated_db)
    # Total Assets = 1000. Liquid (Cash 351 + AR 350) = 701. Non-liquid = 299 (29.9% fails tangibility)
    insert_stock_data(conn, "EXTREME_CO", total_assets=1000.0, cash_equivalents=351.0, accounts_receivable=350.0, total_debt=10.0, total_revenue=100.0, interest_income=1.0, avg_market_cap_36mo=1000.0)
    # Add override for 5% doubtful revenue
    conn.execute("INSERT INTO manual_overrides (ticker, haram_revenue_override, doubtful_revenue_override, updated_at) VALUES (?, ?, ?, ?)", ("EXTREME_CO", 0.0, 0.05, "2026-06-13T00:00:00"))
    conn.commit()
    conn.close()
    
    run_screener()
    
    # Must fail tangibility, so ends up in halal_rejections (grade F)
    conn = sqlite3.connect(isolated_db)
    df_doubt = pd.read_sql_query("SELECT * FROM doubtful_universe WHERE ticker='EXTREME_CO'", conn)
    df_rej = pd.read_sql_query("SELECT * FROM halal_rejections WHERE ticker='EXTREME_CO'", conn)
    conn.close()
    
    assert len(df_doubt) == 0
    assert len(df_rej) == 1
    assert df_rej.iloc[0]["grade"] == "F"
