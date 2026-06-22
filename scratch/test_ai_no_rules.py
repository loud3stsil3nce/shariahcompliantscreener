import asyncio
import json
import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.db.helpers import get_db
from src.data.sec_extractor import get_latest_10k_text
from src.data.harvester import harvest_all_sources
from src.analysis.ai_analyst import analyze_multi_source_compliance

async def main():
    ticker = "AAPL"
    name = "Apple Inc."
    
    conn = get_db()
    # Delete AAPL entries from shariah_segment_map to see purely dynamic behavior
    print("Deleting AAPL entries from shariah_segment_map...")
    conn.execute("DELETE FROM shariah_segment_map WHERE ticker = ?", (ticker,))
    conn.commit()
    conn.close()
    
    sec_text, sec_url = get_latest_10k_text(ticker)
    harvested = await harvest_all_sources(ticker, year=2026, quarter=2, sec_text=sec_text)
    
    print("\n--- Running AI Audit ---")
    ai_res = analyze_multi_source_compliance(ticker, name, harvested, summary="Apple Services segment disaggregation")
    print(json.dumps(ai_res, indent=2))

if __name__ == "__main__":
    asyncio.run(main())
