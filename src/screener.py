import json
import numpy as np
import pandas as pd

from .utils import get_db

MAX_DEBT_RATIO = 0.30
MAX_CASH_RATIO = 0.30
MAX_RECEIVABLES_RATIO = 0.45
MAX_HARAM_INCOME_RATIO = 0.05
MIN_TANGIBILITY_RATIO = 0.30
MAX_LIQUID_RATIO = 0.70

HARAM_SECTORS = ["financial"]
HARAM_INDUSTRY_KEYWORDS = [
    "casino",
    "gambling",
    "tobacco",
    "brewers",
    "wineries",
    "distilleries",
    "entertainment",
    "porn",
    "adult",
    "pork",
]
CURATED_BENCHMARKS = {
        "AAPL": {
            "doubtful_revenue_override": 0.0312,
            "interest_income_override": 0.0096,
            "cash_ratio_override": 0.0447,
            "debt_ratio_override": 0.0262,
        },
        "MSFT": {
            "haram_revenue_override": 0.0760,
            "interest_income_override": 0.0094,
            "cash_ratio_override": 0.0315,
            "debt_ratio_override": 0.0197,
        },
        "GOOG": {
            "doubtful_revenue_override": 0.7200,
            "interest_income_override": 0.0108,
        },
        "GOOGL": {
            "doubtful_revenue_override": 0.7200,
            "interest_income_override": 0.0108,
        },
        "META": {
            "doubtful_revenue_override": 0.9800,
            "interest_income_override": 0.0120,
        }
    }

def get_effective_override(row, field):
        db_val = row[field]
        if db_val is not None and not pd.isna(db_val):
            return db_val
        ticker = str(row["ticker"]).upper().strip()
        if ticker in CURATED_BENCHMARKS and field in CURATED_BENCHMARKS[ticker]:
            return CURATED_BENCHMARKS[ticker][field]
        return np.nan
    

