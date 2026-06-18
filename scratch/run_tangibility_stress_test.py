import math
import sqlite3
import random
import os
import sys
import tempfile
import pandas as pd
import numpy as np

# Adjust sys.path to import from src
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import src.screener

def calculate_oracle_ratio(stock, override, curated):
    """
    Independent math oracle for tangibility ratio calculation and override precedence.
    """
    is_user = override.get("is_user_override") if override else 0
    mo_val = override.get("tangibility_ratio_override") if override else None
    cur_val = curated.get("tangibility_ratio_override") if curated else None
    
    eff_override = None
    
    # 1. User manual override (highest precedence, is_user_override == 1)
    if is_user == 1:
        if mo_val is not None and not pd.isna(mo_val):
            eff_override = mo_val
            
    # 2. Curated benchmarks (second precedence)
    if eff_override is None:
        if cur_val is not None and not pd.isna(cur_val):
            eff_override = cur_val
            
    # 3. AI automated overrides (third precedence, is_user_override != 1)
    if eff_override is None:
        if mo_val is not None and not pd.isna(mo_val):
            eff_override = mo_val
            
    if eff_override is not None:
        return float(eff_override)
        
    # Calculate base tangibility
    tot_assets = stock.get("total_assets")
    cash = stock.get("cash_equivalents")
    ar = stock.get("accounts_receivable")
    
    if tot_assets is None or pd.isna(tot_assets) or tot_assets == 0:
        return 0.0
        
    cash_val = cash if (cash is not None and not pd.isna(cash)) else 0.0
    ar_val = ar if (ar is not None and not pd.isna(ar)) else 0.0
    
    liquid = cash_val + ar_val
    ratio = (tot_assets - liquid) / tot_assets
    
    if pd.isna(ratio):
        return 0.0
    return float(ratio)

