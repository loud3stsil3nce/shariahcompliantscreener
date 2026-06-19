import sys
import os
import sqlite3
import json
import pandas as pd
from dotenv import load_dotenv

# Add workspace to path
sys.path.append("/home/rafi/shariahcompliantscreener")
load_dotenv(dotenv_path="/home/rafi/shariahcompliantscreener/.env")

from src.analysis.ai_analyst import get_historical_guidance
from src.db.setup import save_proposed_rules
from src.db.helpers import get_db

def run_feedback_loop_test():
    ticker = "MOCKCO"
    name = "Mock Conglomerate"
    
    print("--- 1. Testing get_historical_guidance without rules ---")
    rules, audit = get_historical_guidance(ticker)
    print(f"Rules returned:\n{rules}")
    print(f"Historical audit returned:\n{audit}")
    
    # Let's verify that global keyword rules are returned even if ticker rules don't exist
    assert "GLOBAL REVENUE KEYWORD PATTERNS" in rules, "Should load Tier 2 global patterns"
    assert "TICKER-SPECIFIC REVENUE SEGMENT RULES" not in rules, "Should not have ticker-specific rules yet"
    
    print("\n--- 2. Simulating AI response with proposed rules (Auto-Approve) ---")
    mock_ai_res = {
        "haram_revenue": 0.0,
        "doubtful_revenue": 0.0,
        "interest_bearing_debt": 0.0,
        "interest_bearing_securities": 0.0,
        "interest_income": 0.0,
        "total_revenue_millions": 100.0,
        "haram_revenue_millions": 0.0,
        "doubtful_revenue_millions": 0.0,
        "total_debt_millions": 0.0,
        "interest_bearing_debt_millions": 0.0,
        "short_term_debt_millions": 0.0,
        "long_term_debt_millions": 0.0,
        "total_cash_and_securities_millions": 0.0,
        "interest_bearing_securities_millions": 0.0,
        "short_term_securities_millions": 0.0,
        "long_term_securities_millions": 0.0,
        "interest_income_millions": 0.0,
        "filing_period_months": 12,
        "reasoning": "Standard mock company review.",
        "proposed_rules": [
            {
                "segment_name": "Mixed Services",
                "compliance_status": "doubtful",
                "notes": "Contains digital advertising elements which are doubtful"
            }
        ]
    }
    
    # Save the proposed rules (should automatically commit to shariah_segment_map)
    save_proposed_rules(ticker, mock_ai_res)
    print("Saved proposed rules to database.")
    
    # Query database to confirm auto-approval
    conn = get_db()
    
    # 1. Assert saved as approved log in proposed_segment_rules
    row_prop = conn.execute("SELECT * FROM proposed_segment_rules WHERE ticker = ? AND segment_name = ?", (ticker, "Mixed Services")).fetchone()
    assert row_prop is not None, "Proposed rule log should exist"
    assert row_prop['status'] == 'approved', "Rule status should be 'approved' immediately (auto-approve)"
    print(f"Verified proposed log exists with status: {row_prop['status']}")
    
    # 2. Assert saved directly to active rules map
    row_map = conn.execute("SELECT * FROM shariah_segment_map WHERE ticker = ? AND segment_name = ?", (ticker, "Mixed Services")).fetchone()
    assert row_map is not None, "Rule should be written directly to active shariah_segment_map"
    assert row_map['compliance_status'] == 'doubtful'
    print(f"Verified active override exists: Ticker={row_map['ticker']}, Segment={row_map['segment_name']}, Status={row_map['compliance_status']}")
    
    print("\n--- 3. Testing get_historical_guidance with auto-approved rule ---")
    rules, audit = get_historical_guidance(ticker)
    print(f"Rules returned:\n{rules}")
    
    assert "TICKER-SPECIFIC REVENUE SEGMENT RULES FOR MOCKCO" in rules, "Should now load Tier 3 ticker-specific rules"
    assert "Mixed Services" in rules, "Should contain Mixed Services segment name in the rules text"
    print("Verified: Auto-approved rule is correctly loaded and injected into prompt context!")
    
    # Cleanup database
    conn.execute("DELETE FROM proposed_segment_rules WHERE ticker = ?", (ticker,))
    conn.execute("DELETE FROM shariah_segment_map WHERE ticker = ?", (ticker,))
    conn.commit()
    conn.close()
    print("\nFeedback loop test COMPLETED SUCCESSFULY!")

if __name__ == "__main__":
    run_feedback_loop_test()
