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

async def test_spcx_web_search():
    ticker = "SPCX"
    name = "Space Exploration Technologies Corp."
    
    print("--- 1. Preparing database (temporarily disabling SPCX override) ---")
    db_path = "data/halal_screener.db"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    
    # Check if SPCX override exists
    override = conn.execute("SELECT * FROM shariah_segment_map WHERE ticker = 'SPCX'").fetchall()
    if override:
        print("Temporarily renaming SPCX overrides to 'SPCX_TEMP' to test dynamic web-guided search...")
        conn.execute("UPDATE shariah_segment_map SET ticker = 'SPCX_TEMP' WHERE ticker = 'SPCX'")
        conn.commit()
    
    # Fetch long business summary
    stock = conn.execute("SELECT * FROM stocks WHERE ticker = 'SPCX'").fetchone()
    summary = ""
    if stock and stock['raw_info']:
        try:
            info = json.loads(stock['raw_info'])
            summary = info.get('longBusinessSummary', "")
        except Exception:
            pass
            
    conn.close()

    try:
        print("\n--- 2. Extracting SEC Text ---")
        sec_text, sec_url = get_latest_10k_text(ticker)
        print(f"SEC filing URL: {sec_url}")
        
        print("\n--- 3. Running Harvester with Web Search Ingestion ---")
        harvested = await harvest_all_sources(ticker, year=2025, quarter=4, sec_text=sec_text)
        
        # Verify web search evidence was collected
        print(f"Has Web Search Evidence? {harvested.get('has_web_search', False)}")
        
        print("\n--- 4. Running Multi-Source AI Audit (Dynamic Mode) ---")
        res = analyze_multi_source_compliance(ticker, name, harvested, summary=summary)
        
        print("\n=== DYNAMIC AI AUDIT RESULTS ===")
        print(json.dumps(res, indent=2))
        
        print("\n=== DETAILS COMPARE TO EXPECTED/MUSAFFA ===")
        print("Expected dynamic behavior:")
        print("  - Detects space launch business segments (neutral hardware/IP -> Halal)")
        print("  - Identifies AI/X or digital advertising segment as Doubtful")
        print("\nOur Dynamic System Results:")
        print(f"  - Total Revenue: ${res.get('total_revenue_millions'):,.2f}M")
        print(f"  - Haram Business Revenue: ${res.get('haram_revenue_millions'):,.2f}M ({res.get('haram_revenue'):.2%})")
        print(f"  - Doubtful Revenue: ${res.get('doubtful_revenue_millions'):,.2f}M ({res.get('doubtful_revenue'):.2%})")
        print(f"  - Interest Income: ${res.get('interest_income_millions'):,.2f}M ({res.get('interest_income'):.2%})")
        
    finally:
        # Restore database overrides
        print("\n--- 5. Restoring database overrides ---")
        conn = sqlite3.connect(db_path)
        conn.execute("UPDATE shariah_segment_map SET ticker = 'SPCX' WHERE ticker = 'SPCX_TEMP'")
        conn.commit()
        conn.close()
        print("Database overrides restored successfully.")

if __name__ == "__main__":
    asyncio.run(test_spcx_web_search())