def setup_db(db_path, stocks_data, overrides_data, curated_data):
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE stocks (
            ticker TEXT PRIMARY KEY,
            name TEXT,
            sector TEXT,
            industry TEXT,
            total_assets REAL,
            total_debt REAL,
            cash_equivalents REAL,
            accounts_receivable REAL,
            total_revenue REAL,
            interest_income REAL,
            shares_outstanding REAL,
            avg_market_cap_36mo REAL,
            raw_info TEXT,
            fetched_at TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE manual_overrides (
            ticker TEXT PRIMARY KEY,
            haram_revenue_override REAL,
            debt_ratio_override REAL,
            cash_ratio_override REAL,
            receivables_ratio_override REAL,
            tangibility_ratio_override REAL,
            interest_income_override REAL,
            doubtful_revenue_override REAL,
            reasoning TEXT,
            is_user_override INTEGER DEFAULT 0,
            updated_at TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE curated_benchmarks (
            ticker TEXT PRIMARY KEY,
            haram_revenue_override REAL,
            doubtful_revenue_override REAL,
            interest_income_override REAL,
            cash_ratio_override REAL,
            debt_ratio_override REAL,
            tangibility_ratio_override REAL,
            updated_at TEXT
        )
        """
    )
    
    conn.executemany(
        """
        INSERT INTO stocks (
            ticker, name, sector, industry,
            total_assets, total_debt, cash_equivalents,
            accounts_receivable, total_revenue, interest_income,
            shares_outstanding, avg_market_cap_36mo, raw_info, fetched_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        stocks_data
    )
    if overrides_data:
        conn.executemany(
            """
            INSERT INTO manual_overrides (
                ticker, haram_revenue_override, debt_ratio_override,
                cash_ratio_override, receivables_ratio_override, tangibility_ratio_override,
                interest_income_override, doubtful_revenue_override, reasoning,
                is_user_override, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            overrides_data
        )
    if curated_data:
        conn.executemany(
            """
            INSERT INTO curated_benchmarks (
                ticker, haram_revenue_override, doubtful_revenue_override,
                interest_income_override, cash_ratio_override, debt_ratio_override,
                tangibility_ratio_override, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            curated_data
        )
    conn.commit()
    conn.close()

def run_stress_test():
    print("=" * 60)
    print("TANGIBILITY STRESS TEST HARNESS")
    print("=" * 60)
    
    # 1. Generate diverse structured edge cases + randomized cases
    random.seed(42)
    np.random.seed(42)
    
    stocks_dict = {}
    overrides_dict = {}
    curated_dict = {}
    
    # Structured scenarios
    structured_scenarios = [
        # Normal Case
        ("ST_NORM", 1000.0, 100.0, 150.0, None, None, None),
        # Zero Assets
        ("ST_ZERO_AST", 0.0, 100.0, 150.0, None, None, None),
        # Negative Assets
        ("ST_NEG_AST", -1000.0, 100.0, 150.0, None, None, None),
        # Massive Cash
        ("ST_MASS_CSH", 1000.0, 1000000.0, 0.0, None, None, None),
        # Null components
        ("ST_NULL_AST", None, 100.0, 150.0, None, None, None),
        ("ST_NULL_CSH", 1000.0, None, 150.0, None, None, None),
        ("ST_NULL_REC", 1000.0, 100.0, None, None, None, None),
        ("ST_NULL_ALL", None, None, None, None, None, None),
        # Extremes
        ("ST_EXTR_TINY", 1e-15, 1e-16, 1e-16, None, None, None),
        ("ST_EXTR_HUGE", 1e15, 1e14, 1e14, None, None, None),
        # Negative cash & receivables
        ("ST_NEG_CSH", 1000.0, -100.0, 150.0, None, None, None),
        ("ST_NEG_REC", 1000.0, 100.0, -150.0, None, None, None),
        # Liquid assets exceed total assets
        ("ST_LIQ_EXC", 100.0, 80.0, 50.0, None, None, None),
        
        # Override Precedence Cases
        # Case A: User override only (is_user=1)
        ("OP_USER_ONLY", 1000.0, 100.0, 150.0, 0.55, 1, None),
        # Case B: Curated override only
        ("OP_CUR_ONLY", 1000.0, 100.0, 150.0, None, 0, 0.65),
        # Case C: Both present, is_user=1 -> should choose user override
        ("OP_BOTH_USER_1", 1000.0, 100.0, 150.0, 0.55, 1, 0.65),
        # Case D: Both present, is_user=0 -> should choose curated override
        ("OP_BOTH_USER_0", 1000.0, 100.0, 150.0, 0.55, 0, 0.65),
        # Case E: Both present, is_user=None -> should choose curated override
        ("OP_BOTH_USER_N", 1000.0, 100.0, 150.0, 0.55, None, 0.65),
        # Case F: AI override only (is_user=0)
        ("OP_AI_ONLY", 1000.0, 100.0, 150.0, 0.45, 0, None),
    ]
    
    for ticker, assets, cash, ar, override_val, is_user, cur_val in structured_scenarios:
        stocks_dict[ticker] = {
            "total_assets": assets,
            "cash_equivalents": cash,
            "accounts_receivable": ar
        }
        if override_val is not None or is_user is not None:
            overrides_dict[ticker] = {
                "tangibility_ratio_override": override_val,
                "is_user_override": is_user if is_user is not None else 0
            }
        if cur_val is not None:
            curated_dict[ticker] = {
                "tangibility_ratio_override": cur_val
            }

    # Generate additional randomized cases to reach 100+ cases
    for i in range(1, 120):
        ticker = f"RAND_{i:03d}"
        
        # Decide stock parameters randomly
        assets_choice = random.choice([None, 0.0, -100.0, 100.0, 5000.0, 1e-10, 1e12, random.uniform(-1000, 5000)])
        cash_choice = random.choice([None, 0.0, -50.0, 200.0, 10000.0, random.uniform(-200, 2000)])
        ar_choice = random.choice([None, 0.0, -50.0, 200.0, 10000.0, random.uniform(-200, 2000)])
        
        stocks_dict[ticker] = {
            "total_assets": assets_choice,
            "cash_equivalents": cash_choice,
            "accounts_receivable": ar_choice
        }
        
        # Randomly apply overrides
        has_override = random.choice([True, False])
        if has_override:
            overrides_dict[ticker] = {
                "tangibility_ratio_override": random.choice([None, 0.0, 0.25, 0.35, 0.85, random.uniform(-0.5, 1.5)]),
                "is_user_override": random.choice([0, 1, None])
            }
            
        has_curated = random.choice([True, False])
        if has_curated:
            curated_dict[ticker] = {
                "tangibility_ratio_override": random.choice([None, 0.0, 0.40, 0.90, random.uniform(-0.5, 1.5)])
            }

    # Format the data lists for setup_db
    stocks_data = []
    overrides_data = []
    curated_data = []
    
    for ticker, info in stocks_dict.items():
        stocks_data.append((
            ticker, f"Stock {ticker}", "Technology", "Software",
            info["total_assets"], 0.0, info["cash_equivalents"],
            info["accounts_receivable"], 100.0, 0.0,
            100.0, 10000.0, "{}", "2026-06-16"
        ))
        
        # Get corresponding override/curated or defaults
        ov = overrides_dict.get(ticker, {})
        overrides_data.append((
            ticker, None, None, None, None,
            ov.get("tangibility_ratio_override"), None, None, "Override",
            ov.get("is_user_override", 0) if ov.get("is_user_override") is not None else 0,
            "2026-06-16"
        ))
        
        cur = curated_dict.get(ticker, {})
        curated_data.append((
            ticker, None, None, None, None, None,
            cur.get("tangibility_ratio_override"), "2026-06-16"
        ))

    print(f"Generated {len(stocks_dict)} test cases total.")
    
    # 2. Setup temporary database file
    temp_dir = tempfile.mkdtemp()
    db_path = os.path.join(temp_dir, "stress_test.db")
    
    try:
        setup_db(db_path, stocks_data, overrides_data, curated_data)
        print(f"Temporary database set up at: {db_path}")
        
        # 3. Inject mock get_db into src.screener
        def fake_get_db():
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            return conn
            
        src.screener.get_db = fake_get_db
        
        # 4. Run the screener engine
        print("Running screener engine...")
        screener_failed = False
        try:
            # We redirect stdout temporarily to prevent cluttering unless there is an issue
            import io
            old_stdout = sys.stdout
            sys.stdout = io.StringIO()
            
            src.screener.run_screener()
            
            output = sys.stdout.getvalue()
            sys.stdout = old_stdout
        except Exception as e:
            sys.stdout = old_stdout
            print(f"❌ SCREENER ENGINE CRASHED! Error: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)
            
        print("Screener engine executed successfully (no crashes).")
        
        # 5. Retrieve output from db and verify with math oracle
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        
        halal_universe = {row["ticker"]: dict(row) for row in conn.execute("SELECT * FROM halal_universe").fetchall()}
        halal_rejections = {row["ticker"]: dict(row) for row in conn.execute("SELECT * FROM halal_rejections").fetchall()}
        conn.close()
        
        # Verify correctness
        mismatches = []
        for ticker in stocks_dict.keys():
            # Get actual result row
            actual_row = halal_universe.get(ticker) or halal_rejections.get(ticker)
            if not actual_row:
                mismatches.append((ticker, "No output row found in halal_universe or halal_rejections"))
                continue
                
            actual_ratio = actual_row.get("tangibility_ratio")
            actual_pass = bool(actual_row.get("pass_tangibility"))
            
            # Get expected result
            stock = stocks_dict[ticker]
            override = overrides_dict.get(ticker, {})
            curated = curated_dict.get(ticker, {})
            
            expected_ratio = calculate_oracle_ratio(stock, override, curated)
            expected_pass = expected_ratio >= src.screener.MIN_TANGIBILITY_RATIO
            
            # Compare floats safely
            ratio_match = False
            if math.isnan(actual_ratio) and math.isnan(expected_ratio):
                ratio_match = True
            elif math.isinf(actual_ratio) and math.isinf(expected_ratio):
                ratio_match = (actual_ratio > 0) == (expected_ratio > 0)
            else:
                ratio_match = math.isclose(actual_ratio, expected_ratio, abs_tol=1e-9)
                
            pass_match = (actual_pass == expected_pass)
            
            if not ratio_match or not pass_match:
                mismatches.append((ticker, {
                    "stock": stock,
                    "override": override,
                    "curated": curated,
                    "expected_ratio": expected_ratio,
                    "actual_ratio": actual_ratio,
                    "expected_pass": expected_pass,
                    "actual_pass": actual_pass
                }))
                
        # 6. Report results
        print("\n" + "=" * 40)
        print("VERIFICATION RESULTS")
        print("=" * 40)
        
        if mismatches:
            print(f"❌ Verification FAILED with {len(mismatches)} mismatches out of {len(stocks_dict)} cases:")
            for ticker, error_detail in mismatches[:20]:  # print first 20 mismatches
                if isinstance(error_detail, str):
                    print(f"  Ticker {ticker}: {error_detail}")
                else:
                    print(f"  Ticker {ticker}:")
                    print(f"    Stock: {error_detail['stock']}")
                    print(f"    Override: {error_detail['override']}")
                    print(f"    Curated: {error_detail['curated']}")
                    print(f"    Expected: Ratio={error_detail['expected_ratio']}, Pass={error_detail['expected_pass']}")
                    print(f"    Actual  : Ratio={error_detail['actual_ratio']}, Pass={error_detail['actual_pass']}")
            if len(mismatches) > 20:
                print(f"  ... and {len(mismatches) - 20} more mismatches.")
            sys.exit(1)
        else:
            print(f"✅ SUCCESS: All {len(stocks_dict)} cases matched the oracle perfectly!")
            print("1. Screening engine did not crash.")
            print("2. Computed tangibility matched independent math oracle.")
            print("3. Manual and curated overrides behaved exactly as expected.")
            
    finally:
        # Cleanup temporary files
        if os.path.exists(db_path):
            os.remove(db_path)
        if os.path.exists(temp_dir):
            os.rmdir(temp_dir)

if __name__ == "__main__":
    run_stress_test()
