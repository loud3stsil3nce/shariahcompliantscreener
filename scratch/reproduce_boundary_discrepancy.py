#!/usr/bin/env python3
"""
Scratch script to reproduce and validate the off-by-one boundary discrepancy 
reported by Reviewer 2 between the backend screener and the UI progress indicators.
"""
import sys
import pandas as pd
import numpy as np

# Define backend screening logic (from src/screener.py)
MAX_DEBT_RATIO = 0.30
MAX_CASH_RATIO = 0.30
MIN_TANGIBILITY_RATIO = 0.30
MAX_LIQUID_RATIO = 0.70
MAX_HARAM_INCOME_RATIO = 0.05

def run_backend_checks(debt_ratio, cash_ratio, tangibility_ratio, total_haram_ratio, total_combined_ratio):
    pass_debt = debt_ratio < MAX_DEBT_RATIO
    pass_cash = cash_ratio < MAX_CASH_RATIO
    pass_tangibility = tangibility_ratio >= MIN_TANGIBILITY_RATIO
    pass_interest = total_haram_ratio < MAX_HARAM_INCOME_RATIO
    pass_combined_interest = total_combined_ratio < MAX_HARAM_INCOME_RATIO
    
    return {
        "pass_debt": pass_debt,
        "pass_cash": pass_cash,
        "pass_tangibility": pass_tangibility,
        "pass_interest": pass_interest,
        "pass_combined_interest": pass_combined_interest
    }

# Define current UI progress indicator logic (from app.py)
def current_ui_render_status(val, limit, is_combined_check=False, haram_val=0.0):
    if val >= limit:
        if is_combined_check and haram_val < limit:
            return "Doubtful"
        else:
            return "Failed"
    elif (val / limit if limit > 0 else 0) > 0.8:
        return "Warning"
    else:
        return "Passed"

# Define proposed UI progress indicator logic with inclusive/exclusive handling
def proposed_ui_render_status(val, limit, is_combined_check=False, haram_val=0.0, inclusive=False):
    # inclusive=True means val <= limit is Allowed (passes), and val > limit fails.
    # inclusive=False (default) means val < limit is Allowed (passes), and val >= limit fails.
    is_failed = val > limit if inclusive else val >= limit
    if is_failed:
        if is_combined_check and haram_val < limit:
            return "Doubtful"
        else:
            return "Failed"
    elif (val / limit if limit > 0 else 0) > 0.8:
        return "Warning"
    else:
        return "Passed"

def main():
    print("=== BOUNDARY CONDITION TEST (VAL == LIMIT) ===")
    
    # Test cases: value is exactly equal to the limit
    test_cases = [
        {
            "metric": "Debt / Market Cap",
            "val": 0.30,
            "limit": 0.30,
            "backend_pass": run_backend_checks(debt_ratio=0.30, cash_ratio=0.0, tangibility_ratio=0.50, total_haram_ratio=0.0, total_combined_ratio=0.0)["pass_debt"],
            "is_combined": False,
            "inclusive": False
        },
        {
            "metric": "Cash / Market Cap",
            "val": 0.30,
            "limit": 0.30,
            "backend_pass": run_backend_checks(debt_ratio=0.0, cash_ratio=0.30, tangibility_ratio=0.50, total_haram_ratio=0.0, total_combined_ratio=0.0)["pass_cash"],
            "is_combined": False,
            "inclusive": False
        },
        {
            "metric": "Haram Revenue",
            "val": 0.05,
            "limit": 0.05,
            "backend_pass": run_backend_checks(debt_ratio=0.0, cash_ratio=0.0, tangibility_ratio=0.50, total_haram_ratio=0.05, total_combined_ratio=0.05)["pass_interest"],
            "is_combined": False,
            "inclusive": False
        },
        {
            "metric": "Haram + Doubtful Revenue",
            "val": 0.05,
            "limit": 0.05,
            "backend_pass": run_backend_checks(debt_ratio=0.0, cash_ratio=0.0, tangibility_ratio=0.50, total_haram_ratio=0.02, total_combined_ratio=0.05)["pass_combined_interest"],
            "is_combined": True,
            "inclusive": False
        },
        {
            "metric": "Liquid Assets / Total Assets (30% Tangibility)",
            "val": 0.70, # 100% - 30% Tangibility
            "limit": 0.70,
            # Tangibility is exactly 30%
            "backend_pass": run_backend_checks(debt_ratio=0.0, cash_ratio=0.0, tangibility_ratio=0.30, total_haram_ratio=0.0, total_combined_ratio=0.0)["pass_tangibility"],
            "is_combined": False,
            "inclusive": True
        }
    ]
    
    discrepancy_found = False
    
    for tc in test_cases:
        metric = tc["metric"]
        val = tc["val"]
        limit = tc["limit"]
        b_pass = tc["backend_pass"]
        
        # Determine status under current UI
        haram_val = 0.02 if tc["is_combined"] else 0.0
        curr_status = current_ui_render_status(val, limit, is_combined_check=tc["is_combined"], haram_val=haram_val)
        
        # Determine status under proposed UI
        prop_status = proposed_ui_render_status(val, limit, is_combined_check=tc["is_combined"], haram_val=haram_val, inclusive=tc["inclusive"])
        
        backend_str = "Passed" if b_pass else "Failed"
        if tc["is_combined"] and not b_pass:
            # Combined screen in backend could result in doubtful
            backend_str = "Failed" # In backend, pass_combined_interest is False
            
        print(f"\nMetric: {metric}")
        print(f"  Value: {val:.2%}, Limit: {limit:.2%}")
        print(f"  Backend Screening: {backend_str}")
        print(f"  Current UI Status: {curr_status}")
        print(f"  Proposed UI Status: {prop_status}")
        
        # Check for discrepancy
        ui_agrees_with_backend = (b_pass and curr_status == "Passed") or (not b_pass and curr_status in ["Failed", "Doubtful"])
        if not ui_agrees_with_backend:
            print(f"  ⚠️ DISCREPANCY DETECTED under current UI!")
            discrepancy_found = True
        else:
            print(f"  ✅ Current UI agrees with Backend.")
            
        # Check proposed UI consistency
        prop_ui_agrees_with_backend = (b_pass and prop_status == "Passed") or (not b_pass and prop_status in ["Failed", "Doubtful"])
        print(f"  Proposed UI Correctness: {'✅ Resolved' if prop_ui_agrees_with_backend else '❌ Still Discrepant'}")

    if discrepancy_found:
        print("\n[RESULT] Visual off-by-one boundary discrepancy confirmed!")
    else:
        print("\n[RESULT] No discrepancy detected.")

if __name__ == "__main__":
    main()
