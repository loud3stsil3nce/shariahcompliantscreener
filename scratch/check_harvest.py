import asyncio
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.data.sec_extractor import get_latest_10k_text
from src.data.harvester import harvest_all_sources

async def main():
    ticker = "AAPL"
    sec_text, sec_url = get_latest_10k_text(ticker)
    harvested = await harvest_all_sources(ticker, year=2026, quarter=2, sec_text=sec_text)
    
    # Save to a scratch file to inspect
    with open("scratch/harvested_text.txt", "w", encoding="utf-8") as f:
        f.write(harvested.get("compiled_text", ""))
    print("Saved harvested text to scratch/harvested_text.txt")

if __name__ == "__main__":
    asyncio.run(main())
