import sys
import os
import sqlite3
import json
import asyncio
from dotenv import load_dotenv

# Add workspace to path
sys.path.append("/home/rafi/shariahcompliantscreener")
load_dotenv(dotenv_path="/home/rafi/shariahcompliantscreener/.env")

from src.sec_extractor import get_latest_10k_text
from src.harvester import harvest_all_sources
from src.ai_analyst import analyze_multi_source_compliance

async def test_spcx_now():
    ticker = "SPCX"
    name = "Space Exploration Technologies Corp."
    
    db_path = "data/halal_screener.db"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    
    # Fetch stock data
    stock = conn.execute("SELECT * FROM stocks WHERE ticker = 'SPCX'").fetchone()
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
    harvested = await harvest_all_sources(ticker, year=2025, quarter=4, sec_text=sec_text)
    
    print("\n--- 3. Running Multi-Source AI Audit ---")
    res = analyze_multi_source_compliance(ticker, name, harvested, summary=summary)
    
    # Calculate screen ratios using 36mo avg market cap
    ib_debt = res.get("interest_bearing_debt_millions", 0.0) * 1e6
    ib_cash = res.get("interest_bearing_securities_millions", 0.0) * 1e6
    
    debt_ratio = ib_debt / mcap
    cash_ratio = ib_cash / mcap
    
    print("\n=== SYSTEM AUDIT RESULTS (CURRENT PIPELINE) ===")
    print(f"Haram Business Revenue Ratio: {res.get('haram_revenue'):.2%}")
    print(f"Doubtful Business Revenue Ratio: {res.get('doubtful_revenue'):.2%}")
    print(f"Interest Income Ratio: {res.get('interest_income'):.2%}")
    print(f"Debt / Market Cap Ratio: {debt_ratio:.2%}")
    print(f"Cash / Market Cap Ratio: {cash_ratio:.2%}")
    
    print("\n=== COMPARING TO MUSAFFA BENCHMARKS ===")
    print(f"Musaffa Targets:")
    print(f"  - Doubtful Revenue (Starshield): 8.15%")
    print(f"  - Doubtful Revenue (Ads/X): 1.16%")
    print(f"  - Interest Income: 4.34%")
    print(f"  - Total Doubtful Revenue: 9.31%")
    print(f"\nOur Dynamic Outputs:")
    print(f"  - Haram Business Revenue: {res.get('haram_revenue'):.2%}")
    print(f"  - Doubtful Business Revenue: {res.get('doubtful_revenue'):.2%}")
    print(f"  - Interest Income Ratio: {res.get('interest_income'):.2%}")
    
    print(f"\nAI Proposed Rules:")
    print(json.dumps(res.get('proposed_rules'), indent=2))
    print(f"\nAI Reasoning:\n{res.get('reasoning')}")

if __name__ == "__main__":
    asyncio.run(test_spcx_now())
