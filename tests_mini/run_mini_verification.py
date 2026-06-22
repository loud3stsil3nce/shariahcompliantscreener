import sys
import os
import json
import asyncio
import pandas as pd

# Add src to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.db.helpers import get_db
from src.data.sec_extractor import get_latest_10k_text
from src.data.harvester import harvest_all_sources
from src.analysis.ai_analyst import analyze_multi_source_compliance
from src.analysis.screener import run_screener

async def main():
    print("\n=== STARTING AAPL Q2 2026 DYNAMIC COMPLIANCE VERIFICATION ===")
    
    # 1. Setup the Database Anchors
    conn = get_db()
    
    # Ensure tables exist
    from src.db.setup import init_db_tables
    init_db_tables()
    
    # Seed AAPL Q2 2026 baseline financial data in stocks table
    # Musaffa values: total revenue = 257.05B, Cash/securities = 146.59B, Debt = 85.94B, trailing 36mo avg market cap = 3.28T
    ticker = "AAPL"
    name = "Apple Inc."
    total_assets = 359241000000.0
    total_debt = 85940000000.0              # Target Interest-Bearing Debt: 85.94B
    cash_equivalents = 146590000000.0        # Target Interest-Bearing Securities: 146.59B
    accounts_receivable = 39777000000.0
    total_revenue = 257050000000.0          # Target Revenue: 257.05B
    interest_income = 2467680000.0           # Target gross interest: 2.467B (representing 0.96% of 257.05B)
    avg_market_cap = 3280000000000.0        # Target trailing avg market cap: 3.28T
    
    # Raw info containing business summary
    raw_info = json.dumps({
        "longBusinessSummary": (
            "Apple Inc. designs, manufactures, and markets smartphones, personal computers, tablets, wearables, and accessories. "
            "It also offers various services, including Apple Music, Apple TV+, and Apple Card."
        )
    })
    
    print("Seeding baseline stocks data in database...")
    conn.execute("""
        INSERT OR REPLACE INTO stocks 
        (ticker, name, sector, industry, total_assets, total_debt, cash_equivalents, 
         accounts_receivable, total_revenue, interest_income, shares_outstanding, avg_market_cap_36mo, raw_info, fetched_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        ticker, name, "Technology", "Consumer Electronics", total_assets, total_debt, cash_equivalents,
        accounts_receivable, total_revenue, interest_income, 14687356000.0, avg_market_cap, raw_info, "2026-06-21"
    ))
    
    # Strictly delete any manual or curated overrides and segment maps to test the AI's calculation capability
    print("Deleting existing overrides/benchmarks/segment rules for AAPL...")
    conn.execute("DELETE FROM manual_overrides WHERE ticker = ?", (ticker,))
    conn.execute("DELETE FROM curated_benchmarks WHERE ticker = ?", (ticker,))
    conn.execute("DELETE FROM shariah_segment_map WHERE ticker = ?", (ticker,))
    conn.execute("DELETE FROM proposed_segment_rules WHERE ticker = ?", (ticker,))
    conn.commit()
    
    # 2. Extract SEC text and Run Harvester (fetches live search snippets)
    print("\n--- 1. Extracting SEC Filing Text ---")
    sec_text, sec_url = get_latest_10k_text(ticker)
    
    print("\n--- 2. Running Dynamic Harvester (Web Searches in parallel) ---")
    # Using 2026 Q2 as year/quarter to match report context
    harvested = await harvest_all_sources(ticker, year=2026, quarter=2, sec_text=sec_text)
    
    # 3. Execute AI Audit (Generates ratios dynamically)
    print("\n--- 3. Running Multi-Source AI Screener Audit ---")
    ai_res = analyze_multi_source_compliance(ticker, name, harvested, summary="Apple Services segment disaggregation")
    
    if "error" in ai_res:
        print(f"❌ AI Screener Audit failed: {ai_res['error']}")
        conn.close()
        sys.exit(1)
        
    # Scale variables
    filing_period = ai_res.get('filing_period_months', 12) or 12
    scale_factor = 12.0 / filing_period
    
    total_rev_m = (ai_res.get('total_revenue_millions', 1.0) or 1.0) * scale_factor
    haram_rev_m = (ai_res.get('haram_revenue_millions', 0.0) or 0.0) * scale_factor
    doubtful_rev_m = (ai_res.get('doubtful_revenue_millions', 0.0) or 0.0) * scale_factor
    int_inc_m = (ai_res.get('interest_income_millions', 0.0) or 0.0) * scale_factor
    
    final_haram_rev = haram_rev_m / total_rev_m
    final_doubtful_rev = doubtful_rev_m / total_rev_m
    final_int_inc_ratio = int_inc_m / total_rev_m
    cash_and_securities_m = ai_res.get('total_cash_and_securities_millions', 0.0) or 0.0
    
    final_debt_ratio = (ai_res.get('interest_bearing_debt_millions', 0.0) * 1e6) / avg_market_cap
    final_cash_ratio = (cash_and_securities_m * 1e6) / avg_market_cap
    
    # Save the computed manual overrides (mimicking API flow)
    conn.execute("""
        INSERT OR REPLACE INTO manual_overrides 
        (ticker, haram_revenue_override, debt_ratio_override, cash_ratio_override, interest_income_override, doubtful_revenue_override, reasoning, is_user_override, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?)
    """, (
        ticker, 
        final_haram_rev, 
        final_debt_ratio, 
        final_cash_ratio, 
        final_int_inc_ratio,
        final_doubtful_rev,
        json.dumps(ai_res),
        pd.Timestamp.now().isoformat()
    ))
    conn.commit()
    conn.close()
    
    # Run the screener to check final outputs in DB
    print("\n--- 4. Running Compliance Screener ---")
    run_screener(use_current_market_cap=False)
    
    # 4. Compare results to targets
    print("\n================== VERIFICATION REPORT ==================")
    print(f"Total Revenue: {total_rev_m:,.2f}M USD")
    print(f"Haram Revenue Millions: {haram_rev_m:,.2f}M USD")
    print(f"Interest Income Millions: {int_inc_m:,.2f}M USD")
    print(f"Total Cash/Securities Millions: {cash_and_securities_m:,.2f}M USD")
    print(f"Interest-Bearing Debt Millions: {ai_res.get('interest_bearing_debt_millions'):,.2f}M USD")
    
    print("\nComparison Table:")
    print(f"{'Metric':<30} | {'Musaffa Target':<15} | {'Our Output':<15} | {'Diff':<10} | {'Status':<15}")
    print(f"{'-'*30}-+-{'-'*15}-+-{'-'*15}-+-{'-'*10}-+-{'-'*15}")
    
    metrics = [
        ("Haram Business Rev", 0.0312, final_haram_rev),
        ("Doubtful Rev", 0.0, final_doubtful_rev),
        ("Interest Income", 0.0096, final_int_inc_ratio),
        ("Debt / Avg Market Cap", 0.0262, final_debt_ratio),
        ("Cash / Avg Market Cap", 0.0447, final_cash_ratio)
    ]
    
    failures = 0
    tolerance = 0.005 # 0.5% differential allowed
    
    for metric_name, target, actual in metrics:
        diff = abs(target - actual)
        status = "🎯 PASS" if diff <= tolerance else "❌ FAIL"
        if diff > tolerance:
            failures += 1
        print(f"{metric_name:<30} | {target:.4%}         | {actual:.4%}         | {diff:.4%}   | {status:<15}")
        
    print("\n========================================================")
    if failures == 0:
        print("✅ SUCCESS: AI compliance screener matches Musaffa metrics within 0.5%!")
        sys.exit(0)
    else:
        print(f"❌ FAILURE: {failures} metrics diverged by more than 0.5%.")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
