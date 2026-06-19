import os
import json
import time
import pandas as pd
from src.db.helpers import get_db
from src.analysis.ai_analyst import analyze_company_compliance

def run_background_audit():
    conn = get_db()
    
    # Find stocks that haven't been audited yet
    query = """
        SELECT s.ticker, s.name, s.raw_info, s.total_debt, s.cash_equivalents, s.avg_market_cap_36mo, s.total_revenue, s.interest_income
        FROM stocks s
        LEFT JOIN manual_overrides m ON s.ticker = m.ticker
        WHERE m.ticker IS NULL
    """
    to_audit = pd.read_sql_query(query, conn)
    
    if to_audit.empty:
        print("✅ All stocks have been audited!")
        return

    print(f"🚀 Starting Background Audit for {len(to_audit)} stocks...")
    print("Press Ctrl+C to stop at any time. Data is saved stock-by-stock.")

    for idx, row in to_audit.iterrows():
        ticker = row['ticker']
        print(f"[{idx+1}/{len(to_audit)}] Auditing {ticker}...", end=" ", flush=True)
        
        success = False
        attempts = 0
        while not success and attempts < 3:
            try:
                raw_info = json.loads(row['raw_info'])
                summary = raw_info.get('longBusinessSummary', "")
                
                db_financials = {
                    'total_revenue': row.get('total_revenue', 0.0) or 0.0,
                    'total_debt': row.get('total_debt', 0.0) or 0.0,
                    'cash_equivalents': row.get('cash_equivalents', 0.0) or 0.0,
                    'interest_income': row.get('interest_income', 0.0) or 0.0
                }
                
                # Call AI
                res = analyze_company_compliance(ticker, row['name'], summary, db_financials=db_financials)
                
                if "error" in res:
                    if "429" in res["error"] or "quota" in res["error"].lower():
                        attempts += 1
                        wait_time = 60 * attempts
                        print(f"🛑 Rate limit! (Attempt {attempts}/3). Waiting {wait_time}s...")
                        time.sleep(wait_time)
                        continue # Try the SAME ticker again
                    else:
                        print(f"❌ Failed: {res['error']}")
                        break # Give up on this ticker

                # AAOIFI Scale Math matching frontend
                mc_36 = row['avg_market_cap_36mo'] or 1.0

                # Use absolute values from AI (which are in millions of USD, so multiply by 1e6 to convert to USD)
                final_debt_ratio = (res.get('interest_bearing_debt_millions', 0.0) * 1e6) / mc_36
                final_cash_ratio = (res.get('interest_bearing_securities_millions', 0.0) * 1e6) / mc_36

                # Save results
                conn.execute("""
                    INSERT OR REPLACE INTO manual_overrides 
                    (ticker, haram_revenue_override, debt_ratio_override, cash_ratio_override, interest_income_override, doubtful_revenue_override, reasoning, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    ticker, 
                    res['haram_revenue'], 
                    final_debt_ratio, 
                    final_cash_ratio, 
                    res.get('interest_income', 0.0),
                    res.get('doubtful_revenue', 0.0),
                    json.dumps(res),
                    pd.Timestamp.now().isoformat()
                ))
                conn.commit()
                print("✅ Saved.")
                success = True
                
                # Slow and steady (6 requests per minute)
                time.sleep(10)
                
            except KeyboardInterrupt:
                print("\n🛑 Stopped by user.")
                conn.close()
                return
            except Exception as e:
                print(f"❌ Error: {e}")
                break

    conn.close()
    print("🏁 Audit session complete.")

if __name__ == "__main__":
    run_background_audit()