def run_screener(use_current_market_cap=False):
    conn = get_db()
    
    # Check if table exists
    table_check = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='stocks'"
    ).fetchone()
    
    if not table_check:
        print("❌ Error: The 'stocks' table does not exist.")
        print("👉 Run 'Fetch Latest Data' in the UI or 'python main.py ingest' in the CLI first.")
        conn.close()
        return

    # Join with manual_overrides to get qualitative estimates and professional corrections
    query = """
        SELECT s.*, 
               m.haram_revenue_override,
               m.debt_ratio_override,
               m.cash_ratio_override,
               m.receivables_ratio_override,
               m.interest_income_override,
               m.doubtful_revenue_override
        FROM stocks s
        LEFT JOIN manual_overrides m ON s.ticker = m.ticker
    """
    df = pd.read_sql_query(query, conn)
    
    if df.empty:
        print("No data found. Run 'python main.py ingest' first.")
        conn.close()
        return

    def get_market_cap(row):
        if use_current_market_cap:
            try:
                info = json.loads(row["raw_info"])
                val = float(info.get("marketCap", 0))
                if val > 0:
                    return val
            except Exception:
                pass
        return row["avg_market_cap_36mo"]

    df["market_cap_denom"] = df.apply(get_market_cap, axis=1).replace(0, np.nan)
    mc_denom = df["market_cap_denom"]
    assets = df["total_assets"].replace(0, np.nan)
    revenue = df["total_revenue"].replace(0, np.nan)

    df["sector_lower"] = df["sector"].fillna("").str.lower()
    df["industry_lower"] = df["industry"].fillna("").str.lower()

    df["pass_sector"] = ~df["sector_lower"].str.contains("|".join(HARAM_SECTORS), na=False)
    df["pass_industry"] = ~df["industry_lower"].str.contains("|".join(HARAM_INDUSTRY_KEYWORDS), na=False)

    # Curated benchmarks from Musaffa/AAOIFI for major conglomerates
    

    

    # Calculate Ratios with Manual Override and Curated Preset Precedence
    def apply_override(calculated, override):
        return override if not pd.isna(override) else calculated

    df["eff_debt_override"] = df.apply(lambda x: get_effective_override(x, "debt_ratio_override"), axis=1)
    df["debt_ratio"] = (df["total_debt"] / mc_denom).fillna(0)
    df["debt_ratio"] = df.apply(lambda x: apply_override(x["debt_ratio"], x["eff_debt_override"]), axis=1)
    df["pass_debt"] = df["debt_ratio"] < MAX_DEBT_RATIO

    df["eff_cash_override"] = df.apply(lambda x: get_effective_override(x, "cash_ratio_override"), axis=1)
    df["cash_ratio"] = (df["cash_equivalents"] / mc_denom).fillna(0)
    df["cash_ratio"] = df.apply(lambda x: apply_override(x["cash_ratio"], x["eff_cash_override"]), axis=1)
    df["pass_cash"] = df["cash_ratio"] < MAX_CASH_RATIO

    df["eff_rec_override"] = df.apply(lambda x: get_effective_override(x, "receivables_ratio_override"), axis=1)
    df["receivables_ratio"] = (df["accounts_receivable"] / assets).fillna(0)
    df["receivables_ratio"] = df.apply(lambda x: apply_override(x["receivables_ratio"], x["eff_rec_override"]), axis=1)
    df["pass_receivables"] = df["receivables_ratio"] < MAX_RECEIVABLES_RATIO

    # Combine Interest Income with Manual/AI Revenue Overrides
    df["eff_int_override"] = df.apply(lambda x: get_effective_override(x, "interest_income_override"), axis=1)
    df["interest_ratio"] = (df["interest_income"] / revenue).fillna(0)
    df["interest_ratio"] = df.apply(lambda x: apply_override(x["interest_ratio"], x["eff_int_override"]), axis=1)
    
    # Total Haram Revenue (Interest + Qualitative Segments)
    eff_haram_override = df.apply(lambda x: get_effective_override(x, "haram_revenue_override"), axis=1)
    qualitative_haram = eff_haram_override.fillna(0.0)
    df["total_haram_ratio"] = df["interest_ratio"] + qualitative_haram
    df["pass_interest"] = df["total_haram_ratio"] < MAX_HARAM_INCOME_RATIO

    # Doubtful Revenue and combined checks
    eff_doubtful_override = df.apply(lambda x: get_effective_override(x, "doubtful_revenue_override"), axis=1)
    doubtful_revenue = eff_doubtful_override.fillna(0.0)
    df["doubtful_ratio"] = doubtful_revenue
    df["total_combined_ratio"] = df["total_haram_ratio"] + doubtful_revenue
    df["pass_combined_interest"] = df["total_combined_ratio"] < MAX_HARAM_INCOME_RATIO

    df["is_halal"] = (
        df["pass_sector"] &
        df["pass_industry"] &
        df["pass_debt"] &
        df["pass_cash"] &
        df["pass_receivables"] &
        df["pass_interest"] &
        df["pass_combined_interest"]
    )

    # PHASE 9: Weighted Grading System (Expanded)
    def calculate_grade(row):
        if not row["is_halal"]:
            # Check if failed solely due to doubtful revenue rule
            is_doubtful_reason = (
                row["pass_sector"] &
                row["pass_industry"] &
                row["pass_debt"] &
                row["pass_cash"] &
                row["pass_receivables"] &
                row["pass_interest"] &
                (not row["pass_combined_interest"])
            )
            if is_doubtful_reason:
                return "Doubtful", 0.0
            return "F", 0.0
        
        # Calculate scores for each metric (lower is better, 0.0 is perfect)
        s_debt = row["debt_ratio"] / MAX_DEBT_RATIO
        s_cash = row["cash_ratio"] / MAX_CASH_RATIO
        s_rec = row["receivables_ratio"] / MAX_RECEIVABLES_RATIO
        s_int = row["total_combined_ratio"] / MAX_HARAM_INCOME_RATIO
        
        # Total score (average of ratios, lower is better)
        avg_ratio = np.mean([s_debt, s_cash, s_rec, s_int])
        
        # Map to 0-100 (where 100 is best)
        score = max(0, 100 * (1 - avg_ratio))
        
        # More granular tiers to match professional tools
        if score >= 92: return "A+", score
        if score >= 85: return "A", score
        if score >= 78: return "B+", score
        if score >= 70: return "B", score
        if score >= 62: return "C+", score
        if score >= 55: return "C", score
        return "D", score

    df[["grade", "compliance_score"]] = df.apply(
        lambda row: pd.Series(calculate_grade(row)), axis=1
    )

    df["halal_failure"] = df.apply(
        lambda row: ", ".join(
            reason for reason, passed in [
                (f"Sector: {row['sector']}", row["pass_sector"]),
                (f"Industry: {row['industry']}", row["pass_industry"]),
                (f"Debt: {row['debt_ratio']:.1%} > 30%", row["pass_debt"]),
                (f"Cash: {row['cash_ratio']:.1%} > 30%", row["pass_cash"]),
                (f"Receivables: {row['receivables_ratio']:.1%} > 45%", row["pass_receivables"]),
                (f"Total Haram Revenue: {row['total_haram_ratio']:.1%} > 5%", row["pass_interest"]),
                (f"Haram + Doubtful Revenue: {row['total_combined_ratio']:.1%} > 5%", row["pass_combined_interest"]),
            ] if not passed
        ),
        axis=1,
    )

    # PHASE 4: Purification Calculation
    halal_universe = df[df["is_halal"]].copy()
    
    halal_universe["purification_per_share"] = (
        halal_universe["interest_income"].fillna(0) / 
        halal_universe["shares_outstanding"].replace(0, np.nan)
    ).fillna(0)

    rejected_stocks = df[~df["is_halal"]].copy()

    halal_universe.to_sql("halal_universe", conn, if_exists="replace", index=False)
    rejected_stocks.to_sql("halal_rejections", conn, if_exists="replace", index=False)

    print(f"\n✅ Halal Universe ({len(halal_universe)} stocks passed):")
    if not halal_universe.empty:
        summary = halal_universe[["ticker", "name", "grade", "debt_ratio", "purification_per_share"]].copy()
        summary["debt_ratio"] = (summary["debt_ratio"] * 100).round(2).astype(str) + "%"
        summary["purification_per_share"] = "$" + summary["purification_per_share"].round(4).astype(str)
        print(summary.to_string(index=False))

    print(f"\n❌ Rejected Stocks ({len(rejected_stocks)} failed):")
    for _, row in rejected_stocks.iterrows():
        print(f"  - {row['ticker']}: {row['halal_failure']}")

    conn.close()


if __name__ == "__main__":
    run_screener()
