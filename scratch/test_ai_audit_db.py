import sys
import os
import json
import pandas as pd

# Add project root to python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.db.helpers import get_db
from src.db.setup import save_proposed_rules

ticker = "AAPL"
conn = get_db()
try:
    print(f"1. Reading stock {ticker}...")
    stock_df = pd.read_sql_query(f"SELECT * FROM stocks WHERE ticker = '{ticker}'", conn)
    if stock_df.empty:
        print("AAPL not found in stocks table. Please ingest first.")
        sys.exit(0)
    stock_data = stock_df.iloc[0]
    print("Found stock:", stock_data["name"])

    # Simulate AI response structure
    ai_res = {
        "filing_period_months": 12,
        "total_revenue_millions": 383285.0,
        "haram_revenue_millions": 0.0,
        "doubtful_revenue_millions": 11961.0,
        "interest_income_millions": 3750.0,
        "interest_bearing_debt_millions": 95000.0,
        "total_cash_and_securities_millions": 162000.0,
        "proposed_rules": [
            {
                "segment_name": "App Store & Services Commissions",
                "compliance_status": "halal",
                "notes": "Commissions on digital goods/services are generally halal as the underlying platforms represent utility."
            }
        ]
    }

    mc_denom_save = stock_data['avg_market_cap_36mo'] or 1.0
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
    
    final_debt_ratio = (ai_res.get('interest_bearing_debt_millions', 0.0) * 1e6) / mc_denom_save
    final_cash_ratio = (cash_and_securities_m * 1e6) / mc_denom_save

    print("2. Inserting into manual_overrides...")
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
    print("manual_overrides insert successful!")

    print("3. Saving proposed rules...")
    save_proposed_rules(ticker, ai_res)
    print("proposed segment rules saved successfully!")

except Exception as e:
    import traceback
    traceback.print_exc()
finally:
    conn.close()
