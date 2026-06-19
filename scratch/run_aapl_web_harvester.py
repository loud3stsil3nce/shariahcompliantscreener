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

async def test_aapl_web_search():
    ticker = "AAPL"
    name = "Apple Inc."
    
    print("--- 1. Preparing database (temporarily disabling AAPL override) ---")
    db_path = "data/halal_screener.db"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    
    # Check if AAPL override exists
    override = conn.execute("SELECT * FROM shariah_segment_map WHERE ticker = 'AAPL'").fetchall()
    if override:
        print("Temporarily renaming AAPL overrides to 'AAPL_TEMP' to test dynamic web-guided search...")
        conn.execute("UPDATE shariah_segment_map SET ticker = 'AAPL_TEMP' WHERE ticker = 'AAPL'")
        conn.commit()
    
    # Fetch long business summary
    stock = conn.execute("SELECT * FROM stocks WHERE ticker = 'AAPL'").fetchone()
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
        harvested = await harvest_all_sources(ticker, year=2026, quarter=2, sec_text=sec_text)
        
        # Verify web search evidence was collected
        print(f"Has Web Search Evidence? {harvested.get('has_web_search', False)}")
        
        print("\n--- 4. Running Multi-Source AI Audit (Dynamic Mode) ---")
        res = analyze_multi_source_compliance(ticker, name, harvested, summary=summary)
        
        print("\n=== DYNAMIC AI AUDIT RESULTS ===")
        print(json.dumps(res, indent=2))
        
        print("\n=== DETAILS COMPARE TO MUSAFFA ===")
        print("Musaffa targets:")
        print("  - Haram Business Revenue (Apple Music, TV+, Card): 3.12%")
        print("  - Interest Income: 0.96%")
        print("  - Total Haram Revenue: 4.08%")
        print("  - Debt/Market Cap: 2.62%")
        print("  - Cash/Market Cap: 4.47%")
        print("\nOur Dynamic System Results:")
        print(f"  - Total Revenue: ${res.get('total_revenue_millions'):,.2f}M")
        print(f"  - Haram Business Revenue: ${res.get('haram_revenue_millions'):,.2f}M ({res.get('haram_revenue'):.2%})")
        print(f"  - Doubtful Revenue: ${res.get('doubtful_revenue_millions'):,.2f}M ({res.get('doubtful_revenue'):.2%})")
        print(f"  - Interest Income: ${res.get('interest_income_millions'):,.2f}M ({res.get('interest_income'):.2%})")
        print(f"  - Debt/Market Cap: {res.get('interest_bearing_debt'):.2%}")
        print(f"  - Cash/Market Cap: {res.get('interest_bearing_securities'):.2%}")
        
    finally:
        # Restore database overrides
        print("\n--- 5. Restoring database overrides ---")
        conn = sqlite3.connect(db_path)
        conn.execute("UPDATE shariah_segment_map SET ticker = 'AAPL' WHERE ticker = 'AAPL_TEMP'")
        conn.commit()
        conn.close()
        print("Database overrides restored successfully.")

if __name__ == "__main__":
    asyncio.run(test_aapl_web_search())
