import sys
import os
import sqlite3
import json
import asyncio
import time
from dotenv import load_dotenv

# Add workspace to path
sys.path.append("/home/rafi/shariahcompliantscreener")
load_dotenv(dotenv_path="/home/rafi/shariahcompliantscreener/.env")

from src.sec_extractor import get_latest_10k_text
from src.harvester import harvest_all_sources
from src.ai_analyst import analyze_multi_source_compliance

async def audit_stock(ticker, name):
    print(f"\n==================================================")
    print(f"🔍 AUDITING: {ticker} ({name})")
    print(f"==================================================")
    
    db_path = "data/halal_screener.db"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    
    # 1. Fetch Musaffa/Curated Benchmark
    benchmark = conn.execute("SELECT * FROM curated_benchmarks WHERE ticker = ?", (ticker,)).fetchone()
    
    # Fetch business summary
    stock = conn.execute("SELECT * FROM stocks WHERE ticker = ?", (ticker,)).fetchone()
    summary = ""
    if stock and stock['raw_info']:
        try:
            info = json.loads(stock['raw_info'])
            summary = info.get('longBusinessSummary', "")
        except Exception:
            pass
    conn.close()
    
    # 2. Extract SEC Text
    try:
        print("📥 Fetching SEC filing text...")
        sec_text, sec_url = get_latest_10k_text(ticker)
        
        # 3. Run Harvester
        print("🌐 Harvesting transcripts, slides, and web segment evidence...")
        harvested = await harvest_all_sources(ticker, year=2025, quarter=4, sec_text=sec_text)
        
        # 4. Run AI compliance audit
        print("🧠 Analyzing Shariah compliance...")
        res = analyze_multi_source_compliance(ticker, name, harvested, summary=summary)
        
        # Compare
        print("\n📊 SIDE-BY-SIDE COMPARISON:")
        
        bench_haram = f"{benchmark['haram_revenue_override']:.2%}" if benchmark and benchmark['haram_revenue_override'] is not None else "N/A"
        bench_doubt = f"{benchmark['doubtful_revenue_override']:.2%}" if benchmark and benchmark['doubtful_revenue_override'] is not None else "N/A"
        bench_interest = f"{benchmark['interest_income_override']:.2%}" if benchmark and benchmark['interest_income_override'] is not None else "N/A"
        
        # Calculate final ratios using 36mo avg market cap from DB
        mcap = stock['avg_market_cap_36mo'] if stock else 0.0
        if not mcap:
            mcap = 1.0 # Avoid div by zero
            
        ib_debt = res.get("interest_bearing_debt_millions", 0.0) * 1e6
        ib_cash = res.get("interest_bearing_securities_millions", 0.0) * 1e6
        
        debt_ratio = ib_debt / mcap
        cash_ratio = ib_cash / mcap
        
        bench_debt = f"{benchmark['debt_ratio_override']:.2%}" if benchmark and benchmark['debt_ratio_override'] is not None else "N/A"
        bench_cash = f"{benchmark['cash_ratio_override']:.2%}" if benchmark and benchmark['cash_ratio_override'] is not None else "N/A"
        
        print(f"{'Metric':<30} | {'Musaffa Benchmark':<20} | {'Dynamic System Output':<20}")
        print(f"{'-'*30}-+-{'-'*20}-+-{'-'*20}")
        print(f"{'Haram Business Rev %':<30} | {bench_haram:<20} | {res.get('haram_revenue'):.2%}")
        print(f"{'Doubtful Business Rev %':<30} | {bench_doubt:<20} | {res.get('doubtful_revenue'):.2%}")
        print(f"{'Interest Income %':<30} | {bench_interest:<20} | {res.get('interest_income'):.2%}")
        print(f"{'Debt / Market Cap':<30} | {bench_debt:<20} | {debt_ratio:.2%}")
        print(f"{'Cash / Market Cap':<30} | {bench_cash:<20} | {cash_ratio:.2%}")
        
    except Exception as e:
        print(f"❌ Audit failed for {ticker}: {e}")

async def main():
    stocks_to_test = [
        ("MSFT", "Microsoft Corporation"),
        ("GOOGL", "Alphabet Inc. (Class A)"),
        ("META", "Meta Platforms, Inc."),
        ("NVDA", "NVIDIA Corporation"),
        ("QCOM", "Qualcomm Incorporated")
    ]
    
    for ticker, name in stocks_to_test:
        await audit_stock(ticker, name)
        # Sleep to avoid rate limits
        print("Pacing next request...")
        await asyncio.sleep(10)

if __name__ == "__main__":
    asyncio.run(main())
