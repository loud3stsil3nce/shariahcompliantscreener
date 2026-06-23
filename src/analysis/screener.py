import json
import numpy as np
import pandas as pd
import asyncio

# Legacy helper – re-exported for existing code/tests that import get_db directly.
from src.db.helpers import get_db  

# Async imports for new path
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text


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

def get_effective_override(row, field):
    db_val = row[field]
    if db_val is not None and not pd.isna(db_val):
        return db_val
    return np.nan

# ---------------------------------------------------------------------------
# Core async implementation – can be called directly by the FastAPI endpoint.
# ---------------------------------------------------------------------------
async def _run_screener_async(
    request_body: dict | None = None,
    db: AsyncSession | None = None,
    use_current_market_cap: bool = False,
) -> None:
    """Async version of the screener.

    * ``db`` – an ``AsyncSession`` returned by the FastAPI dependency. If ``None``
      we fall back to the legacy ``get_db`` wrapper which mimics a synchronous
      SQLite connection (kept for the existing test suite).
    * ``request_body`` – currently unused but kept for signature compatibility
      with the MCP tool wrapper.
    """
    if db is None:
        # -------------------------------------------------------------------
        # Legacy sync path – preserve original behaviour for unit tests.
        # -------------------------------------------------------------------
        conn = get_db()
        # Verify the ``stocks`` table exists using SQLite query (compatible with legacy tests).
        table_check = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='stocks'"
        ).fetchone()
        if not table_check:
            print("❌ Error: The 'stocks' table does not exist.")
            print(
                "👉 Run the database initialization or ingestion script first."
            )
            return
        # Load data using the historic ``pd.read_sql_query`` helper.
        query = """
            SELECT s.*, 
                   coalesce(m.haram_revenue_override, cb.haram_revenue_override) as haram_revenue_override,
                   coalesce(m.debt_ratio_override, cb.debt_ratio_override) as debt_ratio_override,
                   coalesce(m.cash_ratio_override, cb.cash_ratio_override) as cash_ratio_override,
                   m.receivables_ratio_override as receivables_ratio_override,
                   coalesce(m.tangibility_ratio_override, cb.tangibility_ratio_override) as tangibility_ratio_override,
                   coalesce(m.interest_income_override, cb.interest_income_override) as interest_income_override,
                   coalesce(m.doubtful_revenue_override, cb.doubtful_revenue_override) as doubtful_revenue_override
            FROM stocks s
            LEFT JOIN manual_overrides m ON s.ticker = m.ticker
            LEFT JOIN curated_benchmarks cb ON s.ticker = cb.ticker
        """
        df = pd.read_sql_query(query, conn)
        if df.empty:
            print("No data found. Run 'python main.py ingest' first.")
            return
        # All subsequent calculations are pure pandas and identical for async
        # and sync paths – they operate on ``df`` in‑place.
    else:
        # -------------------------------------------------------------------
        # Async path – used by the FastAPI endpoint.
        # -------------------------------------------------------------------
        # Verify the ``stocks`` table exists using SQLite-compatible query (works for both SQLite and Postgres).
        result = await db.execute(text(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='stocks'"
        ))
        table_name = result.scalar_one_or_none()
        if not table_name:
            print("❌ Error: The 'stocks' table does not exist.")
            print(
                "👉 Run the database initialization or ingestion script first."
            )
            return
        # Load data asynchronously.
        query = """
            SELECT s.*, 
                   coalesce(m.haram_revenue_override, cb.haram_revenue_override) as haram_revenue_override,
                   coalesce(m.debt_ratio_override, cb.debt_ratio_override) as debt_ratio_override,
                   coalesce(m.cash_ratio_override, cb.cash_ratio_override) as cash_ratio_override,
                   m.receivables_ratio_override as receivables_ratio_override,
                   coalesce(m.tangibility_ratio_override, cb.tangibility_ratio_override) as tangibility_ratio_override,
                   coalesce(m.interest_income_override, cb.interest_income_override) as interest_income_override,
                   coalesce(m.doubtful_revenue_override, cb.doubtful_revenue_override) as doubtful_revenue_override
            FROM stocks s
            LEFT JOIN manual_overrides m ON s.ticker = m.ticker
            LEFT JOIN curated_benchmarks cb ON s.ticker = cb.ticker
        """
        result = await db.execute(text(query))
        rows = result.fetchall()
        df = pd.DataFrame(rows, columns=result.keys())
        if df.empty:
            print("No data found. Run 'python main.py ingest' first.")
            return

    # -------------------------------------------------------------------
    # Shared calculation block – works for both sync and async branches.
    # -------------------------------------------------------------------
    def get_market_cap(row):
        val = 0.0
        if use_current_market_cap:
            try:
                info = json.loads(row["raw_info"])
                val = float(info.get("marketCap", 0))
            except Exception:
                pass
        if val <= 0:
            val = float(row.get("avg_market_cap_36mo", 0.0) or 0.0)
        if val <= 0:
            try:
                info = json.loads(row["raw_info"])
                total_liabilities = float(info.get("total_liabilities", 0.0))
            except Exception:
                total_liabilities = 0.0
            total_assets = float(row.get("total_assets", 0.0) or 0.0)
            book_value = total_assets - total_liabilities
            if book_value > 0:
                return book_value
            if total_assets > 0:
                return total_assets
        return val

    df["market_cap_denom"] = df.apply(get_market_cap, axis=1).replace(0, np.nan)
    mc_denom = df["market_cap_denom"]
    assets = df["total_assets"].replace(0, np.nan)
    revenue = df["total_revenue"].replace(0, np.nan)
    df["sector_lower"] = df["sector"].fillna("").str.lower()
    df["industry_lower"] = df["industry"].fillna("").str.lower()
    df["pass_sector"] = ~df["sector_lower"].str.contains("|".join(HARAM_SECTORS), na=False)
    df["pass_industry"] = ~df["industry_lower"].str.contains("|".join(HARAM_INDUSTRY_KEYWORDS), na=False)

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

    df["eff_tang_override"] = df.apply(lambda x: get_effective_override(x, "tangibility_ratio_override"), axis=1)
    liquid_assets = df["cash_equivalents"].fillna(0) + df["accounts_receivable"].fillna(0)
    calculated_tangibility = np.where(df["total_assets"] > 0, (df["total_assets"] - liquid_assets) / df["total_assets"], 0.0)
    df["tangibility_ratio"] = calculated_tangibility
    df["tangibility_ratio"] = df.apply(lambda x: apply_override(x["tangibility_ratio"], x["eff_tang_override"]), axis=1)
    df["tangibility_ratio"] = df["tangibility_ratio"].fillna(0.0)
    df["pass_tangibility"] = df["tangibility_ratio"] >= MIN_TANGIBILITY_RATIO

    df["eff_int_override"] = df.apply(lambda x: get_effective_override(x, "interest_income_override"), axis=1)
    df["interest_ratio"] = (df["interest_income"] / revenue).fillna(0)
    df["interest_ratio"] = df.apply(lambda x: apply_override(x["interest_ratio"], x["eff_int_override"]), axis=1)
    eff_haram_override = df.apply(lambda x: get_effective_override(x, "haram_revenue_override"), axis=1)
    qualitative_haram = eff_haram_override.fillna(0.0)
    df["total_haram_ratio"] = df["interest_ratio"] + qualitative_haram
    df["pass_interest"] = df["total_haram_ratio"] < MAX_HARAM_INCOME_RATIO
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
        df["pass_tangibility"] &
        df["pass_interest"] &
        df["pass_combined_interest"]
    )

    def calculate_grade(row):
        if not row["is_halal"]:
            is_doubtful_reason = (
                row["pass_sector"] &
                row["pass_industry"] &
                row["pass_debt"] &
                row["pass_cash"] &
                row["pass_tangibility"] &
                row["pass_interest"] &
                (not row["pass_combined_interest"])
            )
            if is_doubtful_reason:
                return "Doubtful", 0.0
            return "F", 0.0
        s_debt = row["debt_ratio"] / MAX_DEBT_RATIO
        s_cash = row["cash_ratio"] / MAX_CASH_RATIO
        s_liq = (1 - row["tangibility_ratio"]) / MAX_LIQUID_RATIO
        s_int = row["total_combined_ratio"] / MAX_HARAM_INCOME_RATIO
        avg_ratio = np.mean([s_debt, s_cash, s_liq, s_int])
        score = max(0, 100 * (1 - avg_ratio))
        if score >= 92:
            return "A+", score
        if score >= 85:
            return "A", score
        if score >= 78:
            return "B+", score
        if score >= 70:
            return "B", score
        if score >= 62:
            return "C+", score
        if score >= 55:
            return "C", score
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
                (f"Tangibility: {row['tangibility_ratio']:.1%} < 30%", row["pass_tangibility"]),
                (f"Total Haram Revenue: {row['total_haram_ratio']:.1%} > 5%", row["pass_interest"]),
                (f"Haram + Doubtful Revenue: {row['total_combined_ratio']:.1%} > 5%", row["pass_combined_interest"]),
            ] if not passed
        ),
        axis=1,
    )

    df["purification_per_share"] = (
        df["interest_income"].fillna(0) /
        df["shares_outstanding"].replace(0, np.nan)
    ).fillna(0)

    halal_universe = df[df["is_halal"]].copy()
    doubtful_universe = df[(~df["is_halal"]) & (df["grade"] == "Doubtful")].copy()
    rejected_stocks = df[(~df["is_halal"]) & (df["grade"] == "F")].copy()

    if db is None:
        # Legacy sync write using the helper connection.
        halal_universe.to_sql("halal_universe", conn, if_exists="replace", index=False)
        doubtful_universe.to_sql("doubtful_universe", conn, if_exists="replace", index=False)
        rejected_stocks.to_sql("halal_rejections", conn, if_exists="replace", index=False)
    else:
        # Async writes – use ``run_sync`` on the async session.
        await db.run_sync(lambda sync_conn: halal_universe.to_sql("halal_universe", con=sync_conn, if_exists="replace", index=False))
        await db.run_sync(lambda sync_conn: doubtful_universe.to_sql("doubtful_universe", con=sync_conn, if_exists="replace", index=False))
        await db.run_sync(lambda sync_conn: rejected_stocks.to_sql("halal_rejections", con=sync_conn, if_exists="replace", index=False))

    # Human‑readable summary (unchanged from original implementation).
    print(f"\n✅ Halal Universe ({len(halal_universe)} stocks passed):")
    if not halal_universe.empty:
        summary = halal_universe[["ticker", "name", "grade", "debt_ratio", "purification_per_share"]].copy()
        summary["debt_ratio"] = (summary["debt_ratio"] * 100).round(2).astype(str) + "%"
        summary["purification_per_share"] = "$" + summary["purification_per_share"].round(4).astype(str)
        print(summary.to_string(index=False))
    print(f"\n❔ Doubtful Universe ({len(doubtful_universe)} stocks):")
    if not doubtful_universe.empty:
        summary_doubtful = doubtful_universe[["ticker", "name", "grade", "debt_ratio", "purification_per_share"]].copy()
        summary_doubtful["debt_ratio"] = (summary_doubtful["debt_ratio"] * 100).round(2).astype(str) + "%"
        summary_doubtful["purification_per_share"] = "$" + summary_doubtful["purification_per_share"].round(4).astype(str)
        print(summary_doubtful.to_string(index=False))
    print(f"\n❌ Rejected Stocks ({len(rejected_stocks)} failed):")
    for _, row in rejected_stocks.iterrows():
        print(f"  - {row['ticker']}: {row['halal_failure']}")
    return

# ---------------------------------------------------------------------------
# Public wrapper retained for backward compatibility (synchronous call).
# ---------------------------------------------------------------------------
def run_screener(use_current_market_cap: bool = False) -> None:
    """Legacy sync entry point used by the original test suite.

    It forwards to the async implementation via the ``run_sync`` helper
    defined in ``src.db.helpers``.
    """
    from src.db.helpers import run_sync

    run_sync(_run_screener_async(use_current_market_cap=use_current_market_cap))

# ---------------------------------------------------------------------------
# CLI entry point – unchanged but now uses the async engine.
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import os
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
    from sqlalchemy.orm import sessionmaker

    DATABASE_URL = os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://postgres:postgres@localhost/aegis",
    )
    async_engine = create_async_engine(DATABASE_URL, echo=False)
    async_session = sessionmaker(
        async_engine, expire_on_commit=False, class_=AsyncSession
    )

    async def _run():
        async with async_session() as db:
            await _run_screener_async(db=db)

    asyncio.run(_run())
