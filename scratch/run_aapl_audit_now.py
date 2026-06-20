import sys
import os
import sqlite3
import json
import asyncio
from dotenv import load_dotenv

# Add workspace to path
sys.path.append("/home/rafi/shariahcompliantscreener")
load_dotenv(dotenv_path="/home/rafi/shariahcompliantscreener/.env")

from src.data.sec_extractor import get_latest_10k_text
from src.data.harvester import harvest_all_sources
from src.analysis.ai_analyst import analyze_multi_source_compliance

async def test_aapl_now():
    ticker = "AAPL"
    name = "Apple Inc."
    
    db_path = "data/halal_screener.db"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    
    # Fetch business summary and 36mo avg market cap
    stock = conn.execute("SELECT * FROM stocks WHERE ticker = 'AAPL'").fetchone()
    summary = ""
    mcap = 1.0
    if stock:
        mcap = stock['avg_market_cap_36mo'] or 1.0
        if stock['raw_info']:
            try:
                info = json.loads(stock['raw_info'])
                summary = info.get('longBusinessSummary', "")
            except Exception:
                pass
    conn.close()

    print("\n--- 1. Extracting SEC Text ---")
    sec_text, sec_url = get_latest_10k_text(ticker)
    
    print("\n--- 2. Running Harvester ---")
    harvested = await harvest_all_sources(ticker, year=2026, quarter=2, sec_text=sec_text)
    
    print("\n--- 3. Running Multi-Source AI Audit ---")
    res = analyze_multi_source_compliance(ticker, name, harvested, summary=summary)
    
    # Calculate screen ratios using 36mo avg market cap
    ib_debt = res.get("interest_bearing_debt_millions", 0.0) * 1e6
    ib_cash = res.get("interest_bearing_securities_millions", 0.0) * 1e6
    
    debt_ratio = ib_debt / mcap
    cash_ratio = ib_cash / mcap
    
    print("\n=== SYSTEM AUDIT RESULTS (CURRENT PIPELINE) ===")
    print(f"Total Revenue: ${res.get('total_revenue_millions'):,.2f} million")
    print(f"Haram Business Revenue Ratio: {res.get('haram_revenue'):.2%} (${res.get('haram_revenue_millions'):,.2f} million)")
    print(f"Doubtful Business Revenue Ratio: {res.get('doubtful_revenue'):.2%} (${res.get('doubtful_revenue_millions'):,.2f} million)")
    print(f"Interest Income Ratio: {res.get('interest_income'):.2%} (${res.get('interest_income_millions'):,.2f} million)")
    print(f"Debt / Market Cap Ratio: {debt_ratio:.2%} (${res.get('interest_bearing_debt_millions'):,.2f} million)")
    print(f"Cash / Market Cap Ratio: {cash_ratio:.2%} (${res.get('interest_bearing_securities_millions'):,.2f} million)")
    
    print("\n=== AI DETAILED REASONING & CITATIONS ===")
    print(res.get("reasoning", "No reasoning details found."))
    
    print("\n=== SIDE-BY-SIDE COMPARE TO MUSAFFA ===")
    print(f"{'Metric':<30} | {'Musaffa Target':<15} | {'Our Output':<15} | {'Status':<15}")
    print(f"{'-'*30}-+-{'-'*15}-+-{'-'*15}-+-{'-'*15}")
    
    # Compare interest-bearing debt
    print(f"{'Debt / Market Cap':<30} | {'2.62%':<15} | {debt_ratio:.2%} | {'🎯 100% Match' if abs(debt_ratio - 0.0262) < 0.005 else 'Differs':<15}")
    # Compare interest-bearing cash
    print(f"{'Cash / Market Cap':<30} | {'4.47%':<15} | {cash_ratio:.2%} | {'🎯 100% Match' if abs(cash_ratio - 0.0447) < 0.005 else 'Differs':<15}")
    # Compare interest income
    print(f"{'Interest Income':<30} | {'0.96%':<15} | {res.get('interest_income'):.2%} | {'🎯 100% Match' if abs(res.get('interest_income', 0.0) - 0.0096) < 0.002 else 'Differs':<15}")
    # Compare total business revenue
    total_business = res.get('haram_revenue', 0.0) - res.get('interest_income', 0.0) + res.get('doubtful_revenue', 0.0)
    print(f"{'Total Non-Halal Business Rev':<30} | {'3.12%':<15} | {total_business:.2%} | {'🎯 100% Match' if abs(total_business - 0.0312) < 0.005 else 'Differs':<15}")

if __name__ == "__main__":
    asyncio.run(test_aapl_now())
